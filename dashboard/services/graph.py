import math
import random
from datetime import timedelta

import plotly.graph_objs as go
from django.utils import timezone
from plotly.offline import plot

from config.settings import TINKOFF_TOKEN, logger

try:
    from tinkoff.invest import CandleInterval, Client
    from tinkoff.invest.utils import now

    TINKOFF_AVAILABLE = True
except ImportError:  # SDK необязателен: без него используется синтетический ряд цен
    CandleInterval = Client = now = None
    TINKOFF_AVAILABLE = False

# Высота графика (px). Явно задаём и в layout, и через контейнер в шаблоне,
# иначе plotly генерирует div со style="height:100%" и без высоты родителя
# график «схлопывается» (выглядит как плоская линия) и наезжает на контент.
GRAPH_HEIGHT = 400
CHART_MARGIN = dict(l=40, r=40, t=20, b=50)


def _trading_days(days):
    """Список торговых дней (без субботы и воскресенья) от старого к новому."""
    today = timezone.localdate()
    result = []
    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() < 5:
            result.append(day)
    return result


def _mock_candles(share, days=180):
    """Генерирует реалистичный синтетический ряд исторических цен.

    Используется логарифмическое случайное блуждание с мягкой коррекцией к
    линейному тренду: ряд начинается около стартовой цены, заканчивается
    около текущей цены акции и имеет естественные колебания (волатильность,
    редкие «новостные» всплески). Ряд детерминирован для конкретной акции
    (сид зависит от figi/ticker), поэтому график не «прыгает» при перезагрузке.
    """
    seed_source = share.figi or share.ticker or str(share.pk)
    rng = random.Random(sum(ord(char) for char in seed_source))

    base_price = float(share.last_price) if share.last_price else 100.0
    precision = 4 if base_price < 1 else 2

    # Тренд за период: от стартовой цены к текущей (может быть как вверх, так и вниз)
    drift = rng.uniform(-0.30, 0.45)
    start_price = max(0.01, base_price / (1 + drift))
    volatility = rng.uniform(0.010, 0.028)  # дневная волатильность

    x_data = _trading_days(days)
    total = max(len(x_data) - 1, 1)
    log_start, log_end = math.log(start_price), math.log(base_price)

    y_data = []
    price = start_price
    for index, day in enumerate(x_data):
        # целевая линия тренда на текущем шаге
        progress = index / total
        target = math.exp(log_start + (log_end - log_start) * progress)

        shock = rng.gauss(0, volatility)
        if rng.random() < 0.05:  # редкие резкие движения на новостях
            shock *= rng.uniform(2.5, 4.0)

        price = max(0.01, price * (1 + shock))
        price += (target - price) * 0.3  # мягкий возврат к тренду

        x_data[index] = day
        y_data.append(round(price, precision))

    return x_data, y_data


def _tinkoff_candles(share):
    """Загружает реальные дневные свечи через Tinkoff Invest API."""
    x_data, y_data = [], []
    with Client(TINKOFF_TOKEN) as client:
        for candle in client.get_all_candles(
            figi=share.figi,
            from_=now() - timedelta(days=180),
            interval=CandleInterval.CANDLE_INTERVAL_DAY,
        ):
            x_data.append(candle.time.date())
            # цена = units + nano / 1e9 (в API цена представлена парой целых)
            y_data.append(round(candle.close.units + candle.close.nano / 1e9, 4))
    return x_data, y_data


def get_graph(share):
    """Возвращает HTML-разметку графика Plotly с настроенным layout.

    Если SDK Tinkoff доступен и данные получены — строится график по реальным
    свечам. Во всех остальных случаях (SDK не установлен, ошибка запроса,
    пустой ответ) используется синтетический ряд, чтобы график всегда
    отображался корректно.
    """
    x_data, y_data = [], []
    if TINKOFF_AVAILABLE:
        try:
            x_data, y_data = _tinkoff_candles(share)
        except Exception as error:  # noqa: BLE001 — грациозная деградация
            logger.error(f"Не удалось получить данные Tinkoff Invest: {error}")

    if not x_data:
        logger.warning(
            "Используется синтетический ряд исторических цен "
            "(Tinkoff Invest SDK недоступен или вернул пустой ответ)"
        )
        x_data, y_data = _mock_candles(share)

    figure = go.Figure(
        data=[
            go.Scatter(
                x=x_data,
                y=y_data,
                mode="lines",
                name=share.ticker,
                line=dict(color="#d62728", width=2),
            )
        ],
        layout=go.Layout(
            height=GRAPH_HEIGHT,
            margin=CHART_MARGIN,
            hovermode="x unified",
            xaxis=dict(title="Дата", showgrid=True, automargin=True),
            yaxis=dict(
                title=f"Цена, {share.currency}",
                showgrid=True,
                automargin=True,
                autorange=True,
            ),
        ),
    )

    return plot(figure, output_type="div", include_plotlyjs=False)
