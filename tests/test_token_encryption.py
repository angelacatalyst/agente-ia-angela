"""QuickBooks tokens are stored encrypted and read back transparently."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.crypto import decrypt, encrypt
from app.models.database import QBOToken


def test_round_trip_and_legacy_plaintext() -> None:
    assert decrypt(encrypt("RT1-abc")) == "RT1-abc"
    assert encrypt("RT1-abc") != "RT1-abc"
    assert decrypt("legacy-plain-token") == "legacy-plain-token"


def test_column_is_encrypted_at_rest() -> None:
    async def run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: QBOToken.__table__.create(c))
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            db.add(QBOToken(realm_id="1", user_id="u", access_token="AT", refresh_token="RT",
                            expires_at=datetime.now(timezone.utc)))
            await db.commit()
            raw = (await db.execute(text("SELECT refresh_token FROM qbo_tokens"))).scalar_one()
            assert raw != "RT" and raw.startswith("gAAAAA")
            row = (await db.execute(select(QBOToken))).scalar_one()
            assert row.refresh_token == "RT"
        await engine.dispose()

    asyncio.run(run())
