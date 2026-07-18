"""
Renueva los access tokens QBO expirados usando el refresh_token.
Ejecutar desde la carpeta finance-ops-agent.
"""

import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./finance_ops.db"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

# Credenciales de tu app Intuit
CLIENT_ID = "ABV26raDvRdwv3NMPFUUnV7L2l2dkBgoad3OQqIGBzvLjJWp4X"
CLIENT_SECRET = "npFa0albITpVKBrqq1okYi11nwaPqbkUoYXnJRHC"

REFRESH_TOKENS = {
    "9341454429254087": {
        "company": "3010 (For-Profit)",
        "refresh_token": "RT1-208-H0-1790628431ats59tyj2938e0kd3hbj",
    },
    "9341454010854556": {
        "company": "Nonprofit Allapattah CDC",
        "refresh_token": "RT1-250-H0-1790628329ruflpnlvzb56r11mkga2",
    },
}


async def refresh_token(realm_id: str, refresh_token: str, company: str) -> dict | None:
    print(f"\n🔄 Renovando token para {company}...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                auth=(CLIENT_ID, CLIENT_SECRET),
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            print(f"   ✅ Token renovado exitosamente")
            return data
        except httpx.HTTPStatusError as e:
            print(f"   ❌ Error HTTP {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None


async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for realm_id, info in REFRESH_TOKENS.items():
            data = await refresh_token(realm_id, info["refresh_token"], info["company"])
            if not data:
                continue

            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
            new_refresh = data.get("refresh_token", info["refresh_token"])

            await session.execute(
                text("""
                    UPDATE qbo_tokens
                    SET access_token = :access_token,
                        refresh_token = :refresh_token,
                        expires_at = :expires_at,
                        updated_at = :now
                    WHERE realm_id = :realm_id
                """),
                {
                    "access_token": data["access_token"],
                    "refresh_token": new_refresh,
                    "expires_at": expires_at,
                    "now": datetime.now(timezone.utc),
                    "realm_id": realm_id,
                }
            )
            print(f"   💾 BD actualizada. Token válido hasta: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")

        await session.commit()

    await engine.dispose()
    print("\n✅ Proceso completado.")


if __name__ == "__main__":
    asyncio.run(main())
