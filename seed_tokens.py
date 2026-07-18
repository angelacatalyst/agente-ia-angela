"""
Script para insertar tokens QBO directamente en la base de datos SQLite.
Ejecutar DESPUÉS de levantar el backend al menos una vez (para que cree las tablas).

Uso:
    python seed_tokens.py
"""

import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./finance_ops.db"

TOKENS = [
    {
        "realm_id": "9341454429254087",
        "user_id": "angela",
        "access_token": "eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4Q0JDLUhTMjU2IiwieC5vcmciOiJIMCJ9..dRmAzJ8NVI2FJ6Py3n9G_w.LfISKXxmYlDN-mDhaQa6OispDmkhGhTAXzJKYznPHnHwRYQkTIK3zG7jWQAi-0Kg6eGzsNpP0FOmoqd4E3vsjZfw7namqL4eRNn9Fo48UwEhAz7yIm36saEtNZmiSPugAWjk-HRzTjN9cCJz7S0QBmYipq4TYz-nP2_bO1hf6Zc-wJC0305C6rPMQu63fO-bEVdIKNS1ck9EwG3wmUtOwSMYRSut2dmFTJZ4pf2B9GEb-OSMDYYAvy5IR1-TD30dlleWAc6fWs0TLfLYadiL_WVa93tLbBG6KS9NrZNKz5VQCmVQ7Mwv8Dt4PbNECU_jNKdVVKCw9cIENK5N6kXIUYrOBkvgrF3NyM69_0EIHo4XRBl31FvrSDaoPOE52rpy4dpYMIN9k3FVXbtTSLTiXdeAfPiOwvui-iLyNlLnDUorwZj26oJGPoW4Ck6eXpcE7zs5euOccLwID-VgmcazhQoPPJ__i_lg1ToTPKUe-KE.5AyBNZ2hTAikOL3N6Wv9pA",
        "refresh_token": "RT1-208-H0-1790628431ats59tyj2938e0kd3hbj",
        "expires_at": 1781905631.924208,
        "company": "3010 (For-Profit)",
    },
    {
        "realm_id": "9341454010854556",
        "user_id": "angela",
        "access_token": "eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4Q0JDLUhTMjU2IiwieC5vcmciOiJIMCJ9..k574UNyD_MXQ5dVuaZ7TGA.yddu61oy5SDSENGUeY5gcPo6Tuel5-RvHjFxmsEGu_8zHA9I38TY5A3rOeOf41yT8xOPdT2tiRf3fB8Bo2JoN0pDC02Ho69yBe6UWJE8-S2iEwzZYE8Fa1f1CtDKt6YVnz6Ub4m8BSIIo0L3WjD-QLSg7qqoSSeoJpzoIibajicWSkdNIDGFVYtprz9GvGmykWsx_vE3oJAlBBV6tj8_F3tRrfAXCY51aZvNsUnUc2Ldh2iTI_akuEh49Plgy23xQVEkovZsMq4jpRwFPz1eYkAgbfwGS-Ew7WcEon-4bYCIkdcygG7pY959PhlfkKQ-K07TgIpYqNqdqvmRnn-cTELs4RS-b94cuBFSpB5QeJBIW_cN-kSC14EHj3VKF0lxLSi5TyHzdr0IWywMo6UiMofk1RkHIg9gVwRb_sZXOx2GaIMBWRT8T8GXplPJaR9k30xG8iwrE-iyLYkL55HfqimVwj_nMFapB6BEnrIeTBU.oZy9WnN6l9C3SmvyoryzcQ",
        "refresh_token": "RT1-250-H0-1790628329ruflpnlvzb56r11mkga2",
        "expires_at": 1781905529.424352,
        "company": "Nonprofit Allapattah CDC",
    },
]


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for t in TOKENS:
            from sqlalchemy import text

            expires_at = datetime.fromtimestamp(t["expires_at"], tz=timezone.utc)
            now = datetime.now(timezone.utc)

            # Note: access token may be expired, app will auto-refresh using refresh_token
            print(f"\n📊 {t['company']} (realm: {t['realm_id']})")
            print(f"   Access token expired: {expires_at < now} (expired {(now - expires_at).days} days ago)")
            print(f"   Refresh token: {t['refresh_token'][:30]}...")

            await session.execute(
                text("""
                    INSERT INTO qbo_tokens (realm_id, user_id, access_token, refresh_token, expires_at, created_at, updated_at)
                    VALUES (:realm_id, :user_id, :access_token, :refresh_token, :expires_at, :now, :now)
                    ON CONFLICT(realm_id) DO UPDATE SET
                        access_token = excluded.access_token,
                        refresh_token = excluded.refresh_token,
                        expires_at = excluded.expires_at,
                        updated_at = excluded.updated_at
                """),
                {
                    "realm_id": t["realm_id"],
                    "user_id": t["user_id"],
                    "access_token": t["access_token"],
                    "refresh_token": t["refresh_token"],
                    "expires_at": expires_at,
                    "now": now,
                }
            )
            print(f"   ✅ Token insertado en BD")

        await session.commit()

    await engine.dispose()
    print("\n✅ Tokens sembrados correctamente.")
    print("\n⚠️  IMPORTANTE: Los access tokens están expirados.")
    print("   El sistema intentará renovarlos automáticamente con el refresh_token.")
    print("   Para que funcione la renovación, agrega QBO_CLIENT_ID y QBO_CLIENT_SECRET al .env")


if __name__ == "__main__":
    asyncio.run(seed())
