from django.contrib.auth import get_user_model
from django.db import models

from core.models import TimeStampedModel

User = get_user_model()


class PantryItem(TimeStampedModel):
    """One ingredient a user currently has in their pantry."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pantry_items")
    ingredient_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=50)  # e.g. grams, cups, pieces

    class Meta:
        unique_together = ("user", "ingredient_name")  # no duplicate ingredients per user
        ordering = ["ingredient_name"]

    def __str__(self):
        return f"{self.user.email} — {self.ingredient_name} ({self.quantity} {self.unit})"


class IngredientLog(TimeStampedModel):
    """
    Append-only audit trail. Every add/update/remove on PantryItem
    writes a row here. Rows are never deleted.
    """

    class Action(models.TextChoices):
        ADDED = "ADDED", "Added"
        UPDATED = "UPDATED", "Updated"
        REMOVED = "REMOVED", "Removed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ingredient_logs")
    ingredient_name = models.CharField(max_length=255)
    action = models.CharField(max_length=10, choices=Action.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=50)

    class Meta:
        ordering = ["-created_at"]  # newest log first

    def __str__(self):
        return f"{self.user.email} — {self.action} {self.ingredient_name}"