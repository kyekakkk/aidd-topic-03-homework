import logging

from django.utils import timezone

from config.celery import app
from dashboard.models import Share
from dashboard.services.history import check_alerts, record_snapshots
from dashboard.services.market_data import get_last_data

logger = logging.getLogger("main")


def get_trend(old_price, new_price, old_trend):
    """True — цена выросла, False — упала; без изменения тренд сохраняется.

    Если предыдущей цены нет, тренд неизвестен (None).
    """
    if old_price is None:
        return None
    if new_price > old_price:
        return True
    if new_price < old_price:
        return False
    return old_trend


@app.task
def update_last_price():
    shares = list(Share.objects.only("id", "figi", "last_price", "is_trend_high"))
    if not shares:
        return 0

    # Ошибки источников логируются внутри; акции без цены просто пропускаются
    prices = get_last_data(shares)

    now = timezone.now()
    updated = []
    for share in shares:
        if share.figi not in prices:
            continue
        last_price, _ = prices[share.figi]
        share.is_trend_high = get_trend(
            share.last_price, last_price, share.is_trend_high
        )
        share.last_price = last_price
        # bulk_update не вызывает save(), поэтому auto_now выставляем вручную
        share.updated_at = now
        updated.append(share)

    Share.objects.bulk_update(
        updated, ["last_price", "is_trend_high", "updated_at"], batch_size=500
    )
    record_snapshots(updated, prices, now)
    check_alerts({share.id: share.last_price for share in updated}, now)
    logger.info(f"Updated last price for {len(updated)} shares")
    return len(updated)
