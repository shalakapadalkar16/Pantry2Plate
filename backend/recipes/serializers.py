from rest_framework import serializers

from recipes.models import Recipe, SavedRecipe


class SavedRecipeCardSerializer(serializers.ModelSerializer):
    """Recipe fields needed to render a book entry. Steps are excluded —
    the detail endpoint serves those."""

    class Meta:
        model = Recipe
        fields = ("id", "name", "minutes", "n_ingredients", "n_required", "tags")
        read_only_fields = fields


class SavedRecipeSerializer(serializers.ModelSerializer):
    recipe = SavedRecipeCardSerializer(read_only=True)

    class Meta:
        model = SavedRecipe
        fields = ("id", "recipe", "notes", "created_at", "updated_at")
        read_only_fields = fields


class SaveRecipeSerializer(serializers.Serializer):
    """POST body. recipe_id rather than a nested object — the client is
    saving something it already has an id for."""

    recipe_id = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=2000
    )


class UpdateNotesSerializer(serializers.Serializer):
    notes = serializers.CharField(allow_blank=True, max_length=2000)