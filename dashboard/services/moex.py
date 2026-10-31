"""Клиент ISS Московской биржи — открытые данные без токена.

Документация: https://iss.moex.com/iss/reference/
Котировки для неподписанных пользователей отдаются с задержкой (~15 минут).
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

from dashboard.services.errors import MarketDataError

logger = logging.getLogger("main")

MOSCOW = ZoneInfo("Europe/Moscow")
SHARES_PATH = "engines/stock/markets/shares/boards/{board}/securities"
# Префикс FIGI/UID для акций, импортированных с биржи (настоящего FIGI ISS не даёт)
FIGI_PREFIX = "MOEX-"
CURRENCIES = {"SUR": "rub", "RUB": "rub", "USD": "usd", "EUR": "eur", "CNY": "cny"}


class MoexError(MarketDataError):
    """Ошибка обращения к ISS MOEX."""


def figi_for(secid):
    return f"{FIGI_PREFIX}{secid}"


def secid_from(figi):
    return figi[len(FIGI_PREFIX) :]


RETRIES = 2


def call(path, params=None):
    url = f"{settings.MOEX_ISS_URL}/{path}.json"
    for attempt in range(1, RETRIES + 1):
        try:
            response = requests.get(
                url,
                params={"iss.meta": "off", **(params or {})},
                timeout=settings.MOEX_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            # Сетевые сбои бывают разовыми — повторяем запрос
            if attempt == RETRIES:
                raise MoexError(f"{path}: {e}") from e
            logger.warning(f"MOEX {path}: {e}, retry {attempt}")
        except (requests.RequestException, ValueError) as e:
            raise MoexError(f"{path}: {e}") from e


def rows(data, block):
    """Блок ISS {columns, data} -> список словарей."""
    columns = data[block]["columns"]
    return [dict(zip(columns, row)) for row in data[block]["data"]]


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=MOSCOW)


def market_price(market):
    """Последняя сделка, иначе текущая рыночная цена."""
    return market.get("LAST") or market.get("MARKETPRICE")


def get_board_data(secids=None):
    params = {
        "securities.columns": "SECID,SHORTNAME,SECNAME,ISIN,CURRENCYID,PREVPRICE",
        "marketdata.columns": "SECID,LAST,MARKETPRICE,SYSTIME",
    }
    if secids:
        params["securities"] = ",".join(secids)
    return call(SHARES_PATH.format(board=settings.MOEX_BOARD), params)


def get_shares():
    """Акции основного режима торгов с текущими ценами."""
    data = get_board_data()
    market = {row["SECID"]: row for row in rows(data, "marketdata")}
    shares = []
    for security in rows(data, "securities"):
        quote = market.get(security["SECID"], {})
        shares.append(
            {
                "secid": security["SECID"],
                "name": security["SECNAME"] or security["SHORTNAME"],
                "isin": security["ISIN"] or "",
                "currency": CURRENCIES.get(security["CURRENCYID"], (security["CURRENCYID"] or "").lower()),
                "price": market_price(quote) or security["PREVPRICE"],
            }
        )
    return shares


def get_last_prices(secids):
    """Возвращает {secid: (цена, время)} одним запросом."""
    data = get_board_data(secids)
    result = {}
    for quote in rows(data, "marketdata"):
        price = market_price(quote)
        if price is not None:
            result[quote["SECID"]] = (float(price), parse_time(quote.get("SYSTIME")))
    return result


def get_day_candles(secid, from_, to):
    """Возвращает [(время свечи, цена закрытия), ...]; ISS отдаёт страницы по 500 свечей."""
    path = f"{SHARES_PATH.format(board=settings.MOEX_BOARD)}/{secid}/candles"
    candles = []
    while True:
        data = call(
            path,
            {
                "interval": 24,
                "from": from_.astimezone(MOSCOW).date().isoformat(),
                "till": to.astimezone(MOSCOW).date().isoformat(),
                "start": len(candles),
            },
        )
        page = rows(data, "candles")
        candles.extend((parse_time(c["begin"]), float(c["close"])) for c in page)
        if len(page) < 500:
            return candles
