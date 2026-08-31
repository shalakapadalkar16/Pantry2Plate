"""
Shared fixtures.

The seed vocabulary is loaded once per test session rather than per test.
It is read-only reference data, so rebuilding it 50 times would just be
slow. pytest-django wraps each test in a transaction that rolls back, and
this data is committed outside that transaction, so it survives.
"""

import pytest
from django.core.management import call_command


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Load the canonical ingredient vocabulary into the test database."""
    with django_db_blocker.unblock():
        call_command("load_ingredients", verbosity=0)


@pytest.fixture(autouse=True)
def _reset_matcher_cache(request):
    """
    The matcher is a module-level singleton holding an in-memory index.

    Without this, the first test to touch it caches an index built against
    whatever state existed then, and later tests silently match against
    stale data. This is the main hazard of the caching design.
    """
    if "django_db_setup" in request.fixturenames:
        from ingredients.matcher import matcher

        matcher.refresh()
    yield