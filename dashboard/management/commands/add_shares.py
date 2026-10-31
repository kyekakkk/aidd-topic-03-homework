from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from dashboard.models import Share
from dashboard.services import moex, tinvest
from dashboard.services.errors import MarketDataError


class Command(BaseCommand):
    help = (
        "Загружает справочник акций: из T-Invest (нужен TINKOFF_TOKEN) или из "
        "открытых данных Московской биржи (MOEX ISS, без токена)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["auto", "tinvest", "moex"],
            default="auto",
            help="auto — T-Invest, если задан токен, иначе MOEX",
        )

    def handle(self, *args, **options):
        source = options["source"]
        if source == "auto":
            source = "tinvest" if settings.TINKOFF_TOKEN else "moex"
        self.stdout.write(f"Источник: {'T-Invest' if source == 'tinvest' else 'MOEX ISS'}")

        try:
            if source == "tinvest":
                instruments = [self.from_tinvest(item) for item in tinvest.get_shares()]
            else:
                instruments = [self.from_moex(item) for item in moex.get_shares()]
        except MarketDataError as e:
            raise CommandError(f"Не удалось получить список акций: {e}") from e

        ticker_max_length = Share._meta.get_field("ticker").max_length
        created = updated = skipped = 0
        for instrument in instruments:
            if instrument is None or len(instrument["ticker"]) > ticker_max_length:
                skipped += 1
                continue
            try:
                with transaction.atomic():
                    is_created = self.save(instrument, source)
            except DatabaseError as e:
                self.stderr.write(f"Пропущена акция {instrument['ticker']}: {e}")
                skipped += 1
                continue
            if is_created is None:
                skipped += 1
            elif is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Добавлено: {created}, обновлено: {updated}, пропущено: {skipped}"
            )
        )

    @staticmethod
    def from_tinvest(item):
        try:
            return {
                "figi": item["figi"],
                "uid": item["uid"],
                "ticker": item["ticker"],
                "name": item.get("name", ""),
                "isin": item.get("isin", ""),
                "currency": item.get("currency", ""),
                "price": None,
            }
        except KeyError:
            return None

    @staticmethod
    def from_moex(item):
        return {
            "figi": moex.figi_for(item["secid"]),
            "uid": f"moex-{item['secid'].lower()}",
            "ticker": item["secid"],
            "name": item["name"],
            "isin": item["isin"],
            "currency": item["currency"],
            "price": item["price"],
        }

    @staticmethod
    def save(instrument, source):
        """True — создана, False — обновлена, None — пропущена."""
        share = Share.objects.filter(figi=instrument["figi"]).first()
        if share is None:
            same_ticker = Share.objects.filter(ticker=instrument["ticker"]).first()
            if same_ticker is not None:
                if source == "moex" or same_ticker.source != Share.SOURCE_MOEX:
                    # Бумага уже есть из другого источника — не дублируем
                    return None
                # Акция с биржи получает настоящий FIGI; история и позиции сохраняются
                share = same_ticker

        is_created = share is None
        share = share or Share()
        for field in ("figi", "uid", "ticker", "name", "isin", "currency"):
            setattr(share, field, instrument[field])
        if instrument["price"] is not None and share.last_price is None:
            share.last_price = float(instrument["price"])
        share.save()
        return is_created
