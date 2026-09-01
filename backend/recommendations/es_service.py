"""
Elasticsearch coverage search.

Returns the same SearchResult dataclass as the SQL implementation, so the
two are interchangeable behind the view. That is deliberate: it makes them
comparable, and it means the SQL path stays usable as a fallback if the
cluster is unavailable.

The ingredient breakdown for the visible page still comes from Postgres.
Duplicating ingredient text into the index would inflate every document to
serve one page of twenty, and Postgres answers it in a single indexed query.
"""

from __future__ import annotations

from recipes.models import Recipe
from recipes.search import INDEX_NAME, build_query, decode_score, get_client

from .services import CoverageSearch, RecipeMatch, SearchResult

# from + size cannot page past this in Elasticsearch without search_after.
# Nobody pages 500 results deep, so the cap is a guard rather than a
# limitation worth engineering around.
MAX_WINDOW = 10_000


class ElasticCoverageSearch:

    @staticmethod
    def available() -> bool:
        """Cheap health check so callers can fall back rather than 500."""
        try:
            return bool(get_client().ping())
        except Exception:
            return False

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
        if not pantry_ids:
            return SearchResult([], 0, offset, limit)

        if offset + limit > MAX_WINDOW:
            return SearchResult([], 0, offset, limit)

        query = build_query(
            pantry_ids,
            max_missing=max_missing,
            tag_groups=tag_groups,
            max_minutes=max_minutes,
            min_required=min_required,
        )

        sort = cls._sort(order)

        response = get_client().search(
            index=INDEX_NAME,
            query=query,
            sort=sort,
            from_=offset,
            size=limit,
            # Exact totals cost more than the default 10k cap, but the SQL
            # path returns an exact count and the two are being compared.
            # An approximate number would make the comparison meaningless.
            track_total_hits=True,
            # Only the fields needed to rebuild the result. The document
            # body is not the source of truth — Postgres is.
            source_includes=["n_required"],
        )

        hits = response["hits"]["hits"]
        total = response["hits"]["total"]["value"]

        if not hits:
            return SearchResult([], total, offset, limit)

        ordered_ids = [int(hit["_id"]) for hit in hits]
        recipes = Recipe.objects.in_bulk(ordered_ids)

        matches = []
        for hit in hits:
            recipe = recipes.get(int(hit["_id"]))
            if recipe is None:
                # Index drifted ahead of the database. Skipping is better
                # than raising: one stale document should not break a page.
                continue

            n_required = hit["_source"]["n_required"]
            have, missing = decode_score(hit["_score"], n_required)
            matches.append(
                RecipeMatch(
                    recipe=recipe,
                    have=have,
                    missing=missing,
                    coverage=round(have / n_required, 3) if n_required else 0.0,
                )
            )

        CoverageSearch._annotate_ingredients(matches, set(pantry_ids))
        return SearchResult(matches, total, offset, limit)

    @staticmethod
    def _sort(order: str) -> list[dict | str]:
        """
        'best' needs no explicit sort: the packed score already encodes
        missing ascending then have descending. The other modes sort on a
        stored field first and use score as the tiebreak.
        """
        if order == "quickest":
            return [
                {"minutes": {"order": "asc", "missing": "_last"}},
                "_score",
            ]
        if order == "simplest":
            return [{"n_required": {"order": "asc"}}, "_score"]
        # minutes is the third key, matching the SQL ordering exactly.
        # The packed score encodes missing and have but not cook time, so
        # without this recipes tied on both were ordered by internal doc
        # order and the two backends disagreed on page membership.
        return [
            "_score",
            {"minutes": {"order": "asc", "missing": "_last"}},
            {"n_required": {"order": "asc"}},
        ]