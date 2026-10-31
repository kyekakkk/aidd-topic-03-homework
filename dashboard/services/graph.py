from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.safestring import mark_safe
from plotly.graph_objs import Scatter
from plotly.offline import plot

from dashboard.services.market_data import get_candles as fetch_candles

HISTORY_DAYS = 180


def get_candles(share):
    cache_key = f"candles:{share.figi}"
    candles = cache.get(cache_key)
    if candles is None:
        to = timezone.now()
        candles = fetch_candles(share, to - timedelta(days=HISTORY_DAYS), to)
        cache.set(cache_key, candles, settings.CANDLES_CACHE_TIMEOUT)
    return candles


def get_graph(share):
    """HTML-div с графиком цен закрытия. Может выбросить MarketDataError."""
    candles = get_candles(share)
    plot_div = plot(
        [
            Scatter(
                x=[time.date() for time, _ in candles],
                y=[close for _, close in candles],
                mode="lines",
                name=share.ticker,
                opacity=0.8,
                line_color="red",
            )
        ],
        output_type="div",
        include_plotlyjs="cdn",
    )
    # Разметку генерирует plotly из числовых данных, экранирование не требуется
    return mark_safe(plot_div)
