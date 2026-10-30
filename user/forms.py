from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from user.models import User


class RegistrationForm(forms.Form):
    """Форма регистрации пользователей"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Email"}
        ),
    )
    password1 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Пароль"}
        ),
    )
    password2 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Повторите пароль"}
        ),
    )

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").strip().lower()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("Введенные пароли не совпадают")

        if email:
            # e-mail используется как логин, поэтому проверяем его без учёта регистра
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError(
                    "Данный e-mail уже зарегистрирован! Введите другой e-mail или"
                    " воспользуйтесь формой авторизации."
                )
            if password1:
                validate_password(password1)

        cleaned["email"] = email
        return cleaned

    def save(self):
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        User.objects.create_user(email, email, password)
        return authenticate(username=email, password=password)


class AuthForm(forms.Form):
    """Форма авторизации пользователей"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Email"}
        ),
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Пароль"}
        ),
    )
