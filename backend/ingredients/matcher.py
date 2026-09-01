"""
Free text -> canonical Ingredient resolution.

Called from two places with very different load profiles and different
error distributions:

  * PantryService.add_item  — once per user action, human typos, one
    ingredient per string
  * import_recipes command  — ~2M calls, machine-cleaned text, but strings
    like "salt and pepper" name two ingredients at once

Hence two entry points. match() returns a single result and is what the
pantry uses: a person filling in a form is entering one thing. match_all()
returns a list and is what recipe import uses.

Matching is a ladder. Each rung throws away more information than the one
above it, and the first exact hit wins. Stripping only ever runs after an
exact lookup fails, which is what makes it safe to remove words that are
sometimes meaningful.

Scope note: this resolves WHICH ingredient, never HOW MUCH. Mass and volume
are not interconvertible without per-ingredient density, which the recipe
dataset does not provide, so coverage scoring is presence-based.
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

# Conjunctions that join two ingredients in one string. Whitespace-padded
# on purpose: normalize_name turns hyphens into spaces, so "half-and-half"
# becomes "half and half" and would otherwise be torn in two.
COMPOUND_SEPARATORS = re.compile(r"\s+and\s+|\s*&\s*|\s+or\s+|\s*,\s*|\s*/\s*")

# A string naming more than this many ingredients is almost certainly a
# parse failure rather than a real compound.
MAX_COMPOUND_PARTS = 4

# Measure words. Built from the unit alias table so the two stay in sync,
# plus packaging nouns that appear in recipe text but never in a pantry.
MEASURE_TOKENS: set[str] = {
    normalize_name(k) for k in UNIT_ALIASES if k
} | {
    "can", "package", "packet", "pkg", "container", "jar", "bottle", "box",
    "bag", "bunch", "head", "stalk", "sprig", "stick", "fillet",
    "strip", "cube", "block", "loaf", "sheet", "sachet", "tin",
}

# Preparation words that carry no identity information.
#
# NOTE: "ground" and "whole" are deliberately absent — "ground beef" and
# "whole cloves" are identities, not preparations.
#
# NOTE: "and" and "or" were removed. They were destroying the very signal
# the compound splitter needs: "salt and pepper" was being stripped to
# "salt pepper" before anything could notice it named two ingredients.
DESCRIPTORS: set[str] = {
    "fresh", "freshly", "frozen", "dried", "canned", "tinned", "jarred",
    "packaged", "chopped", "minced", "diced", "sliced", "grated", "crushed",
    "mashed", "cubed", "julienned", "halved", "quartered", "shredded", "torn",
    "beaten", "whisked", "whipped", "sifted", "packed", "level", "heaping",
    "finely", "roughly", "coarsely", "thinly", "thickly", "lightly",
    "peeled", "seeded", "cored", "trimmed", "rinsed", "drained", "washed",
    "cooked", "uncooked", "raw", "boiled", "roasted", "toasted", "melted",
    "softened", "chilled", "warm", "cold", "hot", "room", "temperature",
    "large", "medium", "small", "extra", "jumbo", "baby", "thick", "thin",
    "organic", "free", "range", "boneless", "skinless", "ripe", "overripe",
    "optional", "divided", "more", "taste", "needed", "garnish",
    "unsalted", "salted", "sweetened", "unsweetened", "low", "fat", "lean",
    "of", "for", "into", "about", "approximately", "such", "as",
    # Second pass, added from corpus misses. Safe to strip aggressively
    # because exact lookup always runs first: "dry mustard" and "sweet
    # potato" are vocabulary entries and never reach this stage.
    "dry", "hard", "soft", "nonfat", "sodium", "prepared", "slivered",
    "flaked", "elbow", "sweet", "stewed", "mini", "miniature", "instant",
    "quick", "unbleached", "plain", "regular", "pitted", "stemmed",
    "deveined", "boiling", "light", "dark", "reduced", "skim", "bottled",
}

# Below this ratio a fuzzy suggestion is more likely wrong than right.
FUZZY_CUTOFF = 0.86


@dataclass(frozen=True)
class MatchResult:
    ingredient: Ingredient | None
    method: str | None      # exact | measures | descriptors | fuzzy | None
    confidence: float       # 1.0 for deterministic hits
    normalized: str
    part: str = ""          # the fragment this result came from

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


def split_compound(raw: str) -> list[str]:
    """
    Break a string on conjunctions. Returns [normalized] if it does not split.

    Never called before a whole-string lookup has failed — that ordering is
    what protects 'cream of mushroom soup' and any vocabulary entry that
    legitimately contains a conjunction.
    """
    pieces = [p.strip() for p in COMPOUND_SEPARATORS.split(raw.lower()) if p.strip()]
    parts = [n for n in (normalize_name(p) for p in pieces) if n]
    if len(parts) < 2 or len(parts) > MAX_COMPOUND_PARTS:
        return []
    return parts


class IngredientMatcher:
    """Build once, reuse for the life of the process."""

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
        self._loaded = False
        self.load()

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ------------------------------------------------------------ internals

    def _deterministic(self, normalized: str) -> MatchResult | None:
        """Exact rungs only. Returns None rather than guessing."""
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
                return MatchResult(
                    self._by_id[ing_id], method, 1.0, normalized, normalized
                )
        return None

    def _fuzzy(self, normalized: str) -> MatchResult | None:
        target = strip_descriptors(strip_measures(normalized))
        candidates = difflib.get_close_matches(
            target, self._keys, n=1, cutoff=FUZZY_CUTOFF
        )
        if not candidates:
            return None
        key = candidates[0]

        # A high ratio can still hide a dropped word: "salt ground black
        # pepper" scores 0.88 against "ground black pepper", which would
        # silently tell a user the recipe needs no salt. Same word count
        # or no match.
        if len(key.split()) != len(target.split()):
            return None

        score = difflib.SequenceMatcher(None, target, key).ratio()
        return MatchResult(
            self._by_id[self._by_key[key]], "fuzzy", score, normalized, normalized
        )

    # ---------------------------------------------------------------- match

    def match(self, raw: str, *, allow_fuzzy: bool = True) -> MatchResult:
        """Single-ingredient resolution. Used by the pantry."""
        self._ensure_loaded()

        normalized = normalize_name(raw)
        if not normalized:
            return MatchResult(None, None, 0.0, normalized, normalized)

        result = self._deterministic(normalized)
        if result:
            return result

        if allow_fuzzy:
            result = self._fuzzy(normalized)
            if result:
                return result

        return MatchResult(None, None, 0.0, normalized, normalized)

    def match_all(self, raw: str, *, allow_fuzzy: bool = True) -> list[MatchResult]:
        """
        Resolve a string that may name several ingredients.

        "salt and pepper" is the single largest unmatched string in the
        Food.com corpus at 15,415 mentions. It is not a vocabulary gap —
        no alias fixes a string that names two things.

        Unresolved parts are returned too, not dropped. A recipe row that
        keeps its unknown fragment can never reach full coverage, so the
        system never tells a user they can cook something they cannot.
        Dropping the fragment would produce exactly that false positive.
        """
        self._ensure_loaded()

        normalized = normalize_name(raw)
        if not normalized:
            return [MatchResult(None, None, 0.0, normalized, normalized)]

        # Whole string first. Protects vocabulary entries that contain a
        # conjunction, and is the common case.
        whole = self._deterministic(normalized)
        if whole:
            return [whole]

        parts = split_compound(raw)
        if parts:
            results = [self._deterministic(p) for p in parts]

            # Only accept the split if it actually explained something.
            # Otherwise "half and half" would become two useless halves
            # instead of one honest miss.
            if any(results):
                return [
                    r if r else MatchResult(None, None, 0.0, normalized, part)
                    for r, part in zip(results, parts)
                ]

        if allow_fuzzy:
            fuzzy = self._fuzzy(normalized)
            if fuzzy:
                return [fuzzy]

        return [MatchResult(None, None, 0.0, normalized, normalized)]

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