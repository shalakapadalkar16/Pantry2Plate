"""
Recipe book and recipe detail.
"""

import pytest

from recipes.models import SavedRecipe
from tests.factories import UserFactory, make_recipe, stock_pantry

pytestmark = pytest.mark.django_db

SAVED = "/api/v1/recipes/saved/"
IDS = "/api/v1/recipes/saved/ids/"


def detail(pk):
    return f"/api/v1/recommendations/recipes/{pk}/"


# --------------------------------------------------------------------- auth

@pytest.mark.parametrize("method,url", [("get", SAVED), ("post", SAVED), ("get", IDS)])
def test_requires_authentication(api_client, method, url):
    assert getattr(api_client, method)(url).status_code == 401


# --------------------------------------------------------------------- save

def test_save_a_recipe(auth_client, user):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    response = auth_client.post(
        SAVED, {"recipe_id": recipe.pk, "notes": "try friday"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["recipe"]["id"] == recipe.pk
    assert body["notes"] == "try friday"
    assert SavedRecipe.objects.filter(user=user, recipe=recipe).exists()


def test_notes_are_optional(auth_client):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    assert auth_client.post(SAVED, {"recipe_id": recipe.pk}).json()["notes"] == ""


def test_saving_twice_returns_409(auth_client):
    """
    The unique constraint is the authority — the service catches
    IntegrityError rather than checking first, because check-then-create
    leaves a race between the two statements.
    """
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    auth_client.post(SAVED, {"recipe_id": recipe.pk})
    response = auth_client.post(SAVED, {"recipe_id": recipe.pk})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate"


def test_saving_a_missing_recipe_returns_404(auth_client):
    response = auth_client.post(SAVED, {"recipe_id": 99_999_999})
    assert response.status_code == 404


def test_save_requires_a_recipe_id(auth_client):
    assert auth_client.post(SAVED, {"notes": "hello"}).status_code == 400


# --------------------------------------------------------------------- list

def test_book_lists_saved_recipes(auth_client):
    first = make_recipe(required=["onion", "garlic", "rice"], name="One")
    second = make_recipe(required=["onion", "garlic", "egg"], name="Two")
    auth_client.post(SAVED, {"recipe_id": first.pk})
    auth_client.post(SAVED, {"recipe_id": second.pk})

    body = auth_client.get(SAVED).json()
    assert body["count"] == 2
    assert {r["recipe"]["name"] for r in body["results"]} == {"One", "Two"}


def test_book_is_paginated(auth_client):
    for index in range(25):
        recipe = make_recipe(required=["onion", "garlic", "rice"], name=f"R{index}")
        auth_client.post(SAVED, {"recipe_id": recipe.pk})

    body = auth_client.get(SAVED).json()
    assert body["count"] == 25
    assert len(body["results"]) == 20


def test_ids_endpoint_returns_bare_ids(auth_client):
    """
    Exists so a client can mark saved search results without an is_saved
    flag entering the recommendation response, which is cached on a key
    that does not account for per-user state beyond the pantry.
    """
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    auth_client.post(SAVED, {"recipe_id": recipe.pk})

    body = auth_client.get(IDS).json()
    assert body == {"count": 1, "recipe_ids": [recipe.pk]}


# -------------------------------------------------------------- notes/delete

def test_update_notes(auth_client):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    auth_client.post(SAVED, {"recipe_id": recipe.pk, "notes": "first"})

    response = auth_client.patch(f"{SAVED}{recipe.pk}/", {"notes": "second"})
    assert response.status_code == 200
    assert response.json()["notes"] == "second"


def test_update_notes_on_unsaved_recipe_returns_404(auth_client):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    assert auth_client.patch(f"{SAVED}{recipe.pk}/", {"notes": "x"}).status_code == 404


def test_remove_from_book(auth_client, user):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    auth_client.post(SAVED, {"recipe_id": recipe.pk})

    assert auth_client.delete(f"{SAVED}{recipe.pk}/").status_code == 204
    assert not SavedRecipe.objects.filter(user=user).exists()
    assert auth_client.delete(f"{SAVED}{recipe.pk}/").status_code == 404


def test_removing_from_the_book_leaves_the_recipe_alone(auth_client):
    from recipes.models import Recipe

    recipe = make_recipe(required=["onion", "garlic", "rice"])
    auth_client.post(SAVED, {"recipe_id": recipe.pk})
    auth_client.delete(f"{SAVED}{recipe.pk}/")

    assert Recipe.objects.filter(pk=recipe.pk).exists()


# ---------------------------------------------------------------- isolation

def test_books_are_private(auth_client, other_client, other_user):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    other_client.post(SAVED, {"recipe_id": recipe.pk})

    assert auth_client.get(SAVED).json()["count"] == 0
    assert auth_client.get(IDS).json()["count"] == 0
    # Not in this user's book, so it is not theirs to delete.
    assert auth_client.delete(f"{SAVED}{recipe.pk}/").status_code == 404
    assert SavedRecipe.objects.filter(user=other_user).count() == 1


def test_two_users_can_save_the_same_recipe(auth_client, other_client):
    recipe = make_recipe(required=["onion", "garlic", "rice"])
    assert auth_client.post(SAVED, {"recipe_id": recipe.pk}).status_code == 201
    assert other_client.post(SAVED, {"recipe_id": recipe.pk}).status_code == 201


# ------------------------------------------------------------------- detail

def test_recipe_detail_marks_ingredient_state(auth_client, user):
    stock_pantry(user, ["onion", "garlic"])
    recipe = make_recipe(
        required=["onion", "garlic", "butter"],
        staples=["salt"],
        unresolved=["mystery paste"],
    )

    body = auth_client.get(detail(recipe.pk)).json()
    states = {i["display_name"]: i["state"] for i in body["ingredients"]}

    assert states["Onion"] == "have"
    assert states["Garlic"] == "have"
    assert states["Butter"] == "missing"
    assert states["Salt"] == "staple"
    assert states["mystery paste"] == "unknown"

    # Staples are reported but never counted against coverage.
    assert body["summary"] == {
        "n_required": 4,
        "have": 2,
        "missing": 1,
        "unknown": 1,
    }


def test_recipe_detail_includes_steps(auth_client, user):
    stock_pantry(user, ["onion"])
    recipe = make_recipe(required=["onion", "garlic", "rice"])

    body = auth_client.get(detail(recipe.pk)).json()
    assert body["steps"] == ["do the thing"]


def test_missing_recipe_detail_returns_404(auth_client):
    assert auth_client.get(detail(99_999_999)).status_code == 404