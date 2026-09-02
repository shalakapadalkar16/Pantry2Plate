"""
Set up a demo account in one command.

Exists because recording a walkthrough should not open with typing fifteen
ingredients into a modal. It also acts as a reset button: if a take goes
badly, re-run with --reset and start again from a known state.

Lives in core rather than pantry because it touches users, pantry and
recipes — no single app owns it.

    python manage.py seed_demo
    python manage.py seed_demo --reset
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

DEFAULT_EMAIL = "demo@pantry2plate.local"
# Has to satisfy AUTH_PASSWORD_VALIDATORS, which are now actually enforced —
# "demo1234" fails on the common-password check.
DEFAULT_PASSWORD = "Pantry2Plate!42"

# Written the way a person would type, not as canonical names. The demo then
# shows the matcher working rather than asserting that it does: "EVOO"
# becomes Olive Oil, "2 large onions" becomes Onion, and the deliberate typo
# in "corriander" resolves through the fuzzy rung.
PANTRY = [
    ("boneless skinless chicken breasts", "500", "g"),
    ("basmati rice", "1", "kg"),
    ("2 large onions", "2", "pieces"),
    ("garlic", "1", "piece"),
    ("frozen peas", "300", "g"),
    ("soy sauce", "250", "ml"),
    ("large eggs", "6", "pieces"),
    ("carrots", "4", "pieces"),
    ("EVOO", "500", "ml"),
    ("unsalted butter", "250", "g"),
    ("whole milk", "1", "l"),
    ("sharp cheddar cheese", "200", "g"),
    ("spaghetti", "500", "g"),
    ("2 cans crushed tomatoes", "800", "g"),
    ("russet potatoes", "1", "kg"),
    ("corriander", "30", "g"),
    ("plain flour", "1", "kg"),
    # Deliberately unresolvable. The pantry page badges it and warns, which
    # is worth showing: the system admits what it cannot identify rather
    # than guessing.
    ("unobtainium powder", "1", "g"),
]


class Command(BaseCommand):
    help = "Create a demo user with a realistic pantry and a couple of saved recipes."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the demo user first and start from scratch.",
        )
        parser.add_argument(
            "--no-saved",
            action="store_true",
            help="Skip pre-saving recipes, so the book starts empty.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from ingredients.matcher import matcher
        from pantry.models import IngredientLog, PantryItem
        from recipes.models import Recipe, SavedRecipe

        User = get_user_model()
        email = options["email"]

        if options["reset"]:
            deleted, _ = User.objects.filter(email=email).delete()
            if deleted:
                self.stdout.write(f"Removed the existing demo account.")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"first_name": "Demo", "last_name": "Cook"},
        )
        if created:
            user.set_password(options["password"])
            user.save(update_fields=["password"])
        else:
            # Idempotent: clear the pantry so re-running gives the same
            # state rather than a doubled list.
            PantryItem.objects.filter(user=user).delete()
            IngredientLog.objects.filter(user=user).delete()

        matcher.load()

        added = unresolved = 0
        for raw_input, quantity, unit in PANTRY:
            result = matcher.match(raw_input)
            ingredient = result.ingredient

            if ingredient is None:
                unresolved += 1
            elif PantryItem.objects.filter(user=user, ingredient=ingredient).exists():
                # Two raw strings can resolve to one ingredient; the unique
                # constraint on (user, ingredient) is the authority.
                continue

            PantryItem.objects.create(
                user=user,
                ingredient=ingredient,
                raw_input=raw_input,
                quantity=Decimal(quantity),
                unit=self._unit(unit),
                expiry_date=None,
            )
            added += 1

        saved = 0
        if not options["no-saved".replace("-", "_")]:
            saved = self._save_recipes(user, Recipe, SavedRecipe)

        self._report(email, options["password"], added, unresolved, saved)

    @staticmethod
    def _unit(raw: str) -> str:
        from ingredients.units import UnknownUnitError, parse_unit

        try:
            return parse_unit(raw)
        except UnknownUnitError:
            return "piece"

    def _save_recipes(self, user, Recipe, SavedRecipe) -> int:
        """
        Pre-save two recipes so the book is not empty on camera.

        Picked by coverage against this pantry rather than hardcoded ids,
        which would break the moment the corpus is reimported and ids shift.
        """
        from recommendations.services import CoverageSearch

        SavedRecipe.objects.filter(user=user).delete()

        pantry_ids = CoverageSearch.pantry_ingredient_ids(user)
        if not pantry_ids:
            return 0

        result = CoverageSearch.search(pantry_ids, max_missing=0, limit=2)
        notes = [
            "Made this last week — needed less soy sauce than it says.",
            "Good for a weeknight. Doubles well.",
        ]

        saved = 0
        for match, note in zip(result.matches, notes):
            SavedRecipe.objects.create(
                user=user, recipe=match.recipe, notes=note
            )
            saved += 1
        return saved

    def _report(self, email, password, added, unresolved, saved):
        w = self.stdout.write

        w(f"\n{'=' * 56}")
        w("DEMO ACCOUNT READY")
        w(f"{'=' * 56}")
        w(f"  email      {email}")
        w(f"  password   {password}")
        w(f"  pantry     {added} items ({unresolved} deliberately unresolvable)")
        w(f"  saved      {saved} recipes")

        w(f"\n{'=' * 56}")
        w("WORTH SHOWING, IN THIS ORDER")
        w(f"{'=' * 56}")
        w("  1. Pantry — 'EVOO' reads as Olive Oil, '2 large onions' as")
        w("     Onion, 'corriander' resolved despite the typo. One item is")
        w("     badged unrecognised, and the banner says so.")
        w("  2. Find Recipes — threshold at 0, fried rice near the top using")
        w("     7-8 pantry items with nothing missing.")
        w("  3. Drag the threshold to 2, then back to 0. The line under the")
        w("     results reads 'Elasticsearch · cached' on the way back.")
        w("  4. Add a mood, then a second. Count drops both times and the")
        w("     'must match all' note appears.")
        w("  5. Open a recipe. Ingredients group by state; salt and pepper")
        w("     sit under 'assumed in every kitchen' and do not count.")
        w("  6. Terminal: manage.py compare_search. Ten seconds, and the")
        w("     SQL-versus-Elasticsearch table lands harder than any screen.")
        w("")