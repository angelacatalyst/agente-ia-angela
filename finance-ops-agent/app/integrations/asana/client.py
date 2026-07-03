"""Asana REST API async client."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_BASE = "https://app.asana.com/api/1.0"


class AsanaClient:
    def __init__(self, access_token: str | None = None) -> None:
        self._token = access_token or settings.asana_access_token
        self._workspace = settings.asana_workspace_gid
        self._default_project = settings.asana_default_project_gid

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_BASE}/{path}", headers=self._headers(), params=params or {}
            )
            resp.raise_for_status()
            return resp.json().get("data")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _post(self, path: str, payload: dict) -> Any:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE}/{path}", headers=self._headers(), json={"data": payload}
            )
            resp.raise_for_status()
            return resp.json().get("data")

    async def _put(self, path: str, payload: dict) -> Any:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.put(
                f"{_BASE}/{path}", headers=self._headers(), json={"data": payload}
            )
            resp.raise_for_status()
            return resp.json().get("data")

    # ── Tasks ─────────────────────────────────────────────────────────────────

    async def create_task(
        self,
        name: str,
        notes: str = "",
        due_on: str | None = None,
        assignee: str | None = None,
        project_gid: str | None = None,
        tags: list[str] | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "name": name,
            "notes": notes,
            "workspace": self._workspace,
            "projects": [project_gid or self._default_project],
        }
        if due_on:
            payload["due_on"] = due_on
        if assignee:
            payload["assignee"] = assignee
        if custom_fields:
            payload["custom_fields"] = custom_fields

        task = await self._post("tasks", payload)
        logger.info("Asana task created", task_gid=task["gid"], name=name)
        return task  # type: ignore[return-value]

    async def get_task(self, task_gid: str) -> dict:
        return await self._get(f"tasks/{task_gid}")  # type: ignore[return-value]

    async def update_task(self, task_gid: str, payload: dict) -> dict:
        return await self._put(f"tasks/{task_gid}", payload)  # type: ignore[return-value]

    async def complete_task(self, task_gid: str) -> dict:
        return await self.update_task(task_gid, {"completed": True})

    async def add_comment(self, task_gid: str, text: str) -> dict:
        return await self._post(  # type: ignore[return-value]
            f"tasks/{task_gid}/stories", {"text": text}
        )

    # ── Projects ──────────────────────────────────────────────────────────────

    async def get_project_tasks(self, project_gid: str) -> list[dict]:
        return await self._get(  # type: ignore[return-value]
            f"projects/{project_gid}/tasks",
            {"opt_fields": "name,completed,due_on,assignee,notes"},
        )

    async def list_projects(self) -> list[dict]:
        return await self._get(  # type: ignore[return-value]
            "projects",
            {"workspace": self._workspace, "opt_fields": "name,gid,color"},
        )

    # ── Vendor Onboarding Checklist ───────────────────────────────────────────

    async def create_vendor_onboarding_task(
        self,
        vendor_name: str,
        missing_docs: list[str],
        due_on: str | None = None,
    ) -> dict:
        notes_lines = [
            f"Vendor Onboarding: {vendor_name}",
            "",
            "Required Documents:",
            *[f"  ☐ {doc}" for doc in missing_docs],
        ]
        return await self.create_task(
            name=f"[Vendor Onboarding] {vendor_name}",
            notes="\n".join(notes_lines),
            due_on=due_on,
        )

    # ── Payment Request Task ──────────────────────────────────────────────────

    async def create_payment_request_task(
        self,
        vendor: str,
        amount: float,
        invoice_number: str | None,
        notes: str = "",
        due_on: str | None = None,
    ) -> dict:
        inv = invoice_number or "N/A"
        return await self.create_task(
            name=f"[Payment Request] {vendor} — ${amount:,.2f} | Inv#{inv}",
            notes=notes,
            due_on=due_on,
        )
