from datetime import datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from dashboard.models import Portfolio, PortfolioPosition, Share
from dashboard.services import moex
from dashboard.services.errors import MarketDataError
from dashboard.services.market_data import get_candles, get_last_data
from dashboard.services.moex import MoexError
from dashboard.services.tinvest import TinvestError

MOSCOW = ZoneInfo("Europe/Moscow")


def iss_board(securities, marketdata):
    return {
        "securities": {
            "columns": ["SECID", "SHORTNAME", "SECNAME", "ISIN", "CURRENCYID", "PREVPRICE"],
            "data": securities,
        },
        "marketdata": {"columns": ["SECID", "LAST", "MARKETPRICE", "SYSTIME"], "data": marketdata},
    }


BOARD = iss_board(
    [
        ["SBER", "Сбербанк", "Сбербанк России ПАО ао", "RU0009029540", "SUR", 290.0],
        ["GAZP", "ГАЗПРОМ ао", "\"Газпром\" (ПАО) ао", "RU0007661625", "SUR", 120.0],
        ["LONGTICKER12", "Длинный", "Длинный тикер", "RU000LONG", "SUR", 1.0],
    ],
    [
        ["SBER", 293.45, 293.4, "2026-10-31 17:21:53"],
        ["GAZP", None, 121.5, "2026-10-31 17:21:50"],
        ["LONGTICKER12", None, None, None],
    ],
)


def make_share(figi, ticker):
    return Share.objects.create(
        figi=figi, isin=f"I-{ticker}", name=ticker, ticker=ticker, currency="rub", uid=f"u-{ticker}"
    )


class MoexClientTests(TestCase):
    @mock.patch("dashboard.services.moex.call", return_value=BOARD)
    def test_get_shares(self, call):
        shares = {share["secid"]: share for share in moex.get_shares()}
        self.assertEqual(shares["SBER"]["name"], "Сбербанк России ПАО ао")
        self.assertEqual(shares["SBER"]["currency"], "rub")
        self.assertEqual(shares["SBER"]["price"], 293.45)
        # Нет последней сделки — берётся рыночная цена, нет и её — вчерашняя
        self.assertEqual(shares["GAZP"]["price"], 121.5)
        self.assertEqual(shares["LONGTICKER12"]["price"], 1.0)

    @mock.patch("dashboard.services.moex.call", return_value=BOARD)
    def test_get_last_prices(self, call):
        prices = moex.get_last_prices(["SBER", "GAZP"])
        self.assertEqual(call.call_args.args[1]["securities"], "SBER,GAZP")
        price, time = prices["SBER"]
        self.assertEqual(price, 293.45)
        self.assertEqual(time, datetime(2026, 10, 31, 17, 21, 53, tzinfo=MOSCOW))
        self.assertNotIn("LONGTICKER12", prices)

    @mock.patch("dashboard.services.moex.call")
    def test_candles_pagination(self, call):
        def page(n, offset):
            return {
                "candles": {
                    "columns": ["close", "begin"],
                    "data": [
                        [float(offset + i), (datetime(2025, 1, 1) + timedelta(days=offset + i)).isoformat(sep=" ")]
                        for i in range(n)
                    ],
                }
            }

        call.side_effect = [page(500, 0), page(20, 500)]
        to = timezone.now()
        candles = moex.get_day_candles("SBER", to - timedelta(days=600), to)
        self.assertEqual(len(candles), 520)
        self.assertEqual(call.call_args_list[1].args[1]["start"], 500)
        self.assertEqual(candles[0][0].tzinfo, MOSCOW)

    @mock.patch("dashboard.services.moex.requests.get", side_effect=moex.requests.ConnectionError("down"))
    def test_network_error(self, get):
        with self.assertRaises(MoexError):
            moex.get_shares()
        self.assertEqual(get.call_count, moex.RETRIES)
        self.assertTrue(issubclass(MoexError, MarketDataError))

    @mock.patch("dashboard.services.moex.requests.get")
    def test_retry_after_timeout(self, get):
        response = mock.Mock()
        response.json.return_value = BOARD
        get.side_effect = [moex.requests.Timeout("slow"), response]
        self.assertEqual(len(moex.get_shares()), 3)
        self.assertEqual(get.call_count, 2)


class MarketDataRoutingTests(TestCase):
    def setUp(self):
        self.moex_share = make_share("MOEX-SBER", "SBER")
        self.tinvest_share = make_share("BBG000B9XRY4", "AAPL")
        self.demo_share = make_share("DEMO00000001", "DEMOA")
        self.now = timezone.now()

    def test_source(self):
        self.assertEqual(self.moex_share.source, Share.SOURCE_MOEX)
        self.assertEqual(self.tinvest_share.source, Share.SOURCE_TINVEST)
        self.assertEqual(self.demo_share.source, Share.SOURCE_DEMO)

    @override_settings(TINKOFF_TOKEN="")
    @mock.patch("dashboard.services.market_data.get_last_prices")
    @mock.patch("dashboard.services.moex.get_last_prices")
    def test_without_token_only_moex(self, moex_prices, tinvest_prices):
        moex_prices.return_value = {"SBER": (300.0, self.now)}
        prices = get_last_data([self.moex_share, self.tinvest_share, self.demo_share])
        self.assertEqual(prices, {"MOEX-SBER": (300.0, self.now)})
        moex_prices.assert_called_once_with(["SBER"])
        tinvest_prices.assert_not_called()

    @override_settings(TINKOFF_TOKEN="token")
    @mock.patch("dashboard.services.market_data.get_last_prices")
    @mock.patch("dashboard.services.moex.get_last_prices", side_effect=MoexError("down"))
    def test_one_source_failing_does_not_block_other(self, moex_prices, tinvest_prices):
        tinvest_prices.return_value = {"BBG000B9XRY4": (200.0, self.now)}
        prices = get_last_data([self.moex_share, self.tinvest_share])
        self.assertEqual(prices, {"BBG000B9XRY4": (200.0, self.now)})

    @mock.patch("dashboard.services.moex.get_day_candles", return_value=[("t", 1.0)])
    def test_candles_routing(self, moex_candles):
        self.assertEqual(get_candles(self.moex_share, self.now, self.now), [("t", 1.0)])
        moex_candles.assert_called_once_with("SBER", self.now, self.now)
        with self.assertRaises(MarketDataError):
            get_candles(self.demo_share, self.now, self.now)

    @override_settings(TINKOFF_TOKEN="")
    def test_tinvest_candles_without_token(self):
        with self.assertRaises(TinvestError):
            get_candles(self.tinvest_share, self.now, self.now)


@override_settings(TINKOFF_TOKEN="")
class AddSharesFromMoexTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("add_shares", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    @mock.patch("dashboard.services.moex.call", return_value=BOARD)
    def test_import_without_token_uses_moex(self, call):
        output = self.run_command()
        self.assertIn("MOEX ISS", output)
        self.assertIn("Добавлено: 2", output)
        sber = Share.objects.get(ticker="SBER")
        self.assertEqual(sber.figi, "MOEX-SBER")
        self.assertEqual(sber.isin, "RU0009029540")
        self.assertEqual(sber.last_price, 293.45)
        self.assertEqual(sber.source, Share.SOURCE_MOEX)
        # Тикер длиннее 10 символов пропускается
        self.assertFalse(Share.objects.filter(ticker="LONGTICKER12").exists())

        # Повторный запуск идемпотентен
        self.assertIn("Добавлено: 0, обновлено: 2", self.run_command())
        self.assertEqual(Share.objects.count(), 2)

    @mock.patch("dashboard.services.moex.call", return_value=BOARD)
    def test_moex_does_not_duplicate_tinvest_share(self, call):
        make_share("BBG004730N88", "SBER")
        self.run_command("--source", "moex")
        self.assertEqual(Share.objects.filter(ticker="SBER").count(), 1)
        self.assertEqual(Share.objects.get(ticker="SBER").figi, "BBG004730N88")

    @mock.patch("dashboard.services.tinvest.get_shares")
    @mock.patch("dashboard.services.moex.call", return_value=BOARD)
    def test_tinvest_upgrades_moex_share(self, call, tinvest_shares):
        self.run_command("--source", "moex")
        sber = Share.objects.get(ticker="SBER")
        user = get_user_model().objects.create_user("x@x.ru", "x@x.ru", "pw")
        PortfolioPosition.objects.create(
            portfolio=Portfolio.objects.create(user=user), share=sber, quantity=1, average_price=1
        )
        tinvest_shares.return_value = [
            {"figi": "BBG004730N88", "uid": "real-uid", "ticker": "SBER", "name": "Сбер Банк",
             "isin": "RU0009029540", "currency": "rub"},
        ]
        self.run_command("--source", "tinvest")
        sber.refresh_from_db()
        self.assertEqual((sber.figi, sber.uid), ("BBG004730N88", "real-uid"))
        self.assertEqual(sber.positions.count(), 1)
        self.assertEqual(Share.objects.filter(ticker="SBER").count(), 1)
