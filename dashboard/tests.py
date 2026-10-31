from datetime import datetime, timezone as dt_timezone
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import PortfolioPosition, Share
from dashboard.services.tinvest import TinvestError, quotation_to_float
from dashboard.tasks import update_last_price

User = get_user_model()


def create_apple():
    return Share.objects.create(
        figi="BBG000B9XRY4",
        isin="US0378331005",
        name="Apple",
        ticker="AAPL",
        currency="usd",
        uid="a9eb4238-eba9-488c-b102-b6140fd08e38",
        last_price=100.50,
        is_trend_high=True,
    )


class DashboardTests(APITestCase):
    def setUp(self) -> None:
        self.apple_share = create_apple()
        self.user = User.objects.create_user("api@example.com", "api@example.com", "pw")
        self.missing_id = self.apple_share.id + 1000

        self.second_company = {
            "figi": "BBG000B9XRY5",
            "isin": "US0378331004",
            "name": "Company_test",
            "ticker": "TESTTEST",
            "currency": "usd",
            "uid": "a9eb4238-eba9-488c-b102-b6140fd08e39",
        }

    def test_share_list_html(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_list(self):
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        apple_share = response.json().get("results")[0]
        self.assertEqual(apple_share["id"], self.apple_share.id)
        self.assertEqual(apple_share["figi"], self.apple_share.figi)
        self.assertEqual(apple_share["isin"], self.apple_share.isin)
        self.assertEqual(apple_share["name"], self.apple_share.name)
        self.assertEqual(apple_share["ticker"], self.apple_share.ticker)
        self.assertEqual(apple_share["currency"], self.apple_share.currency)
        self.assertEqual(apple_share["uid"], self.apple_share.uid)

    def test_share_search(self):
        response = self.client.get("/api/v1/shares/", {"search": "app"})
        self.assertEqual(len(response.data["results"]), 1)
        # Спецсимволы регулярных выражений больше не ломают запрос
        response = self.client.get("/api/v1/shares/", {"search": "("})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_share_search_cyrillic(self):
        Share.objects.filter(id=self.apple_share.id).update(name="Сбер Банк")
        response = self.client.get("/api/v1/shares/", {"search": "сбер"})
        self.assertEqual(len(response.data["results"]), 1)

    def test_share_detail(self):
        response = self.client.get(f"/api/v1/shares/{self.apple_share.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_detail_invalid(self):
        response = self.client.get(f"/api/v1/shares/{self.missing_id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_share_update(self):
        self.client.force_authenticate(self.user)
        response = self.client.put(
            f"/api/v1/shares/{self.apple_share.id}/",
            {
                "figi": self.apple_share.figi,
                "isin": self.apple_share.isin,
                "name": f"{self.apple_share.name}_test",
                "ticker": self.apple_share.ticker,
                "currency": self.apple_share.currency,
                "uid": self.apple_share.uid,
                "last_price": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["figi"], self.apple_share.figi)
        self.assertEqual(body["name"], f"{self.apple_share.name}_test")
        # Рыночные данные через API не меняются
        self.assertEqual(body["last_price"], self.apple_share.last_price)

    def test_share_update_invalid(self):
        self.client.force_authenticate(self.user)
        response = self.client.put(
            f"/api/v1/shares/{self.apple_share.id}/",
            {
                "figi": self.apple_share.figi,
                "name": f"{self.apple_share.name}_test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_create(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/shares/", self.second_company, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body["figi"], self.second_company["figi"])
        self.assertEqual(body["name"], self.second_company["name"])
        self.assertEqual(body["ticker"], self.second_company["ticker"])

        response = self.client.get("/api/v1/shares/")
        self.assertEqual(len(response.data["results"]), 2)

    def test_share_create_duplicate_uid(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/shares/",
            {**self.second_company, "uid": self.apple_share.uid},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_create_invalid(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/shares/", {"figi": "BBG000B9XRY5"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_delete(self):
        self.client.force_authenticate(self.user)
        response = self.client.delete(f"/api/v1/shares/{self.apple_share.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_share_delete_invalid(self):
        self.client.force_authenticate(self.user)
        response = self.client.delete(f"/api/v1/shares/{self.missing_id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_modify(self):
        url = f"/api/v1/shares/{self.apple_share.id}/"
        self.assertEqual(
            self.client.post("/api/v1/shares/", self.second_company).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(url, {"name": "x"}).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Share.objects.filter(id=self.apple_share.id).exists())


class ShareHtmlViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.share = create_apple()

    def test_detail_not_found(self):
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id + 1]))
        self.assertEqual(response.status_code, 404)

    @override_settings(TINKOFF_TOKEN="")
    def test_detail_without_api(self):
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Исторические данные сейчас недоступны")

    @mock.patch("dashboard.services.market_data.get_day_candles")
    def test_detail_with_graph(self, get_day_candles):
        get_day_candles.return_value = [(datetime(2026, 10, 1, tzinfo=dt_timezone.utc), 10.5)]
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "plotly-graph-div")
        # Повторный просмотр берёт свечи из кэша
        self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        get_day_candles.assert_called_once()

    def test_create_requires_login(self):
        response = self.client.get(reverse("dashboard:create"))
        self.assertRedirects(
            response, f"{reverse('user:auth')}?next={reverse('dashboard:create')}"
        )

    def test_create_html(self):
        user = User.objects.create_user("u@example.com", "u@example.com", "pw")
        self.client.force_login(user)
        response = self.client.post(
            reverse("dashboard:create"),
            {
                "figi": "F2",
                "isin": "I2",
                "name": "Second",
                "ticker": "SEC",
                "currency": "rub",
                "uid": "uid-2",
            },
        )
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertTrue(Share.objects.filter(ticker="SEC").exists())


@override_settings(TINKOFF_TOKEN="")
class PortfolioTests(TestCase):
    def setUp(self):
        self.share = create_apple()
        self.user = User.objects.create_user("p@example.com", "p@example.com", "pw")
        self.client.force_login(self.user)

    def buy(self, quantity, price, share=None):
        share = share or self.share
        return self.client.post(
            reverse("dashboard:portfolio_buy", args=[share.id]),
            {"quantity": quantity, "price": price},
        )

    def test_portfolio_url(self):
        self.assertEqual(reverse("dashboard:portfolio"), "/portfolio/")

    def test_portfolio_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:portfolio"))
        self.assertRedirects(
            response, f"{reverse('user:auth')}?next={reverse('dashboard:portfolio')}"
        )
        self.assertEqual(self.buy(1, 10).status_code, 302)
        self.assertFalse(PortfolioPosition.objects.exists())

    def test_empty_portfolio(self):
        response = self.client.get(reverse("dashboard:portfolio"))
        self.assertContains(response, "В портфеле пока нет акций")

    def test_detail_has_buy_form(self):
        response = self.client.get(reverse("dashboard:detail", args=[self.share.id]))
        self.assertContains(response, reverse("dashboard:portfolio_buy", args=[self.share.id]))
        self.assertContains(response, 'value="100.5"')

    def test_buy_and_average_price(self):
        response = self.buy(10, 100)
        self.assertRedirects(response, reverse("dashboard:portfolio"))
        self.buy(30, 120)

        position = PortfolioPosition.objects.get()
        self.assertEqual(position.portfolio.user, self.user)
        self.assertEqual(position.quantity, 40)
        self.assertAlmostEqual(position.average_price, 115.0)

        response = self.client.get(reverse("dashboard:portfolio"))
        self.assertContains(response, "AAPL")
        self.assertEqual(response.context["total_quantity"], 40)
        self.assertAlmostEqual(response.context["total_cost"], 4600.0)
        self.assertAlmostEqual(response.context["total_value"], 40 * 100.5)
        self.assertFalse(response.context["has_unpriced"])

    def test_unpriced_share_not_in_value(self):
        other = Share.objects.create(
            figi="F2", isin="I2", name="Zeta", ticker="ZZZ", currency="rub", uid="U2"
        )
        self.buy(1, 100)
        self.buy(5, 10, share=other)
        response = self.client.get(reverse("dashboard:portfolio"))
        self.assertEqual(response.context["total_quantity"], 6)
        self.assertAlmostEqual(response.context["total_value"], 100.5)
        self.assertTrue(response.context["has_unpriced"])

    def test_invalid_buy(self):
        for quantity, price in ((0, 10), (-1, 10), (1, 0), ("abc", 10)):
            response = self.buy(quantity, price)
            self.assertEqual(response.status_code, 400)
        self.assertFalse(PortfolioPosition.objects.exists())

    def test_buy_missing_share(self):
        response = self.client.post(
            reverse("dashboard:portfolio_buy", args=[self.share.id + 1000]),
            {"quantity": 1, "price": 1},
        )
        self.assertEqual(response.status_code, 404)

    def test_portfolios_are_separate(self):
        self.buy(3, 100)
        other = User.objects.create_user("o@example.com", "o@example.com", "pw")
        self.client.force_login(other)
        response = self.client.get(reverse("dashboard:portfolio"))
        self.assertContains(response, "В портфеле пока нет акций")


@override_settings(TINKOFF_TOKEN="test-token")
class UpdateLastPriceTests(TestCase):
    def setUp(self):
        self.share = create_apple()

    @mock.patch("dashboard.services.market_data.get_last_prices")
    def test_updates_price_trend_and_time(self, get_last_prices):
        get_last_prices.return_value = {self.share.figi: (99.25, None)}
        self.assertEqual(update_last_price(), 1)
        self.share.refresh_from_db()
        self.assertEqual(self.share.last_price, 99.25)
        self.assertIs(self.share.is_trend_high, False)
        self.assertIsNotNone(self.share.updated_at)

        get_last_prices.return_value = {self.share.figi: (99.25, None)}
        update_last_price()
        self.share.refresh_from_db()
        # Цена не изменилась — тренд сохраняется
        self.assertIs(self.share.is_trend_high, False)

    @mock.patch("dashboard.services.market_data.get_last_prices")
    def test_first_price_has_unknown_trend(self, get_last_prices):
        Share.objects.filter(id=self.share.id).update(last_price=None, is_trend_high=None)
        get_last_prices.return_value = {self.share.figi: (5.0, None)}
        update_last_price()
        self.share.refresh_from_db()
        self.assertEqual(self.share.last_price, 5.0)
        self.assertIsNone(self.share.is_trend_high)

    @mock.patch("dashboard.services.market_data.get_last_prices")
    def test_api_error_keeps_data(self, get_last_prices):
        get_last_prices.side_effect = TinvestError("down")
        self.assertEqual(update_last_price(), 0)
        self.share.refresh_from_db()
        self.assertEqual(self.share.last_price, 100.50)


class TinvestTests(TestCase):
    def test_quotation_keeps_fraction(self):
        self.assertEqual(quotation_to_float({"units": "245", "nano": 970000000}), 245.97)
        self.assertEqual(quotation_to_float({"nano": 34500000}), 0.0345)
        self.assertIsNone(quotation_to_float(None))

    @mock.patch("dashboard.services.tinvest.get_shares")
    def test_add_shares_is_idempotent(self, get_shares):
        instrument = {
            "figi": "F1",
            "isin": "I1",
            "name": "Old name",
            "ticker": "T1",
            "currency": "rub",
            "uid": "U1",
        }
        get_shares.return_value = [instrument, {**instrument, "figi": "F9", "ticker": "TOO_LONG_TICKER"}]
        call_command("add_shares", "--source", "tinvest", stdout=StringIO(), stderr=StringIO())
        get_shares.return_value = [{**instrument, "name": "New name"}]
        call_command("add_shares", "--source", "tinvest", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Share.objects.count(), 1)
        self.assertEqual(Share.objects.get(figi="F1").name, "New name")

    @override_settings(TINKOFF_TOKEN="")
    def test_add_shares_without_token(self):
        with self.assertRaises(CommandError):
            call_command("add_shares", "--source", "tinvest", stdout=StringIO())
