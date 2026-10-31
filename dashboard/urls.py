from django.urls import include, path

from dashboard.views import (
    PortfolioBuyView,
    PortfolioView,
    ShareCreateView,
    ShareDeleteView,
    ShareDetailView,
    ShareListView,
    ShareUpdateView,
)
from dashboard.views_monitoring import (
    MarketDynamicsView,
    PriceAlertCreateView,
    PriceAlertDeleteView,
    ShareHistoryView,
    WatchlistAddShareView,
    WatchlistDeleteView,
    WatchlistDetailView,
    WatchlistIndexView,
    WatchlistItemDeleteView,
)
from dashboard.views_strategies import (
    SimulationRunDetailView,
    StrategyCreateView,
    StrategyDeleteView,
    StrategyDetailView,
    StrategyListView,
    StrategyRunView,
)

app_name = "dashboard"

urlpatterns = [
    path("", ShareListView.as_view(), name="index"),
    path("<int:pk>", ShareDetailView.as_view(), name="detail"),
    path("create", ShareCreateView.as_view(), name="create"),
    path("update/<int:pk>", ShareUpdateView.as_view(), name="update"),
    path("delete/<int:pk>", ShareDeleteView.as_view(), name="delete"),
    path("<int:pk>/history/", ShareHistoryView.as_view(), name="history"),
    path("dynamics/", MarketDynamicsView.as_view(), name="dynamics"),
    path("portfolio/", PortfolioView.as_view(), name="portfolio"),
    path("portfolio/buy/<int:pk>/", PortfolioBuyView.as_view(), name="portfolio_buy"),
    path("watchlists/", WatchlistIndexView.as_view(), name="watchlists"),
    path("watchlists/<int:pk>/", WatchlistDetailView.as_view(), name="watchlist"),
    path(
        "watchlists/<int:pk>/delete/",
        WatchlistDeleteView.as_view(),
        name="watchlist_delete",
    ),
    path(
        "watchlists/add/<int:share_pk>/",
        WatchlistAddShareView.as_view(),
        name="watchlist_add",
    ),
    path(
        "watchlists/items/<int:pk>/delete/",
        WatchlistItemDeleteView.as_view(),
        name="watchlist_item_delete",
    ),
    path(
        "watchlists/items/<int:item_pk>/alerts/",
        PriceAlertCreateView.as_view(),
        name="alert_create",
    ),
    path("alerts/<int:pk>/delete/", PriceAlertDeleteView.as_view(), name="alert_delete"),
    path("strategies/", StrategyListView.as_view(), name="strategies"),
    path("strategies/new/", StrategyCreateView.as_view(), name="strategy_create"),
    path("strategies/<int:pk>/", StrategyDetailView.as_view(), name="strategy"),
    path("strategies/<int:pk>/run/", StrategyRunView.as_view(), name="strategy_run"),
    path(
        "strategies/<int:pk>/delete/",
        StrategyDeleteView.as_view(),
        name="strategy_delete",
    ),
    path(
        "strategies/runs/<int:pk>/",
        SimulationRunDetailView.as_view(),
        name="simulation_run",
    ),
    path("api/", include("dashboard.api.urls")),
]
