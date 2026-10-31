from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Share(models.Model):
    """Акция"""

    figi = models.CharField(max_length=255, unique=True)
    isin = models.CharField(max_length=255)
    name = models.CharField(max_length=255, verbose_name="Наименование компании")
    ticker = models.CharField(max_length=10, unique=True, verbose_name="Тикер")
    currency = models.CharField(max_length=20, verbose_name="Валюта")
    uid = models.CharField(max_length=255, unique=True)
    last_price = models.FloatField(blank=True, null=True, verbose_name="Текущая цена")
    is_trend_high = models.BooleanField(
        blank=True, null=True, verbose_name="Растет цена"
    )
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    SOURCE_TINVEST = "tinvest"
    SOURCE_MOEX = "moex"
    SOURCE_DEMO = "demo"

    class Meta:
        verbose_name = "Акция"
        verbose_name_plural = "Акции"

    def __str__(self):
        return f"{self.ticker} — {self.name}"

    @property
    def source(self):
        """Откуда берутся котировки: биржа (MOEX ISS), T-Invest или демо-данные."""
        if self.figi.startswith("MOEX-"):
            return self.SOURCE_MOEX
        if self.figi.startswith("DEMO"):
            return self.SOURCE_DEMO
        return self.SOURCE_TINVEST


class Portfolio(models.Model):
    """Виртуальный портфель пользователя"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolio",
        verbose_name="Пользователь",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Портфель"
        verbose_name_plural = "Портфели"

    def __str__(self):
        return f"Портфель {self.user}"


class PortfolioPosition(models.Model):
    """Позиция портфеля: сколько акций куплено и по какой средней цене"""

    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="positions",
        verbose_name="Портфель",
    )
    share = models.ForeignKey(
        Share,
        on_delete=models.CASCADE,
        related_name="positions",
        verbose_name="Акция",
    )
    quantity = models.PositiveIntegerField(verbose_name="Количество")
    average_price = models.FloatField(verbose_name="Средняя цена покупки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата изменения")

    class Meta:
        verbose_name = "Позиция портфеля"
        verbose_name_plural = "Позиции портфеля"
        constraints = [
            models.UniqueConstraint(
                fields=["portfolio", "share"], name="unique_portfolio_share"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="position_quantity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.share.ticker} × {self.quantity}"

    @property
    def cost(self):
        """Сколько потрачено на покупку"""
        return self.quantity * self.average_price

    @property
    def market_value(self):
        """Текущая стоимость; None, если цена акции неизвестна"""
        if self.share.last_price is None:
            return None
        return self.quantity * self.share.last_price

    @property
    def profit(self):
        if self.market_value is None:
            return None
        return self.market_value - self.cost

    def add(self, quantity, price):
        """Докупка: средняя цена пересчитывается как средневзвешенная."""
        total = self.quantity + quantity
        self.average_price = (
            self.quantity * self.average_price + quantity * price
        ) / total
        self.quantity = total


class PriceSnapshot(models.Model):
    """Снимок рыночной цены акции; из снимков складывается история цен"""

    share = models.ForeignKey(
        Share,
        on_delete=models.CASCADE,
        related_name="price_history",
        verbose_name="Акция",
    )
    price = models.FloatField(verbose_name="Цена")
    time = models.DateTimeField(verbose_name="Время котировки")

    class Meta:
        verbose_name = "Снимок цены"
        verbose_name_plural = "История цен"
        ordering = ["time"]
        constraints = [
            # Одна и та же котировка не сохраняется дважды;
            # заодно служит индексом для выборок по акции и периоду
            models.UniqueConstraint(fields=["share", "time"], name="unique_share_time"),
        ]

    def __str__(self):
        return f"{self.share.ticker} {self.price} @ {self.time:%Y-%m-%d %H:%M}"


class Watchlist(models.Model):
    """Персональный список наблюдения"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watchlists",
        verbose_name="Пользователь",
    )
    name = models.CharField(max_length=100, verbose_name="Название")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Список наблюдения"
        verbose_name_plural = "Списки наблюдения"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_user_watchlist"),
        ]

    def __str__(self):
        return self.name


class WatchlistItem(models.Model):
    """Акция в списке наблюдения"""

    watchlist = models.ForeignKey(
        Watchlist,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Список",
    )
    share = models.ForeignKey(
        Share,
        on_delete=models.CASCADE,
        related_name="watchlist_items",
        verbose_name="Акция",
    )
    added_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        verbose_name = "Акция в списке наблюдения"
        verbose_name_plural = "Акции в списках наблюдения"
        constraints = [
            models.UniqueConstraint(
                fields=["watchlist", "share"], name="unique_watchlist_share"
            ),
        ]

    def __str__(self):
        return f"{self.watchlist}: {self.share.ticker}"


class PriceAlert(models.Model):
    """Целевой ценовой уровень для акции из списка наблюдения"""

    ABOVE = "above"
    BELOW = "below"
    DIRECTIONS = [
        (ABOVE, "Цена поднимется до уровня"),
        (BELOW, "Цена опустится до уровня"),
    ]

    item = models.ForeignKey(
        WatchlistItem,
        on_delete=models.CASCADE,
        related_name="alerts",
        verbose_name="Акция в списке",
    )
    direction = models.CharField(
        max_length=5, choices=DIRECTIONS, verbose_name="Условие"
    )
    target_price = models.FloatField(verbose_name="Целевая цена")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    triggered_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Время достижения"
    )
    triggered_price = models.FloatField(
        blank=True, null=True, verbose_name="Цена в момент достижения"
    )

    class Meta:
        verbose_name = "Целевой уровень"
        verbose_name_plural = "Целевые уровни"
        ordering = ["triggered_at", "target_price"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target_price__gt=0), name="alert_target_positive"
            ),
        ]

    def __str__(self):
        return f"{self.item.share.ticker} {self.get_direction_display()} {self.target_price}"

    @property
    def is_triggered(self):
        return self.triggered_at is not None

    def is_reached(self, price):
        if price is None:
            return False
        if self.direction == self.ABOVE:
            return price >= self.target_price
        return price <= self.target_price

    def check_price(self, price, when):
        """Фиксирует достижение уровня. Возвращает True, если уровень сработал сейчас."""
        if self.is_triggered or not self.is_reached(price):
            return False
        self.triggered_at = when
        self.triggered_price = price
        return True


class Strategy(models.Model):
    """Инвестиционная стратегия для моделирования на истории цен"""

    LEVELS = "levels"
    DIP = "dip"
    SMA = "sma"
    KINDS = [
        (LEVELS, "Ценовые уровни: купить ниже, продать выше"),
        (DIP, "Покупка на просадке с фиксацией прибыли"),
        (SMA, "Пересечение скользящих средних"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="strategies",
        verbose_name="Пользователь",
    )
    share = models.ForeignKey(
        Share, on_delete=models.CASCADE, related_name="strategies", verbose_name="Акция"
    )
    name = models.CharField(max_length=100, verbose_name="Название")
    kind = models.CharField(max_length=10, choices=KINDS, verbose_name="Тип стратегии")

    buy_below = models.FloatField(blank=True, null=True, verbose_name="Купить, когда цена ≤")
    sell_above = models.FloatField(blank=True, null=True, verbose_name="Продать, когда цена ≥")
    buy_drop_percent = models.FloatField(
        blank=True, null=True, verbose_name="Купить при падении от максимума на, %"
    )
    take_profit_percent = models.FloatField(
        blank=True, null=True, verbose_name="Продать при росте от цены покупки на, %"
    )
    short_window = models.PositiveIntegerField(
        blank=True, null=True, verbose_name="Короткая средняя, точек"
    )
    long_window = models.PositiveIntegerField(
        blank=True, null=True, verbose_name="Длинная средняя, точек"
    )
    stop_loss_percent = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Стоп-лосс, %",
        help_text="Продать, если цена упала от цены покупки на столько процентов",
    )
    initial_capital = models.FloatField(default=100_000, verbose_name="Стартовый капитал")
    commission_percent = models.FloatField(default=0.05, verbose_name="Комиссия за сделку, %")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    # Какие параметры обязательны для каждого типа
    REQUIRED = {
        LEVELS: ("buy_below", "sell_above"),
        DIP: ("buy_drop_percent", "take_profit_percent"),
        SMA: ("short_window", "long_window"),
    }

    class Meta:
        verbose_name = "Стратегия"
        verbose_name_plural = "Стратегии"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        for field in self.REQUIRED.get(self.kind, ()):
            if getattr(self, field) is None:
                errors[field] = "Обязательно для выбранного типа стратегии"
        for field in ("buy_below", "sell_above"):
            value = getattr(self, field)
            if value is not None and value <= 0:
                errors[field] = "Цена должна быть больше нуля"
        for field in ("buy_drop_percent", "stop_loss_percent"):
            value = getattr(self, field)
            if value is not None and not 0 < value < 100:
                errors[field] = "Укажите от 0 до 100 %"
        if self.take_profit_percent is not None and self.take_profit_percent <= 0:
            errors["take_profit_percent"] = "Должно быть больше нуля"
        if (
            self.kind == self.LEVELS
            and None not in (self.buy_below, self.sell_above)
            and self.buy_below >= self.sell_above
        ):
            errors["sell_above"] = "Цена продажи должна быть выше цены покупки"
        if self.kind == self.SMA and None not in (self.short_window, self.long_window):
            if self.short_window < 1:
                errors["short_window"] = "Минимум 1 точка"
            if self.long_window <= self.short_window:
                errors["long_window"] = "Длинная средняя должна быть длиннее короткой"
        if self.initial_capital is not None and self.initial_capital <= 0:
            errors["initial_capital"] = "Капитал должен быть больше нуля"
        if self.commission_percent is not None and not 0 <= self.commission_percent < 10:
            errors["commission_percent"] = "Укажите от 0 до 10 %"
        if errors:
            raise ValidationError(errors)

    @property
    def rules(self):
        """Правила стратегии человеческим языком."""
        if self.kind == self.LEVELS:
            rules = [
                f"Купить при цене ≤ {self.buy_below:g}",
                f"Продать при цене ≥ {self.sell_above:g}",
            ]
        elif self.kind == self.DIP:
            rules = [
                f"Купить при падении на {self.buy_drop_percent:g}% от максимума",
                f"Продать при росте на {self.take_profit_percent:g}% от цены покупки",
            ]
        else:
            rules = [
                f"Купить, когда SMA{self.short_window} пересекает SMA{self.long_window} снизу вверх",
                f"Продать, когда SMA{self.short_window} пересекает SMA{self.long_window} сверху вниз",
            ]
        if self.stop_loss_percent:
            rules.append(
                f"Стоп-лосс: продать при падении на {self.stop_loss_percent:g}% от цены покупки"
            )
        return rules


class SimulationRun(models.Model):
    """Прогон стратегии на истории цен"""

    strategy = models.ForeignKey(
        Strategy, on_delete=models.CASCADE, related_name="runs", verbose_name="Стратегия"
    )
    period = models.CharField(max_length=10, verbose_name="Период")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время запуска")
    date_from = models.DateTimeField(verbose_name="Начало истории")
    date_to = models.DateTimeField(verbose_name="Конец истории")
    points_count = models.PositiveIntegerField(verbose_name="Точек истории")
    initial_capital = models.FloatField(verbose_name="Стартовый капитал")
    final_cash = models.FloatField(verbose_name="Деньги в конце")
    final_quantity = models.PositiveIntegerField(verbose_name="Акций в конце")
    final_price = models.FloatField(verbose_name="Цена в конце")
    final_value = models.FloatField(verbose_name="Итоговая стоимость")
    return_percent = models.FloatField(verbose_name="Доходность, %")
    benchmark_return_percent = models.FloatField(verbose_name="Изменение цены акции, %")
    max_drawdown_percent = models.FloatField(verbose_name="Максимальная просадка, %")
    trades_count = models.PositiveIntegerField(verbose_name="Сделок")
    # [[время ISO, стоимость портфеля, цена], ...] — для графика, прорежено
    equity_curve = models.JSONField(default=list, verbose_name="Кривая капитала")

    class Meta:
        verbose_name = "Прогон стратегии"
        verbose_name_plural = "Прогоны стратегий"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.strategy} @ {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def profit(self):
        return self.final_value - self.initial_capital


class SimulatedTrade(models.Model):
    """Виртуальная сделка в журнале прогона"""

    BUY = "buy"
    SELL = "sell"
    SIDES = [(BUY, "Покупка"), (SELL, "Продажа")]

    run = models.ForeignKey(
        SimulationRun, on_delete=models.CASCADE, related_name="trades", verbose_name="Прогон"
    )
    time = models.DateTimeField(verbose_name="Время")
    side = models.CharField(max_length=4, choices=SIDES, verbose_name="Операция")
    price = models.FloatField(verbose_name="Цена")
    quantity = models.PositiveIntegerField(verbose_name="Количество")
    amount = models.FloatField(verbose_name="Сумма")
    commission = models.FloatField(verbose_name="Комиссия")
    cash_after = models.FloatField(verbose_name="Деньги после сделки")
    quantity_after = models.PositiveIntegerField(verbose_name="Акций после сделки")
    profit = models.FloatField(blank=True, null=True, verbose_name="Результат сделки")
    reason = models.CharField(max_length=255, verbose_name="Причина")

    class Meta:
        verbose_name = "Виртуальная сделка"
        verbose_name_plural = "Журнал виртуальных сделок"
        ordering = ["time", "id"]

    def __str__(self):
        return f"{self.get_side_display()} {self.quantity} × {self.price}"
