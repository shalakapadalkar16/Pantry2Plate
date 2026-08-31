"""
Free text -> canonical Ingredient resolution.

Called from two places with very different load profiles:

  * PantryService.add_item     — once per user action
  * import_recipes command     — roughly 1.6M times for a 180k recipe corpus

That second number is why the alias table is loaded into memory once per
process instead of queried per lookup. A DB round trip per call would
dominate import runtime.

Matching is a ladder. Each rung throws away more information than the one
above it, and the first exact hit wins. Stripping only ever runs after an
exact lookup has already failed, which is what makes it safe to remove
words that are sometimes meaningful.

Scope note: this resolves WHICH ingredient, never HOW MUCH. Mass and volume
are not interconvertible without per-ingredient density, which the recipe
dataset does not provide, so coverage scoring is presence-based. See
units.same_dimension().
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F

from .models import Ingredient, IngredientAlias, UnmatchedIngredient, normalize_name
from .units import UNIT_ALIASES

# Leading quantities: "1", "2.5", "1/2", "1 1/2", "2-3".
QUANTITY_PREFIX = re.compile(r"^[\d\s./\-]+")

# Measure words. Built from the unit alias table so the two stay in sync,
# plus packaging nouns that appear in recipe text but never in a pantry.
MEASURE_TOKENS: set[str] = {
    normalize_name(k) for k in UNIT_ALIASES if k
} | {
    "can", "package", "packet", "pkg", "container", "jar", "bottle", "box",
    "bag", "bunch", "head", "stalk", "sprig", "stick", "fillet",
    "strip", "cube", "block", "loaf", "sheet", "sachet", "tin",
}

# Preparation and packaging words that carry no identity information.
#
# NOTE: "ground" is deliberately NOT here. "Ground beef" and "ground cumin"
# are identities, not preparations. Same reasoning for "whole".
DESCRIPTORS: set[str] = {
    "fresh", "frozen", "dried", "canned", "tinned", "jarred", "packaged",
    "chopped", "minced", "diced", "sliced", "grated", "crushed", "mashed",
    "cubed", "julienned", "halved", "quartered", "shredded", "torn",
    "beaten", "whisked", "whipped", "sifted", "packed", "level", "heaping",
    "finely", "roughly", "coarsely", "thinly", "thickly", "lightly",
    "peeled", "seeded", "cored", "trimmed", "rinsed", "drained", "washed",
    "cooked", "uncooked", "raw", "boiled", "roasted", "toasted", "melted",
    "softened", "chilled", "warm", "cold", "hot", "room", "temperature",
    "large", "medium", "small", "extra", "jumbo", "baby", "thick", "thin",
    "organic", "free", "range", "boneless", "skinless", "ripe", "overripe",
    "optional", "divided", "plu", "more", "taste", "needed", "garnish",
    "unsalted", "salted", "sweetened", "unsweetened", "low", "fat", "lean",
    "and", "or", "of", "for", "into", "about", "approximately", "such", "as",
}

# Below this ratio a fuzzy suggestion is more likely wrong than right.
# Re-tune once you have a labelled sample from UnmatchedIngredient.
FUZZY_CUTOFF = 0.86


@dataclass(frozen=True)
class MatchResult:
    ingredient: Ingredient | None
    method: str | None      # exact | measures | descriptors | fuzzy | None
    confidence: float       # 1.0 for deterministic hits
    normalized: str

    @property
    def matched(self) -> bool:
        return self.ingredient is not None


def strip_measures(normalized: str) -> str:
    """Remove leading quantities and any measure or packaging words."""
    text = QUANTITY_PREFIX.sub("", normalized)
    kept = [
        t for t in text.split()
        if t not in MEASURE_TOKENS and not re.fullmatch(r"[\d./]+", t)
    ]
    return " ".join(kept) if kept else normalized


def strip_descriptors(normalized: str) -> str:
    """Remove preparation adjectives. Runs only after exact lookups fail."""
    kept = [t for t in normalized.split() if t not in DESCRIPTORS]
    return " ".join(kept) if kept else normalized


class IngredientMatcher:
    """
    Build once, reuse for the life of the process.

    Not thread safe on first build. Django's request handling makes that
    acceptable here — worst case two threads build the same dict.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, int] = {}
        self._by_id: dict[int, Ingredient] = {}
        self._keys: list[str] = []
        self._loaded = False

    # ---------------------------------------------------------------- index

    def load(self) -> None:
        ingredients = list(Ingredient.objects.all())
        self._by_id = {ing.pk: ing for ing in ingredients}

        by_key: dict[str, int] = {}
        for ing in ingredients:
            by_key[normalize_name(ing.display_name)] = ing.pk
            by_key[normalize_name(ing.canonical_name.replace("-", " "))] = ing.pk

        for alias, ing_id in IngredientAlias.objects.values_list(
            "alias", "ingredient_id"
        ):
            by_key[alias] = ing_id

        self._by_key = by_key
        self._keys = list(by_key.keys())
        self._loaded = True

    def refresh(self) -> None:
        """Call after loading new vocabulary in a long-lived process."""
        self._loaded = False
        self.load()

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ---------------------------------------------------------------- match

    def match(self, raw: str, *, allow_fuzzy: bool = True) -> MatchResult:
        self._ensure_loaded()

        normalized = normalize_name(raw)
        if not normalized:
            return MatchResult(None, None, 0.0, normalized)

        # Each rung discards more than the last. First hit wins.
        ladder: list[tuple[str, str]] = [("exact", normalized)]

        without_measures = strip_measures(normalized)
        if without_measures != normalized:
            ladder.append(("measures", without_measures))

        without_descriptors = strip_descriptors(without_measures)
        if without_descriptors != without_measures:
            ladder.append(("descriptors", without_descriptors))

        for method, key in ladder:
            ing_id = self._by_key.get(key)
            if ing_id is not None:
                return MatchResult(self._by_id[ing_id], method, 1.0, normalized)

        # Approximate, deliberately last and deliberately strict. A wrong
        # match tells a user they can cook something they cannot.
        if allow_fuzzy:
            target = ladder[-1][1]
            candidates = difflib.get_close_matches(
                target, self._keys, n=1, cutoff=FUZZY_CUTOFF
            )
            if candidates:
                key = candidates[0]
                score = difflib.SequenceMatcher(None, target, key).ratio()
                return MatchResult(
                    self._by_id[self._by_key[key]], "fuzzy", score, normalized
                )

        return MatchResult(None, None, 0.0, normalized)

    # --------------------------------------------------------- miss logging

    @staticmethod
    @transaction.atomic
    def record_miss(raw: str, normalized: str) -> None:
        """
        Record an unresolved string so the vocabulary gap is measurable.

        One write per miss. Do NOT call this inside the recipe import loop —
        collect misses in a Counter and bulk-write them at the end.
        """
        updated = UnmatchedIngredient.objects.filter(raw_text=raw).update(
            hit_count=F("hit_count") + 1
        )
        if not updated:
            UnmatchedIngredient.objects.get_or_create(
                raw_text=raw, defaults={"normalized": normalized}
            )


# Module-level instance. Import this, not the class.
matcher = IngredientMatcher()