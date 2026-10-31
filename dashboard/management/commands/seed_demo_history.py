import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from dashboard.models import PriceSnapshot, Share

DEMO_SHARES = [
    # figi, ticker, name, currency, начальная цена
    ("DEMO00000001", "DEMOA", "Демо: Альфа Индастриз", "rub", 250.0),
    ("DEMO00000002", "DEMOB", "Демо: Бета Энерджи", "rub", 1200.0),
    ("DEMO00000003", "DEMOC", "Демо: Гамма Тек", "usd", 35.5),
]


class Command(BaseCommand):
    help = (
        "Создаёт демо-акции DEMOA, DEMOB, DEMOC с вымышленной историей цен "
        "(случайное блуждание) для проверки интерфейса без токена T-Invest. "
        "Реальные акции не затрагиваются."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)
        parser.add_argument("--points-per-day", type=int, default=8)
        parser.add_argument("--seed", type=int, default=42, help="Для воспроизводимости")

    def handle(self, *args, **options):
        if options["days"] < 1 or options["points_per_day"] < 1:
            raise CommandError("--days и --points-per-day должны быть положительными")
        count = options["days"] * options["points_per_day"]
        if count < 2:
            raise CommandError("Нужно хотя бы две точки истории")
        rng = random.Random(options["seed"])
        now = timezone.now()
        step = timedelta(days=1) / options["points_per_day"]

        total = 0
        for figi, ticker, name, currency, price in DEMO_SHARES:
            share, _ = Share.objects.get_or_create(
                figi=figi,
                defaults={
                    "isin": figi,
                    "name": name,
                    "ticker": ticker,
                    "currency": currency,
                    "uid": f"demo-{ticker.lower()}",
                },
            )
            if share.price_history.exists():
                self.stdout.write(f"{ticker}: история уже есть, пропущено")
                continue

            snapshots = []
            for i in range(count):
                price = max(0.01, price * (1 + rng.gauss(0.0005, 0.015)))
                snapshots.append(
                    PriceSnapshot(
                        share=share,
                        price=round(price, 2),
                        time=now - step * (count - 1 - i),
                    )
                )
            PriceSnapshot.objects.bulk_create(snapshots, batch_size=1000)
            previous, last = snapshots[-2].price, snapshots[-1].price
            share.last_price = last
            share.is_trend_high = last >= previous
            share.save(update_fields=["last_price", "is_trend_high", "updated_at"])
            total += len(snapshots)
            self.stdout.write(f"{ticker}: {len(snapshots)} точек")

        self.stdout.write(self.style.SUCCESS(f"Создано демо-точек истории: {total}"))
