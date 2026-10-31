from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from dashboard.models import PriceSnapshot, Share
from dashboard.services.errors import MarketDataError
from dashboard.services.market_data import get_candles


class Command(BaseCommand):
    help = (
        "Загружает историю цен (дневные свечи MOEX ISS или T-Invest) в БД. По умолчанию — "
        "для акций из портфелей и списков наблюдения."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=365, help="Глубина истории, дней (до 365)")
        parser.add_argument("--ticker", action="append", help="Тикер; можно указать несколько раз")
        parser.add_argument("--all", action="store_true", help="Все акции справочника")

    def handle(self, *args, **options):
        days = options["days"]
        if not 1 <= days <= 365:
            raise CommandError("--days должен быть от 1 до 365 (ограничение API для дневных свечей)")

        shares = Share.objects.exclude(figi__startswith="DEMO")
        if options["ticker"]:
            shares = shares.filter(ticker__in=options["ticker"])
        elif not options["all"]:
            shares = shares.filter(
                Q(positions__isnull=False) | Q(watchlist_items__isnull=False)
            ).distinct()

        to = timezone.now()
        loaded = 0
        for share in shares:
            try:
                candles = get_candles(share, to - timedelta(days=days), to)
            except MarketDataError as e:
                raise CommandError(f"Не удалось загрузить свечи {share.ticker}: {e}") from e
            PriceSnapshot.objects.bulk_create(
                [
                    PriceSnapshot(share=share, price=close, time=time)
                    for time, close in candles
                    if close is not None
                ],
                ignore_conflicts=True,
            )
            loaded += len(candles)
            self.stdout.write(f"{share.ticker}: {len(candles)} свечей")

        self.stdout.write(self.style.SUCCESS(f"Загружено точек истории: {loaded}"))
