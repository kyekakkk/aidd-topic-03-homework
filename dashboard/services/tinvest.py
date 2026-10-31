"""Минимальный клиент REST-шлюза T-Invest API.

Документация: https://developer.tbank.ru/invest/api
"""
import logging
from datetime import datetime

import requests
from django.conf import settings

from dashboard.services.errors import MarketDataError

logger = logging.getLogger("main")

CONTRACT = "tinkoff.public.invest.api.contract.v1"


class TinvestError(MarketDataError):
    """Ошибка обращения к T-Invest API."""


def quotation_to_float(quotation):
    """Quotation/MoneyValue {units, nano} -> float без потери дробной части.

    В JSON protobuf int64 приходит строкой, а нулевые поля опускаются.
    """
    if not quotation:
        return None
    units = int(quotation.get("units", 0))
    nano = int(quotation.get("nano", 0))
    return units + nano / 1_000_000_000


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def call(service, method, payload):
    if not settings.TINKOFF_TOKEN:
        raise TinvestError("TINKOFF_TOKEN не задан")

    url = f"{settings.TINVEST_API_URL}/{CONTRACT}.{service}/{method}"
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.TINKOFF_TOKEN}"},
            timeout=settings.TINVEST_TIMEOUT,
            verify=settings.TINVEST_CA_BUNDLE or True,
        )
    except requests.RequestException as e:
        raise TinvestError(f"{service}/{method}: {e}") from e

    if response.status_code != 200:
        raise TinvestError(
            f"{service}/{method}: HTTP {response.status_code} {response.text[:200]}"
        )
    return response.json()


def get_shares():
    data = call(
        "InstrumentsService", "Shares", {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}
    )
    return data.get("instruments", [])


def get_last_prices(figis):
    """Возвращает {figi: (цена, время)} для переданного списка FIGI."""
    data = call("MarketDataService", "GetLastPrices", {"figi": list(figis)})
    result = {}
    for item in data.get("lastPrices", []):
        price = quotation_to_float(item.get("price"))
        if price is not None:
            result[item["figi"]] = (price, parse_time(item.get("time")))
    return result


def get_day_candles(figi, from_, to):
    """Возвращает [(время свечи, цена закрытия), ...] по дневным свечам."""
    data = call(
        "MarketDataService",
        "GetCandles",
        {
            "figi": figi,
            "from": from_.isoformat(),
            "to": to.isoformat(),
            "interval": "CANDLE_INTERVAL_DAY",
        },
    )
    return [
        (parse_time(candle["time"]), quotation_to_float(candle.get("close")))
        for candle in data.get("candles", [])
    ]
