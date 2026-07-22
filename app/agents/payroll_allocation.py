"""Module 10 — Payroll Allocation & Analysis Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.tools.file_tools import FILE_TOOLS


class PayrollAllocationAgent(FinanceAgentBase):
    """
    Analyzes payroll entries, validates allocations across grants and programs,
    reviews functional expense classification, and detects payroll anomalies.
    """

    module = "payroll_allocation"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=qbo_tools)

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def analyze_payroll(
        self,
        realm_id: str,
        period_start: str,
        period_end: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full payroll analysis for a given period."""
        prompt = f"""
Perform a complete payroll analysis and allocation review for:

Period: {period_start} to {period_end}
QBO Realm: {realm_id}

Steps:
1. Fetch payroll journal entries for the period using get_payroll_entries
2. Fetch the employee list using get_employees
3. Fetch time activities (timesheets) if available using get_time_activities
4. Fetch the chart of accounts to identify payroll accounts (salaries, taxes, benefits)
5. Fetch the P&L to compare payroll vs budget

ANALYZE:

## PAYROLL SUMMARY
- Total Gross Wages
- Total Employer Taxes (FICA, FUTA, SUTA, etc.)
- Total Benefits (health, retirement, etc.)
- Total Net Payroll Cost
- Payroll as % of Total Expenses

## ALLOCATION BREAKDOWN
Analyze how payroll is split across:
- Programs (direct program costs)
- Administrative/Management
- Fundraising
- By Grant/Class (if applicable)

For nonprofits: Verify the functional expense split follows Form 990 requirements.

## EMPLOYEE-LEVEL DETAIL
| Employee | Gross Pay | Taxes | Benefits | Program % | Admin % | Grant Allocation |

## PAYROLL ACCOUNT VERIFICATION
- Are payroll liabilities cleared (Payroll Taxes Payable = $0 after payment)?
- Any payroll liability balances > 30 days?
- Are employer taxes properly accrued?

## COMPLIANCE CHECKS
- Do allocations match approved FTE in grant budgets?
- Any employees over-allocated (>100% across grants)?
- Any payroll posted to wrong period?
- Are time sheets on file to support grant allocations?

## RED FLAGS
🔴 HIGH RISK: [any payroll issues requiring immediate action]
🟡 WARNING: [items needing correction]
🟢 RECOMMENDATION: [best practices]

## RECOMMENDED JOURNAL ENTRIES
Any correcting entries needed for misallocated payroll.
"""
        return await self.run(prompt, context=context)

    async def verify_grant_payroll_allocation(
        self,
        realm_id: str,
        grant_name: str,
        period_start: str,
        period_end: str,
        approved_fte: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify payroll allocation matches grant-approved FTE for a specific grant."""
        fte_text = f"Approved FTE for this grant: {approved_fte}" if approved_fte else ""
        prompt = f"""
Verify payroll allocation for grant: {grant_name}
Period: {period_start} to {period_end}
QBO Realm: {realm_id}
{fte_text}

1. Fetch payroll journal entries filtered to class/grant "{grant_name}"
2. Fetch time activities for this period
3. Fetch employees to get their pay rates

CALCULATE:
- Total salary charged to this grant
- Total FTE (based on time sheets)
- Average hourly/salary rate by employee
- Are charges consistent with approved budget?

RETURN:
- Total payroll charged to grant: $X
- FTE utilized: X.XX out of approved {approved_fte or 'X.XX'}
- Employee breakdown table
- Compliance status: COMPLIANT / AT RISK / FINDING
- Specific issues and recommended corrections
"""
        return await self.run(prompt, context=context)

    async def breakdown_payroll_by_period(
        self,
        realm_id: str,
        pay_period: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Detailed payroll desglose (breakdown) for a specific pay period."""
        prompt = f"""
Provide a complete payroll desglose (breakdown) for pay period: {pay_period}
QBO Realm: {realm_id}

Fetch all payroll journal entries for this period.
Then provide a complete breakdown:

## GROSS WAGES BY EMPLOYEE
| Employee Name | Classification | Gross Pay | Regular Hours | OT Hours |

## TAX WITHHOLDING DETAIL
| Tax Type | Employee Portion | Employer Portion | Total |
|----------|-----------------|------------------|-------|
| Federal Income Tax | | | |
| Social Security (6.2%) | | | |
| Medicare (1.45%) | | | |
| State Income Tax | | | |
| FUTA (0.6%) | | | |
| SUTA | | | |

## BENEFIT DEDUCTIONS
| Benefit | Employee Pre-Tax | Employer Contribution | Total |

## NET PAY SUMMARY
- Gross Wages: $X
- Total Employee Deductions: $(X)
- Net Pay (to employees): $X
- Total Employer Taxes: $X
- Total Employer Benefits: $X
- Total Payroll Cost to Organization: $X

## PAYROLL ACCOUNTS STATUS (in QBO after entry)
- Salaries & Wages Payable: should be $0 after ACH
- Payroll Taxes Payable: [current balance]
- Benefits Payable: [current balance]

## ALLOCATION SUMMARY
How this payroll is split across programs/grants/functions.
"""
        return await self.run(prompt, context=context)
