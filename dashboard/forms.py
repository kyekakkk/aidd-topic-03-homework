from django import forms

from .models import Share


class ShareModelForm(forms.ModelForm):
    """Инструмент"""

    class Meta:
        model = Share
        fields = "__all__"


class TradeForm(forms.Form):
    """Форма покупки/продажи акции"""

    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Количество",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
