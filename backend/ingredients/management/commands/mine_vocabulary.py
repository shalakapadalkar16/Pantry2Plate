"""
Measure the gap between the current vocabulary and real recipe text.

Streams the corpus, counts every distinct ingredient string, runs each one
through the matcher, and reports coverage.

Since compound splitting landed, a string has three possible outcomes
rather than two, and collapsing them would hide which problem is which:

  * full     — every part resolved
  * partial  — some parts resolved, at least one did not ("salt and
               unobtainium"). Counted as a miss for coverage, because a
               recipe with an unknown fragment can never be fully cooked
               from a pantry.
  * none     — nothing resolved

    python manage.py mine_vocabulary
    python manage.py mine_vocabulary --limit 20000 --no-fuzzy

Uses only the standard library. Pandas would be convenient, but it is a
large dependency to add to a production requirements file for a script
that streams a CSV once.
"""

import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_SOURCE = "data/raw/RAW_recipes.csv"
DEFAULT_OUTPUT = "data/vocabulary_report.json"

csv.field_size_limit(sys.maxsize)


class Command(BaseCommand):
    help = "Measure matcher coverage against the recipe corpus."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=DEFAULT_SOURCE)
        parser.add_argument("--output", default=DEFAULT_OUTPUT)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--top", type=int, default=400)
        parser.add_argument(
            "--no-fuzzy",
            action="store_true",
            help="Deterministic rungs only. The honest lower bound.",
        )

    def handle(self, *args, **options):
        from ingredients.matcher import matcher

        path = Path(settings.BASE_DIR) / options["path"]
        if not path.exists():
            raise CommandError(f"Corpus not found: {path}")

        counts, recipes, malformed, samples = self._read(path, options["limit"])
        if not counts:
            raise CommandError("No ingredients parsed. Check the column name.")

        self.stdout.write("\nSample ingredient lists:")
        for sample in samples:
            self.stdout.write(f"  {sample}")

        matcher.load()
        allow_fuzzy = not options["no_fuzzy"]

        full_occ = partial_occ = none_occ = 0
        full_distinct = partial_distinct = 0
        by_method = Counter()
        compound_occ = 0
        unmatched: list[tuple[str, int]] = []
        partial_examples: list[tuple[str, int]] = []

        for raw, count in counts.items():
            results = matcher.match_all(raw, allow_fuzzy=allow_fuzzy)
            resolved = [r for r in results if r.matched]

            if len(results) > 1:
                compound_occ += count

            for r in resolved:
                by_method[r.method] += count

            if resolved and len(resolved) == len(results):
                full_occ += count
                full_distinct += 1
            elif resolved:
                partial_occ += count
                partial_distinct += 1
                partial_examples.append((raw, count))
            else:
                none_occ += count
                unmatched.append((raw, count))

        total_distinct = len(counts)
        total_occ = sum(counts.values())
        unmatched.sort(key=lambda p: -p[1])
        partial_examples.sort(key=lambda p: -p[1])

        self._report(
            recipes=recipes,
            malformed=malformed,
            total_distinct=total_distinct,
            total_occ=total_occ,
            full_occ=full_occ,
            partial_occ=partial_occ,
            none_occ=none_occ,
            full_distinct=full_distinct,
            partial_distinct=partial_distinct,
            compound_occ=compound_occ,
            by_method=by_method,
            counts=counts,
            unmatched=unmatched,
            partial_examples=partial_examples,
        )

        out_path = Path(settings.BASE_DIR) / options["output"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "recipes": recipes,
                    "distinct_strings": total_distinct,
                    "total_occurrences": total_occ,
                    "fully_resolved_occurrences": full_occ,
                    "partially_resolved_occurrences": partial_occ,
                    "unresolved_occurrences": none_occ,
                    "compound_occurrences": compound_occ,
                    "fuzzy_enabled": allow_fuzzy,
                    "unmatched_top": [
                        {"text": t, "count": c} for t, c in unmatched[: options["top"]]
                    ],
                    "partial_top": [
                        {"text": t, "count": c} for t, c in partial_examples[:100]
                    ],
                },
                indent=2,
            )
        )
        self.stdout.write(self.style.SUCCESS(f"\nReport written to {out_path}"))

    # ------------------------------------------------------------------ io

    def _read(self, path: Path, limit: int):
        counts: Counter[str] = Counter()
        recipes = malformed = 0
        samples: list[str] = []

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "ingredients" not in reader.fieldnames:
                raise CommandError(f"No 'ingredients' column: {reader.fieldnames}")

            for row in reader:
                try:
                    # Lists are stored as Python literals inside CSV cells.
                    # literal_eval, never eval — this is untrusted input.
                    items = ast.literal_eval(row["ingredients"])
                except (ValueError, SyntaxError):
                    malformed += 1
                    continue

                if not isinstance(items, list):
                    malformed += 1
                    continue

                if len(samples) < 3:
                    samples.append(str(items[:8]))

                counts.update(str(i).strip() for i in items if str(i).strip())
                recipes += 1

                if limit and recipes >= limit:
                    break

        return counts, recipes, malformed, samples

    # -------------------------------------------------------------- report

    def _report(self, **k):
        w = self.stdout.write
        total_occ = k["total_occ"]

        w(f"\n{'=' * 62}")
        w("CORPUS")
        w(f"{'=' * 62}")
        w(f"  recipes parsed        {k['recipes']:,}")
        w(f"  malformed rows        {k['malformed']:,}")
        w(f"  ingredient mentions   {total_occ:,}")
        w(f"  distinct strings      {k['total_distinct']:,}")

        w(f"\n{'=' * 62}")
        w("RESOLUTION (by occurrence)")
        w(f"{'=' * 62}")
        for label, value in (
            ("fully resolved", k["full_occ"]),
            ("partially resolved", k["partial_occ"]),
            ("unresolved", k["none_occ"]),
        ):
            w(f"  {label:20} {100 * value / total_occ:5.1f}%  ({value:,})")

        w(f"\n  compound strings     {100 * k['compound_occ'] / total_occ:5.1f}%"
          f"  ({k['compound_occ']:,})")

        if k["by_method"]:
            resolved_total = sum(k["by_method"].values())
            w("\n  resolved via:")
            for method, count in k["by_method"].most_common():
                w(f"    {method:14} {100 * count / resolved_total:5.1f}%")

        w(f"\n{'=' * 62}")
        w("HEAD/TAIL — distinct strings needed for X% of all mentions")
        w(f"{'=' * 62}")
        ordered = sorted(k["counts"].values(), reverse=True)
        running, idx = 0, 0
        targets = [50, 80, 90, 95, 99]
        for rank, count in enumerate(ordered, start=1):
            running += count
            while idx < len(targets) and running >= total_occ * targets[idx] / 100:
                w(f"  {targets[idx]:3d}%  →  {rank:,} strings")
                idx += 1
            if idx >= len(targets):
                break

        if k["partial_examples"]:
            w(f"\n{'=' * 62}")
            w("PARTIALLY RESOLVED — one fragment still unknown")
            w(f"{'=' * 62}")
            for text, count in k["partial_examples"][:15]:
                w(f"  {count:7,}  {text}")

        w(f"\n{'=' * 62}")
        w("TOP UNMATCHED — curate these first")
        w(f"{'=' * 62}")
        for text, count in k["unmatched"][:30]:
            w(f"  {count:7,}  {text}")