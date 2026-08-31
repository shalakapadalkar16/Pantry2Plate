"""
Pantry business logic.

Every method that writes both a PantryItem and an IngredientLog is atomic.
The log is append-only and its value depends entirely on being complete —
a pantry change with no corresponding log row is a silent hole in the
audit trail.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction

from core.exceptions import DuplicateResourceError, ResourceNotFoundError
from ingredients.matcher import matcher

from .models import IngredientLog, PantryItem


class PantryService:

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _resolve(raw_input: str):
        """
        Resolve free text to an Ingredient, recording misses.

        Returns None when nothing resolves. The item is still stored — it
        simply never matches a recipe. Rejecting the input or guessing are
        both worse for the user.
        """
        result = matcher.match(raw_input)
        if not result.matched:
            matcher.record_miss(raw_input, result.normalized)
        return result.ingredient

    @staticmethod
    def _log(user, item: PantryItem, action: str, quantity: Decimal, unit: str) -> None:
        IngredientLog.objects.create(
            user=user,
            ingredient=item.ingredient,
            ingredient_name=item.raw_input,
            action=action,
            quantity=quantity,
            unit=unit,
        )

    # -------------------------------------------------------------- writes

    @staticmethod
    @transaction.atomic
    def add_item(
        user,
        raw_input: str,
        quantity: Decimal,
        unit: str,
        expiry_date: date | None = None,
    ) -> PantryItem:
        ingredient = PantryService._resolve(raw_input)

        # Unresolved items are never deduplicated — the database treats NULL
        # ingredient values as distinct, and two unrecognised strings may well
        # be different things.
        if ingredient is not None:
            exists = PantryItem.objects.filter(
                user=user, ingredient=ingredient
            ).exists()
            if exists:
                raise DuplicateResourceError(
                    f"'{ingredient.display_name}' is already in your pantry. "
                    f"Update the existing item instead."
                )

        try:
            item = PantryItem.objects.create(
                user=user,
                ingredient=ingredient,
                raw_input=raw_input,
                quantity=quantity,
                unit=unit,
                expiry_date=expiry_date,
            )
        except IntegrityError:
            # The check above is not a lock. Two concurrent requests can both
            # pass it, and the database constraint is what actually enforces
            # uniqueness. Without this, the loser gets a 500.
            raise DuplicateResourceError(
                f"'{raw_input}' is already in your pantry."
            ) from None

        PantryService._log(user, item, IngredientLog.Action.ADDED, quantity, unit)
        return item

    @staticmethod
    @transaction.atomic
    def update_item(
        user,
        item_id: int,
        quantity: Decimal | None = None,
        unit: str | None = None,
        expiry_date: date | None = None,
        clear_expiry: bool = False,
    ) -> PantryItem:
        """
        Partial update. Every field is optional, which is what PATCH means —
        the previous version required quantity AND unit together, so sending
        only a quantity returned a 400.
        """
        try:
            item = PantryItem.objects.select_for_update().get(id=item_id, user=user)
        except PantryItem.DoesNotExist:
            raise ResourceNotFoundError("Pantry item not found.") from None

        changed = []
        if quantity is not None:
            item.quantity = quantity
            changed.append("quantity")
        if unit is not None:
            item.unit = unit
            changed.append("unit")
        if clear_expiry:
            item.expiry_date = None
            changed.append("expiry_date")
        elif expiry_date is not None:
            item.expiry_date = expiry_date
            changed.append("expiry_date")

        if not changed:
            return item

        item.save(update_fields=changed + ["updated_at"])
        PantryService._log(
            user, item, IngredientLog.Action.UPDATED, item.quantity, item.unit
        )
        return item

    @staticmethod
    @transaction.atomic
    def remove_item(user, item_id: int) -> None:
        try:
            item = PantryItem.objects.get(id=item_id, user=user)
        except PantryItem.DoesNotExist:
            raise ResourceNotFoundError("Pantry item not found.") from None

        PantryService._log(
            user, item, IngredientLog.Action.REMOVED, item.quantity, item.unit
        )
        item.delete()

    # --------------------------------------------------------------- reads

    @staticmethod
    def get_pantry(user):
        # select_related avoids one query per row when serializing
        # ingredient.display_name across a full pantry.
        return PantryItem.objects.filter(user=user).select_related("ingredient")

    @staticmethod
    def get_logs(user):
        """
        The log is append-only and never pruned, so this must stay paginated
        at the view layer. Returning it unbounded was the previous behaviour
        and does not survive a year of use.
        """
        return IngredientLog.objects.filter(user=user).select_related("ingredient")

    @staticmethod
    def get_expiring(user, within_days: int = 7):
        from datetime import timedelta

        cutoff = date.today() + timedelta(days=within_days)
        return (
            PantryItem.objects.filter(
                user=user, expiry_date__isnull=False, expiry_date__lte=cutoff
            )
            .select_related("ingredient")
            .order_by("expiry_date")
        )