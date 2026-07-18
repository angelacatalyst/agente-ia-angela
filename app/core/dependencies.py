"""FastAPI dependency injection — DB sessions, Redis, clients."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.database import AsyncSessionLocal

logger = get_logger(__name__)


# ── Settings ──────────────────────────────────────────────────────────────────

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ── DB Session ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── Redis ─────────────────────────────────────────────────────────────────────

_redis_pool: aioredis.Redis | None = None


async def get_redis(settings: SettingsDep) -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]


# ── QBO Client factory ────────────────────────────────────────────────────────

async def get_qbo_client_for_realm(
    realm_id: str,
    db: AsyncSession,
) -> Any | None:
    """
    Load QBO tokens from DB for the given realm_id and return a configured QBOClient.
    Returns None if no token found.
    Auto-refreshes expired access tokens and saves new tokens to DB.
    """
    from app.integrations.quickbooks.client import QBOClient
    from app.models.database import QBOToken

    token = await db.get(QBOToken, realm_id)
    if not token:
        logger.warning("No QBO token found for realm", realm_id=realm_id)
        return None

    async def on_token_refresh(rid: str, new_tokens: dict) -> None:
        """Persist refreshed tokens back to DB."""
        t = await db.get(QBOToken, rid)
        if t:
            t.access_token = new_tokens["access_token"]
            t.refresh_token = new_tokens["refresh_token"]
            t.expires_at = new_tokens["expires_at"]
            t.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("QBO token refreshed and saved", realm_id=rid)

    return QBOClient(
        realm_id=token.realm_id,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
        on_token_refresh=on_token_refresh,
    )
