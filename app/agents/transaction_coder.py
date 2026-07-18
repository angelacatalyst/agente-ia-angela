"""Module 2 — Transaction Coding Agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.models.schemas import RawTransaction, TransactionCodingRequest
from app.tools.file_tools import FILE_TOOLS


class TransactionCoderAgent(FinanceAgentBase):
    """
    Categorizes bank and credit card transactions with QBO account codes,
    grant, program, class, and project assignments.
    """

    module = "transaction_coder"

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def code_transactions(
        self,
        request: TransactionCodingRequest,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Code a batch of transactions."""
        txn_json = json.dumps(
            [t.model_dump() for t in request.transactions], default=str, indent=2
        )

        context_parts = {
            "organization_type": request.organization_type,
            "chart_of_accounts": json.dumps(request.chart_of_accounts),
            "active_grants": ", ".join(request.active_grants) or "None",
            "active_programs": ", ".join(request.active_programs) or "None",
            "active_classes": ", ".join(request.active_classes) or "None",
        }

        prompt = f"""
Code the following {len(request.transactions)} transactions for QuickBooks Online entry.

Organization Type: {request.organization_type}

Active Grants: {', '.join(request.active_grants) or 'N/A'}
Active Programs: {', '.join(request.active_programs) or 'N/A'}
Active Classes: {', '.join(request.active_classes) or 'N/A'}

TRANSACTIONS TO CODE:
{txn_json}

Return a structured coding result for each transaction including:
- vendor (standardized name)
- account (QBO account name)
- account_code (number if available)
- category
- grant (if applicable)
- program (if applicable)
- class (if applicable)
- project (if applicable)
- memo (descriptive)
- confidence (HIGH/MEDIUM/LOW)
- reasoning

Group uncertain items separately and explain what additional information is needed.
"""
        merged_ctx = {**(context or {}), **context_parts}
        return await self.run(prompt, context=merged_ctx)

    async def code_from_file(
        self,
        file_path: str,
        file_type: str = "auto",
        organization_type: str = "nonprofit",
        active_grants: list[str] | None = None,
        active_programs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Code transactions from an uploaded CSV/Excel file."""
        prompt = (
            f"Read the file at '{file_path}' and code all transactions for QBO. "
            f"Organization type: {organization_type}. "
            f"Active grants: {', '.join(active_grants or []) or 'none'}. "
            f"Active programs: {', '.join(active_programs or []) or 'none'}. "
            "Parse the file, then code each transaction with full QBO coding including "
            "account, grant, program, class, and memo. "
            "Return HIGH/MEDIUM/LOW confidence for each."
        )
        return await self.run(prompt)
