from config.settings import logger


def get_last_data(client, share):
    """Возвращает последнюю цену и время сделки по акции.

    Клиент Tinkoff API передаётся извне, чтобы переиспользовать одно
    соединение при массовом обновлении цен (см. dashboard/tasks.py).
    """
    resp = client.market_data.get_last_prices(figi=[share.figi])
    last_price = resp.last_prices.pop()
    logger.info(f"Get last data for share with id {share.id}")
    return last_price.units, last_price.time
