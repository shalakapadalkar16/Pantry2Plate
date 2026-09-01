"""
Recipe corpus.

Coverage ranking is the point of these tables, so the counters that feed
it are denormalised onto Recipe rather than computed per request. Counting
rows across ~2.1M RecipeIngredient records on every search would be the
whole latency budget.

The tradeoff is staleness: the counters are wrong if the vocabulary
changes. That is acceptable because a vocabulary change already requires a
reindex, and the counters are recomputed as part of it.
"""

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from ingredients.models import Ingredient


class Recipe(TimeStampedModel):
    # Stable id from the source dataset. Reimporting updates rather than
    # duplicating, which matters because import is re-run whenever the
    # vocabulary changes.
    external_id = models.CharField(max_length=64, unique=True)

    name = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    minutes = models.PositiveIntegerField(null=True, db_index=True)
    n_steps = models.PositiveSmallIntegerField(default=0)
    steps = models.JSONField(default=list)

    # Source tags: cuisine, occasion, dietary, season, time bracket.
    # This is what mood filtering will map onto — deterministic and
    # testable, rather than asking a model to guess at a vibe.
    tags = ArrayField(models.CharField(max_length=64), default=list, blank=True)

    # The source stores nutrition as a bare positional list. Keeping the
    # raw list without documenting the order would make it unreadable in
    # six months, so calories is pulled out and the rest kept as-is.
    calories = models.FloatField(null=True)
    nutrition = models.JSONField(
        default=list,
        help_text="[calories, total_fat_pdv, sugar_pdv, sodium_pdv, "
                  "protein_pdv, saturated_fat_pdv, carbs_pdv]",
    )

    submitted = models.DateField(null=True)

    # ---- coverage counters, all set at import ----------------------------

    n_ingredients = models.PositiveSmallIntegerField(default=0)

    # Non-staple ingredients only. Salt and oil are assumed present in
    # every kitchen, so counting them would make every recipe look less
    # cookable than it is. This is the coverage denominator.
    n_required = models.PositiveSmallIntegerField(default=0, db_index=True)

    # Ingredients the matcher could not resolve. These can never be
    # satisfied by a pantry, so they always count as missing. 31.2% of the
    # corpus has none; 65.5% has at most one.
    n_unresolved = models.PositiveSmallIntegerField(
        default=0, db_index=True, validators=[MinValueValidator(0)]
    )

    class Meta:
        ordering = ["id"]
        indexes = [
            GinIndex(fields=["tags"], name="recipe_tags_gin"),
            models.Index(fields=["n_unresolved", "n_required"]),
            models.Index(fields=["minutes", "n_required"]),
        ]

    @property
    def is_fully_resolved(self) -> bool:
        return self.n_unresolved == 0

    def __str__(self) -> str:
        return self.name


class RecipeIngredient(models.Model):
    """
    One ingredient slot in a recipe.

    ingredient is nullable and unresolved rows are kept deliberately. A row
    holding raw_text with no foreign key can never be matched by a pantry
    item, so it counts as missing — which is correct, because the user
    cannot confirm they have something the system could not identify.
    Dropping the row would tell them the recipe needs less than it does.
    """

    recipe = models.ForeignKey(
        Recipe, related_name="recipe_ingredients", on_delete=models.CASCADE
    )
    ingredient = models.ForeignKey(
        Ingredient,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recipe_ingredients",
    )

    # Exactly what the source listed, kept for display and for growing the
    # alias table from real misses.
    raw_text = models.CharField(max_length=500)

    # Set at import from Ingredient.is_staple. Denormalised so coverage
    # queries never join back to the ingredient table.
    is_staple = models.BooleanField(default=False)

    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["recipe_id", "position"]
        indexes = [
            # Drives the core lookup: given a set of pantry ingredient ids,
            # find every recipe that uses them.
            models.Index(fields=["ingredient", "recipe"]),
            models.Index(fields=["recipe", "is_staple"]),
        ]

    def __str__(self) -> str:
        return self.ingredient.display_name if self.ingredient else self.raw_text


class SavedRecipe(TimeStampedModel):
    """A user's recipe book."""

    user = models.ForeignKey(
        "users.User", related_name="saved_recipes", on_delete=models.CASCADE
    )
    recipe = models.ForeignKey(
        Recipe, related_name="saved_by", on_delete=models.CASCADE
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "recipe"], name="uniq_user_saved_recipe"
            )
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user.email} — {self.recipe.name}"