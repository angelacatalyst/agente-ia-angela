"""Module 9 — Bank Reconciliation Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.tools.file_tools import FILE_TOOLS


class BankReconciliationAgent(FinanceAgentBase):
    """
    Performs bank and credit card reconciliation.
    Identifies uncleared items, outstanding checks, deposits in transit,
    and reconciling differences.
    """

    module = "bank_reconciliation"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=qbo_tools)

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def reconcile_account(
        self,
        realm_id: str,
        account_name: str,
        statement_balance: float,
        statement_date: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a full bank reconciliation for a specific account."""
        prompt = f"""
Perform a complete bank reconciliation for:

Account: {account_name}
Statement Date: {statement_date}
Statement Ending Balance: ${statement_balance:,.2f}
QBO Realm: {realm_id}

Steps to perform:
1. Use get_bank_accounts to find the account ID for "{account_name}"
2. Fetch the balance sheet to get the QBO book balance for this account
3. Fetch recent bank transactions (last 60 days) for this account
4. Identify all UNCLEARED transactions (checks issued but not cashed, deposits in transit)
5. Calculate the adjusted book balance

Reconciliation Formula:
Bank Statement Balance: ${statement_balance:,.2f}
+ Deposits in Transit: [list each one]
- Outstanding Checks/Payments: [list each one]
= Adjusted Bank Balance: [calculated]

QBO Book Balance: [from Balance Sheet]
+/- Journal Entry Adjustments: [if any]
= Adjusted Book Balance: [calculated]

RESULT: Do they match? If not, identify the difference.

Return:
## RECONCILIATION SUMMARY
- Statement Balance vs Book Balance
- Total Deposits in Transit (itemized)
- Total Outstanding Checks (itemized)
- Adjusted Balances
- RECONCILED ✅ or DIFFERENCE FOUND ❌

## UNCLEARED ITEMS (table format)
Date | Description | Amount | Type | Days Outstanding

## DISCREPANCIES
List any amounts that can't be reconciled with explanation and corrective action.

## RECOMMENDED JOURNAL ENTRIES
Any bank charges, interest income, or errors that need to be recorded in QBO.
"""
        return await self.run(prompt, context=context)

    async def reconcile_all_accounts(
        self,
        realm_id: str,
        as_of_date: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Review reconciliation status for ALL bank and credit card accounts."""
        prompt = f"""
Perform a reconciliation status review for ALL bank and credit card accounts as of {as_of_date}.
QBO Realm: {realm_id}

1. Use get_bank_accounts to list all bank and credit card accounts
2. For each account, check the current balance and last reconciliation date
3. Identify which accounts are UNRECONCILED or OVERDUE for reconciliation
4. Pull undeposited funds balance
5. Check cash flow statement for the period

Return a complete bank reconciliation status dashboard:

## ACCOUNT STATUS SUMMARY
| Account | QBO Balance | Last Reconciled | Days Since Rec | Status |
|---------|------------|-----------------|----------------|--------|

## CRITICAL ISSUES (accounts > 30 days unreconciled)

## UNDEPOSITED FUNDS STATUS

## RECONCILING ITEMS SUMMARY (across all accounts)

## RECOMMENDED ACTIONS (prioritized)
"""
        return await self.run(prompt, context=context)
