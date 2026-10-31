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

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "Данный e-mail уже зарегистрирован! Введите другой e-mail или"
                " воспользуйтесь формой авторизации."
            )
        return email

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2:
            if password1 != password2:
                raise ValidationError("Введенные пароли не совпадают")
            validate_password(password1, User(username=email, email=email))
        return cleaned_data

    def save(self):
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        User.objects.create_user(email, email, password)
        user = authenticate(username=email, password=password)
        return user


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

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        if email and password:
            # username совпадает с e-mail; учитываем старые записи в другом регистре
            account = User.objects.filter(email__iexact=email).first()
            username = account.username if account else email.lower()
            self.user = authenticate(
                self.request, username=username, password=password
            )
            if self.user is None:
                raise ValidationError("Неверный логин или пароль! Повторите попытку.")
        return cleaned_data
