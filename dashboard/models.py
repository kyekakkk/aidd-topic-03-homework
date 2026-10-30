from django.conf import settings
from django.db import models
from django.utils import timezone


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

    class Meta:
        verbose_name = "Акция"
        verbose_name_plural = "Акции"

    def __str__(self):
        return f"{self.ticker} — {self.name}"


class Portfolio(models.Model):
    """Портфель пользователя"""

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

    @property
    def total_value(self):
        """Текущая рыночная стоимость всех позиций."""
        return sum(position.current_value for position in self.positions.all())

    @property
    def total_cost(self):
        """Сумма затрат на покупку всех позиций."""
        return sum(position.cost for position in self.positions.all())

    @property
    def total_profit(self):
        """Суммарная прибыль/убыток (P&L)."""
        return self.total_value - self.total_cost


class PortfolioPosition(models.Model):
    """Позиция портфеля: акция, количество, цена покупки, дата"""

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
    quantity = models.PositiveIntegerField(default=0, verbose_name="Количество")
    purchase_price = models.FloatField(
        default=0.0, verbose_name="Средняя цена покупки"
    )
    purchased_at = models.DateTimeField(
        default=timezone.now, verbose_name="Дата покупки"
    )

    class Meta:
        verbose_name = "Позиция портфеля"
        verbose_name_plural = "Позиции портфеля"
        unique_together = ("portfolio", "share")
        ordering = ["share__name"]

    def __str__(self):
        return f"{self.share.ticker} × {self.quantity}"

    @property
    def current_price(self):
        return float(self.share.last_price or 0.0)

    @property
    def cost(self):
        """Стоимость позиции по цене покупки."""
        return self.quantity * self.purchase_price

    @property
    def current_value(self):
        """Текущая рыночная стоимость позиции."""
        return self.quantity * self.current_price

    @property
    def profit(self):
        """Прибыль/убыток в абсолютном выражении (P&L)."""
        return self.current_value - self.cost

    @property
    def profit_percent(self):
        """Прибыль/убыток в процентах от затрат."""
        if not self.cost:
            return 0.0
        return self.profit / self.cost * 100
