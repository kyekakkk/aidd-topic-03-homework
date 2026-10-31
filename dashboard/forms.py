from django import forms

from .models import PriceAlert, Share, Strategy, Watchlist
from .services.history import PERIODS


class ShareModelForm(forms.ModelForm):
    """Инструмент"""

    class Meta:
        model = Share
        # last_price и is_trend_high заполняет фоновая задача
        fields = ("figi", "isin", "name", "ticker", "currency", "uid")


class BuyShareForm(forms.Form):
    """Покупка акций в виртуальный портфель"""

    quantity = forms.IntegerField(
        label="Количество", min_value=1, max_value=1_000_000, initial=1
    )
    price = forms.FloatField(
        label="Цена покупки",
        min_value=0.000000001,
        help_text="По умолчанию — текущая цена акции",
    )


class WatchlistForm(forms.ModelForm):
    """Новый список наблюдения"""

    class Meta:
        model = Watchlist
        fields = ("name",)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        # Сравниваем в Python: iexact в SQLite не учитывает регистр кириллицы
        existing = Watchlist.objects.filter(user=self.user).values_list("name", flat=True)
        if name.casefold() in {other.casefold() for other in existing}:
            raise forms.ValidationError("Список с таким названием уже есть")
        return name

    def save(self, commit=True):
        self.instance.user = self.user
        return super().save(commit)


class AddToWatchlistForm(forms.Form):
    """Добавление акции в один из списков пользователя"""

    watchlist = forms.ModelChoiceField(
        label="Список", queryset=Watchlist.objects.none(), required=False,
        empty_label="Избранное (создать)",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["watchlist"].queryset = Watchlist.objects.filter(user=user)
        if self.fields["watchlist"].queryset.exists():
            self.fields["watchlist"].empty_label = None


class PriceAlertForm(forms.ModelForm):
    """Целевой ценовой уровень"""

    class Meta:
        model = PriceAlert
        fields = ("direction", "target_price")

    def clean_target_price(self):
        price = self.cleaned_data["target_price"]
        if price <= 0:
            raise forms.ValidationError("Цена должна быть больше нуля")
        return price


class StrategyForm(forms.ModelForm):
    """Создание стратегии; параметры зависят от выбранного типа"""

    # Поля, которые показываются для каждого типа стратегии
    KIND_FIELDS = {
        Strategy.LEVELS: ("buy_below", "sell_above"),
        Strategy.DIP: ("buy_drop_percent", "take_profit_percent"),
        Strategy.SMA: ("short_window", "long_window"),
    }
    COMMON_FIELDS = ("name", "share", "kind")
    MONEY_FIELDS = ("stop_loss_percent", "initial_capital", "commission_percent")

    class Meta:
        model = Strategy
        fields = (
            "name",
            "share",
            "kind",
            "buy_below",
            "sell_above",
            "buy_drop_percent",
            "take_profit_percent",
            "short_window",
            "long_window",
            "stop_loss_percent",
            "initial_capital",
            "commission_percent",
        )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        self.fields["share"].queryset = Share.objects.order_by("ticker")

    def clean(self):
        cleaned_data = super().clean()
        # Параметры других типов не сохраняем, чтобы не путать
        kind = cleaned_data.get("kind")
        for other_kind, fields in self.KIND_FIELDS.items():
            if other_kind != kind:
                for name in fields:
                    cleaned_data[name] = None
                    setattr(self.instance, name, None)
        return cleaned_data

    def kind_groups(self):
        return [
            (kind, [self[name] for name in fields]) for kind, fields in self.KIND_FIELDS.items()
        ]


class SimulationRunForm(forms.Form):
    period = forms.ChoiceField(
        label="История за период",
        choices=[(code, title) for code, (title, _) in PERIODS.items()],
        initial="all",
    )
