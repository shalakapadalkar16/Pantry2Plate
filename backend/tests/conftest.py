"""API-level fixtures. Nested under the root conftest, which handles
seed vocabulary loading and matcher cache resets."""

import pytest
from rest_framework.test import APIClient

from tests.factories import UserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def other_user(db):
    return UserFactory()


@pytest.fixture
def auth_client(api_client, user):
    """
    Authenticates directly rather than through the login endpoint.

    These tests are about pantry behaviour. Routing every one of them
    through JWT issuance would make an auth regression fail thirty
    unrelated tests and tell you nothing about where the problem is.
    """
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def other_client(api_client, other_user):
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client
