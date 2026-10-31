from rest_framework import serializers

from dashboard.models import Share


class ShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = Share
        fields = (
            "id",
            "figi",
            "isin",
            "name",
            "ticker",
            "currency",
            "uid",
            "last_price",
            "is_trend_high",
            "updated_at",
        )
        # Рыночные данные заполняет фоновая задача
        read_only_fields = ("last_price", "is_trend_high", "updated_at")
