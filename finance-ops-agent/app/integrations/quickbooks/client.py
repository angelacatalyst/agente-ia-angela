"""QuickBooks Online REST API async client with auto token refresh."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.quickbooks.auth import refresh_access_token

logger = get_logger(__name__)
settings = get_settings()


class QBOClient:
    """Async QBO API client. Instantiate per-request with stored tokens."""

    def __init__(
        self,
        realm_id: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        on_token_refresh: Any = None,  # callback(realm_id, new_tokens) -> None
    ) -> None:
        self.realm_id = realm_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.on_token_refresh = on_token_refresh
        self._base = f"{settings.qbo_base_url}/v3/company/{realm_id}"
        self._minor_version = settings.qbo_minor_version

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _ensure_token(self) -> None:
        if datetime.now(timezone.utc) >= self.expires_at:
            logger.info("QBO access token expired — refreshing", realm_id=self.realm_id)
            new_tokens = await refresh_access_token(self.refresh_token)
            self.access_token = new_tokens["access_token"]
            self.refresh_token = new_tokens["refresh_token"]
            self.expires_at = new_tokens["expires_at"]
            if self.on_token_refresh:
                await self.on_token_refresh(self.realm_id, new_tokens)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _params(self, extra: dict | None = None) -> dict:
        p = {"minorversion": str(self._minor_version)}
        if extra:
            p.update(extra)
        return p

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        await self._ensure_token()
        url = f"{self._base}/{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=self._params(params))
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _query(self, sql: str) -> list[dict[str, Any]]:
        """Run a QBO SQL-like query via the /query endpoint."""
        await self._ensure_token()
        url = f"{self._base}/query"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers=self._headers(),
                params={**self._params(), "query": sql},
            )
            resp.raise_for_status()
            data = resp.json()
        qr = data.get("QueryResponse", {})
        # Return first non-empty entity list
        for key, value in qr.items():
            if isinstance(value, list):
                return value  # type: ignore[return-value]
        return []

    # ── Reports ───────────────────────────────────────────────────────────────

    async def get_balance_sheet(self, as_of_date: str | None = None) -> dict:
        params: dict = {}
        if as_of_date:
            params["date_macro"] = as_of_date
        return await self._get("reports/BalanceSheet", params)

    async def get_profit_loss(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        params: dict = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return await self._get("reports/ProfitAndLoss", params)

    async def get_trial_balance(self, as_of_date: str | None = None) -> dict:
        params: dict = {}
        if as_of_date:
            params["date_macro"] = as_of_date
        return await self._get("reports/TrialBalance", params)

    async def get_general_ledger(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        params: dict = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return await self._get("reports/GeneralLedger", params)

    async def get_ar_aging(self) -> dict:
        return await self._get("reports/AgedReceivables")

    async def get_ap_aging(self) -> dict:
        return await self._get("reports/AgedPayables")

    # ── Transactions ──────────────────────────────────────────────────────────

    async def get_undeposited_funds(self) -> list[dict]:
        return await self._query(
            "SELECT * FROM Deposit WHERE DepositToAccountRef = 'Undeposited Funds' MAXRESULTS 200"
        )

    async def get_bank_transactions(
        self, account_id: str, start_date: str, end_date: str
    ) -> list[dict]:
        sql = (
            f"SELECT * FROM Transaction WHERE AccountRef = '{account_id}' "
            f"AND TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' "
            "MAXRESULTS 1000"
        )
        return await self._query(sql)

    async def get_uncategorized_transactions(self) -> list[dict]:
        return await self._query(
            "SELECT * FROM Purchase WHERE AccountRef IS NULL MAXRESULTS 200"
        )

    # ── Vendors ───────────────────────────────────────────────────────────────

    async def get_vendors(self, active: bool = True) -> list[dict]:
        where = "WHERE Active = true" if active else ""
        return await self._query(f"SELECT * FROM Vendor {where} MAXRESULTS 500")

    async def get_vendor(self, vendor_id: str) -> dict:
        return await self._get(f"vendor/{vendor_id}")

    async def create_vendor(self, payload: dict) -> dict:
        await self._ensure_token()
        url = f"{self._base}/vendor"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url, headers=self._headers(), params=self._params(), json=payload
            )
            resp.raise_for_status()
            return resp.json()

    # ── Bills ─────────────────────────────────────────────────────────────────

    async def get_bills(
        self, start_date: str | None = None, unpaid_only: bool = False
    ) -> list[dict]:
        clauses = []
        if start_date:
            clauses.append(f"TxnDate >= '{start_date}'")
        if unpaid_only:
            clauses.append("Balance > '0'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return await self._query(f"SELECT * FROM Bill {where} MAXRESULTS 200")

    async def create_bill(self, payload: dict) -> dict:
        await self._ensure_token()
        url = f"{self._base}/bill"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url, headers=self._headers(), params=self._params(), json=payload
            )
            resp.raise_for_status()
            return resp.json()

    # ── Chart of Accounts ─────────────────────────────────────────────────────

    async def get_chart_of_accounts(self) -> list[dict]:
        return await self._query("SELECT * FROM Account WHERE Active = true MAXRESULTS 1000")

    # ── Customers / AR ────────────────────────────────────────────────────────

    async def get_invoices(self, unpaid_only: bool = True) -> list[dict]:
        where = "WHERE Balance > '0'" if unpaid_only else ""
        return await self._query(f"SELECT * FROM Invoice {where} MAXRESULTS 200")

    # ── Payroll ───────────────────────────────────────────────────────────────

    async def get_journal_entries(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict]:
        clauses = []
        if start_date:
            clauses.append(f"TxnDate >= '{start_date}'")
        if end_date:
            clauses.append(f"TxnDate <= '{end_date}'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return await self._query(f"SELECT * FROM JournalEntry {where} MAXRESULTS 200")

    # ── Classes / Departments ─────────────────────────────────────────────────

    async def get_classes(self) -> list[dict]:
        return await self._query("SELECT * FROM Class WHERE Active = true MAXRESULTS 200")

    async def get_departments(self) -> list[dict]:
        return await self._query("SELECT * FROM Department WHERE Active = true MAXRESULTS 200")
