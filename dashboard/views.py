from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, View, UpdateView

from .forms import ShareModelForm, TradeForm
from .models import Portfolio, PortfolioPosition, Share
from .services.graph import get_graph


class IsUserAuthenticatedMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated

    @staticmethod
    def handle_no_permission():
        return redirect("dashboard:index")


class ShareListView(ListView):
    """Список акций"""

    model = Share
    template_name = "dashboard/list.html"
    paginate_by = 100
    ordering = ["name"]


class ShareDetailView(View):
    @staticmethod
    def get(request, pk):
        share = get_object_or_404(Share, id=pk)

        position = None
        if request.user.is_authenticated:
            position = PortfolioPosition.objects.filter(
                portfolio__user=request.user, share=share
            ).first()

        return render(
            request,
            "dashboard/detail.html",
            {
                "plot_div": get_graph(share),
                "share": share,
                "trade_form": TradeForm(),
                "position": position,
            },
        )


class ShareCreateView(IsUserAuthenticatedMixin, CreateView):
    """Добавление инструмента"""

    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareUpdateView(IsUserAuthenticatedMixin, UpdateView):
    """Редактирование инструмента"""

    model = Share
    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareDeleteView(IsUserAuthenticatedMixin, DeleteView):
    """Удаление задачи"""

    model = Share
    template_name = "dashboard/delete.html"
    success_url = reverse_lazy("dashboard:index")


def buy_share(portfolio, share, quantity, price):
    """Покупка акции: увеличивает количество и пересчитывает среднюю цену."""
    position, _ = PortfolioPosition.objects.get_or_create(
        portfolio=portfolio,
        share=share,
        defaults={"quantity": 0, "purchase_price": 0.0},
    )
    total_cost = position.quantity * position.purchase_price + quantity * price
    position.quantity += quantity
    position.purchase_price = total_cost / position.quantity
    position.purchased_at = timezone.now()
    position.save()
    return position


def sell_share(portfolio, share, quantity):
    """Продажа акции. Возвращает (успех, текст_ошибки)."""
    position = PortfolioPosition.objects.filter(
        portfolio=portfolio, share=share
    ).first()
    if position is None:
        return False, "В портфеле нет данной акции."
    if quantity > position.quantity:
        return False, f"В портфеле только {position.quantity} шт."

    position.quantity -= quantity
    if position.quantity == 0:
        position.delete()
    else:
        position.save()
    return True, None


class ShareTradeView(IsUserAuthenticatedMixin, View):
    """Покупка и продажа акции"""

    @staticmethod
    def post(request, pk):
        share = get_object_or_404(Share, id=pk)
        action = request.POST.get("action")
        form = TradeForm(request.POST)
        next_url = request.POST.get("next") or reverse_lazy(
            "dashboard:detail", kwargs={"pk": pk}
        )

        if not form.is_valid():
            messages.error(request, "Укажите корректное количество (целое число > 0).")
            return redirect(next_url)

        quantity = form.cleaned_data["quantity"]
        portfolio, _ = Portfolio.objects.get_or_create(user=request.user)

        if action == "buy":
            if share.last_price is None:
                messages.error(
                    request,
                    "Текущая цена акции неизвестна — покупка невозможна.",
                )
            else:
                buy_share(portfolio, share, quantity, float(share.last_price))
                messages.success(
                    request, f"Куплено {quantity} шт. {share.ticker}."
                )
        elif action == "sell":
            success, error = sell_share(portfolio, share, quantity)
            if success:
                messages.success(request, f"Продано {quantity} шт. {share.ticker}.")
            else:
                messages.error(request, error)
        else:
            messages.error(request, "Неизвестное действие.")

        return redirect(next_url)


class PortfolioView(IsUserAuthenticatedMixin, View):
    """Портфель пользователя: состав, стоимость и P&L"""

    @staticmethod
    def get(request):
        portfolio, _ = Portfolio.objects.get_or_create(user=request.user)
        positions = portfolio.positions.select_related("share")
        return render(
            request,
            "dashboard/portfolio.html",
            {
                "portfolio": portfolio,
                "positions": positions,
                "trade_form": TradeForm(),
            },
        )
