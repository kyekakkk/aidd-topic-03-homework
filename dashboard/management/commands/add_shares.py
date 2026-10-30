from django.core.management.base import BaseCommand, CommandError

from config.settings import TINKOFF_TOKEN
from dashboard.models import Share

try:
    from tinkoff.invest import Client
except ImportError:  # SDK необязателен: команда подскажет, как его установить
    Client = None


class Command(BaseCommand):
    help = "Add shares to DB"

    def handle(self, *args, **options):
        if Client is None:
            raise CommandError(
                "Tinkoff Invest SDK не установлен. Установите пакет "
                "'tinkoff-investments' для загрузки справочника акций."
            )

        with Client(TINKOFF_TOKEN) as client:
            shares = client.instruments.shares()
            for share in shares.instruments:
                Share.objects.get_or_create(
                    figi=share.figi,
                    name=share.name,
                    isin=share.isin,
                    ticker=share.ticker,
                    currency=share.currency,
                    uid=share.uid,
                )
