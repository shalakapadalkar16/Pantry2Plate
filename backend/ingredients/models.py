"""
Canonical ingredient vocabulary.

Both PantryItem and RecipeIngredient point at Ingredient. That shared
foreign key is what makes coverage scoring a set operation instead of
a string comparison.
"""

import re
import unicodedata

from django.db import models

from core.models import TimeStampedModel

from .units import Unit


class IngredientCategory(models.TextChoices):
    PRODUCE = "produce", "Produce"
    MEAT = "meat", "Meat"
    SEAFOOD = "seafood", "Seafood"
    DAIRY = "dairy", "Dairy"
    GRAIN = "grain", "Grain"
    LEGUME = "legume", "Legume"
    SPICE = "spice", "Spice"
    CONDIMENT = "condiment", "Condiment"
    BAKING = "baking", "Baking"
    OIL = "oil", "Oil"
    BEVERAGE = "beverage", "Beverage"
    OTHER = "other", "Other"


def _singular(token: str) -> str:
    """Crude per-token singularization. Correctness is not the goal —
    determinism is. Both the stored alias and the lookup string pass
    through this same function, so consistent nonsense still matches."""
    if len(token) <= 3 or token.endswith("ss"):
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"          # berries -> berry
    if token.endswith("oes"):
        return token[:-2]                # tomatoes -> tomato
    if token.endswith(("ches", "shes", "xes", "zes", "ses")):
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token


def normalize_name(raw: str) -> str:
    """
    Reduce a free-text ingredient string to a comparable key.

    >>> normalize_name("  Extra-Virgin Olive Oil! ")
    'extra virgin olive oil'
    >>> normalize_name("large eggs, beaten")
    'large egg beaten'
    """
    if not raw:
        return ""

    text = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    return " ".join(_singular(t) for t in text.split())


class Ingredient(TimeStampedModel):
    """One real-world ingredient. The vocabulary is closed and seeded."""

    canonical_name = models.SlugField(max_length=120, unique=True)
    display_name = models.CharField(max_length=120)
    category = models.CharField(
        max_length=32,
        choices=IngredientCategory.choices,
        default=IngredientCategory.OTHER,
        db_index=True,
    )
    default_unit = models.CharField(
        max_length=20, choices=Unit.choices, default=Unit.PIECE
    )

    # Staples are assumed present in every kitchen: salt, pepper, water, oil.
    # Without this, pantry-only mode returns almost nothing, because users
    # never list salt but nearly every recipe requires it.
    is_staple = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["display_name"]
        indexes = [models.Index(fields=["is_staple", "category"])]

    def __str__(self) -> str:
        return self.display_name


class IngredientAlias(models.Model):
    """
    Alternative spellings pointing at one Ingredient.

    Populated from the seed file and grown over time from unmatched
    user input. This is where 'evoo', 'scallion', and 'coriander leaves'
    get resolved.
    """

    ingredient = models.ForeignKey(
        Ingredient, related_name="aliases", on_delete=models.CASCADE
    )
    alias = models.CharField(max_length=160, unique=True, db_index=True)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "ingredient aliases"

    def save(self, *args, **kwargs):
        # Aliases are always stored normalized so lookups never have to
        # normalize the database side of the comparison.
        self.alias = normalize_name(self.alias)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.alias} → {self.ingredient.canonical_name}"


class UnmatchedIngredient(TimeStampedModel):
    """
    Free text the matcher could not resolve, with a hit counter.

    This is the feedback loop: query it sorted by count to find the
    aliases worth adding next. It also gives you a concrete number for
    match coverage, which is the metric to quote when defending this
    system.
    """

    raw_text = models.CharField(max_length=255, unique=True)
    normalized = models.CharField(max_length=255, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    resolved_to = models.ForeignKey(
        Ingredient,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-hit_count"]

    def __str__(self) -> str:
        return f"{self.raw_text} ({self.hit_count})"