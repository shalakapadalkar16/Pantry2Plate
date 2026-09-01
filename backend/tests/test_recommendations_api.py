"""
Recommendation API.

Caching is exercised with Django's local-memory backend rather than Redis.
Redis is a single shared instance with no per-test isolation, and test user
primary keys are recycled across runs — a real cache would hand one test
another's payload. The key logic is pure and tested directly; the view
behaviour is tested with a backend that resets between tests.

The SQL backend is pinned explicitly with ?backend=sql. Automatic selection
prefers Elasticsearch when reachable, which would make results depend on
whether a container happens to be running.
"""

import pytest
from django.test.utils import override_settings

from recommendations import cache, moods
from tests.factories import UserFactory, make_recipe, stock_pantry

pytestmark = pytest.mark.django_db

URL = "/api/v1/recommendations/"
MOODS_URL = "/api/v1/recommendations/moods/"

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-reco",
    }
}


def names(body):
    return [r["recipe"]["name"] for r in body["results"]]


# --------------------------------------------------------------------- auth

def test_requires_authentication(api_client):
    assert api_client.get(URL).status_code == 401


def test_mood_catalog_is_public(api_client):
    body = api_client.get(MOODS_URL).json()
    assert len(body["moods"]) == len(moods.MOODS)
    assert {"key", "label", "description", "tags"} <= set(body["moods"][0])


# ------------------------------------------------------------------ results

def test_returns_ranked_matches(auth_client, user):
    stock_pantry(user, ["onion", "garlic", "rice", "egg"])
    make_recipe(required=["onion", "garlic", "rice", "egg"], name="Big Overlap")
    make_recipe(required=["onion", "garlic", "rice"], name="Small Overlap")

    body = auth_client.get(f"{URL}?backend=sql&min_required=1").json()

    assert body["count"] == 2
    assert names(body)[0] == "Big Overlap"
    assert body["pantry_size"] == 4
    assert body["backend"] == "sql"


def test_empty_pantry_is_explained_not_just_empty(auth_client, user):
    """
    Distinguished from "searched and found nothing" so the client can prompt
    for ingredients rather than suggest loosening filters.
    """
    body = auth_client.get(URL).json()
    assert body["count"] == 0
    assert body["pantry_size"] == 0
    assert "pantry" in body["detail"].lower()


def test_reports_missing_and_unknown_separately(auth_client, user):
    stock_pantry(user, ["onion", "garlic"])
    make_recipe(
        required=["onion", "garlic", "butter"],
        unresolved=["mystery paste"],
        name="Partly Known",
    )

    body = auth_client.get(f"{URL}?backend=sql&min_required=1&max_missing=2").json()
    result = body["results"][0]

    assert result["missing_ingredients"] == ["Butter"]
    assert result["unknown_ingredients"] == ["mystery paste"]
    assert result["missing"] == 2


def test_pagination(auth_client, user):
    stock_pantry(user, ["onion", "garlic", "rice"])
    for _ in range(5):
        make_recipe(required=["onion", "garlic", "rice"])

    first = auth_client.get(f"{URL}?backend=sql&min_required=1&limit=2").json()
    assert first["count"] == 5
    assert len(first["results"]) == 2
    assert first["next"] is not None
    assert first["previous"] is None

    second = auth_client.get(
        f"{URL}?backend=sql&min_required=1&limit=2&offset=2"
    ).json()
    assert second["previous"] is not None


def test_users_see_only_their_own_pantry(auth_client, other_user):
    stock_pantry(other_user, ["onion", "garlic", "rice"])
    make_recipe(required=["onion", "garlic", "rice"])

    body = auth_client.get(f"{URL}?backend=sql&min_required=1").json()
    assert body["pantry_size"] == 0


# -------------------------------------------------------------- validation

@pytest.mark.parametrize(
    "query",
    [
        "max_missing=-1",
        "max_missing=999",
        "limit=0",
        "limit=5000",
        "offset=-1",
        "order=random",
        "max_minutes=0",
        "backend=mysql",
    ],
)
def test_rejects_out_of_range_parameters(auth_client, query):
    assert auth_client.get(f"{URL}?{query}").status_code == 400


def test_unknown_mood_is_rejected_not_ignored(auth_client, user):
    """
    A silently dropped filter returns results the user did not ask for, with
    no way for them to notice.
    """
    stock_pantry(user, ["onion"])
    response = auth_client.get(f"{URL}?mood=nonsense")

    assert response.status_code == 400
    assert "nonsense" in response.json()["error"]["message"]


def test_too_many_moods_is_rejected(auth_client, user):
    stock_pantry(user, ["onion"])
    many = ",".join(list(moods.MOODS)[:5])
    assert auth_client.get(f"{URL}?mood={many}").status_code == 400


# ------------------------------------------------------------------- moods

def test_mood_filters_results(auth_client, user):
    stock_pantry(user, ["onion", "garlic", "rice"])
    tagged = make_recipe(
        required=["onion", "garlic", "rice"],
        tags=["comfort-food"],
        name="Comforting",
    )
    make_recipe(required=["onion", "garlic", "rice"], tags=["desserts"], name="Sweet")

    body = auth_client.get(
        f"{URL}?backend=sql&min_required=1&mood=comfort"
    ).json()

    assert body["count"] == 1
    assert body["results"][0]["recipe"]["id"] == tagged.pk
    assert body["moods_applied"] == ["comfort"]


def test_multiple_moods_are_and_ed(auth_client, user):
    stock_pantry(user, ["onion", "garlic", "rice"])
    both = make_recipe(
        required=["onion", "garlic", "rice"],
        tags=["comfort-food", "vegetarian"],
    )
    make_recipe(required=["onion", "garlic", "rice"], tags=["comfort-food"])

    body = auth_client.get(
        f"{URL}?backend=sql&min_required=1&mood=comfort,vegetarian"
    ).json()

    assert body["count"] == 1
    assert body["results"][0]["recipe"]["id"] == both.pk


def test_every_mood_maps_to_defined_tags():
    """Guards against a typo turning a mood into a filter that matches
    nothing — which looks like an empty result rather than a bug."""
    for key, mood in moods.MOODS.items():
        assert mood.tags, f"{key} has no tags"
        assert mood.key == key
        for tag in mood.tags:
            assert tag == tag.lower().strip()


def test_moods_avoid_taxonomy_header_tags():
    """
    'preparation', 'course' and similar sit on ~95% of the corpus. A mood
    built on them is a no-op that looks like a filter.
    """
    forbidden = {
        "preparation", "time-to-make", "course", "main-ingredient",
        "dietary", "cuisine", "occasion", "easy", "equipment",
        "number-of-servings", "low-in-something", "taste-mood",
    }
    for key, mood in moods.MOODS.items():
        overlap = forbidden & set(mood.tags)
        assert not overlap, f"{key} uses over-broad tags: {overlap}"


def test_resolve_raises_on_unknown_key():
    with pytest.raises(moods.UnknownMoodError):
        moods.resolve(["quick", "not-a-mood"])


# ------------------------------------------------------------------- cache

def test_cache_key_is_stable_for_the_same_inputs():
    params = {"max_missing": 1, "limit": 20}
    first = cache.build_key(1, [3, 1, 2], params)
    second = cache.build_key(1, [3, 1, 2], params)
    assert first == second


def test_cache_key_ignores_pantry_ordering():
    """Insertion order must not produce two keys for one pantry."""
    params = {"max_missing": 0}
    assert cache.build_key(1, [1, 2, 3], params) == cache.build_key(
        1, [3, 2, 1], params
    )


def test_cache_key_changes_with_pantry_contents():
    """This is the invalidation mechanism — no signals involved."""
    params = {"max_missing": 0}
    assert cache.build_key(1, [1, 2], params) != cache.build_key(1, [1, 2, 3], params)


def test_cache_key_changes_with_query_and_user():
    assert cache.build_key(1, [1], {"max_missing": 0}) != cache.build_key(
        1, [1], {"max_missing": 1}
    )
    assert cache.build_key(1, [1], {"max_missing": 0}) != cache.build_key(
        2, [1], {"max_missing": 0}
    )


@override_settings(CACHES=LOCMEM)
def test_second_request_is_served_from_cache(auth_client, user):
    from django.core.cache import cache as django_cache

    django_cache.clear()
    stock_pantry(user, ["onion", "garlic", "rice"])
    make_recipe(required=["onion", "garlic", "rice"])

    url = f"{URL}?backend=sql&min_required=1"
    first = auth_client.get(url).json()
    second = auth_client.get(url).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert first["results"] == second["results"]


@override_settings(CACHES=LOCMEM)
def test_changing_the_pantry_bypasses_the_cache(auth_client, user):
    from django.core.cache import cache as django_cache

    django_cache.clear()
    stock_pantry(user, ["onion", "garlic", "rice"])
    make_recipe(required=["onion", "garlic", "rice"])

    url = f"{URL}?backend=sql&min_required=1"
    auth_client.get(url)
    assert auth_client.get(url).json()["cached"] is True

    stock_pantry(user, ["egg"])
    after = auth_client.get(url).json()
    assert after["cached"] is False
    assert after["pantry_size"] == 4


@override_settings(CACHES=LOCMEM)
def test_reverting_the_pantry_reuses_the_earlier_entry(auth_client, user):
    """
    The upside of content-addressed keys. Signal-based invalidation would
    have deleted this entry on the write and recomputed for nothing.
    """
    from django.core.cache import cache as django_cache
    from pantry.models import PantryItem

    django_cache.clear()
    stock_pantry(user, ["onion", "garlic", "rice"])
    make_recipe(required=["onion", "garlic", "rice"])

    url = f"{URL}?backend=sql&min_required=1"
    auth_client.get(url)

    added = stock_pantry(user, ["egg"])
    assert auth_client.get(url).json()["cached"] is False

    PantryItem.objects.filter(user=user, ingredient_id__in=added).delete()
    assert auth_client.get(url).json()["cached"] is True