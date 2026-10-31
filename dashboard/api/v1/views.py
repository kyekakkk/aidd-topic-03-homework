import re

from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from dashboard.models import Share

from .serializer import ShareSerializer


class ShareFilter(filters.FilterSet):
    class Meta:
        model = Share
        fields = ("name", "ticker")


class EscapedSearchFilter(SearchFilter):
    """Поиск через iregex с экранированием ввода.

    iregex регистронезависим и для кириллицы (icontains в SQLite — только для
    ASCII), а экранирование не даёт передать в БД некорректное выражение.
    """

    def get_search_terms(self, request):
        return [re.escape(term) for term in super().get_search_terms(request)]


class ShareViewSet(viewsets.ModelViewSet):
    serializer_class = ShareSerializer
    # Явная сортировка нужна для стабильной пагинации
    queryset = Share.objects.order_by("name", "id")
    filter_backends = (OrderingFilter, filters.DjangoFilterBackend, EscapedSearchFilter)
    filterset_class = ShareFilter
    ordering_fields = ["name", "ticker"]
    search_fields = ["$name"]
