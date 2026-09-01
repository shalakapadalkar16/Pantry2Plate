"""
Elasticsearch layer for coverage search.

The Postgres implementation in recommendations/services.py is the reference:
it defines correct behaviour and gives the latency baseline. This exists to
be compared against it, not to replace it on faith.

Why Elasticsearch can win here: the Postgres query aggregates
recipes_recipeingredient for every ingredient the user owns. Common
ingredients like onion appear in ~50k recipes, so a 15-item pantry touches
a few hundred thousand rows before any filtering happens. Elasticsearch
stores each recipe as one document with its ingredient ids as an array, so
the same question is one pass over an inverted index instead of a join and
a GROUP BY.

The query shape is `terms_set`, which exists for exactly this problem:
match documents where at least N of the supplied terms are present, with N
computed per document. That maps directly onto the coverage rule:

    matched >= n_required - max_missing        (i.e. missing <= max_missing)
"""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings

INDEX_NAME = "recipes"

# Ranking is folded into a single score so results need one sort key rather
# than two scripts. missing is the primary signal, have breaks ties:
#
#     score = (MISSING_WEIGHT - missing) * 1000 + have
#
# MISSING_WEIGHT exceeds the max_missing ceiling (10) so the term never goes
# negative, and 1000 exceeds any plausible ingredient count so `have` can
# never outrank a lower `missing`. Sorting by score descending therefore
# gives missing ascending, then have descending — the same ordering as the
# SQL "best" mode.
MISSING_WEIGHT = 20
MISSING_SCALE = 1000

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        # Single-node cluster. Asking for a replica leaves the index yellow
        # forever with nowhere to place it.
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "external_id": {"type": "keyword"},
            "name": {
                "type": "text",
                # Kept for eventual free-text search. Coverage search never
                # queries it, so it costs indexing time and nothing else.
                "fields": {"raw": {"type": "keyword", "ignore_above": 256}},
            },
            # Non-staple, resolved ingredient ids only. Staples are excluded
            # because they are assumed present; unresolved ingredients have
            # no id, so they cannot appear here and can never be matched —
            # which is why they always count as missing.
            "ingredient_ids": {"type": "integer"},
            "n_required": {"type": "short"},
            "n_unresolved": {"type": "short"},
            "n_ingredients": {"type": "short"},
            "minutes": {"type": "integer"},
            "tags": {"type": "keyword"},
            "calories": {"type": "float"},
        }
    },
}


@lru_cache(maxsize=1)
def get_client():
    """
    One client per process.

    Cached because constructing it opens a connection pool, and both the
    request path and the indexing command reach for it repeatedly.
    """
    from elasticsearch import Elasticsearch

    return Elasticsearch(
        settings.ELASTICSEARCH_URL,
        request_timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )


def index_exists() -> bool:
    return bool(get_client().indices.exists(index=INDEX_NAME))


def build_document(recipe_row: dict, ingredient_ids: list[int]) -> dict:
    """One recipe as a flat document. recipe_row comes from values()."""
    return {
        "external_id": recipe_row["external_id"],
        "name": recipe_row["name"],
        "ingredient_ids": ingredient_ids,
        "n_required": recipe_row["n_required"],
        "n_unresolved": recipe_row["n_unresolved"],
        "n_ingredients": recipe_row["n_ingredients"],
        "minutes": recipe_row["minutes"],
        "tags": recipe_row["tags"],
        "calories": recipe_row["calories"],
    }


def build_query(
    pantry_ids: list[int],
    *,
    max_missing: int,
    tag_groups: list[list[str]] | None = None,
    max_minutes: int | None = None,
    min_required: int | None = 3,
) -> dict:
    """
    Coverage query.

    terms_set with a per-document minimum is the whole trick. Without it
    this would need either one query per possible n_required value or a
    script filter over the entire index.
    """
    filters: list[dict] = [
        {
            "terms_set": {
                "ingredient_ids": {
                    "terms": pantry_ids,
                    "minimum_should_match_script": {
                        # At least one match is required regardless, matching
                        # the SQL behaviour: a recipe you have nothing for is
                        # not a pantry recommendation.
                        "source": (
                            "Math.max(1, doc['n_required'].value - params.slack)"
                        ),
                        "params": {"slack": max_missing},
                    },
                }
            }
        },
        # A recipe needing more than the pantry could ever cover cannot
        # qualify. Same pruning as the SQL version.
        {"range": {"n_required": {"gte": 1, "lte": len(pantry_ids) + max_missing}}},
    ]

    if min_required:
        filters.append({"range": {"n_required": {"gte": min_required}}})

    if max_minutes:
        filters.append({"range": {"minutes": {"gt": 0, "lte": max_minutes}}})

    # One terms clause per mood: tags inside a mood are OR, moods are AND.
    for group in tag_groups or []:
        filters.append({"terms": {"tags": group}})

    return {
        "function_score": {
            "query": {"bool": {"filter": filters}},
            # The (int) cast is load-bearing. doc values for an integer
            # field are longs, params.pantry arrives from JSON as
            # List<Integer>, and Integer.equals(Long) is always false in
            # Java - so without it `have` is silently always zero and
            # ranking collapses to n_required ascending. Totals stay
            # correct because terms_set does the filtering, which is what
            # made the bug invisible.
        "script_score": {
                "script": {
                    "source": (
                        "int have = 0;"
                        "for (def id : doc['ingredient_ids']) {"
                        "  if (params.pantry.contains((int) id)) { have++; }"
                        "}"
                        "int missing = (int) doc['n_required'].value - have;"
                        "return (params.weight - missing) * params.scale + have;"
                    ),
                    "params": {
                        "pantry": pantry_ids,
                        "weight": MISSING_WEIGHT,
                        "scale": MISSING_SCALE,
                    },
                }
            },
            # replace, not multiply: relevance scoring is meaningless here.
            # The only thing that ranks a recipe is how well it fits the
            # pantry.
            "boost_mode": "replace",
        }
    }


def decode_score(score: float, n_required: int) -> tuple[int, int]:
    """Recover (have, missing) from the packed score."""
    have = int(round(score)) % MISSING_SCALE
    missing = n_required - have
    return have, missing