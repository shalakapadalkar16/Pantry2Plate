from decimal import Decimal

from rest_framework import serializers

from ingredients.units import UnknownUnitError, parse_unit

from .models import IngredientLog, PantryItem


class IngredientBriefSerializer(serializers.Serializer):
    """Minimal ingredient shape. Nested read-only inside pantry responses."""

    id = serializers.IntegerField()
    canonical_name = serializers.CharField()
    display_name = serializers.CharField()
    category = serializers.CharField()
    is_staple = serializers.BooleanField()


class PantryItemSerializer(serializers.ModelSerializer):
    ingredient = IngredientBriefSerializer(read_only=True)
    display_name = serializers.CharField(read_only=True)
    is_resolved = serializers.SerializerMethodField()

    class Meta:
        model = PantryItem
        fields = (
            "id",
            "ingredient",
            "raw_input",
            "display_name",
            "is_resolved",
            "quantity",
            "unit",
            "expiry_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_is_resolved(self, obj) -> bool:
        """
        Surfaced deliberately. An unresolved item will never appear in a
        recipe match, and the user should be able to see why rather than
        wonder where their ingredient went.
        """
        return obj.ingredient_id is not None


class UnitField(serializers.CharField):
    """Accepts any spelling the unit alias table knows, stores canonical."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return parse_unit(value)
        except UnknownUnitError:
            raise serializers.ValidationError(
                f"'{value}' is not a unit we recognise."
            ) from None


class PantryItemCreateSerializer(serializers.Serializer):
    """POST — the ingredient FK is resolved in the service, not here."""

    raw_input = serializers.CharField(max_length=255, trim_whitespace=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    unit = UnitField(max_length=50, required=False, default="piece")
    expiry_date = serializers.DateField(required=False, allow_null=True)


class PantryItemUpdateSerializer(serializers.Serializer):
    """
    PATCH — every field optional.

    The previous version declared quantity and unit as required, so a
    partial update was impossible and PATCH behaved like PUT.
    """

    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False
    )
    unit = UnitField(max_length=50, required=False)
    expiry_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs


class IngredientLogSerializer(serializers.ModelSerializer):
    ingredient = IngredientBriefSerializer(read_only=True)

    class Meta:
        model = IngredientLog
        fields = (
            "id",
            "ingredient",
            "ingredient_name",
            "action",
            "quantity",
            "unit",
            "created_at",
        )
        read_only_fields = fields