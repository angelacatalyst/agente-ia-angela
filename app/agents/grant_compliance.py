"""Module 3 — Nonprofit Grant Compliance Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.tools.file_tools import FILE_TOOLS


class GrantComplianceAgent(FinanceAgentBase):
    """
    Audits grant spending against budget and compliance rules.
    Identifies disallowable costs, payroll misallocations, and compliance risks.
    """

    module = "grant_compliance"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=qbo_tools)

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def audit_grant(
        self,
        realm_id: str,
        grant_name: str,
        period_start: str,
        period_end: str,
        grant_budget: dict[str, float] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full compliance audit for a single grant."""
        budget_text = ""
        if grant_budget:
            import json
            budget_text = f"\nApproved Budget:\n{json.dumps(grant_budget, indent=2)}"

        prompt = f"""
Perform a complete grant compliance audit for:

Grant: {grant_name}
Period: {period_start} to {period_end}
QBO Realm: {realm_id}
{budget_text}

Please:
1. Fetch the General Ledger filtered to this grant/class for the period
2. Review all expenses for allowability
3. Check payroll allocations
4. Verify no unallowable costs (alcohol, lobbying, political, entertainment > limits)
5. Compare actual spending to budget (if provided)
6. Identify any expenses outside the grant period
7. Check for proper documentation requirements

Return a compliance report with:
- FINDINGS (will cause audit issues)
- CONCERNS (need documentation or correction)
- ADVISORIES (best practice gaps)
- Summary of grant financial position (budget vs actual)
- Specific correcting entries recommended
"""
        return await self.run(prompt, context=context)

    async def audit_all_grants(
        self,
        realm_id: str,
        grant_names: list[str],
        period_start: str,
        period_end: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Audit multiple grants and return a consolidated compliance dashboard."""
        grants_list = "\n".join(f"- {g}" for g in grant_names)
        prompt = f"""
Perform a consolidated grant compliance review for all active grants:

Period: {period_start} to {period_end}
QBO Realm: {realm_id}

Grants to Review:
{grants_list}

For each grant, check:
1. Budget vs actual spending by line item
2. Allowable vs unallowable costs
3. Payroll allocation accuracy
4. Grant period compliance
5. Documentation completeness
6. Class/program tracking accuracy in QBO

Return:
1. COMPLIANT grants (no issues)
2. AT-RISK grants (minor issues, fixable before audit)
3. CRITICAL grants (major issues requiring immediate action)
4. Cross-grant issues (e.g., costs not allocated to any grant)
5. Executive summary for controller review
"""
        return await self.run(prompt, context=context)
