"""Симулятор инвестиционных стратегий."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime
from django.views.generic import View

from .forms import SimulationRunForm, StrategyForm
from .models import Share, SimulationRun, Strategy
from .services.history import PERIODS
from .services.simulator import SimulationError, run_simulation


class StrategyListView(LoginRequiredMixin, View):
    """Стратегии пользователя с результатом последнего прогона"""

    @staticmethod
    def get(request):
        strategies = list(
            Strategy.objects.filter(user=request.user)
            .select_related("share")
            .annotate(runs_count=Count("runs"))
        )
        latest = {}
        for run in SimulationRun.objects.filter(strategy__in=strategies).order_by("created_at"):
            latest[run.strategy_id] = run
        for strategy in strategies:
            strategy.latest_run = latest.get(strategy.id)
        return render(request, "dashboard/strategies.html", {"strategies": strategies})


class StrategyCreateView(LoginRequiredMixin, View):
    """Создание стратегии; акцию можно передать в ?share=<id>"""

    @staticmethod
    def get(request):
        initial = {}
        share_id = request.GET.get("share")
        if share_id and share_id.isdigit() and Share.objects.filter(pk=share_id).exists():
            initial["share"] = share_id
        form = StrategyForm(user=request.user, initial=initial)
        return render(request, "dashboard/strategy_form.html", {"form": form})

    @staticmethod
    def post(request):
        form = StrategyForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(request, "dashboard/strategy_form.html", {"form": form}, status=400)
        strategy = form.save()
        messages.success(request, f"Стратегия «{strategy.name}» создана — запустите моделирование")
        return redirect("dashboard:strategy", pk=strategy.pk)


class StrategyDetailView(LoginRequiredMixin, View):
    """Правила стратегии, запуск моделирования и история прогонов"""

    @staticmethod
    def get(request, pk):
        strategy = get_object_or_404(
            Strategy.objects.select_related("share"), pk=pk, user=request.user
        )
        return render(
            request,
            "dashboard/strategy_detail.html",
            {
                "strategy": strategy,
                "runs": strategy.runs.all(),
                "run_form": SimulationRunForm(),
                "history_count": strategy.share.price_history.count(),
                "periods": {code: title for code, (title, _) in PERIODS.items()},
            },
        )


class StrategyRunView(LoginRequiredMixin, View):
    """Запуск моделирования на истории цен"""

    @staticmethod
    def post(request, pk):
        strategy = get_object_or_404(
            Strategy.objects.select_related("share"), pk=pk, user=request.user
        )
        form = SimulationRunForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Выберите период истории")
            return redirect("dashboard:strategy", pk=pk)
        try:
            run = run_simulation(strategy, form.cleaned_data["period"])
        except SimulationError as e:
            messages.error(
                request,
                f"{e}. Загрузите историю цен {strategy.share.ticker} командой "
                f"python manage.py load_price_history --ticker {strategy.share.ticker}",
            )
            return redirect("dashboard:strategy", pk=pk)
        messages.success(request, f"Моделирование завершено: {run.trades_count} сделок")
        return redirect("dashboard:simulation_run", pk=run.pk)


class StrategyDeleteView(LoginRequiredMixin, View):
    @staticmethod
    def post(request, pk):
        strategy = get_object_or_404(Strategy, pk=pk, user=request.user)
        strategy.delete()
        messages.success(request, f"Стратегия «{strategy.name}» удалена")
        return redirect("dashboard:strategies")


class SimulationRunDetailView(LoginRequiredMixin, View):
    """Итоги прогона, график капитала и журнал виртуальных сделок"""

    @staticmethod
    def get(request, pk):
        run = get_object_or_404(
            SimulationRun.objects.select_related("strategy__share"),
            pk=pk,
            strategy__user=request.user,
        )
        trades = list(run.trades.all())

        def ms(value):
            # Chart.js с линейной осью времени: миллисекунды эпохи
            return int(value.timestamp() * 1000)

        chart = {
            "equity": [{"x": ms(parse_datetime(t)), "y": e} for t, e, _ in run.equity_curve],
            "price": [{"x": ms(parse_datetime(t)), "y": p} for t, _, p in run.equity_curve],
            "buys": [{"x": ms(t.time), "y": t.price} for t in trades if t.side == t.BUY],
            "sells": [{"x": ms(t.time), "y": t.price} for t in trades if t.side == t.SELL],
        }
        sells = [t for t in trades if t.profit is not None]
        return render(
            request,
            "dashboard/simulation_run.html",
            {
                "run": run,
                "strategy": run.strategy,
                "trades": trades,
                "chart": chart,
                "period_title": PERIODS.get(run.period, (run.period,))[0],
                "winning": sum(1 for t in sells if t.profit > 0),
                "closed": len(sells),
            },
        )
