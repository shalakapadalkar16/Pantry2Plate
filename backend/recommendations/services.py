"""
Coverage ranking.

Given the set of ingredient ids in a user's pantry, return recipes ordered
by how many ingredients they are missing.

Deliberately plain SQL against Postgres before any Elasticsearch work. Two
reasons: it produces the correct results an ES implementation can be
checked against, and it gives a latency baseline. "Postgres did it in X ms,
Elasticsearch in Y" is a real answer; "I used Elasticsearch because it is
for search" is not.

The maths, with staples and unresolved rows already handled at import:

    n_required = non-staple ingredient rows on the recipe
    have       = non-staple rows whose ingredient is in the pantry
    missing    = n_required - have
    coverage   = have / n_required

Staples never enter the denominator, so a recipe needing salt is not
penalised. Unresolved rows have a null ingredient and are non-staple, so
they sit in n_required and can never be matched — they always count as
missing, which is correct: the user cannot confirm having something the
matcher could not name.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import connection

from recipes.models import Recipe, RecipeIngredient


@dataclass
class RecipeMatch:
    recipe: Recipe
    have: int
    missing: int
    coverage: float
    missing_ingredients: list[str] = field(default_factory=list)
    unknown_ingredients: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    matches: list[RecipeMatch]
    total: int
    offset: int
    limit: int


# Fewest missing first, then GREATEST OVERLAP.
#
# Ordering by coverage ratio was the first attempt and it was wrong: once
# missing = 0, every recipe has coverage exactly 1.0, so the ratio carries
# no information and the tiebreak decided everything. Results were
# two-ingredient recipes — "roast onions", "salty milk biscuits" — which
# are technically cookable and useless as recommendations.
#
# Absolute overlap is the signal that matters. A recipe using eight things
# from your pantry is a better answer than one using two.
ORDERINGS = {
    "best": "missing ASC, have DESC, r.minutes ASC NULLS LAST",
    "quickest": "r.minutes ASC NULLS LAST, missing ASC, have DESC",
    "simplest": "missing ASC, r.n_required ASC",
}


class CoverageSearch:

    @staticmethod
    def pantry_ingredient_ids(user) -> list[int]:
        from pantry.models import PantryItem

        return list(
            PantryItem.objects.filter(user=user, ingredient__isnull=False)
            .values_list("ingredient_id", flat=True)
            .distinct()
        )

    # ----------------------------------------------------------------- sql

    @staticmethod
    def _where_clause(*, tag_groups, max_minutes, min_required) -> str:
        filters = [
            "(r.n_required - m.have) <= %(max_missing)s",
            "r.n_required > 0",
            # Candidate pruning. A recipe needing more ingredients than the
            # pantry can possibly cover cannot qualify, and n_required is
            # indexed — a cheap filter that removes most of the corpus
            # before the expensive sort.
            "r.n_required <= %(max_possible_required)s",
        ]
        if min_required:
            filters.append("r.n_required >= %(min_required)s")

        # One overlap test per mood. Tags within a mood are OR (array
        # overlap); moods are AND (separate conditions). Someone asking for
        # quick AND vegetarian means both, not either.
        for index in range(len(tag_groups or [])):
            # Explicit cast required: r.tags is varchar[] (ArrayField of
            # CharField) while psycopg2 sends a Python list as text[],
            # and Postgres has no varchar[] && text[] operator.
            filters.append(f"r.tags && %(tags_{index})s::varchar[]")

        if max_minutes:
            filters.append("r.minutes IS NOT NULL AND r.minutes <= %(max_minutes)s")
        return " AND ".join(filters)

    @classmethod
    def search(
        cls,
        pantry_ids: list[int],
        *,
        max_missing: int = 0,
        limit: int = 20,
        offset: int = 0,
        tag_groups: list[list[str]] | None = None,
        max_minutes: int | None = None,
        min_required: int | None = 3,
        order: str = "best",
    ) -> SearchResult:
        """
        min_required defaults to 3 because a two-ingredient recipe is not a
        useful recommendation even when it scores perfectly.

        A recipe only appears if the pantry covers at least one of its
        required ingredients. A recipe you have nothing for is not a pantry
        recommendation, and including them would flood results whenever
        max_missing is raised.
        """
        if not pantry_ids:
            return SearchResult([], 0, offset, limit)

        tag_groups = tag_groups or []
        where = cls._where_clause(
            tag_groups=tag_groups,
            max_minutes=max_minutes,
            min_required=min_required,
        )
        order_by = ORDERINGS.get(order, ORDERINGS["best"])

        # COUNT(*) OVER () gives the total in the same pass as the page. An
        # earlier version ran the aggregate twice — once for rows, once for
        # a count — doubling the work for a number in a pagination header.
        sql = f"""
            WITH matches AS (
                SELECT recipe_id, COUNT(*) AS have
                FROM recipes_recipeingredient
                WHERE ingredient_id = ANY(%(pantry_ids)s)
                  AND NOT is_staple
                GROUP BY recipe_id
            )
            SELECT
                r.id,
                m.have,
                (r.n_required - m.have) AS missing,
                (m.have::float / r.n_required) AS coverage,
                COUNT(*) OVER () AS total
            FROM matches m
            JOIN recipes_recipe r ON r.id = m.recipe_id
            WHERE {where}
            ORDER BY {order_by}
            LIMIT %(limit)s OFFSET %(offset)s
        """

        params = {
            "pantry_ids": pantry_ids,
            "max_missing": max_missing,
            "max_possible_required": len(pantry_ids) + max_missing,
            "min_required": min_required,
            "max_minutes": max_minutes,
            "limit": limit,
            "offset": offset,
        }
        for index, group in enumerate(tag_groups):
            params[f"tags_{index}"] = group

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            return SearchResult([], 0, offset, limit)

        total = rows[0][4]

        # Fetch Recipe objects in one query, then restore the SQL ordering
        # from a dict rather than asking the database to sort twice.
        ordered_ids = [row[0] for row in rows]
        recipes = Recipe.objects.in_bulk(ordered_ids)

        matches = [
            RecipeMatch(
                recipe=recipes[recipe_id],
                have=have,
                missing=missing,
                coverage=round(coverage, 3),
            )
            for recipe_id, have, missing, coverage, _ in rows
            if recipe_id in recipes
        ]

        # Only the visible page gets its ingredient breakdown. Doing this
        # for every qualifying recipe would defeat pagination.
        cls._annotate_ingredients(matches, set(pantry_ids))

        return SearchResult(matches, total, offset, limit)

    # --------------------------------------------------------- page detail

    @staticmethod
    def _annotate_ingredients(matches: list[RecipeMatch], pantry: set[int]) -> None:
        """Fill in what the user is missing, for this page only."""
        if not matches:
            return

        by_recipe = {match.recipe.pk: match for match in matches}

        rows = (
            RecipeIngredient.objects
            .filter(recipe_id__in=by_recipe.keys(), is_staple=False)
            .select_related("ingredient")
            .order_by("recipe_id", "position")
        )

        for row in rows:
            match = by_recipe.get(row.recipe_id)
            if match is None:
                continue

            if row.ingredient_id is None:
                # Kept separate from "missing" in the response: the system
                # could not identify this, so it is unknown rather than
                # known to be absent. Both count against coverage.
                match.unknown_ingredients.append(row.raw_text)
            elif row.ingredient_id not in pantry:
                match.missing_ingredients.append(row.ingredient.display_name)


class RecommendationService:
    """Thin wrapper so views never assemble a pantry id list themselves."""

    @staticmethod
    def for_user(user, **kwargs) -> SearchResult:
        pantry_ids = CoverageSearch.pantry_ingredient_ids(user)
        return CoverageSearch.search(pantry_ids, **kwargs)