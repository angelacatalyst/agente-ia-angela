"""Module 1 — QBO Accounting Auditor Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.tools.file_tools import FILE_TOOLS


class QBOAuditorAgent(FinanceAgentBase):
    """
    Analyzes QBO reports and identifies accounting risks, anomalies,
    and compliance issues. Produces structured risk reports.
    """

    module = "qbo_auditor"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=qbo_tools)

    def _default_tools(self) -> list[BaseTool]:
        # File tools always available; QBO tools injected at runtime if connected
        return list(FILE_TOOLS)

    async def run_full_audit(
        self,
        realm_id: str,
        as_of_date: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a comprehensive QBO audit across all standard reports."""
        prompt = (
            f"Run a complete accounting audit for QBO realm {realm_id}. "
            f"{'Use reports as of ' + as_of_date + '. ' if as_of_date else ''}"
            "Fetch and analyze: Balance Sheet, P&L, AR Aging, AP Aging, "
            "Undeposited Funds, and Journal Entries. "
            "Return a complete risk report with HIGH RISK, WARNINGS, RECOMMENDATIONS, "
            "and PRIORITY ACTIONS sections."
        )
        return await self.run(prompt, context=context)
