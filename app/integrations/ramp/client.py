"""Ramp API async client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class RampClient:
    """OAuth2 client_credentials Ramp client."""

    def __init__(self) -> None:
        self._base = settings.ramp_base_url
        self._client_id = settings.ramp_client_id
        self._client_secret = settings.ramp_client_secret
        self._access_token: str | None = None
        self._token_expires_at: datetime = datetime.now(timezone.utc)

    async def _get_token(self) -> str:
        if self._access_token and datetime.now(timezone.utc) < self._token_expires_at:
            return self._access_token

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.ramp.com/developer/v1/token",
                data={
                    "grant_type": "client_credentials",
                    "scope": "transactions:read cards:read users:read",
                },
                auth=(self._client_id, self._client_secret),
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=data.get("expires_in", 3600) - 60
        )
        return self._access_token  # type: ignore[return-value]

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{self._base}/{path}", headers=headers, params=params or {}
            )
            resp.raise_for_status()
            return resp.json()

    # ── Transactions ──────────────────────────────────────────────────────────

    async def get_transactions(
        self,
        start: str | None = None,
        end: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page_size": page_size}
        if start:
            params["from_date"] = start
        if end:
            params["to_date"] = end

        results: list[dict] = []
        next_page = None

        while True:
            if next_page:
                params["next"] = next_page
            data = await self._get("transactions", params)
            results.extend(data.get("data", []))
            next_page = data.get("page", {}).get("next")
            if not next_page:
                break

        return results

    async def get_transaction(self, txn_id: str) -> dict:
        return await self._get(f"transactions/{txn_id}")

    # ── Cards ─────────────────────────────────────────────────────────────────

    async def get_cards(self) -> list[dict]:
        data = await self._get("cards")
        return data.get("data", [])

    # ── Users ─────────────────────────────────────────────────────────────────

    async def get_users(self) -> list[dict]:
        data = await self._get("users")
        return data.get("data", [])

    # ── Receipts ──────────────────────────────────────────────────────────────

    async def get_receipts_missing(self) -> list[dict]:
        """Transactions missing receipts."""
        txns = await self.get_transactions()
        return [t for t in txns if not t.get("receipts")]

    # ── QBO Sync ──────────────────────────────────────────────────────────────

    async def get_unsynced_transactions(self) -> list[dict]:
        """Transactions not yet synced to QBO."""
        txns = await self.get_transactions()
        return [t for t in txns if not t.get("accounting_field_selections")]

    def normalize_for_coding(self, txn: dict) -> dict:
        """Flatten a Ramp transaction for the Transaction Coder agent."""
        return {
            "date": txn.get("user_transaction_time", "")[:10],
            "description": txn.get("merchant_name", ""),
            "amount": abs(txn.get("amount", 0) / 100),  # Ramp uses cents
            "type": "debit",
            "raw_memo": txn.get("memo", ""),
            "ramp_id": txn.get("id"),
            "card_last4": txn.get("card_holder", {}).get("last_name", ""),
            "category_code": txn.get("sk_category_name", ""),
        }
