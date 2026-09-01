"""
Recipe book.

Straightforward CRUD, with one design decision worth stating: saved recipes
are addressed by recipe id, not by SavedRecipe id.

The client always knows the recipe id — it just rendered a result card.
Making it look up a SavedRecipe id first would mean an extra round trip
for every unsave, and the unique constraint on (user, recipe) means the
pair already identifies the row.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from core.exceptions import DuplicateResourceError, ResourceNotFoundError
from recipes.models import Recipe, SavedRecipe


class SavedRecipeService:

    @staticmethod
    def list_for(user):
        # select_related on the recipe because every serialised row reads
        # its name and cook time; without it this is one query per card.
        return SavedRecipe.objects.filter(user=user).select_related("recipe")

    @staticmethod
    def saved_recipe_ids(user) -> list[int]:
        """
        Just the ids.

        Exists so a client can mark which search results are already saved
        without that flag going into the recommendation response. Putting it
        there would make the cached payload user-specific in a way the cache
        key comments promise it is not.
        """
        return list(
            SavedRecipe.objects.filter(user=user).values_list("recipe_id", flat=True)
        )

    @staticmethod
    @transaction.atomic
    def save(user, recipe_id: int, notes: str = "") -> SavedRecipe:
        if not Recipe.objects.filter(pk=recipe_id).exists():
            raise ResourceNotFoundError("Recipe not found.")

        try:
            return SavedRecipe.objects.create(
                user=user, recipe_id=recipe_id, notes=notes
            )
        except IntegrityError:
            # The unique constraint is the authority. Checking first and
            # then creating would leave a race between the two statements.
            raise DuplicateResourceError(
                "That recipe is already in your book."
            ) from None

    @staticmethod
    def update_notes(user, recipe_id: int, notes: str) -> SavedRecipe:
        try:
            saved = SavedRecipe.objects.select_related("recipe").get(
                user=user, recipe_id=recipe_id
            )
        except SavedRecipe.DoesNotExist:
            raise ResourceNotFoundError("That recipe is not in your book.") from None

        saved.notes = notes
        saved.save(update_fields=["notes", "updated_at"])
        return saved

    @staticmethod
    def remove(user, recipe_id: int) -> None:
        deleted, _ = SavedRecipe.objects.filter(
            user=user, recipe_id=recipe_id
        ).delete()
        if not deleted:
            raise ResourceNotFoundError("That recipe is not in your book.")