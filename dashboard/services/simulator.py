"""Моделирование стратегии на истории цен (бэктест) с журналом виртуальных сделок.

Модель торговли: покупается максимум целых акций на весь свободный капитал,
продаётся вся позиция. Сделка исполняется по цене точки истории, в которой
сработало условие; комиссия берётся с суммы каждой сделки.
"""
from collections import deque
from dataclasses import dataclass, field

from django.db import transaction

from dashboard.models import SimulatedTrade, SimulationRun, Strategy
from dashboard.services.history import history_points, period_start, thin


class SimulationError(Exception):
    """Моделирование невозможно (например, мало истории)."""


@dataclass
class Trade:
    time: object
    side: str
    price: float
    quantity: int
    amount: float
    commission: float
    cash_after: float
    quantity_after: int
    reason: str
    profit: float = None


@dataclass
class Result:
    trades: list = field(default_factory=list)
    equity: list = field(default_factory=list)  # [(время, стоимость, цена)]
    final_cash: float = 0.0
    final_quantity: int = 0
    final_price: float = 0.0
    final_value: float = 0.0
    return_percent: float = 0.0
    benchmark_return_percent: float = 0.0
    max_drawdown_percent: float = 0.0


class MovingAverage:
    def __init__(self, window):
        self.window = window
        self.values = deque()
        self.total = 0.0

    def add(self, value):
        self.values.append(value)
        self.total += value
        if len(self.values) > self.window:
            self.total -= self.values.popleft()

    @property
    def value(self):
        return self.total / self.window if len(self.values) == self.window else None


def simulate(strategy, points):
    """Прогоняет стратегию по точкам [(время, цена), ...] в порядке времени."""
    if len(points) < 2:
        raise SimulationError("Для моделирования нужно хотя бы две точки истории цен")

    commission_rate = strategy.commission_percent / 100
    cash = strategy.initial_capital
    quantity = 0
    cost_basis = 0.0  # сколько потрачено на текущую позицию вместе с комиссией
    entry_price = None
    peak = None  # максимум цены с момента последней продажи (для DIP)
    short_ma = MovingAverage(strategy.short_window or 1)
    long_ma = MovingAverage(strategy.long_window or 1)
    previous_diff = None
    peak_equity = cash
    result = Result()

    for time, price in points:
        cross_up = cross_down = False
        if strategy.kind == Strategy.SMA:
            short_ma.add(price)
            long_ma.add(price)
            if long_ma.value is not None:
                diff = short_ma.value - long_ma.value
                if previous_diff is not None:
                    cross_up = previous_diff <= 0 < diff
                    cross_down = previous_diff >= 0 > diff
                previous_diff = diff

        if quantity > 0:
            reason = sell_reason(strategy, price, entry_price, cross_down)
            if reason:
                amount = quantity * price
                commission = amount * commission_rate
                cash += amount - commission
                result.trades.append(
                    Trade(time, SimulatedTrade.SELL, price, quantity, amount, commission,
                          cash, 0, reason, profit=amount - commission - cost_basis)
                )
                quantity, cost_basis, entry_price, peak = 0, 0.0, None, price
        else:
            peak = price if peak is None else max(peak, price)
            reason = buy_reason(strategy, price, peak, cross_up)
            if reason:
                affordable = int(cash // (price * (1 + commission_rate)))
                if affordable > 0:
                    amount = affordable * price
                    commission = amount * commission_rate
                    cash -= amount + commission
                    quantity, cost_basis, entry_price = affordable, amount + commission, price
                    result.trades.append(
                        Trade(time, SimulatedTrade.BUY, price, quantity, amount, commission,
                              cash, quantity, reason)
                    )

        equity = cash + quantity * price
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity * 100 if peak_equity else 0
        result.max_drawdown_percent = max(result.max_drawdown_percent, drawdown)
        result.equity.append((time, equity, price))

    first_price, last_price = points[0][1], points[-1][1]
    result.final_cash = cash
    result.final_quantity = quantity
    result.final_price = last_price
    # Открытая позиция оценивается по последней цене
    result.final_value = cash + quantity * last_price
    result.return_percent = (result.final_value / strategy.initial_capital - 1) * 100
    result.benchmark_return_percent = (last_price / first_price - 1) * 100
    return result


def buy_reason(strategy, price, peak, cross_up):
    if strategy.kind == Strategy.LEVELS and price <= strategy.buy_below:
        return f"Цена {price:g} ≤ уровня покупки {strategy.buy_below:g}"
    if strategy.kind == Strategy.DIP:
        threshold = peak * (1 - strategy.buy_drop_percent / 100)
        if price <= threshold:
            return f"Падение на {strategy.buy_drop_percent:g}% от максимума {peak:.2f}"
    if strategy.kind == Strategy.SMA and cross_up:
        return f"SMA{strategy.short_window} пересекла SMA{strategy.long_window} снизу вверх"
    return None


def sell_reason(strategy, price, entry_price, cross_down):
    if strategy.stop_loss_percent:
        stop = entry_price * (1 - strategy.stop_loss_percent / 100)
        if price <= stop:
            return f"Стоп-лосс: цена {price:g} ≤ {stop:.2f} (−{strategy.stop_loss_percent:g}%)"
    if strategy.kind == Strategy.LEVELS and price >= strategy.sell_above:
        return f"Цена {price:g} ≥ уровня продажи {strategy.sell_above:g}"
    if strategy.kind == Strategy.DIP:
        target = entry_price * (1 + strategy.take_profit_percent / 100)
        if price >= target:
            return f"Фиксация прибыли: +{strategy.take_profit_percent:g}% от цены покупки"
    if strategy.kind == Strategy.SMA and cross_down:
        return f"SMA{strategy.short_window} пересекла SMA{strategy.long_window} сверху вниз"
    return None


def run_simulation(strategy, period):
    """Моделирует стратегию на истории за период и сохраняет прогон с журналом."""
    points = history_points(strategy.share, period_start(period))
    result = simulate(strategy, points)

    with transaction.atomic():
        run = SimulationRun.objects.create(
            strategy=strategy,
            period=period,
            date_from=points[0][0],
            date_to=points[-1][0],
            points_count=len(points),
            initial_capital=strategy.initial_capital,
            final_cash=result.final_cash,
            final_quantity=result.final_quantity,
            final_price=result.final_price,
            final_value=result.final_value,
            return_percent=result.return_percent,
            benchmark_return_percent=result.benchmark_return_percent,
            max_drawdown_percent=result.max_drawdown_percent,
            trades_count=len(result.trades),
            equity_curve=[
                [time.isoformat(), round(equity, 2), price]
                for time, equity, price in thin(result.equity)
            ],
        )
        SimulatedTrade.objects.bulk_create(
            SimulatedTrade(run=run, **trade.__dict__) for trade in result.trades
        )
    return run
