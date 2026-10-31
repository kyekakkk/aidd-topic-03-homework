from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

STRONG_PASSWORD = "Xq7!vLm2pR9z"


class RegistrationTests(TestCase):
    def register(self, **data):
        payload = {
            "email": "New@Example.com",
            "password1": STRONG_PASSWORD,
            "password2": STRONG_PASSWORD,
        }
        payload.update(data)
        return self.client.post(reverse("user:registration"), payload)

    def test_register_and_login(self):
        response = self.register()
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertTrue(User.objects.filter(username="new@example.com").exists())

        self.client.post(reverse("user:logout"))
        response = self.client.post(
            reverse("user:auth"),
            {"email": "NEW@example.com", "password": STRONG_PASSWORD},
        )
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_invalid_email(self):
        response = self.register(email="not-an-email")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_email_case_insensitive(self):
        self.register()
        self.client.post(reverse("user:logout"))
        response = self.register(email="new@EXAMPLE.com")
        self.assertContains(response, "уже зарегистрирован")
        self.assertEqual(User.objects.count(), 1)

    def test_passwords_mismatch(self):
        response = self.register(password2="other")
        self.assertContains(response, "не совпадают")

    def test_weak_password(self):
        response = self.register(password1="123", password2="123")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())


class AuthTests(TestCase):
    def setUp(self):
        User.objects.create_user("u@example.com", "u@example.com", STRONG_PASSWORD)

    def test_wrong_password(self):
        response = self.client.post(
            reverse("user:auth"), {"email": "u@example.com", "password": "bad"}
        )
        self.assertContains(response, "Неверный логин или пароль")

    def test_missing_fields(self):
        response = self.client.post(reverse("user:auth"), {})
        self.assertEqual(response.status_code, 200)

    def test_redirect_to_next(self):
        url = f"{reverse('user:auth')}?next={reverse('dashboard:create')}"
        response = self.client.post(
            url, {"email": "u@example.com", "password": STRONG_PASSWORD}
        )
        self.assertRedirects(response, reverse("dashboard:create"))

    def test_external_next_ignored(self):
        url = f"{reverse('user:auth')}?next=https://evil.example.com/"
        response = self.client.post(
            url, {"email": "u@example.com", "password": STRONG_PASSWORD}
        )
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_logout_requires_post(self):
        self.client.login(username="u@example.com", password=STRONG_PASSWORD)
        self.assertEqual(self.client.get(reverse("user:logout")).status_code, 405)
        response = self.client.post(reverse("user:logout"))
        self.assertRedirects(response, reverse("dashboard:index"))
