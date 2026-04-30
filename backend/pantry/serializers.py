from rest_framework import serializers

from .models import IngredientLog, PantryItem


class PantryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PantryItem
        fields = ("id", "ingredient_name", "quantity", "unit", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class PantryItemCreateSerializer(serializers.ModelSerializer):
    """Used for POST — creating a new pantry item."""

    class Meta:
        model = PantryItem
        fields = ("ingredient_name", "quantity", "unit")


class PantryItemUpdateSerializer(serializers.ModelSerializer):
    """Used for PATCH — only quantity and unit can be changed."""

    class Meta:
        model = PantryItem
        fields = ("quantity", "unit")


class IngredientLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngredientLog
        fields = ("id", "ingredient_name", "action", "quantity", "unit", "created_at")
        read_only_fields = fields