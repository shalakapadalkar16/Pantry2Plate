from decimal import Decimal

from django.contrib.auth import get_user_model

from .models import IngredientLog, PantryItem

User = get_user_model()


class PantryService:

    @staticmethod
    def add_item(user, ingredient_name: str, quantity: Decimal, unit: str) -> PantryItem:
        """Add a new ingredient to the pantry and log the action."""

        if PantryItem.objects.filter(user=user, ingredient_name=ingredient_name).exists():
            raise ValueError(f"'{ingredient_name}' already exists in your pantry. Update it instead.")

        item = PantryItem.objects.create(
            user=user,
            ingredient_name=ingredient_name,
            quantity=quantity,
            unit=unit,
        )

        IngredientLog.objects.create(
            user=user,
            ingredient_name=ingredient_name,
            action=IngredientLog.Action.ADDED,
            quantity=quantity,
            unit=unit,
        )

        return item

    @staticmethod
    def update_item(user, item_id: int, quantity: Decimal, unit: str) -> PantryItem:
        """Update quantity/unit of an existing pantry item and log the action."""

        try:
            item = PantryItem.objects.get(id=item_id, user=user)
        except PantryItem.DoesNotExist:
            raise ValueError("Pantry item not found.")

        item.quantity = quantity
        item.unit = unit
        item.save()

        IngredientLog.objects.create(
            user=user,
            ingredient_name=item.ingredient_name,
            action=IngredientLog.Action.UPDATED,
            quantity=quantity,
            unit=unit,
        )

        return item

    @staticmethod
    def remove_item(user, item_id: int) -> None:
        """Remove an ingredient from the pantry and log the action."""

        try:
            item = PantryItem.objects.get(id=item_id, user=user)
        except PantryItem.DoesNotExist:
            raise ValueError("Pantry item not found.")

        IngredientLog.objects.create(
            user=user,
            ingredient_name=item.ingredient_name,
            action=IngredientLog.Action.REMOVED,
            quantity=item.quantity,
            unit=item.unit,
        )

        item.delete()

    @staticmethod
    def get_pantry(user):
        """Return all pantry items for a user."""
        return PantryItem.objects.filter(user=user)

    @staticmethod
    def get_logs(user):
        """Return the full audit log for a user."""
        return IngredientLog.objects.filter(user=user)