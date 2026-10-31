import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import PriceSnapshot, Share, SimulatedTrade, SimulationRun, Strategy
from dashboard.services.simulator import SimulationError, run_simulation, simulate

User = get_user_model()
START = timezone.now() - timedelta(days=30)


def points(*prices):
    return [(START + timedelta(hours=i), price) for i, price in enumerate(prices)]


def strategy(kind=Strategy.LEVELS, **params):
    defaults = {"initial_capital": 1000, "commission_percent": 0}
    defaults.update(params)
    return Strategy(kind=kind, name="Тест", **defaults)


class SimulateLevelsTests(TestCase):
    def test_round_trips_and_open_position(self):
        result = simulate(
            strategy(buy_below=90, sell_above=110), points(100, 95, 89, 100, 111, 85, 80)
        )
        sides = [(t.side, t.price, t.quantity) for t in result.trades]
        self.assertEqual(sides, [("buy", 89, 11), ("sell", 111, 11), ("buy", 85, 14)])
        self.assertAlmostEqual(result.trades[1].profit, 242)
        self.assertIsNone(result.trades[0].profit)
        self.assertEqual(result.final_quantity, 14)
        self.assertAlmostEqual(result.final_cash, 52)
        self.assertAlmostEqual(result.final_value, 52 + 14 * 80)
        self.assertAlmostEqual(result.return_percent, 17.2)
        self.assertAlmostEqual(result.benchmark_return_percent, -20)
        self.assertEqual(len(result.equity), 7)

    def test_commission(self):
        result = simulate(
            strategy(buy_below=90, sell_above=110, commission_percent=1), points(89, 111)
        )
        buy, sell = result.trades
        self.assertEqual(buy.quantity, 11)  # 1000 // (89 * 1.01)
        self.assertAlmostEqual(buy.commission, 9.79)
        self.assertAlmostEqual(buy.cash_after, 11.21)
        self.assertAlmostEqual(sell.commission, 12.21)
        self.assertAlmostEqual(sell.cash_after, 1220)
        self.assertAlmostEqual(sell.profit, 220)

    def test_stop_loss(self):
        result = simulate(
            strategy(buy_below=90, sell_above=200, stop_loss_percent=10), points(89, 85, 80.1)
        )
        self.assertEqual([t.side for t in result.trades], ["buy", "sell"])
        self.assertIn("Стоп-лосс", result.trades[1].reason)
        self.assertLess(result.trades[1].profit, 0)

    def test_not_enough_money(self):
        result = simulate(strategy(buy_below=90, sell_above=110, initial_capital=50), points(89, 120))
        self.assertEqual(result.trades, [])
        self.assertAlmostEqual(result.final_value, 50)
        self.assertAlmostEqual(result.return_percent, 0)

    def test_max_drawdown(self):
        result = simulate(strategy(buy_below=90, sell_above=500), points(89, 44.5, 89))
        # Капитал: 1000 -> 21 + 11 * 44.5 = 510.5
        self.assertAlmostEqual(result.max_drawdown_percent, 48.95)

    def test_needs_two_points(self):
        with self.assertRaises(SimulationError):
            simulate(strategy(buy_below=90, sell_above=110), points(100))


class SimulateDipAndSmaTests(TestCase):
    def test_dip_with_take_profit(self):
        result = simulate(
            strategy(Strategy.DIP, buy_drop_percent=10, take_profit_percent=5),
            points(100, 105, 94.5, 99, 99.3, 95, 89.37),
        )
        self.assertEqual(
            [(t.side, t.price) for t in result.trades],
            [("buy", 94.5), ("sell", 99.3), ("buy", 89.37)],
        )
        self.assertIn("105.00", result.trades[0].reason)
        # После продажи максимум отсчитывается заново от цены продажи
        self.assertIn("99.30", result.trades[2].reason)

    def test_sma_crossover(self):
        result = simulate(
            strategy(Strategy.SMA, short_window=2, long_window=3), points(10, 10, 10, 13, 13, 7, 7)
        )
        self.assertEqual([(t.side, t.price) for t in result.trades], [("buy", 13), ("sell", 7)])
        self.assertIn("снизу вверх", result.trades[0].reason)
        self.assertIn("сверху вниз", result.trades[1].reason)


class StrategyValidationTests(TestCase):
    def assert_invalid(self, field, **params):
        with self.assertRaises(ValidationError) as ctx:
            strategy(**params).clean()
        self.assertIn(field, ctx.exception.message_dict)

    def test_rules(self):
        self.assert_invalid("buy_below", kind=Strategy.LEVELS, sell_above=10)
        self.assert_invalid("sell_above", kind=Strategy.LEVELS, buy_below=10, sell_above=10)
        self.assert_invalid("take_profit_percent", kind=Strategy.DIP, buy_drop_percent=5)
        self.assert_invalid("buy_drop_percent", kind=Strategy.DIP, buy_drop_percent=150, take_profit_percent=5)
        self.assert_invalid("long_window", kind=Strategy.SMA, short_window=5, long_window=5)
        self.assert_invalid("stop_loss_percent", buy_below=1, sell_above=2, stop_loss_percent=0)
        self.assert_invalid("initial_capital", buy_below=1, sell_above=2, initial_capital=0)
        strategy(buy_below=1, sell_above=2).clean()

    def test_rules_text(self):
        s = strategy(Strategy.DIP, buy_drop_percent=5, take_profit_percent=8, stop_loss_percent=3)
        self.assertEqual(len(s.rules), 3)
        self.assertIn("5%", s.rules[0])


class StrategyViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("s@example.com", "s@example.com", "pw")
        self.client.force_login(self.user)
        self.share = Share.objects.create(
            figi="MOEX-SBER", isin="RU0009029540", name="Сбербанк", ticker="SBER",
            currency="rub", uid="moex-sber",
        )
        PriceSnapshot.objects.bulk_create(
            PriceSnapshot(share=self.share, price=price, time=time)
            for time, price in points(100, 95, 89, 100, 111, 85, 80)
        )

    def create(self, **data):
        payload = {
            "name": "Уровни", "share": self.share.id, "kind": "levels",
            "buy_below": 90, "sell_above": 110, "initial_capital": 1000, "commission_percent": 0,
        }
        payload.update(data)
        return self.client.post(reverse("dashboard:strategy_create"), payload)

    def test_requires_login(self):
        self.client.logout()
        for url in (reverse("dashboard:strategies"), reverse("dashboard:strategy_create")):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_empty_list(self):
        self.assertContains(self.client.get(reverse("dashboard:strategies")), "Стратегий пока нет")

    def test_create_form_preselects_share(self):
        response = self.client.get(reverse("dashboard:strategy_create"), {"share": self.share.id})
        self.assertEqual(response.context["form"].initial["share"], str(self.share.id))

    def test_create_and_other_kind_params_dropped(self):
        response = self.create(buy_drop_percent=5, short_window=3)
        created = Strategy.objects.get()
        self.assertRedirects(response, reverse("dashboard:strategy", args=[created.id]))
        self.assertEqual(created.user, self.user)
        self.assertIsNone(created.buy_drop_percent)
        self.assertIsNone(created.short_window)

    def test_create_invalid(self):
        response = self.create(kind="dip", buy_drop_percent="", take_profit_percent="")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Обязательно для выбранного типа", status_code=400)
        self.assertFalse(Strategy.objects.exists())

    def test_run_simulation_and_journal(self):
        self.create()
        created = Strategy.objects.get()
        response = self.client.post(reverse("dashboard:strategy_run", args=[created.id]), {"period": "all"})
        run = SimulationRun.objects.get()
        self.assertRedirects(response, reverse("dashboard:simulation_run", args=[run.id]))
        self.assertEqual(run.trades_count, 3)
        self.assertEqual(run.points_count, 7)
        self.assertAlmostEqual(run.return_percent, 17.2)
        self.assertEqual(len(run.equity_curve), 7)
        self.assertEqual(SimulatedTrade.objects.filter(run=run).count(), 3)

        page = self.client.get(reverse("dashboard:simulation_run", args=[run.id]))
        self.assertContains(page, "Журнал виртуальных сделок")
        self.assertContains(page, "+17,20%")
        self.assertContains(page, "прибыльных продаж 1 из 1")
        html = page.content.decode()
        start = html.index('id="run-data"')
        chart = json.loads(html[html.index(">", start) + 1 : html.index("</script>", start)])
        self.assertEqual(len(chart["buys"]), 2)
        self.assertEqual(len(chart["sells"]), 1)
        self.assertEqual(len(chart["equity"]), 7)

        listing = self.client.get(reverse("dashboard:strategies"))
        self.assertContains(listing, "+17,20%")
        self.assertContains(listing, "-20,00%")

    def test_run_without_history(self):
        PriceSnapshot.objects.all().delete()
        self.create()
        created = Strategy.objects.get()
        response = self.client.post(
            reverse("dashboard:strategy_run", args=[created.id]), {"period": "all"}, follow=True
        )
        self.assertContains(response, "load_price_history --ticker SBER")
        self.assertFalse(SimulationRun.objects.exists())

    def test_foreign_strategy(self):
        stranger = User.objects.create_user("x@example.com", "x@example.com", "pw")
        foreign = Strategy.objects.create(
            user=stranger, share=self.share, name="Чужая", kind="levels", buy_below=90, sell_above=110
        )
        run = run_simulation(foreign, "all")
        for url in (
            reverse("dashboard:strategy", args=[foreign.id]),
            reverse("dashboard:simulation_run", args=[run.id]),
        ):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("dashboard:strategy_run", args=[foreign.id]), {"period": "all"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("dashboard:strategy_delete", args=[foreign.id])).status_code, 404
        )
        self.assertEqual(SimulationRun.objects.count(), 1)

    def test_delete(self):
        self.create()
        created = Strategy.objects.get()
        run_simulation(created, "all")
        response = self.client.post(reverse("dashboard:strategy_delete", args=[created.id]))
        self.assertRedirects(response, reverse("dashboard:strategies"))
        self.assertFalse(SimulationRun.objects.exists())
        self.assertFalse(SimulatedTrade.objects.exists())

    @mock.patch("dashboard.services.moex.get_day_candles", return_value=[])
    def test_detail_page_link(self, get_day_candles):
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        self.assertContains(response, f"{reverse('dashboard:strategy_create')}?share={self.share.id}")
