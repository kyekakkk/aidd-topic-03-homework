from django.contrib import admin

from dashboard.models import (
    Portfolio,
    PortfolioPosition,
    PriceAlert,
    PriceSnapshot,
    Share,
    SimulatedTrade,
    SimulationRun,
    Strategy,
    Watchlist,
    WatchlistItem,
)


@admin.register(Share)
class ShareAdmin(admin.ModelAdmin):
    list_display = ("figi", "isin", "name", "ticker", "currency")
    search_fields = ("figi", "isin", "name", "ticker")
    fields = (
        "figi",
        "isin",
        "name",
        "ticker",
        "currency",
        "uid",
        "last_price",
        "is_trend_high",
    )


class PortfolioPositionInline(admin.TabularInline):
    model = PortfolioPosition
    extra = 0
    autocomplete_fields = ("share",)


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__email",)
    inlines = (PortfolioPositionInline,)


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("share", "price", "time")
    list_filter = ("time",)
    search_fields = ("share__ticker",)
    autocomplete_fields = ("share",)
    date_hierarchy = "time"


class WatchlistItemInline(admin.TabularInline):
    model = WatchlistItem
    extra = 0
    autocomplete_fields = ("share",)


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__email")
    inlines = (WatchlistItemInline,)


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = ("item", "direction", "target_price", "triggered_at", "triggered_price")
    list_filter = ("direction", ("triggered_at", admin.EmptyFieldListFilter))


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "share", "kind", "created_at")
    list_filter = ("kind",)
    search_fields = ("name", "share__ticker", "user__email")


class SimulatedTradeInline(admin.TabularInline):
    model = SimulatedTrade
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SimulatedTrade._meta.fields]


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = ("strategy", "period", "created_at", "trades_count", "return_percent")
    exclude = ("equity_curve",)
    inlines = (SimulatedTradeInline,)
