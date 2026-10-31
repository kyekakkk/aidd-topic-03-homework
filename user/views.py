from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import View

from .forms import AuthForm, RegistrationForm


def first_error(form):
    """Первое сообщение об ошибке формы для вывода под полями."""
    for errors in form.errors.values():
        return errors[0]
    return ""


def redirect_after_login(request):
    next_url = request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("dashboard:index")


class AuthView(View):
    """Авторизация"""

    @staticmethod
    def get(request):
        return render(request, "user/auth.html", {"form": AuthForm()})

    @staticmethod
    def post(request):
        form = AuthForm(request.POST, request=request)
        if form.is_valid():
            login(request, form.user)
            return redirect_after_login(request)
        return render(
            request, "user/auth.html", {"form": form, "error": first_error(form)}
        )


class RegistrationView(View):
    """Регистрация"""

    @staticmethod
    def get(request):
        return render(request, "user/registration.html", {"form": RegistrationForm()})

    @staticmethod
    def post(request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("dashboard:index")
        return render(
            request,
            "user/registration.html",
            {"form": form, "error": first_error(form)},
        )


class LogoutView(View):
    """Выход"""

    http_method_names = ["post"]

    @staticmethod
    def post(request):
        logout(request)
        return redirect("dashboard:index")
