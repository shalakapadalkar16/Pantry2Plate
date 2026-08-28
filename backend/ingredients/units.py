"""
Canonical units and unit parsing.

Lives in the ingredients app because pantry, recipes, and the dataset
importer all need it. Keeping it out of models.py avoids circular imports.
"""

from decimal import Decimal

from django.db import models


class Dimension(models.TextChoices):
    MASS = "mass", "Mass"
    VOLUME = "volume", "Volume"
    COUNT = "count", "Count"
    UNSPECIFIED = "unspecified", "Unspecified"


class Unit(models.TextChoices):
    # Mass
    GRAM = "g", "grams"
    KILOGRAM = "kg", "kilograms"
    OUNCE = "oz", "ounces"
    POUND = "lb", "pounds"

    # Volume
    MILLILITRE = "ml", "millilitres"
    LITRE = "l", "litres"
    TEASPOON = "tsp", "teaspoons"
    TABLESPOON = "tbsp", "tablespoons"
    CUP = "cup", "cups"
    FLUID_OUNCE = "fl_oz", "fluid ounces"

    # Count
    PIECE = "piece", "pieces"
    CLOVE = "clove", "cloves"
    SLICE = "slice", "slices"

    # Unspecified quantity — common in recipe text, useless for arithmetic
    TO_TASTE = "to_taste", "to taste"
    PINCH = "pinch", "pinch"


UNIT_DIMENSION: dict[str, str] = {
    Unit.GRAM: Dimension.MASS,
    Unit.KILOGRAM: Dimension.MASS,
    Unit.OUNCE: Dimension.MASS,
    Unit.POUND: Dimension.MASS,
    Unit.MILLILITRE: Dimension.VOLUME,
    Unit.LITRE: Dimension.VOLUME,
    Unit.TEASPOON: Dimension.VOLUME,
    Unit.TABLESPOON: Dimension.VOLUME,
    Unit.CUP: Dimension.VOLUME,
    Unit.FLUID_OUNCE: Dimension.VOLUME,
    Unit.PIECE: Dimension.COUNT,
    Unit.CLOVE: Dimension.COUNT,
    Unit.SLICE: Dimension.COUNT,
    Unit.TO_TASTE: Dimension.UNSPECIFIED,
    Unit.PINCH: Dimension.UNSPECIFIED,
}

# Multiplier to the base unit of each dimension: grams, millilitres, pieces.
# US customary volumes. Deliberately not exact for cooking purposes.
TO_BASE: dict[str, Decimal] = {
    Unit.GRAM: Decimal("1"),
    Unit.KILOGRAM: Decimal("1000"),
    Unit.OUNCE: Decimal("28.3495"),
    Unit.POUND: Decimal("453.592"),
    Unit.MILLILITRE: Decimal("1"),
    Unit.LITRE: Decimal("1000"),
    Unit.TEASPOON: Decimal("4.92892"),
    Unit.TABLESPOON: Decimal("14.7868"),
    Unit.CUP: Decimal("236.588"),
    Unit.FLUID_OUNCE: Decimal("29.5735"),
    Unit.PIECE: Decimal("1"),
    Unit.CLOVE: Decimal("1"),
    Unit.SLICE: Decimal("1"),
}


# Every spelling seen in user input or recipe text, mapped to a canonical unit.
UNIT_ALIASES: dict[str, str] = {
    "g": Unit.GRAM, "gm": Unit.GRAM, "gms": Unit.GRAM,
    "gram": Unit.GRAM, "grams": Unit.GRAM,
    "kg": Unit.KILOGRAM, "kgs": Unit.KILOGRAM,
    "kilo": Unit.KILOGRAM, "kilos": Unit.KILOGRAM,
    "kilogram": Unit.KILOGRAM, "kilograms": Unit.KILOGRAM,

    "oz": Unit.OUNCE, "ounce": Unit.OUNCE, "ounces": Unit.OUNCE,
    "lb": Unit.POUND, "lbs": Unit.POUND,
    "pound": Unit.POUND, "pounds": Unit.POUND,

    "ml": Unit.MILLILITRE, "milliliter": Unit.MILLILITRE,
    "millilitre": Unit.MILLILITRE, "milliliters": Unit.MILLILITRE,
    "millilitres": Unit.MILLILITRE,
    "l": Unit.LITRE, "liter": Unit.LITRE, "litre": Unit.LITRE,
    "liters": Unit.LITRE, "litres": Unit.LITRE,

    "tsp": Unit.TEASPOON, "t": Unit.TEASPOON,
    "teaspoon": Unit.TEASPOON, "teaspoons": Unit.TEASPOON,
    "tbsp": Unit.TABLESPOON, "tbs": Unit.TABLESPOON, "T": Unit.TABLESPOON,
    "tablespoon": Unit.TABLESPOON, "tablespoons": Unit.TABLESPOON,

    "cup": Unit.CUP, "cups": Unit.CUP, "c": Unit.CUP,
    "fl oz": Unit.FLUID_OUNCE, "fl_oz": Unit.FLUID_OUNCE,
    "fluid ounce": Unit.FLUID_OUNCE, "fluid ounces": Unit.FLUID_OUNCE,

    "piece": Unit.PIECE, "pieces": Unit.PIECE, "pc": Unit.PIECE,
    "pcs": Unit.PIECE, "whole": Unit.PIECE, "each": Unit.PIECE,
    "": Unit.PIECE,
    "clove": Unit.CLOVE, "cloves": Unit.CLOVE,
    "slice": Unit.SLICE, "slices": Unit.SLICE,

    "to taste": Unit.TO_TASTE, "as needed": Unit.TO_TASTE,
    "pinch": Unit.PINCH, "dash": Unit.PINCH,
}


class UnknownUnitError(ValueError):
    """Raised when a unit string cannot be mapped to a canonical Unit."""


def parse_unit(raw: str) -> str:
    """
    Map a raw unit string to a canonical Unit value.

    >>> parse_unit("Grams")
    'g'
    >>> parse_unit("TBSP.")
    'tbsp'
    """
    if raw is None:
        return Unit.PIECE

    key = raw.strip().lower().rstrip(".")
    key = " ".join(key.split())

    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]

    raise UnknownUnitError(f"Unrecognised unit: {raw!r}")


def dimension_of(unit: str) -> str:
    return UNIT_DIMENSION.get(unit, Dimension.UNSPECIFIED)


def to_base(quantity: Decimal, unit: str) -> Decimal | None:
    """
    Convert a quantity to the base unit of its dimension.

    Returns None for unspecified units ("to taste", "pinch"), which carry
    no numeric meaning.
    """
    if unit not in TO_BASE:
        return None
    return Decimal(quantity) * TO_BASE[unit]


def same_dimension(unit_a: str, unit_b: str) -> bool:
    """
    True if two units measure the same kind of thing.

    Mass and volume are NOT interconvertible without per-ingredient density,
    which the recipe dataset does not provide. See the note in the module
    docstring of ingredients/matcher.py.
    """
    dim_a = dimension_of(unit_a)
    if dim_a == Dimension.UNSPECIFIED:
        return False
    return dim_a == dimension_of(unit_b)