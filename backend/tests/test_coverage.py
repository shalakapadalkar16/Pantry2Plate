"""
Coverage ranking.

The arithmetic here decides what the product shows, so these tests pin down
the three rules that are easy to get wrong:

  * staples are excluded from the denominator
  * unresolved ingredients count as missing and can never be satisfied
  * ordering is missing ascending, then absolute overlap descending

Elasticsearch is not tested here. The index is a single shared cluster with
no per-test isolation, so indexing fixtures would write into the same index
the application reads. Parity between the two backends is covered by
`manage.py compare_search`, which runs against the real corpus and compares
totals, membership, and have/missing values.
"""

import pytest

from recommendations.services import CoverageSearch
from tests.factories import UserFactory, make_recipe, stock_pantry

pytestmark = pytest.mark.django_db


def ids_of(result):
    return [m.recipe.pk for m in result.matches]


# --------------------------------------------------------------- arithmetic

def test_full_coverage_reports_nothing_missing():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])
    recipe = make_recipe(required=["onion", "garlic", "rice"])

    result = CoverageSearch.search(pantry, max_missing=0, min_required=1)

    assert ids_of(result) == [recipe.pk]
    match = result.matches[0]
    assert (match.have, match.missing, match.coverage) == (3, 0, 1.0)
    assert match.missing_ingredients == []


def test_staples_are_not_counted_as_required():
    """
    Nobody lists salt in their pantry. If staples entered the denominator
    every recipe would read as less cookable than it is, and a zero-missing
    search would return almost nothing.
    """
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])
    recipe = make_recipe(
        required=["onion", "garlic", "rice"],
        staples=["salt", "black-pepper", "olive-oil"],
    )

    assert recipe.n_ingredients == 6
    assert recipe.n_required == 3

    result = CoverageSearch.search(pantry, max_missing=0, min_required=1)
    assert ids_of(result) == [recipe.pk]
    assert result.matches[0].missing == 0


def test_unresolved_ingredients_always_count_as_missing():
    """
    The user cannot confirm having something the matcher could not name, so
    an unresolved row must never be satisfiable. Dropping it would tell them
    a recipe needs less than it does.
    """
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])
    recipe = make_recipe(
        required=["onion", "garlic", "rice"], unresolved=["some mystery paste"]
    )

    assert recipe.n_required == 4

    strict = CoverageSearch.search(pantry, max_missing=0, min_required=1)
    assert strict.matches == []

    loose = CoverageSearch.search(pantry, max_missing=1, min_required=1)
    assert ids_of(loose) == [recipe.pk]
    match = loose.matches[0]
    assert (match.have, match.missing) == (3, 1)
    assert match.unknown_ingredients == ["some mystery paste"]
    assert match.missing_ingredients == []


def test_missing_ingredients_are_named():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic"])
    make_recipe(required=["onion", "garlic", "butter"])

    result = CoverageSearch.search(pantry, max_missing=1, min_required=1)
    assert result.matches[0].missing_ingredients == ["Butter"]


def test_max_missing_is_a_ceiling():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion"])
    make_recipe(required=["onion", "garlic", "butter"])

    for ceiling, expected in [(0, 0), (1, 0), (2, 1), (3, 1)]:
        result = CoverageSearch.search(pantry, max_missing=ceiling, min_required=1)
        assert len(result.matches) == expected, f"max_missing={ceiling}"


# ----------------------------------------------------------------- ordering

def test_ranks_by_missing_then_absolute_overlap():
    """
    Regression: ranking was originally missing ASC then coverage DESC. Once
    missing is 0 every recipe has coverage exactly 1.0, so the ratio carried
    no information and short recipes won on the tiebreak — the results were
    two-ingredient recipes. Absolute overlap is the signal that matters.
    """
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice", "egg", "butter"])

    small = make_recipe(required=["onion", "garlic", "rice"], minutes=10)
    large = make_recipe(
        required=["onion", "garlic", "rice", "egg", "butter"], minutes=60
    )

    result = CoverageSearch.search(pantry, max_missing=0, min_required=1)

    # Both are fully covered, so coverage is 1.0 for each. The recipe using
    # more of the pantry must win despite taking longer.
    assert ids_of(result) == [large.pk, small.pk]
    assert result.matches[0].have == 5


def test_zero_missing_outranks_better_coverage_ratio():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice", "egg"])

    complete = make_recipe(required=["onion", "garlic"])
    incomplete = make_recipe(required=["onion", "garlic", "rice", "egg", "butter"])

    result = CoverageSearch.search(pantry, max_missing=1, min_required=1)

    assert ids_of(result)[0] == complete.pk
    assert result.matches[0].missing == 0
    assert result.matches[1].recipe.pk == incomplete.pk


def test_order_quickest_prefers_short_cook_time():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice", "egg", "butter"])

    slow = make_recipe(
        required=["onion", "garlic", "rice", "egg", "butter"], minutes=90
    )
    fast = make_recipe(required=["onion", "garlic", "rice"], minutes=5)

    result = CoverageSearch.search(
        pantry, max_missing=0, min_required=1, order="quickest"
    )
    assert ids_of(result) == [fast.pk, slow.pk]

    default = CoverageSearch.search(pantry, max_missing=0, min_required=1)
    assert ids_of(default) == [slow.pk, fast.pk]


# ------------------------------------------------------------------ filters

def test_min_required_excludes_trivial_recipes():
    """A two-ingredient recipe scores perfectly and is a useless
    recommendation, which is why the default floor is 3."""
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])

    trivial = make_recipe(required=["onion", "garlic"])
    real = make_recipe(required=["onion", "garlic", "rice"])

    default = CoverageSearch.search(pantry, max_missing=0)
    assert ids_of(default) == [real.pk]

    permissive = CoverageSearch.search(pantry, max_missing=0, min_required=1)
    assert set(ids_of(permissive)) == {trivial.pk, real.pk}


def test_max_minutes_filter():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])

    quick = make_recipe(required=["onion", "garlic", "rice"], minutes=10)
    make_recipe(required=["onion", "garlic", "rice"], minutes=120)

    result = CoverageSearch.search(
        pantry, max_missing=0, min_required=1, max_minutes=30
    )
    assert ids_of(result) == [quick.pk]


def test_tag_groups_are_and_ed_across_moods():
    """Tags within a group are OR, groups are AND — someone asking for two
    moods means both."""
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])

    both = make_recipe(
        required=["onion", "garlic", "rice"], tags=["quick-x", "veg-x"]
    )
    only_one = make_recipe(required=["onion", "garlic", "rice"], tags=["quick-x"])

    either = CoverageSearch.search(
        pantry, max_missing=0, min_required=1, tag_groups=[["quick-x"]]
    )
    assert set(ids_of(either)) == {both.pk, only_one.pk}

    intersection = CoverageSearch.search(
        pantry,
        max_missing=0,
        min_required=1,
        tag_groups=[["quick-x"], ["veg-x"]],
    )
    assert ids_of(intersection) == [both.pk]


# -------------------------------------------------------------- edge cases

def test_empty_pantry_returns_nothing():
    user = UserFactory()
    make_recipe(required=["onion", "garlic", "rice"])

    result = CoverageSearch.search([], max_missing=5, min_required=1)
    assert result.matches == []
    assert result.total == 0


def test_recipe_with_no_pantry_overlap_is_excluded():
    """
    A recipe you have nothing for is not a pantry recommendation. Without
    this rule, raising max_missing would flood results with recipes needing
    exactly N things the user does not own.
    """
    user = UserFactory()
    pantry = stock_pantry(user, ["onion"])
    make_recipe(required=["butter", "milk", "egg"])

    result = CoverageSearch.search(pantry, max_missing=5, min_required=1)
    assert result.matches == []


def test_pantry_ingredient_ids_skips_unresolved_items():
    from tests.factories import PantryItemFactory

    user = UserFactory()
    resolved = stock_pantry(user, ["onion"])
    PantryItemFactory(user=user, ingredient=None, raw_input="unidentifiable goo")

    assert CoverageSearch.pantry_ingredient_ids(user) == resolved


def test_total_reflects_all_matches_not_just_the_page():
    user = UserFactory()
    pantry = stock_pantry(user, ["onion", "garlic", "rice"])
    for _ in range(5):
        make_recipe(required=["onion", "garlic", "rice"])

    result = CoverageSearch.search(pantry, max_missing=0, min_required=1, limit=2)
    assert len(result.matches) == 2
    assert result.total == 5


def test_counters_match_import_rules():
    """
    Guards the duplication in make_recipe(). If the import changes how
    n_required or n_unresolved are computed, the fixtures encode the old
    rule and every coverage test silently validates the wrong thing.
    """
    recipe = make_recipe(
        required=["onion", "garlic"],
        staples=["salt"],
        unresolved=["mystery"],
    )
    rows = recipe.recipe_ingredients.all()

    assert recipe.n_ingredients == rows.count()
    assert recipe.n_required == sum(1 for r in rows if not r.is_staple)
    assert recipe.n_unresolved == sum(1 for r in rows if r.ingredient_id is None)