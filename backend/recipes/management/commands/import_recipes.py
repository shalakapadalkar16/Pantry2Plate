"""
Import the recipe corpus into Postgres.

Three things make this run in minutes rather than hours:

  1. Resolution is memoised. The corpus has 2.1M ingredient mentions but
     only ~15k distinct strings, so the matcher is called ~15k times, not
     2.1M. This is the single biggest win.
  2. Rows are bulk inserted in batches. Postgres returns primary keys from
     bulk_create, so recipes and their ingredients go in two statements per
     batch instead of two per row.
  3. Fuzzy matching is off. It contributes 0.3% on this corpus and is the
     slowest rung by far — every miss scans the whole key list. A wrong
     guess written into the database is also invisible afterwards, unlike
     one made at request time.

    python manage.py import_recipes
    python manage.py import_recipes --limit 5000 --fresh
"""

import ast
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ingredients.models import UnmatchedIngredient
from recipes.models import Recipe, RecipeIngredient

DEFAULT_SOURCE = "data/raw/RAW_recipes.csv"

csv.field_size_limit(sys.maxsize)


class Command(BaseCommand):
    help = "Import recipes from the Food.com corpus."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=DEFAULT_SOURCE)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Delete all existing recipes first. Use after a vocabulary "
                 "change, since the denormalised counters go stale.",
        )

    def handle(self, *args, **options):
        from ingredients.matcher import matcher

        path = Path(settings.BASE_DIR) / options["path"]
        if not path.exists():
            raise CommandError(f"Corpus not found: {path}")

        if options["fresh"]:
            deleted, _ = Recipe.objects.all().delete()
            self.stdout.write(f"Deleted {deleted:,} existing rows.")

        matcher.load()

        # raw string -> [(ingredient_id | None, is_staple)]
        # The corpus has ~15k distinct strings across 2.1M mentions, so
        # memoising here turns the matcher from the bottleneck into noise.
        resolution_cache: dict[str, list[tuple[int | None, bool]]] = {}
        misses: Counter[str] = Counter()

        def resolve(raw: str) -> list[tuple[int | None, bool]]:
            cached = resolution_cache.get(raw)
            if cached is not None:
                return cached

            results = matcher.match_all(raw, allow_fuzzy=False)
            out = []
            for r in results:
                if r.matched:
                    out.append((r.ingredient.pk, r.ingredient.is_staple))
                else:
                    out.append((None, False))
            resolution_cache[raw] = out
            return out

        existing = set(Recipe.objects.values_list("external_id", flat=True))
        if existing:
            self.stdout.write(f"Skipping {len(existing):,} already imported.")

        batch: list[tuple[Recipe, list]] = []
        imported = skipped = malformed = 0
        batch_size = options["batch_size"]

        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                external_id = (row.get("id") or "").strip()
                if not external_id or external_id in existing:
                    skipped += 1
                    continue

                parsed = self._build(row, external_id, resolve, misses)
                if parsed is None:
                    malformed += 1
                    continue

                batch.append(parsed)

                if len(batch) >= batch_size:
                    imported += self._flush(batch)
                    batch = []
                    self.stdout.write(f"  {imported:,} imported", ending="\r")
                    self.stdout.flush()

                if options["limit"] and imported + len(batch) >= options["limit"]:
                    break

        if batch:
            imported += self._flush(batch)

        self._record_misses(misses)
        self._summarise(imported, skipped, malformed, resolution_cache, misses)

    # ------------------------------------------------------------- parsing

    def _build(self, row, external_id, resolve, misses):
        """Turn one CSV row into an unsaved Recipe plus its ingredient rows."""
        try:
            raw_ingredients = ast.literal_eval(row.get("ingredients") or "[]")
            tags = ast.literal_eval(row.get("tags") or "[]")
            steps = ast.literal_eval(row.get("steps") or "[]")
            nutrition = ast.literal_eval(row.get("nutrition") or "[]")
        except (ValueError, SyntaxError):
            return None

        if not isinstance(raw_ingredients, list) or not raw_ingredients:
            return None

        seen_ingredients: set[int] = set()
        rows: list[dict] = []

        for raw in raw_ingredients:
            text = str(raw).strip()
            if not text:
                continue

            for ingredient_id, is_staple in resolve(text):
                if ingredient_id is None:
                    misses[text] += 1
                    rows.append(
                        {"ingredient_id": None, "raw_text": text[:500],
                         "is_staple": False}
                    )
                    continue

                # A recipe listing the same canonical ingredient twice
                # would inflate the coverage denominator and make it look
                # harder to cook than it is.
                if ingredient_id in seen_ingredients:
                    continue
                seen_ingredients.add(ingredient_id)
                rows.append(
                    {"ingredient_id": ingredient_id, "raw_text": text[:500],
                     "is_staple": is_staple}
                )

        if not rows:
            return None

        recipe = Recipe(
            external_id=external_id,
            name=(row.get("name") or "").strip()[:500] or "Untitled",
            description=(row.get("description") or "").strip(),
            minutes=self._int(row.get("minutes")),
            n_steps=self._int(row.get("n_steps")) or len(steps),
            steps=steps if isinstance(steps, list) else [],
            tags=[str(t)[:64] for t in tags][:64] if isinstance(tags, list) else [],
            nutrition=nutrition if isinstance(nutrition, list) else [],
            calories=nutrition[0] if isinstance(nutrition, list) and nutrition else None,
            submitted=self._date(row.get("submitted")),
            n_ingredients=len(rows),
            # Staples are assumed present in every kitchen, so they are not
            # part of the coverage denominator. Unresolved rows are, because
            # the user cannot confirm having something we could not name.
            n_required=sum(1 for r in rows if not r["is_staple"]),
            n_unresolved=sum(1 for r in rows if r["ingredient_id"] is None),
        )
        return recipe, rows

    @staticmethod
    def _int(value):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        # A handful of rows carry absurd values (one claims a million
        # minutes). Clamp rather than drop the recipe.
        return parsed if 0 <= parsed <= 100_000 else None

    @staticmethod
    def _date(value):
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------ database

    @transaction.atomic
    def _flush(self, batch) -> int:
        """Two statements per batch instead of two per row."""
        recipes = [recipe for recipe, _ in batch]
        Recipe.objects.bulk_create(recipes, batch_size=1000)

        ingredient_rows = []
        for recipe, rows in batch:
            for position, row in enumerate(rows):
                ingredient_rows.append(
                    RecipeIngredient(
                        recipe_id=recipe.pk, position=position, **row
                    )
                )

        RecipeIngredient.objects.bulk_create(ingredient_rows, batch_size=5000)
        return len(recipes)

    def _record_misses(self, misses: Counter) -> None:
        """
        Bulk write unresolved strings once, at the end.

        A write per miss inside the loop would add hundreds of thousands of
        statements to the import for data nobody reads until afterwards.
        """
        from ingredients.models import normalize_name

        if not misses:
            return

        known = set(UnmatchedIngredient.objects.values_list("raw_text", flat=True))
        new = [
            UnmatchedIngredient(
                raw_text=text[:255],
                normalized=normalize_name(text)[:255],
                hit_count=count,
            )
            for text, count in misses.items()
            if text not in known
        ]
        UnmatchedIngredient.objects.bulk_create(
            new, batch_size=2000, ignore_conflicts=True
        )

    # -------------------------------------------------------------- report

    def _summarise(self, imported, skipped, malformed, cache, misses):
        from django.db.models import Avg, Count, Q

        w = self.stdout.write
        total = Recipe.objects.count()

        w(f"\n\n{'=' * 58}")
        w("IMPORT")
        w(f"{'=' * 58}")
        w(f"  imported this run     {imported:,}")
        w(f"  skipped (existing)    {skipped:,}")
        w(f"  malformed             {malformed:,}")
        w(f"  recipes in database   {total:,}")
        w(f"  ingredient rows       {RecipeIngredient.objects.count():,}")
        w(f"  distinct strings      {len(cache):,}  (matcher calls made)")
        w(f"  unresolved strings    {len(misses):,}")

        if not total:
            return

        stats = Recipe.objects.aggregate(
            clean=Count("id", filter=Q(n_unresolved=0)),
            one_off=Count("id", filter=Q(n_unresolved=1)),
            avg_required=Avg("n_required"),
        )

        w(f"\n{'=' * 58}")
        w("COVERAGE READINESS")
        w(f"{'=' * 58}")
        w(f"  fully resolved        {stats['clean']:,} "
          f"({100 * stats['clean'] / total:.1f}%)")
        w(f"  one unresolved        {stats['one_off']:,} "
          f"({100 * stats['one_off'] / total:.1f}%)")
        w(f"  mean required         {stats['avg_required']:.1f}")
        w("\n  'fully resolved' is the pool for a zero-missing search.")