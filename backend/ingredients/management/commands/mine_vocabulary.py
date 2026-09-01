"""
Measure the gap between the current vocabulary and real recipe text.

Streams the corpus, counts every distinct ingredient string, runs each one
through the matcher, and reports coverage two ways:

  * occurrence-weighted — the number that matters. 'salt' appearing 90,000
    times counts 90,000 times. This is what a user experiences.
  * distinct-string     — how much of the long tail is covered. Always
    much lower, and mostly not worth chasing.

Also writes the highest-frequency unmatched strings to a JSON file so
curation is driven by data rather than guesswork.

    python manage.py mine_vocabulary
    python manage.py mine_vocabulary --limit 20000 --top 500

Uses only the standard library. Pandas would be convenient for a one-off
analysis, but it is a large dependency to add to a production requirements
file for a script that streams a CSV once.
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

# Steps and descriptions blow past the default CSV field limit.
csv.field_size_limit(sys.maxsize)


class Command(BaseCommand):
    help = "Measure matcher coverage against the recipe corpus."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=DEFAULT_SOURCE)
        parser.add_argument("--output", default=DEFAULT_OUTPUT)
        parser.add_argument(
            "--limit", type=int, default=0, help="Stop after N recipes (0 = all)."
        )
        parser.add_argument(
            "--top", type=int, default=400, help="How many unmatched strings to report."
        )
        parser.add_argument(
            "--no-fuzzy",
            action="store_true",
            help="Measure deterministic rungs only. The honest lower bound.",
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

        matched_distinct = 0
        matched_occurrences = 0
        by_method = Counter()
        unmatched: list[tuple[str, int]] = []

        for raw, count in counts.items():
            result = matcher.match(raw, allow_fuzzy=allow_fuzzy)
            if result.matched:
                matched_distinct += 1
                matched_occurrences += count
                by_method[result.method] += count
            else:
                unmatched.append((raw, count))

        total_distinct = len(counts)
        total_occurrences = sum(counts.values())
        unmatched.sort(key=lambda pair: -pair[1])

        self._report(
            recipes=recipes,
            malformed=malformed,
            total_distinct=total_distinct,
            total_occurrences=total_occurrences,
            matched_distinct=matched_distinct,
            matched_occurrences=matched_occurrences,
            by_method=by_method,
            counts=counts,
            unmatched=unmatched,
        )

        out_path = Path(settings.BASE_DIR) / options["output"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "recipes": recipes,
                    "distinct_strings": total_distinct,
                    "total_occurrences": total_occurrences,
                    "matched_distinct": matched_distinct,
                    "matched_occurrences": matched_occurrences,
                    "fuzzy_enabled": allow_fuzzy,
                    "unmatched_top": [
                        {"text": text, "count": count}
                        for text, count in unmatched[: options["top"]]
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
                raise CommandError(
                    f"No 'ingredients' column. Found: {reader.fieldnames}"
                )

            for row in reader:
                try:
                    # The dump stores lists as Python literals inside CSV
                    # cells, so this is literal_eval rather than a split.
                    # literal_eval, never eval — the file is untrusted input.
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

    def _report(
        self,
        *,
        recipes,
        malformed,
        total_distinct,
        total_occurrences,
        matched_distinct,
        matched_occurrences,
        by_method,
        counts,
        unmatched,
    ):
        w = self.stdout.write

        w(f"\n{'=' * 62}")
        w("CORPUS")
        w(f"{'=' * 62}")
        w(f"  recipes parsed        {recipes:,}")
        w(f"  malformed rows        {malformed:,}")
        w(f"  ingredient mentions   {total_occurrences:,}")
        w(f"  distinct strings      {total_distinct:,}")
        w(f"  mean per recipe       {total_occurrences / max(recipes, 1):.1f}")

        w(f"\n{'=' * 62}")
        w("MATCH RATE")
        w(f"{'=' * 62}")
        occ_pct = 100 * matched_occurrences / total_occurrences
        dist_pct = 100 * matched_distinct / total_distinct
        w(f"  by occurrence         {occ_pct:5.1f}%  ({matched_occurrences:,})")
        w(f"  by distinct string    {dist_pct:5.1f}%  ({matched_distinct:,})")

        if by_method:
            w("\n  resolved via:")
            for method, count in by_method.most_common():
                share = 100 * count / matched_occurrences
                w(f"    {method:14} {share:5.1f}%")

        # How much of real usage a curated vocabulary of size N would cover.
        # Ingredient frequency is heavily skewed, so this curve is the
        # argument for curating hundreds rather than thousands.
        w(f"\n{'=' * 62}")
        w("HEAD/TAIL — distinct strings needed for X% of all mentions")
        w(f"{'=' * 62}")
        ordered = sorted(counts.values(), reverse=True)
        running = 0
        targets = [50, 80, 90, 95, 99]
        idx = 0
        for rank, count in enumerate(ordered, start=1):
            running += count
            while idx < len(targets) and running >= total_occurrences * targets[idx] / 100:
                w(f"  {targets[idx]:3d}%  →  {rank:,} strings")
                idx += 1
            if idx >= len(targets):
                break

        w(f"\n{'=' * 62}")
        w("TOP UNMATCHED — curate these first")
        w(f"{'=' * 62}")
        for text, count in unmatched[:30]:
            w(f"  {count:7,}  {text}")

        missed = sum(c for _, c in unmatched)
        w(f"\n  top 30 cover {100 * sum(c for _, c in unmatched[:30]) / max(missed, 1):.1f}% of all misses")