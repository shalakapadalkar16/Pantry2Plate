"""
Compare the Postgres and Elasticsearch coverage backends.

Two questions, in this order:

  1. Do they agree? If Elasticsearch returns different recipes, it is
     wrong, and a faster wrong answer is worthless.
  2. Is Elasticsearch actually faster? Postgres does this in ~170ms, which
     is not obviously a problem. Adding a second datastore has to earn its
     place with a number, not with the observation that Elasticsearch is
     for searching.

    python manage.py compare_search
    python manage.py compare_search --runs 10
"""

import statistics
import time

from django.core.management.base import BaseCommand, CommandError

from ingredients.models import Ingredient
from recommendations.es_service import ElasticCoverageSearch
from recommendations.services import CoverageSearch

# Pantries of increasing size. Larger pantries hurt Postgres more, because
# the aggregate touches every recipe_ingredient row for every ingredient
# owned, and common ingredients appear in tens of thousands of recipes.
PANTRIES = {
    "small (5)": ["egg", "milk", "butter", "all-purpose-flour", "sugar"],
    "medium (15)": [
        "chicken-breast", "rice", "onion", "garlic", "peas", "soy-sauce",
        "egg", "carrot", "butter", "milk", "cheddar", "pasta",
        "canned-tomato", "potato", "all-purpose-flour",
    ],
    "large (30)": [
        "chicken-breast", "chicken-thigh", "ground-beef", "bacon", "rice",
        "pasta", "onion", "garlic", "ginger", "carrot", "celery", "potato",
        "bell-pepper", "mushroom", "spinach", "peas", "corn", "egg", "milk",
        "butter", "cheddar", "mozzarella", "heavy-cream", "yogurt",
        "canned-tomato", "tomato-paste", "soy-sauce", "stock", "lemon",
        "all-purpose-flour",
    ],
}


class Command(BaseCommand):
    help = "Compare SQL and Elasticsearch coverage search."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=5)
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not ElasticCoverageSearch.available():
            raise CommandError(
                "Elasticsearch unreachable. Try: docker compose up -d elasticsearch"
            )

        runs = options["runs"]
        limit = options["limit"]

        self.stdout.write(f"\n{runs} runs per case, limit={limit}\n")
        header = (
            f"{'pantry':14} {'miss':>4} {'sql ms':>8} {'es ms':>8} "
            f"{'speedup':>8} {'sql n':>7} {'es n':>7} {'top20':>6}"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        disagreements = []

        for label, names in PANTRIES.items():
            ids = list(
                Ingredient.objects.filter(canonical_name__in=names)
                .values_list("id", flat=True)
            )
            if not ids:
                self.stderr.write(f"no ingredients resolved for {label}")
                continue

            for max_missing in (0, 1, 2):
                sql_ms, sql_result = self._time(
                    CoverageSearch.search, ids, max_missing, limit, runs
                )
                es_ms, es_result = self._time(
                    ElasticCoverageSearch.search, ids, max_missing, limit, runs
                )

                sql_ids = [m.recipe.pk for m in sql_result.matches]
                es_ids = [m.recipe.pk for m in es_result.matches]
                overlap = len(set(sql_ids) & set(es_ids))

                speedup = sql_ms / es_ms if es_ms else 0
                self.stdout.write(
                    f"{label:14} {max_missing:>4} {sql_ms:>8.1f} {es_ms:>8.1f} "
                    f"{speedup:>7.1f}x {sql_result.total:>7,} "
                    f"{es_result.total:>7,} {overlap:>4}/{len(sql_ids)}"
                )

                if sql_result.total != es_result.total:
                    disagreements.append(
                        f"{label} miss={max_missing}: "
                        f"totals differ, sql={sql_result.total} es={es_result.total}"
                    )
                if overlap < len(sql_ids):
                    disagreements.append(
                        f"{label} miss={max_missing}: "
                        f"top-{limit} overlap {overlap}/{len(sql_ids)}"
                    )

                # The have/missing arithmetic must agree exactly. If the
                # packed score decodes wrong, ranking is wrong even when the
                # result set matches.
                for sql_match, es_match in zip(sql_result.matches, es_result.matches):
                    if sql_match.recipe.pk != es_match.recipe.pk:
                        break
                    if (sql_match.have, sql_match.missing) != (
                        es_match.have, es_match.missing
                    ):
                        disagreements.append(
                            f"{label} miss={max_missing}: recipe "
                            f"{sql_match.recipe.pk} sql=({sql_match.have},"
                            f"{sql_match.missing}) es=({es_match.have},"
                            f"{es_match.missing})"
                        )

        self.stdout.write("")
        if disagreements:
            self.stdout.write(self.style.ERROR("DISAGREEMENTS"))
            for line in disagreements[:20]:
                self.stdout.write(f"  {line}")
            self.stdout.write(
                "\nOrdering differences on equal scores are expected — ties "
                "break arbitrarily in both engines. Differing totals or "
                "have/missing values are real bugs."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Backends agree on totals, membership and counts.")
            )

    @staticmethod
    def _time(fn, ids, max_missing, limit, runs):
        """Median of N runs. The first call warms caches in both engines."""
        fn(ids, max_missing=max_missing, limit=limit)

        timings = []
        result = None
        for _ in range(runs):
            start = time.perf_counter()
            result = fn(ids, max_missing=max_missing, limit=limit)
            timings.append((time.perf_counter() - start) * 1000)

        return statistics.median(timings), result