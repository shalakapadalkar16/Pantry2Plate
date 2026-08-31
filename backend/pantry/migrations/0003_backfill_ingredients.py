"""
Backfill the ingredient foreign key, raw_input, and canonical units.

Uses historical models via apps.get_model, never the live model classes —
a migration must keep working after the models it touches change again.
The pure helper functions (normalize_name, strip_measures) are safe to
import directly because they touch no database state.
"""

from django.db import migrations


def _build_index(apps):
    """Rebuild the matcher's lookup table from historical models."""
    from ingredients.models import normalize_name

    Ingredient = apps.get_model("ingredients", "Ingredient")
    IngredientAlias = apps.get_model("ingredients", "IngredientAlias")

    index = {}
    for pk, display, canonical in Ingredient.objects.values_list(
        "pk", "display_name", "canonical_name"
    ):
        index[normalize_name(display)] = pk
        index[normalize_name(canonical.replace("-", " "))] = pk

    for alias, ingredient_id in IngredientAlias.objects.values_list(
        "alias", "ingredient_id"
    ):
        index[alias] = ingredient_id

    return index


def _resolve(index, raw):
    """
    Exact rungs only — no fuzzy matching during a migration.

    A fuzzy hit here would silently write a wrong association into the
    database with no record of the guess. Unresolved rows are left null
    and surface in the UI as unmatched, which is recoverable.
    """
    from ingredients.matcher import strip_descriptors, strip_measures
    from ingredients.models import normalize_name

    normalized = normalize_name(raw)
    without_measures = strip_measures(normalized)
    candidates = (
        normalized,
        without_measures,
        strip_descriptors(without_measures),
    )
    for key in candidates:
        if key in index:
            return index[key]
    return None


def _normalize_unit(value):
    from ingredients.units import Unit, UnknownUnitError, parse_unit

    try:
        return parse_unit(value)
    except UnknownUnitError:
        return Unit.PIECE


def forwards(apps, schema_editor):
    PantryItem = apps.get_model("pantry", "PantryItem")
    IngredientLog = apps.get_model("pantry", "IngredientLog")

    index = _build_index(apps)

    # The new unique constraint is (user, ingredient). Two free-text rows
    # like "Olive Oil" and "extra virgin olive oil" now collapse to the
    # same ingredient for the same user, which would violate it. Keep the
    # first and leave the rest unresolved rather than deleting user data.
    claimed = set()

    for item in PantryItem.objects.all().order_by("pk").iterator():
        ingredient_id = _resolve(index, item.ingredient_name)

        if ingredient_id is not None:
            key = (item.user_id, ingredient_id)
            if key in claimed:
                ingredient_id = None
            else:
                claimed.add(key)

        item.raw_input = item.ingredient_name
        item.ingredient_id = ingredient_id
        item.unit = _normalize_unit(item.unit)
        item.save(update_fields=["raw_input", "ingredient_id", "unit"])

    # The log is an append-only historical record, so ingredient_name stays
    # exactly as it was written. The FK is added alongside it for querying,
    # not as a replacement.
    for log in IngredientLog.objects.all().iterator():
        log.ingredient_id = _resolve(index, log.ingredient_name)
        log.unit = _normalize_unit(log.unit)
        log.save(update_fields=["ingredient_id", "unit"])


def backwards(apps, schema_editor):
    """No-op. ingredient_name is still present at this point, so reversing
    this migration loses nothing that cannot be recomputed."""


class Migration(migrations.Migration):

    dependencies = [
        ("pantry", "0002_add_ingredient_fields"),
        ("ingredients", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]