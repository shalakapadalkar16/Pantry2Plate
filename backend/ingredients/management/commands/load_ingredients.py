"""
Load the seed ingredient vocabulary.

Idempotent. Safe to re-run after editing seed_ingredients.json — existing
rows are updated, new aliases added, nothing is deleted.

    python manage.py load_ingredients
    python manage.py load_ingredients --path data/seed_ingredients.json
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ingredients.models import Ingredient, IngredientAlias, normalize_name

DEFAULT_PATH = "data/seed_ingredients.json"


class Command(BaseCommand):
    help = "Load canonical ingredients and aliases from a JSON seed file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=DEFAULT_PATH,
            help=f"Path to the seed file, relative to BASE_DIR (default: {DEFAULT_PATH})",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / options["path"]
        if not path.exists():
            raise CommandError(f"Seed file not found: {path}")

        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"Seed file is not valid JSON: {exc}") from None

        rows = payload.get("ingredients")
        if not rows:
            raise CommandError("Seed file has no 'ingredients' key.")

        created = updated = alias_created = 0
        seen_aliases: dict[str, str] = {}

        for row in rows:
            canonical = row["canonical_name"]

            ingredient, was_created = Ingredient.objects.update_or_create(
                canonical_name=canonical,
                defaults={
                    "display_name": row["display_name"],
                    "category": row.get("category", "other"),
                    "default_unit": row.get("default_unit", "piece"),
                    "is_staple": row.get("is_staple", False),
                },
            )
            created += was_created
            updated += not was_created

            for alias in row.get("aliases", []):
                key = normalize_name(alias)
                if not key:
                    continue

                # An alias pointing at two ingredients silently corrupts every
                # lookup that uses it. Fail loudly instead.
                if key in seen_aliases and seen_aliases[key] != canonical:
                    raise CommandError(
                        f"Alias '{alias}' is claimed by both "
                        f"'{seen_aliases[key]}' and '{canonical}'."
                    )
                seen_aliases[key] = canonical

                _, alias_was_created = IngredientAlias.objects.update_or_create(
                    alias=key, defaults={"ingredient": ingredient}
                )
                alias_created += alias_was_created

        staples = Ingredient.objects.filter(is_staple=True).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"Ingredients: {created} created, {updated} updated. "
                f"Aliases: {alias_created} new. "
                f"Staples: {staples}. "
                f"Vocabulary size: {Ingredient.objects.count()}."
            )
        )