from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from ingredients.models import Ingredient
from ingredients.units import Unit

User = get_user_model()


class PantryItem(TimeStampedModel):
    """One ingredient a user currently has in their pantry."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="pantry_items"
    )

    # Nullable on purpose. If the matcher cannot resolve what the user typed,
    # the item is still stored and still shown — it simply never matches a
    # recipe. Rejecting the input or guessing at a match are both worse.
    ingredient = models.ForeignKey(
        Ingredient,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pantry_items",
    )

    # Exactly what the user typed, kept for display and for improving the
    # alias table later.
    raw_input = models.CharField(max_length=255)

    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)

    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["raw_input"]
        constraints = [
            # Postgres treats NULLs as distinct, so a user may hold several
            # unresolved items without colliding. That is the desired
            # behaviour: only resolved ingredients are deduplicated.
            models.UniqueConstraint(
                fields=["user", "ingredient"], name="uniq_user_ingredient"
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=0), name="pantry_quantity_non_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "ingredient"]),
            models.Index(fields=["user", "expiry_date"]),
        ]

    @property
    def display_name(self) -> str:
        return self.ingredient.display_name if self.ingredient else self.raw_input

    def __str__(self) -> str:
        return f"{self.user.email} — {self.display_name} ({self.quantity} {self.unit})"


class IngredientLog(TimeStampedModel):
    """
    Append-only audit trail. Every add/update/remove on PantryItem
    writes a row here. Rows are never deleted.

    ingredient_name is kept verbatim because this is a historical record —
    it must reflect what was written at the time, even if the vocabulary
    changes later. The foreign key is added alongside it for querying, not
    as a replacement.
    """

    class Action(models.TextChoices):
        ADDED = "ADDED", "Added"
        UPDATED = "UPDATED", "Updated"
        REMOVED = "REMOVED", "Removed"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ingredient_logs"
    )
    ingredient = models.ForeignKey(
        Ingredient,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    ingredient_name = models.CharField(max_length=255)
    action = models.CharField(max_length=10, choices=Action.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user.email} — {self.action} {self.ingredient_name}"