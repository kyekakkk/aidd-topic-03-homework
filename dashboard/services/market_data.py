import logging

from django.conf import settings

from dashboard.models import Share
from dashboard.services import moex
from dashboard.services.errors import MarketDataError
from dashboard.services.tinvest import get_day_candles, get_last_prices

logger = logging.getLogger("main")

# Ограничиваем размер одного запроса котировок
CHUNK_SIZE = 200


def chunks(items):
    for start in range(0, len(items), CHUNK_SIZE):
        yield items[start : start + CHUNK_SIZE]


def get_last_data(shares):
    """Последние цены {figi: (цена, время)} для акций из всех источников.

    Сбой одного источника не мешает получить цены из другого.
    """
    by_source = {}
    for share in shares:
        by_source.setdefault(share.source, []).append(share.figi)

    result = {}
    for figis in chunks(by_source.get(Share.SOURCE_MOEX, [])):
        try:
            prices = moex.get_last_prices([moex.secid_from(figi) for figi in figis])
        except MarketDataError:
            logger.exception("Failed to get last prices from MOEX")
            continue
        result.update((moex.figi_for(secid), quote) for secid, quote in prices.items())

    tinvest_figis = by_source.get(Share.SOURCE_TINVEST, [])
    if tinvest_figis and settings.TINKOFF_TOKEN:
        for figis in chunks(tinvest_figis):
            try:
                result.update(get_last_prices(figis))
            except MarketDataError:
                logger.exception("Failed to get last prices from T-Invest")

    logger.info(f"Get last data for {len(result)} of {len(shares)} shares")
    return result


def get_candles(share, from_, to):
    """Дневные свечи [(время, цена закрытия), ...] из источника акции."""
    if share.source == Share.SOURCE_MOEX:
        return moex.get_day_candles(moex.secid_from(share.figi), from_, to)
    if share.source == Share.SOURCE_TINVEST:
        return get_day_candles(share.figi, from_, to)
    raise MarketDataError(f"У акции {share.ticker} нет внешнего источника котировок")
