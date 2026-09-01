from rest_framework import serializers

from recipes.models import Recipe

from . import moods

MAX_LIMIT = 50
MAX_MOODS = 4


class RecipeSummarySerializer(serializers.ModelSerializer):
    """Enough to render a result card. Steps are excluded deliberately —
    a page of 20 recipes would otherwise ship a few hundred KB of
    instructions nobody has asked to read yet."""

    class Meta:
        model = Recipe
        fields = (
            "id",
            "external_id",
            "name",
            "minutes",
            "n_ingredients",
            "n_required",
            "n_unresolved",
            "tags",
            "calories",
        )
        read_only_fields = fields


class RecipeMatchSerializer(serializers.Serializer):
    """One ranked result."""

    recipe = RecipeSummarySerializer(read_only=True)
    have = serializers.IntegerField(read_only=True)
    missing = serializers.IntegerField(read_only=True)
    coverage = serializers.FloatField(read_only=True)

    # Known ingredients the pantry lacks — these can go on a shopping list.
    missing_ingredients = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )
    # Ingredients the matcher could not identify. Surfaced separately
    # because "you need butter" and "we could not read this line" are
    # different messages, even though both count against coverage.
    unknown_ingredients = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )


class RecommendationQuerySerializer(serializers.Serializer):
    """
    Validates query parameters.

    Bounds are enforced here rather than in the view so a malformed or
    hostile request cannot ask the database for 10,000 rows.
    """

    max_missing = serializers.IntegerField(
        required=False, default=0, min_value=0, max_value=10
    )
    limit = serializers.IntegerField(
        required=False, default=20, min_value=1, max_value=MAX_LIMIT
    )
    offset = serializers.IntegerField(required=False, default=0, min_value=0)
    max_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=1440
    )
    min_required = serializers.IntegerField(
        required=False, default=3, min_value=1, max_value=30
    )
    order = serializers.ChoiceField(
        required=False, default="best", choices=["best", "quickest", "simplest"]
    )
    mood = serializers.CharField(required=False, allow_blank=True)
    # Escape hatch for benchmarking. Normal requests omit it and let the
    # view pick whichever backend is reachable.
    backend = serializers.ChoiceField(
        required=False, allow_null=True, default=None, choices=["sql", "es"]
    )

    def validate_mood(self, value):
        """
        Comma-separated mood keys in the URL, tag groups internally.

        An unknown key is rejected rather than ignored. Silently dropping a
        filter returns results the user did not ask for, with no way for
        them to tell it happened.
        """
        if not value:
            return []

        keys = [k.strip() for k in value.split(",") if k.strip()]
        if len(keys) > MAX_MOODS:
            raise serializers.ValidationError(
                f"At most {MAX_MOODS} moods at once."
            )

        unknown = [k for k in keys if k not in moods.MOODS]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown mood: {', '.join(unknown)}. "
                f"See /api/v1/recommendations/moods/ for valid keys."
            )
        return keys