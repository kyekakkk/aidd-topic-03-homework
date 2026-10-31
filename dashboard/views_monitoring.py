"""Списки наблюдения, целевые уровни, история цен и динамика рынка."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import View

from .forms import AddToWatchlistForm, PriceAlertForm, WatchlistForm
from .models import PriceAlert, Share, Watchlist, WatchlistItem
from .services.history import (
    PERIODS,
    daily_changes,
    market_changes,
    parse_period,
    period_start,
    price_series,
    share_stats,
)

DEFAULT_WATCHLIST_NAME = "Избранное"


def chart_data(points, period):
    """Подписи и значения для Chart.js."""
    label_format = "%d.%m %H:%M" if period in ("1d", "7d") else "%d.%m.%Y"
    return {
        "labels": [timezone.localtime(time).strftime(label_format) for time, _ in points],
        "values": [price for _, price in points],
    }


def periods_context(period):
    return {
        "period": period,
        "periods": [(code, title) for code, (title, _) in PERIODS.items()],
    }


# --- Списки наблюдения ---


class WatchlistIndexView(LoginRequiredMixin, View):
    """Списки наблюдения пользователя и создание нового списка"""

    def get(self, request, form=None):
        watchlists = Watchlist.objects.filter(user=request.user).annotate(
            items_count=Count("items", distinct=True),
            triggered_count=Count(
                "items__alerts", filter=Q(items__alerts__triggered_at__isnull=False)
            ),
        )
        triggered = (
            PriceAlert.objects.filter(
                item__watchlist__user=request.user, triggered_at__isnull=False
            )
            .select_related("item__share", "item__watchlist")
            .order_by("-triggered_at")[:10]
        )
        return render(
            request,
            "dashboard/watchlists.html",
            {
                "watchlists": watchlists,
                "triggered": triggered,
                "form": form or WatchlistForm(user=request.user),
            },
            status=400 if form else 200,
        )

    def post(self, request):
        form = WatchlistForm(request.POST, user=request.user)
        if not form.is_valid():
            return self.get(request, form=form)
        watchlist = form.save()
        messages.success(request, f"Список «{watchlist.name}» создан")
        return redirect("dashboard:watchlist", pk=watchlist.pk)


class WatchlistDetailView(LoginRequiredMixin, View):
    """Акции списка, их цены и целевые уровни"""

    @staticmethod
    def get(request, pk):
        watchlist = get_object_or_404(Watchlist, pk=pk, user=request.user)
        items = (
            watchlist.items.select_related("share")
            .prefetch_related("alerts")
            .order_by("share__name")
        )
        return render(
            request,
            "dashboard/watchlist_detail.html",
            {"watchlist": watchlist, "items": items, "alert_form": PriceAlertForm()},
        )


class WatchlistDeleteView(LoginRequiredMixin, View):
    @staticmethod
    def post(request, pk):
        watchlist = get_object_or_404(Watchlist, pk=pk, user=request.user)
        watchlist.delete()
        messages.success(request, f"Список «{watchlist.name}» удалён")
        return redirect("dashboard:watchlists")


class WatchlistAddShareView(LoginRequiredMixin, View):
    """Добавление акции в список со страницы акции"""

    @staticmethod
    def post(request, share_pk):
        share = get_object_or_404(Share, pk=share_pk)
        form = AddToWatchlistForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, "Выберите список наблюдения")
            return redirect("dashboard:detail", pk=share.pk)

        watchlist = form.cleaned_data["watchlist"]
        if watchlist is None:
            watchlist, _ = Watchlist.objects.get_or_create(
                user=request.user, name=DEFAULT_WATCHLIST_NAME
            )
        _, created = WatchlistItem.objects.get_or_create(watchlist=watchlist, share=share)
        if created:
            messages.success(request, f"{share.ticker} добавлена в список «{watchlist.name}»")
        else:
            messages.info(request, f"{share.ticker} уже есть в списке «{watchlist.name}»")
        return redirect("dashboard:watchlist", pk=watchlist.pk)


class WatchlistItemDeleteView(LoginRequiredMixin, View):
    @staticmethod
    def post(request, pk):
        item = get_object_or_404(
            WatchlistItem.objects.select_related("share", "watchlist"),
            pk=pk,
            watchlist__user=request.user,
        )
        item.delete()
        messages.success(request, f"{item.share.ticker} удалена из списка")
        return redirect("dashboard:watchlist", pk=item.watchlist.pk)


class PriceAlertCreateView(LoginRequiredMixin, View):
    """Установка целевого уровня для акции из списка"""

    @staticmethod
    def post(request, item_pk):
        item = get_object_or_404(
            WatchlistItem.objects.select_related("share"),
            pk=item_pk,
            watchlist__user=request.user,
        )
        form = PriceAlertForm(request.POST)
        if not form.is_valid():
            errors = "; ".join(e for field in form.errors.values() for e in field)
            messages.error(request, f"Уровень не сохранён: {errors}")
            return redirect("dashboard:watchlist", pk=item.watchlist_id)

        alert = form.save(commit=False)
        alert.item = item
        # Если уровень уже достигнут текущей ценой — фиксируем сразу
        reached = alert.check_price(item.share.last_price, timezone.now())
        alert.save()
        if reached:
            messages.warning(
                request,
                f"Уровень {alert.target_price:g} для {item.share.ticker} уже достигнут "
                f"(текущая цена {item.share.last_price:g})",
            )
        else:
            messages.success(request, f"Уровень {alert.target_price:g} для {item.share.ticker} установлен")
        return redirect("dashboard:watchlist", pk=item.watchlist_id)


class PriceAlertDeleteView(LoginRequiredMixin, View):
    @staticmethod
    def post(request, pk):
        alert = get_object_or_404(
            PriceAlert.objects.select_related("item"),
            pk=pk,
            item__watchlist__user=request.user,
        )
        alert.delete()
        messages.success(request, "Целевой уровень удалён")
        return redirect("dashboard:watchlist", pk=alert.item.watchlist_id)


# --- История цен и динамика ---


class ShareHistoryView(View):
    """История цены акции за период: график, сводка и дневные изменения"""

    @staticmethod
    def get(request, pk):
        share = get_object_or_404(Share, pk=pk)
        period = parse_period(request.GET.get("period"))
        since = period_start(period)
        return render(
            request,
            "dashboard/history.html",
            {
                "share": share,
                "stats": share_stats(share, since),
                "chart": chart_data(price_series(share, since), period),
                "days": daily_changes(share, since),
                **periods_context(period),
            },
        )


class MarketDynamicsView(View):
    """Изменение цен всех акций с историей за период"""

    TOP = 10

    def get(self, request):
        period = parse_period(request.GET.get("period"))
        rows = market_changes(period_start(period))
        # На графике — лидеры роста и падения
        movers = rows if len(rows) <= 2 * self.TOP else rows[: self.TOP] + rows[-self.TOP :]
        return render(
            request,
            "dashboard/dynamics.html",
            {
                "rows": rows,
                "chart": {
                    "labels": [row["share"].ticker for row in movers],
                    "values": [round(row["change_percent"] or 0, 2) for row in movers],
                },
                **periods_context(period),
            },
        )
