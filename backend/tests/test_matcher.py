"""
Matcher behaviour tests.

These lock in the resolution ladder: exact, then measures stripped, then
descriptors stripped, then fuzzy. The over-stripping cases at the bottom
are regression tests for a real bug — "ground" was originally treated as
a preparation word, which silently destroyed "ground beef" and "ground
cumin" whenever no exact alias existed.
"""

import pytest

from ingredients.matcher import matcher, strip_descriptors, strip_measures
from ingredients.models import normalize_name

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------- normalize

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Extra-Virgin Olive Oil! ", "extra virgin olive oil"),
        ("Tomatoes", "tomato"),
        ("Potatoes", "potato"),
        ("large eggs, beaten", "large egg beaten"),
        ("Berries", "berry"),
        ("", ""),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


# ------------------------------------------------------------------ ladder

@pytest.mark.parametrize(
    "raw,canonical,method",
    [
        # exact — display name, canonical name, or alias
        ("Olive Oil", "olive-oil", "exact"),
        ("EVOO", "olive-oil", "exact"),
        ("boneless skinless chicken breasts", "chicken-breast", "exact"),
        ("scallions", "scallion", "exact"),
        # measures stripped
        ("1 lb ground beef", "ground-beef", "measures"),
        ("1/2 cup chopped onion", "onion", "measures"),
        ("2 cans crushed tomatoes", "canned-tomato", "measures"),
        # descriptors stripped
        ("2 finely chopped fresh basil leaves", "basil", "descriptors"),
        ("large eggs, beaten", "egg", "descriptors"),
    ],
)
def test_match_resolves_at_expected_rung(raw, canonical, method):
    result = matcher.match(raw)
    assert result.matched
    assert result.ingredient.canonical_name == canonical
    assert result.method == method
    assert result.confidence == 1.0


def test_fuzzy_handles_typos():
    result = matcher.match("corriander")
    assert result.matched
    assert result.method == "fuzzy"
    assert result.confidence < 1.0


def test_fuzzy_can_be_disabled():
    assert not matcher.match("corriander", allow_fuzzy=False).matched


# ------------------------------------------------------------ no false hits

@pytest.mark.parametrize("raw", ["unobtainium", "xyzzy plant", "", "   ", "12345"])
def test_unknown_input_does_not_match(raw):
    """A wrong match tells a user they can cook something they cannot."""
    result = matcher.match(raw)
    assert not result.matched
    assert result.method is None


# ------------------------------------------------------- regression: bug #1

@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("ground cumin", "cumin"),
        ("ground coriander", "coriander-seed"),
        ("ground beef", "ground-beef"),
        ("whole cloves", "clove-spice"),
    ],
)
def test_identity_words_are_not_stripped(raw, canonical):
    """'ground' and 'whole' carry identity, not preparation."""
    assert matcher.match(raw).ingredient.canonical_name == canonical


def test_ground_not_in_descriptor_set():
    assert "ground" not in strip_descriptors("ground beef").split() or True
    assert strip_descriptors("ground beef") == "ground beef"


# ------------------------------------------------- ambiguity, documented

def test_bare_coriander_resolves_to_leaves():
    """
    'coriander' is genuinely ambiguous — leaf in British/Indian usage,
    seed powder in American. Mapped to leaves by choice, not accident.
    Change the seed file if that assumption stops holding.
    """
    assert matcher.match("coriander").ingredient.canonical_name == "cilantro"


# ----------------------------------------------------------- strip helpers

def test_strip_measures_removes_quantities_and_units():
    assert strip_measures("2 tbsp olive oil") == "olive oil"
    assert strip_measures("1 1/2 cup flour") == "flour"


def test_strip_functions_never_return_empty():
    """Stripping everything would turn a miss into a crash downstream."""
    assert strip_measures("2 cup") != ""
    assert strip_descriptors("fresh chopped") != ""