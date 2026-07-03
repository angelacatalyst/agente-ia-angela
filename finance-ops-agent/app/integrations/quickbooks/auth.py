"""QuickBooks Online OAuth2 flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
_INTUIT_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
_QBO_SCOPES = "com.intuit.quickbooks.accounting"


def get_authorization_url(state: str) -> str:
    params = {
        "client_id": settings.qbo_client_id,
        "response_type": "code",
        "scope": _QBO_SCOPES,
        "redirect_uri": settings.qbo_redirect_uri,
        "state": state,
    }
    return f"{_INTUIT_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str, realm_id: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _INTUIT_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.qbo_redirect_uri,
            },
            auth=(settings.qbo_client_id, settings.qbo_client_secret),
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
    return {
        "realm_id": realm_id,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": expires_at,
    }


async def refresh_access_token(refresh_token: str) -> dict:
    """Use refresh token to get a new access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _INTUIT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(settings.qbo_client_id, settings.qbo_client_secret),
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_at": expires_at,
    }
