"""История цен: накопление снимков, целевые уровни и расчёт динамики."""
import logging
from collections import OrderedDict
from datetime import timedelta

from django.db.models import Max, Min, OuterRef, Subquery
from django.utils import timezone

from dashboard.models import PriceAlert, PriceSnapshot, Share

logger = logging.getLogger("main")

# Код периода -> (название, длительность; None — вся история)
PERIODS = OrderedDict(
    [
        ("1d", ("День", timedelta(days=1))),
        ("7d", ("Неделя", timedelta(days=7))),
        ("30d", ("Месяц", timedelta(days=30))),
        ("90d", ("Квартал", timedelta(days=90))),
        ("365d", ("Год", timedelta(days=365))),
        ("all", ("Всё время", None)),
    ]
)
DEFAULT_PERIOD = "30d"

# Сколько точек максимум отдавать на график
MAX_CHART_POINTS = 500


def parse_period(value):
    return value if value in PERIODS else DEFAULT_PERIOD


def period_start(period, now=None):
    duration = PERIODS[period][1]
    if duration is None:
        return None
    return (now or timezone.now()) - duration


def record_snapshots(shares, prices, now):
    """Сохраняет снимки цен; prices — {figi: (цена, время котировки)}.

    Повтор той же котировки (то же время) пропускается уникальным ограничением.
    """
    snapshots = [
        PriceSnapshot(share=share, price=prices[share.figi][0], time=prices[share.figi][1] or now)
        for share in shares
        if share.figi in prices
    ]
    PriceSnapshot.objects.bulk_create(snapshots, ignore_conflicts=True, batch_size=500)
    return len(snapshots)


def check_alerts(share_prices, now):
    """Фиксирует достижение целевых уровней; share_prices — {share_id: цена}."""
    alerts = list(
        PriceAlert.objects.filter(
            triggered_at__isnull=True, item__share_id__in=share_prices.keys()
        ).select_related("item")
    )
    triggered = [
        alert
        for alert in alerts
        if alert.check_price(share_prices[alert.item.share_id], now)
    ]
    PriceAlert.objects.bulk_update(triggered, ["triggered_at", "triggered_price"])
    if triggered:
        logger.info(f"Triggered {len(triggered)} price alerts")
    return triggered


def change(first, last):
    """Абсолютное и процентное изменение цены."""
    if first is None or last is None:
        return None, None
    absolute = last - first
    percent = absolute / first * 100 if first else None
    return absolute, percent


def share_stats(share, since):
    """Сводка по акции за период или None, если история пуста."""
    history = share.price_history.all()
    if since is not None:
        history = history.filter(time__gte=since)
    first = history.order_by("time").first()
    if first is None:
        return None
    last = history.order_by("-time").first()
    bounds = history.aggregate(min=Min("price"), max=Max("price"))
    absolute, percent = change(first.price, last.price)
    return {
        "first": first,
        "last": last,
        "min": bounds["min"],
        "max": bounds["max"],
        "change": absolute,
        "change_percent": percent,
        "count": history.count(),
    }


def thin(points, max_points=MAX_CHART_POINTS):
    """Равномерно прореживает ряд до max_points, сохраняя последнюю точку."""
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    thinned = [points[int(i * step)] for i in range(max_points)]
    thinned[-1] = points[-1]
    return thinned


def history_points(share, since):
    """[(время, цена), ...] за период по возрастанию времени."""
    history = share.price_history.all()
    if since is not None:
        history = history.filter(time__gte=since)
    return list(history.order_by("time").values_list("time", "price"))


def price_series(share, since, max_points=MAX_CHART_POINTS):
    """[(время, цена), ...] за период, прореженные до max_points точек."""
    return thin(history_points(share, since), max_points)


def daily_changes(share, since):
    """Дневная статистика: цена закрытия дня, мин/макс и изменение к предыдущему дню."""
    history = share.price_history.all()
    if since is not None:
        history = history.filter(time__gte=since)

    days = OrderedDict()
    for time, price in history.order_by("time").values_list("time", "price"):
        day = timezone.localtime(time).date()
        if day not in days:
            days[day] = {"day": day, "close": price, "min": price, "max": price}
        stats = days[day]
        stats["close"] = price
        stats["min"] = min(stats["min"], price)
        stats["max"] = max(stats["max"], price)

    previous_close = None
    for stats in days.values():
        stats["change"], stats["change_percent"] = change(previous_close, stats["close"])
        previous_close = stats["close"]
    return list(reversed(days.values()))


def market_changes(since):
    """Изменение цены каждой акции с историей за период, по убыванию роста в %."""
    history = PriceSnapshot.objects.filter(share=OuterRef("pk"))
    if since is not None:
        history = history.filter(time__gte=since)
    shares = Share.objects.annotate(
        first_price=Subquery(history.order_by("time").values("price")[:1]),
        first_time=Subquery(history.order_by("time").values("time")[:1]),
        period_last_price=Subquery(history.order_by("-time").values("price")[:1]),
        last_time=Subquery(history.order_by("-time").values("time")[:1]),
    ).filter(first_price__isnull=False)

    rows = []
    for share in shares:
        # Одна точка за период ничего не говорит о динамике
        if share.first_time == share.last_time:
            continue
        absolute, percent = change(share.first_price, share.period_last_price)
        rows.append(
            {
                "share": share,
                "first": share.first_price,
                "last": share.period_last_price,
                "change": absolute,
                "change_percent": percent,
            }
        )
    rows.sort(key=lambda row: row["change_percent"] or 0, reverse=True)
    return rows
