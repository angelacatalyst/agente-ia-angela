"""QBO Auditor endpoint — direct QBO data analysis, no AI API key required."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.integrations.quickbooks.client import QBOClient
from app.models.database import QBOToken

router = APIRouter(prefix="/audit", tags=["QBO Auditor"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_client(realm_id: str, db: AsyncSession) -> QBOClient:
    token = await db.get(QBOToken, realm_id)
    if not token:
        raise HTTPException(404, "Company not connected. Connect it in Settings first.")
    return QBOClient(
        realm_id=realm_id,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
    )


def _safe_float(v: Any) -> float:
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0


def _walk_report(rows: list[dict], results: list[dict], section: str = "") -> None:
    """Recursively walk QBO report rows and collect {section, name, amount}."""
    for row in rows:
        row_type = row.get("type", "")
        if row_type == "Section":
            header = row.get("Header", {})
            cols = header.get("ColData", [])
            sec_name = cols[0].get("value", section) if cols else section
            sub_rows = row.get("Rows", {}).get("Row", [])
            _walk_report(sub_rows, results, sec_name)
            # Also capture section summary
            summary = row.get("Summary", {})
            if summary:
                scols = summary.get("ColData", [])
                if len(scols) >= 2:
                    results.append({
                        "section": section,
                        "name": scols[0].get("value", ""),
                        "amount": _safe_float(scols[1].get("value", 0)),
                        "is_summary": True,
                    })
        elif row_type == "Data":
            cols = row.get("ColData", [])
            if len(cols) >= 2:
                results.append({
                    "section": section,
                    "name": cols[0].get("value", ""),
                    "amount": _safe_float(cols[1].get("value", 0)),
                    "is_summary": False,
                })


def _find_accounts(rows: list[dict], *keywords: str) -> list[dict]:
    """Find rows whose name contains any of the keywords (case-insensitive)."""
    kws = [k.lower() for k in keywords]
    return [r for r in rows if any(kw in r["name"].lower() for kw in kws)]


def _flag(condition: bool, message: str, severity: str = "medium") -> dict | None:
    if condition:
        return {"severity": severity, "message": message}
    return None


# ── Diagnostic checks ─────────────────────────────────────────────────────────

def _check_pl(pl: dict, from_date: str, to_date: str) -> list[dict]:
    findings = []
    rows: list[dict] = []
    _walk_report(pl.get("Rows", {}).get("Row", []), rows)

    # Uncategorized income/expense
    uncategorized = _find_accounts(rows, "uncategorized income", "uncategorized expense")
    for r in uncategorized:
        if r["amount"] != 0:
            f = _flag(True, f"⚠️ '{r['name']}' has a balance of ${r['amount']:,.2f} — transactions need to be categorized.", "high")
            if f: findings.append(f)

    # Ask My Accountant / Reconciliation Discrepancy
    problem_accts = _find_accounts(rows, "ask my accountant", "reconciliation discrepancy")
    for r in problem_accts:
        if r["amount"] != 0:
            f = _flag(True, f"⚠️ '{r['name']}' has ${r['amount']:,.2f} — review and reclassify these transactions.", "high")
            if f: findings.append(f)

    # Negative income balances
    income_rows = [r for r in rows if r["section"] in ("Income", "Revenue", "Operating Revenue") and not r["is_summary"]]
    neg_income = [r for r in income_rows if r["amount"] < 0]
    for r in neg_income:
        findings.append({"severity": "medium", "message": f"Negative income balance in '{r['name']}': ${r['amount']:,.2f}"})

    # Negative expense balances
    expense_rows = [r for r in rows if "expense" in r["section"].lower() and not r["is_summary"]]
    neg_exp = [r for r in expense_rows if r["amount"] < 0]
    for r in neg_exp[:5]:  # cap at 5
        findings.append({"severity": "low", "message": f"Negative expense balance in '{r['name']}': ${r['amount']:,.2f}"})

    return findings


def _check_bs(bs: dict) -> list[dict]:
    findings = []
    rows: list[dict] = []
    _walk_report(bs.get("Rows", {}).get("Row", []), rows)

    # Opening Balance Equity
    obe = _find_accounts(rows, "opening balance equity")
    for r in obe:
        if abs(r["amount"]) > 0:
            findings.append({"severity": "high", "message": f"⚠️ Opening Balance Equity has a balance of ${r['amount']:,.2f} — should be $0.00."})

    # Uncategorized assets
    unc_assets = _find_accounts(rows, "uncategorized asset")
    for r in unc_assets:
        if abs(r["amount"]) > 0:
            findings.append({"severity": "high", "message": f"Uncategorized Asset account has ${r['amount']:,.2f} — needs to be classified."})

    # AR balance check
    ar = _find_accounts(rows, "accounts receivable")
    for r in ar:
        if r["amount"] < 0:
            findings.append({"severity": "medium", "message": f"Accounts Receivable has a negative balance (${r['amount']:,.2f}) — possible duplicate payment or misposted transaction."})

    # AP balance check
    ap = _find_accounts(rows, "accounts payable")
    for r in ap:
        if r["amount"] > 0:
            findings.append({"severity": "medium", "message": f"Accounts Payable shows a debit balance (${r['amount']:,.2f}) — may indicate an overpayment or posting error."})

    # Undeposited Funds
    udf = _find_accounts(rows, "undeposited funds")
    for r in udf:
        if abs(r["amount"]) > 5000:
            findings.append({"severity": "medium", "message": f"Undeposited Funds balance is ${r['amount']:,.2f} — review for stale items older than 30 days."})

    return findings


def _check_coa(accounts: list[dict]) -> list[dict]:
    findings = []
    active = [a for a in accounts if a.get("Active", True)]
    total = len(active)

    if total > 200:
        findings.append({"severity": "medium", "message": f"Chart of Accounts has {total} active accounts — consider archiving unused accounts."})
    elif total > 150:
        findings.append({"severity": "low", "message": f"Chart of Accounts has {total} active accounts — may be more than needed."})

    # Check for accounts without account numbers
    has_numbers = sum(1 for a in active if a.get("AcctNum"))
    if has_numbers == 0 and total > 10:
        findings.append({"severity": "low", "message": "No account numbers found — consider adding account numbers for better organization."})

    return findings


def _check_undeposited(items: list[dict]) -> list[dict]:
    findings = []
    if not items:
        return findings

    today = datetime.now(timezone.utc).date()
    old = []
    for item in items:
        txn_date_str = item.get("TxnDate", "")
        try:
            txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date()
            days = (today - txn_date).days
            if days > 30:
                old.append((days, item))
        except Exception:
            pass

    if old:
        total_old = sum(_safe_float(i.get("TotalAmt", 0)) for _, i in old)
        findings.append({
            "severity": "medium",
            "message": f"{len(old)} undeposited funds item(s) are older than 30 days (total: ${total_old:,.2f}) — review for stale deposits.",
        })

    return findings


def _check_banking(accounts: list[dict]) -> list[dict]:
    findings = []
    bank_accounts = [a for a in accounts if a.get("AccountType") in ("Bank", "Credit Card") and a.get("Active", True)]

    credit_cards = [a for a in bank_accounts if a.get("AccountType") == "Credit Card"]
    for cc in credit_cards:
        bal = _safe_float(cc.get("CurrentBalance", 0))
        if bal > 0:
            findings.append({
                "severity": "medium",
                "message": f"Credit card '{cc['Name']}' shows a positive (debit) balance of ${bal:,.2f} — may indicate an overpayment or posting issue.",
            })

    return findings


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.get("/run", summary="Run a full QBO accounting audit")
async def run_audit(
    realm_id: str = Query(...),
    period_from: str = Query(default="", description="YYYY-MM-DD (defaults to start of current year)"),
    period_to: str = Query(default="", description="YYYY-MM-DD (defaults to today)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Run a QuickBooks diagnostic audit using live QBO data.
    Returns prioritized findings across P&L, Balance Sheet, Banking, and Chart of Accounts.
    No AI API key required — pure QBO data analysis.
    """
    client = await _get_client(realm_id, db)

    today = datetime.now(timezone.utc).date()
    if not period_to:
        period_to = str(today)
    if not period_from:
        period_from = f"{today.year}-01-01"

    # Fetch all data in parallel
    async def safe(coro):
        try:
            return await coro
        except Exception:
            return None

    pl, bs, coa, undeposited = await asyncio.gather(
        safe(client.get_profit_loss(period_from, period_to)),
        safe(client.get_balance_sheet(period_to)),
        safe(client.get_chart_of_accounts()),
        safe(client.get_undeposited_funds()),
    )

    findings: list[dict] = []

    if pl:
        findings += _check_pl(pl, period_from, period_to)
    if bs:
        findings += _check_bs(bs)
    if coa:
        findings += _check_coa(coa)
        findings += _check_banking(coa)
    if undeposited:
        findings += _check_undeposited(undeposited)

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: sev_order.get(f.get("severity", "low"), 2))

    high   = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    low    = [f for f in findings if f["severity"] == "low"]

    status = "clean" if not high and not medium else ("needs_attention" if not high else "critical")

    return {
        "realm_id": realm_id,
        "period_from": period_from,
        "period_to": period_to,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "total_findings": len(findings),
        "high": high,
        "medium": medium,
        "low": low,
        "data_fetched": {
            "profit_loss": pl is not None,
            "balance_sheet": bs is not None,
            "chart_of_accounts": coa is not None,
            "undeposited_funds": undeposited is not None,
        },
    }
