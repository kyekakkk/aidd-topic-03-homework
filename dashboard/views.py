import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from .forms import AddToWatchlistForm, BuyShareForm, ShareModelForm
from .models import Portfolio, PortfolioPosition, Share
from .services.graph import get_graph
from .services.history import period_start, share_stats
from .services.errors import MarketDataError

logger = logging.getLogger("main")


class ShareListView(ListView):
    """Список акций"""

    model = Share
    template_name = "dashboard/list.html"
    paginate_by = 100
    ordering = ["name"]


class ShareDetailView(DetailView):
    """Карточка акции с графиком"""

    model = Share
    template_name = "dashboard/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["plot_div"] = get_graph(self.object)
        except MarketDataError as e:
            logger.warning(f"Graph for share {self.object.id} unavailable: {e}")
            context["plot_div"] = None
        context.setdefault(
            "buy_form", BuyShareForm(initial={"price": self.object.last_price})
        )
        if self.request.user.is_authenticated:
            context["watchlist_form"] = AddToWatchlistForm(user=self.request.user)
        context["month_stats"] = share_stats(self.object, period_start("30d"))
        return context


class ShareCreateView(LoginRequiredMixin, CreateView):
    """Добавление инструмента"""

    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование инструмента"""

    model = Share
    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление инструмента"""

    model = Share
    template_name = "dashboard/delete.html"
    success_url = reverse_lazy("dashboard:index")


class PortfolioView(LoginRequiredMixin, View):
    """Виртуальный портфель текущего пользователя"""

    @staticmethod
    def get(request):
        positions = list(
            PortfolioPosition.objects.filter(portfolio__user=request.user)
            .select_related("share")
            .order_by("share__name")
        )
        values = [p.market_value for p in positions if p.market_value is not None]
        return render(
            request,
            "dashboard/portfolio.html",
            {
                "positions": positions,
                "total_quantity": sum(p.quantity for p in positions),
                "total_cost": sum(p.cost for p in positions),
                "total_value": sum(values),
                "has_unpriced": len(values) < len(positions),
            },
        )


class PortfolioBuyView(LoginRequiredMixin, View):
    """Покупка акций в портфель со страницы акции"""

    @staticmethod
    def post(request, pk):
        share = get_object_or_404(Share, pk=pk)
        form = BuyShareForm(request.POST)
        if not form.is_valid():
            # Показываем карточку заново с ошибками формы
            view = ShareDetailView(request=request, kwargs={"pk": pk})
            view.object = share
            return render(
                request,
                ShareDetailView.template_name,
                view.get_context_data(buy_form=form),
                status=400,
            )

        quantity = form.cleaned_data["quantity"]
        price = form.cleaned_data["price"]
        with transaction.atomic():
            portfolio, _ = Portfolio.objects.get_or_create(user=request.user)
            position = (
                PortfolioPosition.objects.select_for_update()
                .filter(portfolio=portfolio, share=share)
                .first()
            )
            if position is None:
                position = PortfolioPosition(
                    portfolio=portfolio,
                    share=share,
                    quantity=quantity,
                    average_price=price,
                )
            else:
                position.add(quantity, price)
            position.save()

        messages.success(
            request, f"В портфель добавлено {quantity} шт. {share.ticker} по {price:g}"
        )
        return redirect("dashboard:portfolio")
