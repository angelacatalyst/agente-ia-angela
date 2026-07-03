"""Integration management endpoints — QBO OAuth, token status."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DbDep, SettingsDep, get_db
from app.core.security import verify_api_key
from app.integrations.quickbooks.auth import (
    exchange_code_for_tokens,
    get_authorization_url,
)
from app.models.database import QBOToken

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# ── QBO OAuth2 ────────────────────────────────────────────────────────────────

@router.get("/qbo/authorize", summary="Start QBO OAuth2 flow")
async def qbo_authorize(
    user_id: str = Query(...),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Generate the QBO authorization URL.
    Redirect the user to this URL to connect their QuickBooks company.
    """
    state = secrets.token_urlsafe(32)
    auth_url = get_authorization_url(state)
    return {"authorization_url": auth_url, "state": state}


@router.get("/qbo/callback", summary="QBO OAuth2 callback handler")
async def qbo_callback(
    code: str = Query(...),
    realm_id: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Handle QBO OAuth2 callback. Exchanges authorization code for tokens
    and stores them in the database.
    """
    try:
        token_data = await exchange_code_for_tokens(code, realm_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    # Upsert token record
    existing = await db.get(QBOToken, realm_id)
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data["refresh_token"]
        existing.expires_at = token_data["expires_at"]
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(QBOToken(
            realm_id=realm_id,
            user_id="default",  # In production: extract from state
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
        ))

    await db.commit()
    return {"status": "connected", "realm_id": realm_id}


@router.get("/qbo/status", summary="Check QBO connection status")
async def qbo_status(
    realm_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """Check if a QBO realm is connected and tokens are valid."""
    token = await db.get(QBOToken, realm_id)
    if not token:
        return {"connected": False, "realm_id": realm_id}

    is_expired = datetime.now(timezone.utc) >= token.expires_at
    return {
        "connected": True,
        "realm_id": realm_id,
        "token_expired": is_expired,
        "expires_at": token.expires_at.isoformat(),
    }


@router.delete("/qbo/disconnect", summary="Disconnect a QBO company")
async def qbo_disconnect(
    realm_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """Remove stored QBO tokens for a realm."""
    token = await db.get(QBOToken, realm_id)
    if token:
        await db.delete(token)
        await db.commit()
    return {"status": "disconnected", "realm_id": realm_id}
