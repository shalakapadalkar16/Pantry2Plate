"""
Recommendation response caching.

Coverage search costs 30-200ms and the inputs barely move: a pantry changes
a few times a day, and the recipe corpus changes only on reimport. That is
a good cache.

Invalidation is handled by the key, not by signals.

The key contains a hash of the pantry's ingredient ids. Change the pantry
and the key changes, so a stale entry is unreachable rather than wrong.
Nothing has to notice the write, nothing has to fire, and there is no
window where old data is served. Signal-based invalidation would have been
solving a problem the key shape already solves — and would have introduced
a coupling where the pantry app needs to know recommendations exist.

Two consequences worth knowing:

  * Removing an ingredient and adding it back reuses the earlier entry.
    That is correct, not a bug: the pantry is genuinely in the same state.
  * Old entries are never deleted, only orphaned. TTL exists for memory
    reclamation, not correctness.

Quantities are deliberately excluded from the hash. Coverage is
presence-based, so changing "2 onions" to "3 onions" cannot change a
result and should not cost a cache miss.
"""

from __future__ import annotations

import hashlib
import json

from django.core.cache import cache

# Bump when the corpus is reimported or the ranking changes. Recipe data is
# not part of the key, so nothing else would invalidate results computed
# against an older index.
CORPUS_VERSION = 1

# Purely for memory reclamation — staleness is impossible by construction.
TTL_SECONDS = 24 * 60 * 60

KEY_PREFIX = "reco"


def _pantry_digest(pantry_ids: list[int]) -> str:
    """
    Stable short digest of a pantry.

    Sorted so that insertion order cannot produce two keys for one pantry.
    Truncated to 16 hex chars: 64 bits is far more than enough to avoid
    collisions across a key space this small, and full digests make keys
    unwieldy in redis-cli.
    """
    payload = ",".join(str(i) for i in sorted(pantry_ids))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_key(user_id: int, pantry_ids: list[int], params: dict) -> str:
    """
    Key layout: reco:v{corpus}:u{user}:p{pantry}:q{query}

    user_id is included even though the response is currently derived
    entirely from the pantry and the query — two users with identical
    pantries would get byte-identical payloads, so cross-user sharing would
    work today and roughly double the hit rate.

    It is scoped per user anyway. The response is very likely to gain
    user-specific fields (a saved-recipe flag is the obvious one), and a
    shared cache would turn that from a feature into a data leak. Paying
    for hit rate now is cheaper than a privacy bug later.
    """
    query = json.dumps(params, sort_keys=True, default=str)
    query_digest = hashlib.sha256(query.encode()).hexdigest()[:16]
    return (
        f"{KEY_PREFIX}:v{CORPUS_VERSION}"
        f":u{user_id}"
        f":p{_pantry_digest(pantry_ids)}"
        f":q{query_digest}"
    )


def get(key: str):
    """
    Read through, swallowing backend failures.

    A cache is an optimisation. If Redis is down the endpoint should be
    slow, not broken.
    """
    try:
        return cache.get(key)
    except Exception:
        return None


def set(key: str, payload, ttl: int = TTL_SECONDS) -> None:
    try:
        cache.set(key, payload, ttl)
    except Exception:
        pass


def clear_all() -> int:
    """
    Drop every cached recommendation.

    Only needed when CORPUS_VERSION should have been bumped and was not.
    Uses delete_pattern, which is a SCAN under the hood — acceptable for an
    admin action, never on a request path.
    """
    try:
        return cache.delete_pattern(f"{KEY_PREFIX}:*")
    except (AttributeError, Exception):
        return 0