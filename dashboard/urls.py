from django.urls import include, path

from dashboard.views import (
    PortfolioView,
    ShareCreateView,
    ShareDeleteView,
    ShareDetailView,
    ShareListView,
    ShareTradeView,
    ShareUpdateView,
)

app_name = "dashboard"

urlpatterns = [
    path("", ShareListView.as_view(), name="index"),
    path("portfolio/", PortfolioView.as_view(), name="portfolio"),
    path("trade/<int:pk>", ShareTradeView.as_view(), name="trade"),
    path("create", ShareCreateView.as_view(), name="create"),
    path("update/<int:pk>", ShareUpdateView.as_view(), name="update"),
    path("delete/<int:pk>", ShareDeleteView.as_view(), name="delete"),
    path("<int:pk>", ShareDetailView.as_view(), name="detail"),
    path("api/", include("dashboard.api.urls")),
]
