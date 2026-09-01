import factory
from django.contrib.auth import get_user_model

from ingredients.models import Ingredient
from pantry.models import PantryItem
from recipes.models import Recipe, RecipeIngredient

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if create:
            obj.set_password(extracted or "testpass12345")
            obj.save(update_fields=["password"])


class PantryItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PantryItem

    user = factory.SubFactory(UserFactory)
    # Defaults to unresolved: PantryItem has a unique constraint on
    # (user, ingredient), and Postgres treats NULLs as distinct, so
    # factories can create many items for one user without colliding.
    ingredient = None
    raw_input = factory.Sequence(lambda n: f"mystery item {n}")
    quantity = 1
    unit = "piece"


class RecipeFactory(factory.django.DjangoModelFactory):
    """Bare recipe with no ingredients. Prefer make_recipe() below."""

    class Meta:
        model = Recipe

    external_id = factory.Sequence(lambda n: f"test-{n}")
    name = factory.Sequence(lambda n: f"Test Recipe {n}")
    description = ""
    minutes = 30
    n_steps = 1
    steps = factory.List(["do the thing"])
    tags = factory.List([])
    nutrition = factory.List([])
    calories = 100.0
    n_ingredients = 0
    n_required = 0
    n_unresolved = 0


def make_recipe(
    *,
    required: list[str] | None = None,
    staples: list[str] | None = None,
    unresolved: list[str] | None = None,
    **kwargs,
) -> Recipe:
    """
    Build a recipe with a known ingredient breakdown.

    required   canonical names counted in n_required
    staples    canonical names excluded from n_required
    unresolved raw strings with no ingredient — counted in n_required and
               never matchable, so they always read as missing

    The counters are computed here the same way import_recipes computes
    them. That duplication is a real risk: change the import rule and these
    fixtures silently encode the old one. test_counters_match_import_rules
    exists to catch that.
    """
    required = required or []
    staples = staples or []
    unresolved = unresolved or []

    by_name = {
        ing.canonical_name: ing
        for ing in Ingredient.objects.filter(
            canonical_name__in=required + staples
        )
    }
    missing_names = set(required + staples) - set(by_name)
    if missing_names:
        raise AssertionError(f"not in seed vocabulary: {sorted(missing_names)}")

    rows = []
    for name in required:
        rows.append((by_name[name], by_name[name].display_name, False))
    for name in staples:
        rows.append((by_name[name], by_name[name].display_name, True))
    for text in unresolved:
        rows.append((None, text, False))

    recipe = RecipeFactory(
        n_ingredients=len(rows),
        n_required=sum(1 for _, _, is_staple in rows if not is_staple),
        n_unresolved=len(unresolved),
        **kwargs,
    )

    RecipeIngredient.objects.bulk_create(
        [
            RecipeIngredient(
                recipe=recipe,
                ingredient=ingredient,
                raw_text=raw_text,
                is_staple=is_staple,
                position=position,
            )
            for position, (ingredient, raw_text, is_staple) in enumerate(rows)
        ]
    )
    return recipe


def stock_pantry(user, names: list[str]) -> list[int]:
    """Fill a pantry from canonical names, returning the ingredient ids."""
    ingredients = list(Ingredient.objects.filter(canonical_name__in=names))
    if len(ingredients) != len(set(names)):
        found = {i.canonical_name for i in ingredients}
        raise AssertionError(f"not in seed vocabulary: {sorted(set(names) - found)}")

    PantryItem.objects.bulk_create(
        [
            PantryItem(
                user=user,
                ingredient=ing,
                raw_input=ing.display_name,
                quantity=1,
                unit="piece",
            )
            for ing in ingredients
        ]
    )
    return [ing.pk for ing in ingredients]