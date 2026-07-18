"""Module 8 — Fractional Controller Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.models.schemas import ControllerRequest
from app.tools.file_tools import FILE_TOOLS


class ControllerAgent(FinanceAgentBase):
    """
    Performs a Controller-level financial review. Produces executive
    briefings with priorities, risks, KPIs, and month-end checklists.
    """

    module = "controller"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=qbo_tools)

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def morning_briefing(
        self,
        request: ControllerRequest,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a morning controller briefing."""
        prompt = f"""
Perform a complete Controller-level financial review for period: {request.period}
QBO Realm: {request.realm_id}

Pull and analyze:
1. Balance Sheet (current)
2. Profit & Loss (YTD and current period)
3. AR Aging (full detail)
4. AP Aging (full detail)
5. Undeposited Funds
6. Any open bills or overdue invoices

Generate a morning controller briefing with:

## 🎯 TOP PRIORITIES TODAY (ranked by urgency)
[Numbered action items with time estimates]

## ⚠️ FINANCIAL RISKS
[Risk register: HIGH/MEDIUM/LOW with dollar impact]

## 📊 KEY METRICS
- Cash position
- AR balance and > 90 days amount
- AP balance and overdue amount
- Undeposited Funds balance
- Budget vs actual (if available)

## 📋 MONTH-END CLOSE CHECKLIST
[Status of each month-end task ✅/❌/🔄]

## 💡 RECOMMENDATIONS
[Strategic and operational recommendations]

## 📝 NARRATIVE (3-4 sentences for executive summary)
[Plain language financial status summary]

{"Include strategic recommendations." if request.include_recommendations else ""}
"""
        return await self.run(prompt, context=context)

    async def month_end_review(
        self,
        realm_id: str,
        month: str,
        year: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a comprehensive month-end close review."""
        prompt = f"""
Perform a comprehensive month-end close review for {month} {year}.
QBO Realm: {realm_id}

Review ALL of the following and provide status + any needed corrections:

1. BANK RECONCILIATIONS
   - Are all bank accounts reconciled?
   - Any reconciling items > 30 days?

2. CREDIT CARD RECONCILIATIONS
   - All credit cards reconciled to statements?

3. ACCOUNTS RECEIVABLE
   - AR Aging reviewed?
   - Any write-offs needed?
   - Collections follow-up required?

4. ACCOUNTS PAYABLE
   - All bills entered?
   - Any duplicate bills?
   - Accruals needed?

5. PAYROLL
   - Payroll posted correctly?
   - Allocations match time sheets?
   - Employer taxes correct?

6. GRANT ACCOUNTING
   - All grant expenses allocated?
   - Classes/programs used correctly?

7. JOURNAL ENTRIES
   - Depreciation posted?
   - Prepaid amortization posted?
   - Deferred revenue adjustments?

8. FINANCIAL STATEMENT REVIEW
   - P&L reasonable vs prior month?
   - Balance Sheet balances?
   - Equity roll-forward correct?

Return a complete month-end close report with checklist status and action items.
"""
        return await self.run(prompt, context=context)
