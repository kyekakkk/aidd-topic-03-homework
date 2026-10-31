import json
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.models import PriceAlert, PriceSnapshot, Share, Watchlist, WatchlistItem
from dashboard.services.history import (
    check_alerts,
    daily_changes,
    market_changes,
    period_start,
    price_series,
    record_snapshots,
    share_stats,
)
from dashboard.tasks import update_last_price

User = get_user_model()


def make_share(ticker="AAPL", price=100.0):
    return Share.objects.create(
        figi=f"FIGI-{ticker}",
        isin=f"ISIN-{ticker}",
        name=f"Company {ticker}",
        ticker=ticker,
        currency="usd",
        uid=f"uid-{ticker}",
        last_price=price,
    )


def add_history(share, prices, start, step=timedelta(hours=1)):
    PriceSnapshot.objects.bulk_create(
        PriceSnapshot(share=share, price=price, time=start + step * i)
        for i, price in enumerate(prices)
    )


class PriceAlertModelTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("a@example.com", "a@example.com", "pw")
        watchlist = Watchlist.objects.create(user=user, name="Тест")
        self.item = WatchlistItem.objects.create(watchlist=watchlist, share=make_share())

    def test_above_and_below(self):
        above = PriceAlert(item=self.item, direction=PriceAlert.ABOVE, target_price=110)
        below = PriceAlert(item=self.item, direction=PriceAlert.BELOW, target_price=90)
        self.assertFalse(above.is_reached(109.99))
        self.assertTrue(above.is_reached(110))
        self.assertFalse(below.is_reached(90.01))
        self.assertTrue(below.is_reached(90))
        self.assertFalse(above.is_reached(None))

    def test_check_price_triggers_once(self):
        alert = PriceAlert(item=self.item, direction=PriceAlert.ABOVE, target_price=110)
        first = timezone.now()
        self.assertTrue(alert.check_price(111, first))
        self.assertFalse(alert.check_price(150, first + timedelta(hours=1)))
        self.assertEqual(alert.triggered_at, first)
        self.assertEqual(alert.triggered_price, 111)


class HistoryServiceTests(TestCase):
    def setUp(self):
        self.share = make_share()
        self.now = timezone.now()

    def test_record_snapshots_skips_duplicates(self):
        quote_time = self.now - timedelta(minutes=1)
        prices = {self.share.figi: (101.5, quote_time)}
        record_snapshots([self.share], prices, self.now)
        record_snapshots([self.share], prices, self.now)
        self.assertEqual(PriceSnapshot.objects.count(), 1)
        snapshot = PriceSnapshot.objects.get()
        self.assertEqual(snapshot.price, 101.5)
        self.assertEqual(snapshot.time, quote_time)

    def test_record_snapshot_without_quote_time_uses_now(self):
        record_snapshots([self.share], {self.share.figi: (99.0, None)}, self.now)
        self.assertEqual(PriceSnapshot.objects.get().time, self.now)

    def test_share_stats(self):
        add_history(self.share, [100, 120, 80, 110], self.now - timedelta(hours=4))
        stats = share_stats(self.share, None)
        self.assertEqual(stats["first"].price, 100)
        self.assertEqual(stats["last"].price, 110)
        self.assertEqual(stats["min"], 80)
        self.assertEqual(stats["max"], 120)
        self.assertAlmostEqual(stats["change"], 10)
        self.assertAlmostEqual(stats["change_percent"], 10)
        self.assertEqual(stats["count"], 4)

    def test_share_stats_respects_period(self):
        add_history(self.share, [50], self.now - timedelta(days=10))
        add_history(self.share, [100, 105], self.now - timedelta(hours=2))
        stats = share_stats(self.share, period_start("7d", self.now))
        self.assertEqual(stats["first"].price, 100)
        self.assertAlmostEqual(stats["change_percent"], 5)
        self.assertIsNone(share_stats(self.share, self.now + timedelta(days=1)))

    def test_price_series_is_thinned_keeping_last_point(self):
        add_history(self.share, list(range(1, 1001)), self.now - timedelta(hours=1000))
        points = price_series(self.share, None, max_points=100)
        self.assertEqual(len(points), 100)
        self.assertEqual(points[0][1], 1)
        self.assertEqual(points[-1][1], 1000)

    def test_daily_changes(self):
        day = timezone.localtime(self.now).replace(hour=10, minute=0, second=0, microsecond=0)
        add_history(self.share, [100, 104, 102], day - timedelta(days=1), step=timedelta(hours=2))
        add_history(self.share, [110, 99, 105.06], day, step=timedelta(hours=2))
        days = daily_changes(self.share, None)
        self.assertEqual(len(days), 2)
        today, yesterday = days
        self.assertEqual(yesterday["close"], 102)
        self.assertIsNone(yesterday["change"])
        self.assertEqual(today["close"], 105.06)
        self.assertEqual(today["min"], 99)
        self.assertEqual(today["max"], 110)
        self.assertAlmostEqual(today["change"], 3.06)
        self.assertAlmostEqual(today["change_percent"], 3)

    def test_market_changes_sorted_by_percent(self):
        loser = make_share("LOSE")
        flat = make_share("FLAT")
        start = self.now - timedelta(hours=3)
        add_history(self.share, [100, 120], start)
        add_history(loser, [200, 150], start)
        add_history(flat, [10, 10], start)
        make_share("NOHI")  # без истории — не попадает в таблицу
        add_history(make_share("ONE"), [50], start)  # одна точка — тоже

        rows = market_changes(None)
        self.assertEqual([row["share"].ticker for row in rows], ["AAPL", "FLAT", "LOSE"])
        self.assertAlmostEqual(rows[0]["change_percent"], 20)
        self.assertAlmostEqual(rows[2]["change"], -50)

    def test_check_alerts(self):
        user = User.objects.create_user("c@example.com", "c@example.com", "pw")
        item = WatchlistItem.objects.create(
            watchlist=Watchlist.objects.create(user=user, name="L"), share=self.share
        )
        hit = PriceAlert.objects.create(item=item, direction=PriceAlert.ABOVE, target_price=105)
        miss = PriceAlert.objects.create(item=item, direction=PriceAlert.BELOW, target_price=90)

        triggered = check_alerts({self.share.id: 106}, self.now)
        self.assertEqual(triggered, [hit])
        hit.refresh_from_db()
        miss.refresh_from_db()
        self.assertEqual(hit.triggered_price, 106)
        self.assertIsNone(miss.triggered_at)


@override_settings(TINKOFF_TOKEN="test-token")
class UpdateLastPriceHistoryTests(TestCase):
    @mock.patch("dashboard.services.market_data.get_last_prices")
    def test_task_records_history_and_triggers_alerts(self, get_last_prices):
        share = make_share(price=100)
        user = User.objects.create_user("t@example.com", "t@example.com", "pw")
        item = WatchlistItem.objects.create(
            watchlist=Watchlist.objects.create(user=user, name="L"), share=share
        )
        alert = PriceAlert.objects.create(item=item, direction=PriceAlert.BELOW, target_price=95)

        quote_time = timezone.now()
        get_last_prices.return_value = {share.figi: (94.5, quote_time)}
        update_last_price()

        snapshot = PriceSnapshot.objects.get(share=share)
        self.assertEqual((snapshot.price, snapshot.time), (94.5, quote_time))
        alert.refresh_from_db()
        self.assertEqual(alert.triggered_price, 94.5)


@override_settings(TINKOFF_TOKEN="")
class WatchlistViewsTests(TestCase):
    def setUp(self):
        self.share = make_share(price=100)
        self.user = User.objects.create_user("w@example.com", "w@example.com", "pw")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        for url in (
            reverse("dashboard:watchlists"),
            reverse("dashboard:watchlist", args=[1]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("user:auth"), response["Location"])
        response = self.client.post(reverse("dashboard:watchlist_add", args=[self.share.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Watchlist.objects.exists())

    def test_empty_index(self):
        response = self.client.get(reverse("dashboard:watchlists"))
        self.assertContains(response, "Списков пока нет")

    def test_create_watchlist(self):
        response = self.client.post(reverse("dashboard:watchlists"), {"name": "Дивиденды"})
        watchlist = Watchlist.objects.get()
        self.assertRedirects(response, reverse("dashboard:watchlist", args=[watchlist.id]))
        self.assertEqual(watchlist.user, self.user)

        response = self.client.post(reverse("dashboard:watchlists"), {"name": "дивиденды"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "уже есть", status_code=400)
        self.assertEqual(Watchlist.objects.count(), 1)

    def test_add_share_creates_default_list(self):
        response = self.client.post(reverse("dashboard:watchlist_add", args=[self.share.id]))
        watchlist = Watchlist.objects.get(user=self.user)
        self.assertEqual(watchlist.name, "Избранное")
        self.assertRedirects(response, reverse("dashboard:watchlist", args=[watchlist.id]))
        self.assertTrue(watchlist.items.filter(share=self.share).exists())

        # Повторное добавление не создаёт дубликат
        self.client.post(
            reverse("dashboard:watchlist_add", args=[self.share.id]),
            {"watchlist": watchlist.id},
        )
        self.assertEqual(WatchlistItem.objects.count(), 1)

    def test_detail_page_shows_watchlist_form_and_history_link(self):
        Watchlist.objects.create(user=self.user, name="Мой список")
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        self.assertContains(response, reverse("dashboard:watchlist_add", args=[self.share.id]))
        self.assertContains(response, "Мой список")
        self.assertContains(response, reverse("dashboard:history", args=[self.share.id]))

    def test_cannot_use_foreign_watchlist(self):
        stranger = User.objects.create_user("s@example.com", "s@example.com", "pw")
        foreign = Watchlist.objects.create(user=stranger, name="Чужой")
        item = WatchlistItem.objects.create(watchlist=foreign, share=self.share)

        self.assertEqual(
            self.client.get(reverse("dashboard:watchlist", args=[foreign.id])).status_code, 404
        )
        self.client.post(
            reverse("dashboard:watchlist_add", args=[self.share.id]),
            {"watchlist": foreign.id},
        )
        self.assertEqual(foreign.items.count(), 1)
        self.assertEqual(
            self.client.post(reverse("dashboard:alert_create", args=[item.id]),
                             {"direction": "above", "target_price": 1}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("dashboard:watchlist_delete", args=[foreign.id])).status_code,
            404,
        )
        self.assertTrue(Watchlist.objects.filter(id=foreign.id).exists())

    def test_alert_lifecycle(self):
        watchlist = Watchlist.objects.create(user=self.user, name="L")
        item = WatchlistItem.objects.create(watchlist=watchlist, share=self.share)
        url = reverse("dashboard:alert_create", args=[item.id])

        self.client.post(url, {"direction": "above", "target_price": 120})
        pending = PriceAlert.objects.get()
        self.assertFalse(pending.is_triggered)

        # Уровень, уже достигнутый текущей ценой, фиксируется сразу
        response = self.client.post(url, {"direction": "below", "target_price": 105}, follow=True)
        reached = PriceAlert.objects.get(target_price=105)
        self.assertTrue(reached.is_triggered)
        self.assertEqual(reached.triggered_price, 100)
        self.assertContains(response, "уже достигнут")
        self.assertContains(response, "Ожидание")

        index = self.client.get(reverse("dashboard:watchlists"))
        self.assertContains(index, "Последние достигнутые уровни")

        self.client.post(reverse("dashboard:alert_delete", args=[pending.id]))
        self.assertEqual(PriceAlert.objects.count(), 1)

    def test_invalid_alert(self):
        item = WatchlistItem.objects.create(
            watchlist=Watchlist.objects.create(user=self.user, name="L"), share=self.share
        )
        url = reverse("dashboard:alert_create", args=[item.id])
        for data in (
            {"direction": "above", "target_price": 0},
            {"direction": "above", "target_price": "abc"},
            {"direction": "sideways", "target_price": 10},
        ):
            self.client.post(url, data)
        self.assertFalse(PriceAlert.objects.exists())

    def test_delete_item_and_watchlist(self):
        watchlist = Watchlist.objects.create(user=self.user, name="L")
        item = WatchlistItem.objects.create(watchlist=watchlist, share=self.share)
        PriceAlert.objects.create(item=item, direction="above", target_price=200)

        self.client.post(reverse("dashboard:watchlist_item_delete", args=[item.id]))
        self.assertFalse(WatchlistItem.objects.exists())
        self.assertFalse(PriceAlert.objects.exists())

        response = self.client.post(reverse("dashboard:watchlist_delete", args=[watchlist.id]))
        self.assertRedirects(response, reverse("dashboard:watchlists"))
        self.assertFalse(Watchlist.objects.exists())

    def test_get_not_allowed_for_actions(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:watchlist_add", args=[self.share.id])).status_code,
            405,
        )


@override_settings(TINKOFF_TOKEN="")
class HistoryViewsTests(TestCase):
    def setUp(self):
        self.share = make_share()
        self.now = timezone.now()

    def test_history_without_data(self):
        response = self.client.get(reverse("dashboard:history", args=[self.share.id]))
        self.assertContains(response, "истории цен нет")

    def test_history_not_found(self):
        response = self.client.get(reverse("dashboard:history", args=[self.share.id + 1]))
        self.assertEqual(response.status_code, 404)

    def test_history_with_chart(self):
        add_history(self.share, [50], self.now - timedelta(days=20))
        add_history(self.share, [100, 110], self.now - timedelta(hours=3))

        response = self.client.get(reverse("dashboard:history", args=[self.share.id]), {"period": "7d"})
        self.assertEqual(response.context["period"], "7d")
        self.assertAlmostEqual(response.context["stats"]["change_percent"], 10)
        self.assertEqual(response.context["chart"]["values"], [100, 110])
        self.assertContains(response, 'id="price-chart"')
        self.assertContains(response, "chart.js@4.4.1")
        self.assertContains(response, "+10,00%")

        response = self.client.get(reverse("dashboard:history", args=[self.share.id]), {"period": "all"})
        self.assertEqual(response.context["chart"]["values"], [50, 100, 110])
        self.assertAlmostEqual(response.context["stats"]["change_percent"], 120)

    def test_unknown_period_falls_back_to_default(self):
        response = self.client.get(reverse("dashboard:history", args=[self.share.id]), {"period": "x"})
        self.assertEqual(response.context["period"], "30d")

    def test_chart_data_is_valid_json(self):
        add_history(self.share, [1, 2, 3], self.now - timedelta(hours=3))
        response = self.client.get(reverse("dashboard:history", args=[self.share.id]))
        html = response.content.decode()
        start = html.index('id="chart-data"')
        raw = html[html.index(">", start) + 1 : html.index("</script>", start)]
        self.assertEqual(json.loads(raw)["values"], [1, 2, 3])

    def test_dynamics(self):
        loser = make_share("LOSE")
        start = self.now - timedelta(hours=2)
        add_history(self.share, [100, 150], start)
        add_history(loser, [100, 75], start)

        response = self.client.get(reverse("dashboard:dynamics"), {"period": "1d"})
        self.assertEqual([row["share"].ticker for row in response.context["rows"]], ["AAPL", "LOSE"])
        self.assertEqual(response.context["chart"]["values"], [50.0, -25.0])
        self.assertContains(response, "+50,00")
        self.assertContains(response, "-25,00")

    def test_dynamics_empty(self):
        response = self.client.get(reverse("dashboard:dynamics"))
        self.assertContains(response, "истории цен нет")

    def test_detail_shows_month_change(self):
        add_history(self.share, [100, 90], self.now - timedelta(hours=2))
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        self.assertContains(response, "Изменение за месяц")
        self.assertContains(response, "-10,00%")


class HistoryCommandsTests(TestCase):
    def test_seed_demo_history_only_touches_demo_shares(self):
        real = make_share("REAL")
        call_command("seed_demo_history", "--days", "2", "--points-per-day", "4", stdout=StringIO())
        self.assertFalse(real.price_history.exists())
        demo = Share.objects.filter(ticker__startswith="DEMO")
        self.assertEqual(demo.count(), 3)
        for share in demo:
            self.assertEqual(share.price_history.count(), 8)
            self.assertEqual(share.last_price, share.price_history.last().price)

        # Повторный запуск не дублирует историю
        call_command("seed_demo_history", "--days", "2", "--points-per-day", "4", stdout=StringIO())
        self.assertEqual(PriceSnapshot.objects.count(), 24)

    def test_seed_demo_history_validates_args(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_history", "--days", "0", stdout=StringIO())

    @mock.patch("dashboard.management.commands.load_price_history.get_candles")
    def test_load_price_history(self, get_candles):
        watched = make_share("WTCH")
        make_share("SKIP")
        user = User.objects.create_user("l@example.com", "l@example.com", "pw")
        WatchlistItem.objects.create(
            watchlist=Watchlist.objects.create(user=user, name="L"), share=watched
        )
        day = timezone.now() - timedelta(days=1)
        get_candles.return_value = [(day, 10.0), (day + timedelta(days=1), 11.0)]

        call_command("load_price_history", "--days", "30", stdout=StringIO())
        call_command("load_price_history", "--days", "30", stdout=StringIO())

        # По умолчанию — только наблюдаемые акции, без дубликатов
        get_candles.assert_called_with(watched, mock.ANY, mock.ANY)
        self.assertEqual(get_candles.call_count, 2)
        self.assertEqual(list(watched.price_history.values_list("price", flat=True)), [10.0, 11.0])

    def test_load_price_history_validates_days(self):
        with self.assertRaises(CommandError):
            call_command("load_price_history", "--days", "400", stdout=StringIO())

    @override_settings(TINKOFF_TOKEN="")
    def test_load_price_history_without_token(self):
        make_share("ANY")
        with self.assertRaises(CommandError):
            call_command("load_price_history", "--all", stdout=StringIO())
