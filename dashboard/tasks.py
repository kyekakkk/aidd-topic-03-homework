from django.utils import timezone

from config.celery import app
from config.settings import TINKOFF_TOKEN, logger
from dashboard.models import Share
from dashboard.services.market_data import get_last_data

try:
    from tinkoff.invest import Client
except ImportError:  # SDK необязателен: без него задача просто пропускается
    Client = None


@app.task
def update_last_price():
    if Client is None:
        logger.error(
            "Tinkoff Invest SDK не установлен — обновление цен пропущено"
        )
        return

    with Client(TINKOFF_TOKEN) as client:
        for share in Share.objects.all():
            try:
                last_price, _ = get_last_data(client, share)
                is_trend_high = (
                    share.last_price is None or last_price >= share.last_price
                )
                Share.objects.filter(id=share.id).update(
                    last_price=last_price,
                    is_trend_high=is_trend_high,
                    updated_at=timezone.now(),
                )
            except Exception as e:
                logger.error(e)
