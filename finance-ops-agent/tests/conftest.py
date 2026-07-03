"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import get_settings

settings = get_settings()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": (settings.api_keys[0] if settings.api_keys else "test-key")},
    ) as ac:
        yield ac


@pytest.fixture
def api_key():
    return settings.api_keys[0] if settings.api_keys else "test-key"
