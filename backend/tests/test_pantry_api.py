"""
Pantry API tests.

Written after a model change silently broke every pantry endpoint while
`manage.py check` reported no issues and the full test suite passed.
Neither signal touched the API layer, because nothing tested it. DRF
resolves serializer fields lazily, so a serializer pointing at a deleted
model field imports fine and only fails when a request arrives.

These tests exist so that failure mode is loud.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from pantry.models import IngredientLog, PantryItem
from tests.factories import PantryItemFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/pantry/"
LOGS_URL = "/api/v1/pantry/logs/"
EXPIRING_URL = "/api/v1/pantry/expiring/"


def detail_url(pk):
    return f"/api/v1/pantry/{pk}/"


# ------------------------------------------------------------------- auth

@pytest.mark.parametrize(
    "method,url",
    [("get", LIST_URL), ("post", LIST_URL), ("get", LOGS_URL), ("get", EXPIRING_URL)],
)
def test_endpoints_require_authentication(api_client, method, url):
    response = getattr(api_client, method)(url)
    assert response.status_code == 401


# ----------------------------------------------------------------- create

def test_create_resolves_ingredient(auth_client, user):
    response = auth_client.post(
        LIST_URL, {"raw_input": "2 tbsp extra virgin olive oil", "quantity": "1", "unit": "tbsp"}
    )
    assert response.status_code == 201

    body = response.json()
    assert body["is_resolved"] is True
    assert body["ingredient"]["canonical_name"] == "olive-oil"
    assert body["raw_input"] == "2 tbsp extra virgin olive oil"
    assert body["display_name"] == "Olive Oil"


def test_create_stores_unresolved_input(auth_client):
    """Unrecognised input is kept, not rejected. It simply never matches."""
    response = auth_client.post(
        LIST_URL, {"raw_input": "unobtainium powder", "quantity": "1", "unit": "g"}
    )
    assert response.status_code == 201
    assert response.json()["is_resolved"] is False
    assert response.json()["display_name"] == "unobtainium powder"


def test_create_writes_audit_log(auth_client, user):
    auth_client.post(LIST_URL, {"raw_input": "salt", "quantity": "2", "unit": "tsp"})

    log = IngredientLog.objects.get(user=user)
    assert log.action == IngredientLog.Action.ADDED
    assert log.ingredient_name == "salt"
    assert log.ingredient is not None


def test_duplicate_resolved_ingredient_returns_409(auth_client):
    auth_client.post(LIST_URL, {"raw_input": "olive oil", "quantity": "1", "unit": "tbsp"})
    response = auth_client.post(
        LIST_URL, {"raw_input": "EVOO", "quantity": "1", "unit": "tbsp"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate"


def test_multiple_unresolved_items_are_allowed(auth_client):
    """NULL ingredient values are distinct, so the constraint does not fire."""
    assert auth_client.post(
        LIST_URL, {"raw_input": "xyzzy root", "quantity": "1", "unit": "g"}
    ).status_code == 201
    assert auth_client.post(
        LIST_URL, {"raw_input": "frobnitz leaf", "quantity": "1", "unit": "g"}
    ).status_code == 201


def test_unit_aliases_are_normalized(auth_client):
    response = auth_client.post(
        LIST_URL, {"raw_input": "sugar", "quantity": "500", "unit": "Grams"}
    )
    assert response.status_code == 201
    assert response.json()["unit"] == "g"


def test_unknown_unit_is_rejected(auth_client):
    response = auth_client.post(
        LIST_URL, {"raw_input": "sugar", "quantity": "1", "unit": "furlongs"}
    )
    assert response.status_code == 400
    assert "unit" in response.json()["error"]["fields"]


def test_negative_quantity_is_rejected(auth_client):
    response = auth_client.post(
        LIST_URL, {"raw_input": "sugar", "quantity": "-5", "unit": "g"}
    )
    assert response.status_code == 400


# ------------------------------------------------------------------ patch

def test_patch_accepts_quantity_alone(auth_client, user):
    """
    Regression: the update serializer previously required quantity AND
    unit, so PATCH with a single field returned 400 and behaved like PUT.
    """
    item = PantryItemFactory(user=user, quantity=Decimal("1"))
    response = auth_client.patch(detail_url(item.pk), {"quantity": "5"})

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.quantity == Decimal("5")
    assert item.unit == "piece"


def test_patch_writes_audit_log(auth_client, user):
    item = PantryItemFactory(user=user)
    auth_client.patch(detail_url(item.pk), {"quantity": "3"})

    assert IngredientLog.objects.filter(
        user=user, action=IngredientLog.Action.UPDATED
    ).exists()


def test_patch_with_no_fields_is_rejected(auth_client, user):
    item = PantryItemFactory(user=user)
    assert auth_client.patch(detail_url(item.pk), {}).status_code == 400


def test_patch_missing_item_returns_404(auth_client):
    response = auth_client.patch(detail_url(999999), {"quantity": "1"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_patch_can_clear_expiry(auth_client, user):
    item = PantryItemFactory(user=user, expiry_date="2030-01-01")
    response = auth_client.patch(detail_url(item.pk), {"expiry_date": None}, format="json")

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.expiry_date is None


# ----------------------------------------------------------------- delete

def test_delete_removes_item_and_logs_it(auth_client, user):
    item = PantryItemFactory(user=user)
    response = auth_client.delete(detail_url(item.pk))

    assert response.status_code == 204
    assert not PantryItem.objects.filter(pk=item.pk).exists()
    assert IngredientLog.objects.filter(
        user=user, action=IngredientLog.Action.REMOVED
    ).exists()


def test_delete_missing_item_returns_404(auth_client):
    assert auth_client.delete(detail_url(999999)).status_code == 404


# --------------------------------------------------------------- isolation

def test_users_cannot_see_each_others_items(auth_client, other_user):
    PantryItemFactory(user=other_user)
    assert auth_client.get(LIST_URL).json()["count"] == 0


def test_users_cannot_modify_each_others_items(auth_client, other_user):
    item = PantryItemFactory(user=other_user)
    assert auth_client.patch(detail_url(item.pk), {"quantity": "9"}).status_code == 404
    assert auth_client.delete(detail_url(item.pk)).status_code == 404


# -------------------------------------------------------------- pagination

def test_list_is_paginated(auth_client, user):
    """
    Regression: APIView ignores DEFAULT_PAGINATION_CLASS, so both list
    endpoints previously returned every row despite the setting.
    """
    PantryItemFactory.create_batch(25, user=user)
    body = auth_client.get(LIST_URL).json()

    assert body["count"] == 25
    assert len(body["results"]) == 20
    assert body["next"] is not None


def test_logs_are_paginated(auth_client, user):
    for i in range(25):
        auth_client.post(
            LIST_URL, {"raw_input": f"thing {i}", "quantity": "1", "unit": "g"}
        )

    body = auth_client.get(LOGS_URL).json()
    assert body["count"] == 25
    assert len(body["results"]) == 20


# ---------------------------------------------------------------- expiring

def test_expiring_returns_only_soon_to_expire(auth_client, user):
    from datetime import date, timedelta

    PantryItemFactory(user=user, expiry_date=date.today() + timedelta(days=2))
    PantryItemFactory(user=user, expiry_date=date.today() + timedelta(days=90))
    PantryItemFactory(user=user, expiry_date=None)

    assert auth_client.get(EXPIRING_URL).json()["count"] == 1
    assert auth_client.get(f"{EXPIRING_URL}?days=180").json()["count"] == 2


# ----------------------------------------------------------- error shape

def test_errors_share_one_response_shape(auth_client):
    body = auth_client.post(LIST_URL, {"quantity": "1"}).json()

    assert set(body["error"]) == {"message", "code", "status_code", "fields"}
    assert body["error"]["status_code"] == 400
    assert "raw_input" in body["error"]["fields"]