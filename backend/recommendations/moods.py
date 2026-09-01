"""
Mood definitions.

A mood is a named set of corpus tags. Deterministic, testable, and
changeable in one file — no model guessing at a vibe.

Counts below are recipes carrying each tag, measured on the imported
corpus. They matter: a mood mapping to 40,000 recipes is a useful filter,
one mapping to 200 is a broken one.

Two classes of tag were deliberately avoided:

  * Taxonomy headers — 'preparation' (230,546), 'time-to-make' (225,326),
    'course' (218,148), 'cuisine' (91,165). These are category labels
    attached to almost every recipe. Filtering on them is a no-op that
    looks like a filter.
  * Near-universal values — 'easy' at 126,062 is 54% of the corpus. Broad
    enough to be meaningless, and it would swamp any mood it appeared in.

Semantics: tags within a mood are OR (a recipe needs any of them). Moods
combined in one request are AND (a recipe must satisfy every mood). So
'quick,vegetarian' means quick AND vegetarian, which is what a user
sending both expects.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mood:
    key: str
    label: str
    tags: tuple[str, ...]
    description: str


MOODS: dict[str, Mood] = {
    m.key: m
    for m in [
        # ---- time and effort ------------------------------------------
        Mood(
            "quick", "Quick",
            ("15-minutes-or-less", "30-minutes-or-less"),
            "On the table in half an hour",
        ),
        Mood(
            "lazy", "Minimal effort",
            ("3-steps-or-less", "5-ingredients-or-less", "no-cook"),
            "Few steps, few ingredients",
        ),
        Mood(
            "slow", "Set and forget",
            ("crock-pot-slow-cooker",),
            "Slow cooker",
        ),
        Mood(
            "beginner", "Nothing fancy",
            ("beginner-cook", "3-steps-or-less"),
            "Straightforward technique",
        ),
        # ---- feeling ---------------------------------------------------
        Mood(
            "comfort", "Comfort food",
            ("comfort-food", "casseroles", "soups-stews"),
            "Warm and filling",
        ),
        Mood(
            "light", "Something light",
            ("low-calorie", "low-fat", "salads"),
            "Lighter than usual",
        ),
        Mood(
            "healthy", "Healthy",
            ("healthy", "healthy-2", "low-fat", "low-calorie"),
            "Tagged healthy in the source",
        ),
        Mood(
            "spicy", "Spicy",
            ("spicy",),
            "Bring the heat",
        ),
        Mood(
            "impressive", "Cooking for people",
            ("dinner-party", "presentation", "for-large-groups"),
            "Worth serving to guests",
        ),
        Mood(
            "cheap", "Cheap",
            ("inexpensive",),
            "Budget friendly",
        ),
        Mood(
            "kids", "Kid friendly",
            ("kid-friendly",),
            "Goes down well with children",
        ),
        # ---- meal ------------------------------------------------------
        Mood(
            "breakfast", "Breakfast",
            ("breakfast", "brunch"),
            "Morning food",
        ),
        Mood(
            "lunch", "Lunch",
            ("lunch", "sandwiches", "salads"),
            "Midday",
        ),
        Mood(
            "dinner", "Proper dinner",
            ("main-dish", "one-dish-meal"),
            "A main course",
        ),
        Mood(
            "snack", "Snacks",
            ("snacks", "appetizers", "finger-food"),
            "Small things",
        ),
        Mood(
            "dessert", "Something sweet",
            ("desserts", "cakes", "cookies-and-brownies"),
            "Pudding",
        ),
        # ---- dietary ---------------------------------------------------
        Mood(
            "vegetarian", "Vegetarian",
            ("vegetarian", "vegan"),
            "No meat",
        ),
        Mood(
            "vegan", "Vegan",
            ("vegan",),
            "No animal products",
        ),
        Mood(
            "lowcarb", "Low carb",
            ("low-carb", "very-low-carbs"),
            "Fewer carbohydrates",
        ),
        # ---- cuisine ---------------------------------------------------
        Mood(
            "asian", "Asian",
            ("asian",),
            "Asian cuisines",
        ),
        Mood(
            "italian", "Italian",
            ("italian",),
            "Italian",
        ),
        Mood(
            "mexican", "Mexican",
            ("mexican",),
            "Mexican",
        ),
        Mood(
            "american", "American",
            ("american", "southern-united-states"),
            "American",
        ),
    ]
}


class UnknownMoodError(ValueError):
    """Raised for a mood key that is not defined."""


def resolve(keys: list[str]) -> list[list[str]]:
    """
    Turn mood keys into tag groups for the search query.

    Returns one group per mood. The query requires overlap with every
    group, so groups are AND-ed while tags inside a group are OR-ed.

    Unknown keys raise rather than being ignored. Silently dropping a
    filter returns results the user did not ask for, and they have no way
    to tell that happened.
    """
    groups = []
    for key in keys:
        mood = MOODS.get(key)
        if mood is None:
            raise UnknownMoodError(key)
        groups.append(list(mood.tags))
    return groups


def catalog() -> list[dict]:
    """Serialisable list for the client to render mood options."""
    return [
        {
            "key": mood.key,
            "label": mood.label,
            "description": mood.description,
            "tags": list(mood.tags),
        }
        for mood in MOODS.values()
    ]