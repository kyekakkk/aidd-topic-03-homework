from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def signed(value, digits=2):
    """Число со знаком: +1,23 / -4,56; для None — прочерк."""
    if value is None:
        return "—"
    text = floatformat(value, digits)
    return f"+{text}" if value > 0 else text


@register.filter
def change_color(value):
    """CSS-цвет для изменения цены."""
    if not value:
        return "inherit"
    return "seagreen" if value > 0 else "crimson"


@register.filter
def get_item(mapping, key):
    return mapping.get(key, key)
