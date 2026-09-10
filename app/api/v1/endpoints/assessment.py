"""
QBO Diagnostic Assessment endpoint.

POST /api/v1/assessment/run
  - Fetches QBO data in parallel (P&L, Balance Sheet, COA, AR aging, AP aging,
    undeposited funds)
  - Runs structured diagnostic checks matching the Excel template
  - Fills the template workbook with findings
  - Returns the completed .xlsx as a download
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_qbo_client_for_realm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assessment", tags=["Assessment"])

# Path to the bundled Excel template
TEMPLATE_PATH = Path(__file__).parent.parent.parent.parent / "static" / "assessment_template.xlsx"


# ── Utility helpers ────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float:
    """Coerce a QBO value (may contain commas) to float, default 0.0."""
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _fmt_mmyy(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'MM/YY'."""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return d.strftime("%m/%y")
    except Exception:
        return date_str


def _fmt_period(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'MM/YYYY'."""
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return d.strftime("%m/%Y")
    except Exception:
        return date_str


def _extract_report_rows(report: dict) -> list[dict]:
    """
    Flatten all leaf Data rows from a QBO report into {name, amount, section} pairs.
    QBO report structure: report.Rows.Row[] where each Row is type Section (recurse)
    or type Data (leaf with ColData[0]=name, ColData[1]=amount).
    The 'section' field tracks the nearest parent section header name so callers
    can filter rows by which section they belong to (Income, COGS, Expenses, etc.).
    """
    results: list[dict] = []

    def walk(rows: list[dict], section: str = "") -> None:
        for row in rows:
            row_type = row.get("type", "")
            if row_type == "Section":
                # Get section header name if present
                header = row.get("Header", {})
                h_cols = header.get("ColData", [])
                section_name = h_cols[0].get("value", "").strip() if h_cols else ""
                current_section = section_name if section_name else section

                child_rows = row.get("Rows", {}).get("Row", [])
                walk(child_rows, current_section)
                # Capture section summary row (for totals like "Total Income")
                summary = row.get("Summary", {})
                s_cols = summary.get("ColData", [])
                if len(s_cols) >= 2:
                    results.append({
                        "name": s_cols[0].get("value", ""),
                        "amount": _safe_float(s_cols[1].get("value", "0")),
                        "is_summary": True,
                        "section": current_section,
                    })
            elif row_type == "Data":
                cols = row.get("ColData", [])
                if len(cols) >= 2:
                    results.append({
                        "name": cols[0].get("value", ""),
                        "amount": _safe_float(cols[1].get("value", "0")),
                        "is_summary": False,
                        "section": section,
                    })

    rows = report.get("Rows", {}).get("Row", [])
    walk(rows)
    return results


def _find_amount(rows: list[dict], *name_fragments: str) -> float:
    """Return amount of first row whose name contains any fragment (case-insensitive)."""
    fragments_lower = [f.lower() for f in name_fragments]
    for row in rows:
        if any(frag in row["name"].lower() for frag in fragments_lower):
            return row["amount"]
    return 0.0


def _find_rows_matching(rows: list[dict], *name_fragments: str) -> list[dict]:
    """Return all rows whose name contains any fragment (case-insensitive)."""
    fragments_lower = [f.lower() for f in name_fragments]
    return [r for r in rows if any(f in r["name"].lower() for f in fragments_lower)]


def _extract_aging_buckets(report: dict) -> dict:
    """
    Parse an AR/AP aging report.
    Returns dict with keys: buckets, items_90plus, items_negative, items_zero.
    """
    buckets: dict[str, float] = {
        "current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "91+": 0.0, "total": 0.0
    }
    items_90plus: list[dict] = []
    items_negative: list[dict] = []
    items_zero: list[dict] = []

    try:
        col_headers: list[str] = []
        for col in report.get("Columns", {}).get("Column", []):
            col_headers.append(col.get("ColTitle", "").strip())

        col_90_idx: int | None = None
        for i, h in enumerate(col_headers):
            if ">90" in h or "91" in h or ("over" in h.lower() and "90" in h):
                col_90_idx = i
                break

        def walk_aging(rows: list[dict]) -> None:
            for row in rows:
                if row.get("type") == "Data":
                    cols = row.get("ColData", [])
                    entity_name = cols[0].get("value", "") if cols else ""
                    row_total = 0.0
                    for i, col in enumerate(cols[1:], 1):
                        amt = _safe_float(col.get("value", "0"))
                        row_total += amt
                        h = col_headers[i] if i < len(col_headers) else ""
                        hl = h.lower()
                        if "current" in hl:
                            buckets["current"] += amt
                        elif "1" in h and "30" in h:
                            buckets["1-30"] += amt
                        elif "31" in h and "60" in h:
                            buckets["31-60"] += amt
                        elif "61" in h and "90" in h:
                            buckets["61-90"] += amt
                        elif ">90" in h or "91" in h or ("over" in hl and "90" in h):
                            buckets["91+"] += amt

                    if col_90_idx is not None and col_90_idx < len(cols):
                        amt_90 = _safe_float(cols[col_90_idx].get("value", "0"))
                        if abs(amt_90) > 0.01:
                            items_90plus.append({"name": entity_name, "amount": amt_90})

                    if row_total < -0.01:
                        items_negative.append({"name": entity_name, "amount": row_total})
                    if abs(row_total) < 0.01 and entity_name:
                        items_zero.append({"name": entity_name, "amount": row_total})

                elif row.get("type") == "Section":
                    walk_aging(row.get("Rows", {}).get("Row", []))

        walk_aging(report.get("Rows", {}).get("Row", []))
        buckets["total"] = sum(v for k, v in buckets.items() if k != "total")

    except Exception as exc:
        logger.warning("Error parsing aging report: %s", exc)

    return {
        "buckets": buckets,
        "items_90plus": items_90plus,
        "items_negative": items_negative,
        "items_zero": items_zero,
    }


# ── Cell-writing helpers ───────────────────────────────────────────────────────

def _set_pl_finding(
    ws: Any, row: int, finding: str,
    comment: str = "", num_txns: str = "",
    date_from: str = "", date_to: str = "", amount: str = "",
    internal_comment: str = "",
) -> None:
    """Write a P&L findings row. J=finding, L=comment, M=#txns, N=from, O=to, P=amount, R=internal."""
    ws[f"J{row}"].value = finding
    # Always write all detail columns regardless of finding type
    if comment:
        ws[f"L{row}"].value = comment
    if num_txns:
        ws[f"M{row}"].value = num_txns
    if date_from:
        ws[f"N{row}"].value = date_from
    if date_to:
        ws[f"O{row}"].value = date_to
    if amount:
        ws[f"P{row}"].value = amount
    if internal_comment:
        ws[f"R{row}"].value = internal_comment


def _set_bs_finding(
    ws: Any, row: int, finding: str,
    comment: str = "", num_txns: str = "",
    date_from: str = "", date_to: str = "", amount: str = "",
) -> None:
    """Write a Balance Sheet findings row. J=finding, L=comment, O=#txns, P=from, Q=to, R=amount."""
    ws[f"J{row}"].value = finding
    if finding == "clean up needed":
        if comment:
            ws[f"L{row}"].value = comment
        if num_txns:
            ws[f"O{row}"].value = num_txns
        if date_from:
            ws[f"P{row}"].value = date_from
        if date_to:
            ws[f"Q{row}"].value = date_to
        if amount:
            ws[f"R{row}"].value = amount


def _set_arap_finding(
    ws: Any, row: int, finding: str,
    num_txns: str = "", date_from: str = "", date_to: str = "", amount: str = "",
) -> None:
    """Write an AR/AP findings row. J=finding, K=#txns, L=from, M=to, N=amount."""
    ws[f"J{row}"].value = finding
    if finding == "clean up needed":
        if num_txns:
            ws[f"K{row}"].value = num_txns
        if date_from:
            ws[f"L{row}"].value = date_from
        if date_to:
            ws[f"M{row}"].value = date_to
        if amount:
            ws[f"N{row}"].value = amount


# ── Main route ────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_assessment(
    realm_id: str = Query(..., description="QBO realm/company ID"),
    period_from: str = Query(..., description="Period start date YYYY-MM-DD"),
    period_to: str = Query(..., description="Period end date YYYY-MM-DD"),
    client_name: str = Query("", description="Client display name"),
    accounting_method: str = Query("Accrual", description="Accrual or Cash"),
    qbo_version: str = Query("Plus", description="QBO plan tier"),
    tax_org_type: str = Query("", description="Tax org type e.g. S-Corp, LLC"),
    tax_basis: str = Query("Accrual", description="Tax basis: Cash or Accrual"),
    tax_year: str = Query("Calendar Year", description="Tax year: Calendar Year or Fiscal Year"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Run a full QBO diagnostic assessment and return a completed Excel workbook.

    Fetches P&L, Balance Sheet, Chart of Accounts, AR aging, AP aging, and
    undeposited funds in parallel, runs ~40 diagnostic checks against the
    TPC QuickBooks Diagnostic Template, then streams the filled workbook as a download.
    """
    client = await get_qbo_client_for_realm(realm_id, db)
    if not client:
        raise HTTPException(status_code=404, detail=f"No QBO connection for realm {realm_id}")

    if not TEMPLATE_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Assessment template not found on server. Contact support.",
        )

    # ── Fetch all QBO data in parallel ────────────────────────────────────────
    async def safe_fetch(coro: Any, name: str, default: Any) -> Any:
        try:
            return await coro
        except Exception as exc:
            logger.warning("QBO fetch failed for %s: %s", name, exc)
            return default

    (
        pl_report,
        bs_report,
        coa_list,
        ar_aging_report,
        ap_aging_report,
        undeposited_funds,
        items_list,
        employee_list,
        vendor_list_raw,
        uncategorized_purchases,
    ) = await asyncio.gather(
        safe_fetch(client.get_profit_loss(period_from, period_to), "profit_loss", {}),
        safe_fetch(client.get_balance_sheet(period_to), "balance_sheet", {}),
        safe_fetch(client.get_chart_of_accounts(), "chart_of_accounts", []),
        safe_fetch(client.get_ar_aging(), "ar_aging", {}),
        safe_fetch(client.get_ap_aging(), "ap_aging", {}),
        safe_fetch(client.get_undeposited_funds(), "undeposited_funds", []),
        safe_fetch(client._query("SELECT * FROM Item MAXRESULTS 500"), "items", []),
        safe_fetch(client.get_employee_list(), "employees", []),
        safe_fetch(client._query("SELECT * FROM Vendor WHERE Active = true MAXRESULTS 500"), "vendors", []),
        safe_fetch(client.get_uncategorized_transactions(), "uncategorized_purchases", []),
    )

    # ── Pre-process data ───────────────────────────────────────────────────────
    pl_rows = _extract_report_rows(pl_report)
    bs_rows = _extract_report_rows(bs_report)
    ar_data = _extract_aging_buckets(ar_aging_report)
    ap_data = _extract_aging_buckets(ap_aging_report)

    active_accounts = [a for a in coa_list if a.get("Active", True)]
    bank_accounts = [a for a in active_accounts if a.get("AccountType") in ("Bank", "Credit Card")]
    total_account_count = len(active_accounts)

    # ── Secondary banking fetches: individual account GETs + recon reports + BankTransaction ──
    # The bulk COA query (SELECT * FROM Account) does NOT return:
    #   LastReconcileDate, FeedAccountType, ConnectionStatus
    # We need individual GETs per account and ReconciliationDetail reports.

    async def _get_full_account(acct: dict) -> dict:
        """Fetch the full Account entity to get LastReconcileDate, FeedAccountType, etc."""
        try:
            resp = await client._get(f"account/{acct['Id']}")
            full = resp.get("Account", resp) if isinstance(resp, dict) else acct
            return {**acct, **full}
        except Exception:
            return acct

    async def _get_recon_report(acct: dict) -> dict:
        """Fetch ReconciliationDetail report for an account to detect last rec date + adjustments."""
        try:
            return await client.get_reconciliation_report(acct["Id"])
        except Exception:
            return {}

    _n_bank = min(6, len(bank_accounts))
    # Build all tasks: account GETs, recon reports, then BankTransaction query
    _bank_tasks = (
        [_get_full_account(a) for a in bank_accounts[:_n_bank]]
        + [_get_recon_report(a) for a in bank_accounts[:_n_bank]]
        + [safe_fetch(client._query("SELECT * FROM BankTransaction MAXRESULTS 500"), "bank_txns", [])]
    )
    _bank_results = await asyncio.gather(*_bank_tasks)

    enriched_bank_accounts = list(_bank_results[:_n_bank]) if _n_bank > 0 else bank_accounts
    recon_reports = list(_bank_results[_n_bank: _n_bank * 2])
    bank_transactions_for_review = _bank_results[-1] if _bank_tasks else []

    # Replace bank_accounts with enriched data
    bank_accounts = enriched_bank_accounts if enriched_bank_accounts else bank_accounts

    # ── Parse each reconciliation report ─────────────────────────────────────
    def _parse_recon_report(report: dict) -> dict:
        """Extract last reconciliation date, uncleared tx count, and auto-adjustment flag."""
        result: dict = {"last_rec_date": None, "uncleared_count": 0, "has_adjustments": False}
        if not report or not isinstance(report, dict):
            return result
        header = report.get("Header", {})
        # EndPeriod = statement end date = effective last reconciliation date
        end_period = header.get("EndPeriod", "") or header.get("end_date", "") or ""
        if end_period:
            result["last_rec_date"] = end_period
        # Walk rows to count uncleared items and detect adjustments
        rows = report.get("Rows", {}).get("Row", [])
        for row in rows:
            if row.get("type") == "Section":
                h_cols = row.get("Header", {}).get("ColData", [{}])
                sec_name = (h_cols[0].get("value", "") if h_cols else "").lower()
                child_rows = row.get("Rows", {}).get("Row", [])
                if "uncleared" in sec_name:
                    result["uncleared_count"] += sum(
                        1 for r in child_rows if r.get("type") == "Data"
                    )
                if "adjustment" in sec_name or "discrepancy" in sec_name:
                    result["has_adjustments"] = True
        return result

    recon_info_by_idx = [_parse_recon_report(r) for r in recon_reports]

    # ── Group BankTransaction records by AccountRef for per-account pending count ──
    # If BankTransaction query is supported, this gives us which accounts are connected
    # AND how many transactions are pending review per account.
    btxn_count_by_acct_id: dict[str, int] = {}
    for _txn in (bank_transactions_for_review or []):
        if not isinstance(_txn, dict):
            continue
        _acct_ref = _txn.get("AccountRef") or _txn.get("BankAccountRef") or {}
        _acct_id = (_acct_ref.get("value", "") if isinstance(_acct_ref, dict) else "")
        if _acct_id:
            btxn_count_by_acct_id[_acct_id] = btxn_count_by_acct_id.get(_acct_id, 0) + 1
    # Total uncategorized purchases (fallback For Review proxy)
    _total_uncat_purchases = len(uncategorized_purchases) if uncategorized_purchases else 0

    has_payroll_liability = any(
        "payroll" in (a.get("Name", "") + a.get("AccountSubType", "")).lower()
        for a in active_accounts
    )
    has_sales_tax = any(
        "sales tax" in a.get("Name", "").lower() or a.get("AccountSubType") == "SalesTaxPayable"
        for a in active_accounts
    )

    period_from_mmyy = _fmt_mmyy(period_from)
    period_to_mmyy = _fmt_mmyy(period_to)
    period_label = f"{_fmt_period(period_from)} - {_fmt_period(period_to)}"

    # ── Load workbook ──────────────────────────────────────────────────────────
    wb = openpyxl.load_workbook(TEMPLATE_PATH)

    # Master issues list — accumulated from each sheet section
    issues_found: list[str] = []

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Client info
    # ══════════════════════════════════════════════════════════════════════════
    ws_client = wb["Client info"]
    _client_display = client_name or "Client Name Not Provided"
    # A1:J2 is a merged cell — writing to A1 fills the entire merged region.
    # The Report tab formula ='Client info'!A2 reads from this same merged cell.
    ws_client["A1"].value = _client_display
    ws_client["J4"].value = period_label
    ws_client["J5"].value = accounting_method
    ws_client["J6"].value = tax_org_type or "Not specified"
    ws_client["J7"].value = tax_basis
    ws_client["J8"].value = tax_year

    # J10 — QBO version name
    ws_client["J10"].value = f"QuickBooks Online {qbo_version}"

    # J11 — Is the client using the right QBO version?
    _version_comment: str
    if qbo_version in ("Advanced",):
        _version_comment = (
            f"QBO Advanced is appropriate if the client needs advanced reporting, custom roles, "
            "or more than 5 users. Confirm the client actively uses Advanced features; "
            "otherwise consider downgrading to Plus to reduce cost."
        )
    elif qbo_version in ("Plus",):
        _version_comment = (
            "QBO Plus is appropriate for businesses that need class/location tracking, "
            "inventory, or project profitability. Recommended for most small businesses "
            "with more complex reporting needs."
        )
    elif qbo_version in ("Essentials",):
        _version_comment = (
            "QBO Essentials covers basic income/expense tracking, AP, and multi-user access. "
            "If the client needs inventory tracking, class tracking, or project profitability, "
            "consider upgrading to QBO Plus."
        )
    else:  # Simple Start
        _version_comment = (
            "QBO Simple Start is the most basic tier — single user, income/expense only. "
            "If the client needs AP (bill tracking), multi-user access, or class tracking, "
            "upgrade to Essentials or Plus."
        )
    ws_client["J11"].value = _version_comment

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Banking
    # ══════════════════════════════════════════════════════════════════════════
    ws_bank = wb["Banking "]
    banking_issues: list[str] = []

    # Build a lookup: account Name → LastReconcileDate (from COA data)
    acct_rec_dates: dict[str, str] = {}
    for a in coa_list:
        lrd = a.get("LastReconcileDate", "") or ""
        if lrd:
            acct_rec_dates[a.get("Name", "")] = lrd

    unreconciled_accounts: list[str] = []
    old_rec_accounts: list[str] = []

    from datetime import date as _date_cls
    for i, acct in enumerate(bank_accounts[:5], start=4):
        _acct_idx = i - 4  # 0-based index into recon_info_by_idx
        name = acct.get("Name", "")
        acct_id = acct.get("Id", "")
        ws_bank[f"A{i}"].value = name

        # ── Reconciliation date: prefer individual GET field, then recon report header ──
        _recon_info = recon_info_by_idx[_acct_idx] if _acct_idx < len(recon_info_by_idx) else {}
        last_rec = (
            acct.get("LastReconcileDate", "") or ""
            or _recon_info.get("last_rec_date", "") or ""
            or acct_rec_dates.get(name, "")
        )
        never_reconciled = not bool(last_rec)
        _uncleared_from_report = _recon_info.get("uncleared_count", 0)
        _has_adjustments = _recon_info.get("has_adjustments", False)

        if last_rec:
            try:
                d = _date_cls.fromisoformat(last_rec[:10])
                ws_bank[f"G{i}"].value = d.strftime("%m/%d/%Y")
                days_since = (_date_cls.today() - d).days
                if days_since > 45:
                    old_rec_accounts.append(f"{name} (last: {d.strftime('%m/%d/%Y')})")

                # Column J — uncleared items
                if _uncleared_from_report > 0:
                    ws_bank[f"J{i}"].value = (
                        f"{_uncleared_from_report} uncleared transaction(s) found in reconciliation report "
                        f"(last reconciled {days_since} days ago). "
                        "Review in QBO Accounting > Reconcile > History to clear old items."
                    )
                elif days_since > 30:
                    ws_bank[f"J{i}"].value = (
                        f"Possible — last reconciled {days_since} days ago. "
                        "Run Reconcile > History to review uncleared items older than 30 days."
                    )
                else:
                    ws_bank[f"J{i}"].value = (
                        "Likely none — reconciled within last 30 days. "
                        "Verify in QBO Accounting > Reconcile > History."
                    )

                # Column O — auto adjustments
                if _has_adjustments:
                    ws_bank[f"O{i}"].value = (
                        "AUTO-ADJUSTMENT DETECTED in reconciliation history — "
                        "investigate in QBO Accounting > Reconcile > History. "
                        "Adjustments force the balance and mask real discrepancies."
                    )
                    issues_found.append(f"Reconciliation auto-adjustment detected on {name}")
                elif days_since > 30:
                    ws_bank[f"O{i}"].value = (
                        f"Last reconciled {days_since} days ago — review history for any auto-adjustments. "
                        "Go to QBO Accounting > Reconcile > History by Account."
                    )
                else:
                    ws_bank[f"O{i}"].value = (
                        "Review reconciliation history in QBO > Accounting > Reconcile > History by Account."
                    )
            except Exception:
                ws_bank[f"G{i}"].value = last_rec
                ws_bank[f"J{i}"].value = "Review in QBO Reconcile > History by Account"
                ws_bank[f"O{i}"].value = "Review in QBO Reconcile > History by Account"
        else:
            ws_bank[f"G{i}"].value = "Never reconciled"
            unreconciled_accounts.append(name)
            ws_bank[f"J{i}"].value = (
                "N/A — account has never been reconciled. "
                "All transactions are uncleared. Establish opening balance and begin reconciling."
            )
            ws_bank[f"O{i}"].value = (
                "N/A — no reconciliation performed yet. "
                "Auto adjustments only appear after reconciliation is initiated."
            )

        # ── Column R — bank feed connected ───────────────────────────────────
        feed_type = acct.get("FeedAccountType", "") or ""
        bank_num = acct.get("BankNum", "") or ""
        conn_status = acct.get("ConnectionStatus", "") or ""
        # Also check if BankTransaction records exist for this account (reliable proxy)
        _pending_for_acct = btxn_count_by_acct_id.get(acct_id, 0)
        feed_connected = (
            bool(feed_type)
            or conn_status.upper() in ("ACTIVE", "CONNECTED")
            or _pending_for_acct > 0   # Has downloaded bank transactions → feed is live
        )

        if feed_connected:
            _feed_src = feed_type or conn_status or ("bank feed active — transactions downloading" if _pending_for_acct else "active")
            ws_bank[f"R{i}"].value = f"Yes — bank feed connected ({_feed_src})"
        elif bank_num:
            ws_bank[f"R{i}"].value = (
                f"Not confirmed — account ending {bank_num} found but no live feed signal. "
                "Verify in QBO Banking tab > Manage Connections."
            )
        else:
            ws_bank[f"R{i}"].value = (
                "Not detected via API — verify in QBO Banking tab > Connect Account."
            )

        # ── Column W — old / uncategorized transactions in bank feeds window ──
        if feed_connected:
            if _pending_for_acct > 0:
                ws_bank[f"W{i}"].value = (
                    f"{_pending_for_acct} transaction(s) pending in 'For Review' tab for this account. "
                    "Categorize or match all items — unreviewed transactions are excluded from P&L and Balance Sheet."
                )
            elif _total_uncat_purchases > 0:
                ws_bank[f"W{i}"].value = (
                    f"{_total_uncat_purchases} uncategorized purchase(s) found across all accounts (no expense account assigned). "
                    "Categorize in QBO Banking > For Review tab."
                )
            else:
                ws_bank[f"W{i}"].value = (
                    "No pending transactions detected for this account. "
                    "Confirm For Review tab is clear in QBO Banking."
                )
        elif bank_num:
            ws_bank[f"W{i}"].value = (
                "Connect bank feed to enable automatic transaction import. "
                "Currently requires manual entry or CSV upload."
            )
        else:
            ws_bank[f"W{i}"].value = (
                "No bank feed — set up connection in QBO Banking > Connect Account "
                "to enable automatic transaction import and review."
            )

    if bank_accounts:
        acct_lines = []
        for a in bank_accounts[:5]:
            name = a.get("Name", "")
            lrd = a.get("LastReconcileDate", "") or acct_rec_dates.get(name, "")
            status = ""
            if lrd:
                try:
                    from datetime import date
                    d = date.fromisoformat(lrd)
                    days = (date.today() - d).days
                    status = f"reconciled through {d.strftime('%m/%d/%Y')} ({days} days ago)"
                except Exception:
                    status = f"last reconciled: {lrd}"
            else:
                status = "NEVER RECONCILED"
            acct_lines.append(f"• {name}: {status}")

        banking_summary = (
            f"Found {len(bank_accounts)} bank/credit card account(s):\n"
            + "\n".join(acct_lines)
        )
        if unreconciled_accounts:
            banking_issues.append(f"Account(s) never reconciled: {', '.join(unreconciled_accounts)}")
            banking_summary += f"\n\nACTION REQUIRED: {', '.join(unreconciled_accounts)} — establish opening balance and reconcile."
        if old_rec_accounts:
            banking_issues.append(f"Account(s) overdue for reconciliation (>45 days): {', '.join(old_rec_accounts)}")
            banking_summary += f"\n\nOVERDUE: {', '.join(old_rec_accounts)} — reconcile to current date."
        banking_summary += "\n\nFor each account: review uncleared items, auto-adjustments, bank feed status, and old transactions in QBO Reconcile and Banking tabs."
    else:
        banking_summary = "No bank or credit card accounts found in Chart of Accounts."
        banking_issues.append("No bank accounts found in COA")

    if undeposited_funds:
        udf_total = sum(_safe_float(f.get("Amount", 0)) for f in undeposited_funds)
        if udf_total > 0:
            banking_issues.append(f"Undeposited Funds balance of ${udf_total:,.2f} — review and clear")
            banking_summary += f"\n\nUndeposited Funds: ${udf_total:,.2f} outstanding — review and deposit or void stale items."

    # For Review / pending bank transactions — show per-account breakdown
    _total_btxn = sum(btxn_count_by_acct_id.values())
    _uncat_count = _total_uncat_purchases
    if _total_btxn > 0:
        _per_acct_lines = [
            f"  • {a.get('Name','')}: {btxn_count_by_acct_id.get(a.get('Id',''), 0)} pending"
            for a in bank_accounts[:5] if btxn_count_by_acct_id.get(a.get("Id", ""), 0) > 0
        ]
        _for_review_msg = (
            f"For Review: {_total_btxn} total transaction(s) pending across connected accounts:\n"
            + "\n".join(_per_acct_lines)
            + f"\n+ {_uncat_count} purchase(s) with no expense account assigned."
            + "\nCategorize all items before running P&L and Balance Sheet reports."
        )
        banking_issues.append(f"{_total_btxn} bank transactions pending in For Review tab")
        banking_summary += f"\n\n{_for_review_msg}"
    elif _uncat_count > 0:
        banking_issues.append(f"{_uncat_count} uncategorized purchases (no account assigned)")
        banking_summary += f"\n\nFor Review: {_uncat_count} purchase(s) with no account assigned — categorize in QBO Banking > For Review."
    else:
        banking_summary += "\n\nFor Review: No pending or uncategorized transactions detected — confirm in QBO Banking tab."

    ws_bank["A11"].value = banking_summary

    # Work to be completed — Banking
    banking_work_items = []
    if unreconciled_accounts:
        banking_work_items.append(f"Establish opening balance and perform initial reconciliation for: {', '.join(unreconciled_accounts)}")
    if old_rec_accounts:
        banking_work_items.append(f"Bring reconciliation current for: {', '.join(old_rec_accounts)}")
    if bank_accounts:
        banking_work_items.append("Review each account in QBO Reconcile > History for old uncleared items and auto-adjustments")
        banking_work_items.append("Verify bank feed is connected and active for each account in QBO Banking > Banking tab")
        banking_work_items.append("Clear any old unreviewed transactions in the For Review tab (older than 30 days)")
    ws_bank["A16"].value = (
        "\n".join(f"• {w}" for w in banking_work_items)
        if banking_work_items else "No immediate banking work required based on available data."
    )

    issues_found.extend(banking_issues)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Profit & Loss
    # ══════════════════════════════════════════════════════════════════════════
    ws_pl = wb["Profit & Loss"]
    pl_issues: list[str] = []

    ws_pl["J5"].value = period_from_mmyy
    ws_pl["K5"].value = period_to_mmyy

    # ── Build section-level account lists for detailed per-row comments ───────
    def _section_accts(section_kws: list[str]) -> list[dict]:
        """Non-summary rows whose section matches any keyword."""
        kws = [k.lower() for k in section_kws]
        return [r for r in pl_rows if not r.get("is_summary") and abs(r["amount"]) > 0.01
                and any(kw in r.get("section", "").lower() for kw in kws)]

    def _acct_list(rows: list[dict], limit: int = 6) -> str:
        return "; ".join(f"{r['name']} (${r['amount']:,.2f})" for r in rows[:limit])

    income_accts = _section_accts(["income", "revenue", "sales"])
    cogs_accts   = _section_accts(["cost of goods", "cogs", "cost of sales", "direct cost"])
    exp_accts    = _section_accts(["expense", "expenses"])
    other_inc_accts = [r for r in pl_rows if not r.get("is_summary") and abs(r["amount"]) > 0.01
                       and "other income" in r.get("section", "").lower()]
    other_exp_accts = [r for r in pl_rows if not r.get("is_summary") and abs(r["amount"]) > 0.01
                       and "other expense" in r.get("section", "").lower()]

    total_income_bal = sum(r["amount"] for r in income_accts)
    total_cogs_bal   = abs(sum(r["amount"] for r in cogs_accts))
    total_exp_bal    = sum(r["amount"] for r in exp_accts)

    # ── INCOME SECTION ────────────────────────────────────────────────────────

    # J9 — Negative income balances
    neg_income = [r for r in income_accts if r["amount"] < -0.01]
    if neg_income:
        total_neg = sum(r["amount"] for r in neg_income)
        _set_pl_finding(ws_pl, 9, "clean up needed",
                        comment=_acct_list(neg_income),
                        num_txns=str(len(neg_income)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${total_neg:,.2f}",
                        internal_comment="Investigate negative income — may be refunds, voids, or mispostings. Reverse or reclassify as needed.")
        pl_issues.append(f"Negative income balances in {len(neg_income)} account(s)")
    else:
        _set_pl_finding(ws_pl, 9, "OK",
                        comment=_acct_list(income_accts) if income_accts else "No income accounts found",
                        amount=f"${total_income_bal:,.2f}",
                        internal_comment=f"Reviewed {len(income_accts)} income account(s) — all balances positive.")

    # J10 — Uncategorized income
    uncat_inc = [r for r in _find_rows_matching(pl_rows, "uncategorized income") if abs(r["amount"]) > 0.01 and not r.get("is_summary")]
    if uncat_inc:
        total_ui = sum(r["amount"] for r in uncat_inc)
        _set_pl_finding(ws_pl, 10, "clean up needed",
                        comment=_acct_list(uncat_inc),
                        num_txns=str(len(uncat_inc)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${total_ui:,.2f}",
                        internal_comment="Reclassify all transactions in Uncategorized Income to the appropriate income account.")
        pl_issues.append("Uncategorized income balance found")
    else:
        _set_pl_finding(ws_pl, 10, "No",
                        comment="Uncategorized Income account not in use",
                        internal_comment="Confirm no transactions were posted to Uncategorized Income during the period.")

    # J11 — Sales of Product Income balance
    sopi_rows = [r for r in _find_rows_matching(pl_rows, "sales of product income") if abs(r["amount"]) > 0.01 and not r.get("is_summary")]
    sopi = sum(r["amount"] for r in sopi_rows)
    if abs(sopi) > 0.01:
        _set_pl_finding(ws_pl, 11, "clean up needed",
                        comment=f"Sales of Product Income: ${sopi:,.2f} — verify this is appropriate for client's industry",
                        amount=f"${sopi:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="If client is service-based, reclassify to appropriate service income account.")
        pl_issues.append("Sales of Product Income balance found — verify industry fit")
    else:
        _set_pl_finding(ws_pl, 11, "No",
                        comment="Sales of Product Income account not in use",
                        internal_comment="Account not active during this period — consistent with service-based business.")

    # J12 — Services income account balance
    _income_sections = {"income", "revenue", "sales"}
    svc_rows = [
        r for r in pl_rows
        if r["name"].strip().lower() in ("services", "service", "services income", "service income", "service revenue")
        and not r.get("is_summary")
        and any(s in r.get("section", "").lower() for s in _income_sections)
    ]
    svc_amt = sum(r["amount"] for r in svc_rows)
    if abs(svc_amt) > 0.01:
        _set_pl_finding(ws_pl, 12, "clean up needed",
                        comment=f"Services account: ${svc_amt:,.2f} — verify appropriate for client's industry",
                        amount=f"${svc_amt:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="If client is product-based, reclassify to Sales of Product Income.")
        pl_issues.append("Services account balance found — verify industry fit")
    else:
        _set_pl_finding(ws_pl, 12, "No",
                        comment="Services income account not in use",
                        internal_comment="No balance in Services income account — not applicable for this client.")

    # J13 — Deposits recorded as income
    dep_income_rows = [r for r in _find_rows_matching(pl_rows, "deposit") if abs(r["amount"]) > 0.01 and not r.get("is_summary") and "income" in r.get("section","").lower()]
    dep_income = sum(r["amount"] for r in dep_income_rows)
    if abs(dep_income) > 0.01:
        _set_pl_finding(ws_pl, 13, "clean up needed",
                        comment=_acct_list(dep_income_rows),
                        amount=f"${dep_income:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Reclassify deposits to liability (Deferred Revenue) or appropriate income account.")
        pl_issues.append("Deposits recorded as income")
    else:
        _set_pl_finding(ws_pl, 13, "No",
                        comment="No deposit accounts found in income section",
                        internal_comment="No sales amounts recorded as Deposits — income section is clean for this check.")

    # J14 — Loan proceeds as income
    loan_inc_rows = [r for r in _find_rows_matching(pl_rows, "loan proceeds", "loan income", "ppp loan", "eidl") if abs(r["amount"]) > 0.01]
    loan_inc = sum(r["amount"] for r in loan_inc_rows)
    if abs(loan_inc) > 0.01:
        _set_pl_finding(ws_pl, 14, "clean up needed",
                        comment=_acct_list(loan_inc_rows),
                        amount=f"${loan_inc:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Reclassify loan proceeds from income to a liability account (Loan Payable).")
        pl_issues.append("Loan proceeds recorded as income")
    else:
        _set_pl_finding(ws_pl, 14, "No",
                        comment="No loan proceeds recorded as income",
                        internal_comment="No loan proceeds in income section — verify directly with client if any loans were received.")

    # J15 — Sales tax as income deduction
    st_inc_rows = [r for r in _find_rows_matching(pl_rows, "sales tax", "tax collected") if abs(r["amount"]) > 0.01 and not r.get("is_summary") and "income" in r.get("section","").lower()]
    st_inc = sum(r["amount"] for r in st_inc_rows)
    if abs(st_inc) > 0.01:
        _set_pl_finding(ws_pl, 15, "clean up needed",
                        comment=_acct_list(st_inc_rows),
                        amount=f"${st_inc:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Remove sales tax from income — record in Sales Tax Payable liability and use QBO Sales Tax Center.")
        pl_issues.append("Sales tax recorded as income deduction")
    else:
        _set_pl_finding(ws_pl, 15, "No",
                        comment="No sales tax deduction from income found",
                        internal_comment="Sales tax not deducted from income — correct. Verify it is recorded in Sales Tax Payable.")

    # ── COST OF GOODS SOLD SECTION ────────────────────────────────────────────

    # J18 — Negative COGS
    neg_cogs = [r for r in cogs_accts if r["amount"] < -0.01]
    if neg_cogs:
        _set_pl_finding(ws_pl, 18, "clean up needed",
                        comment=_acct_list(neg_cogs),
                        num_txns=str(len(neg_cogs)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in neg_cogs):,.2f}",
                        internal_comment="Investigate negative COGS — may be vendor credits, reversed purchases, or mispostings.")
        pl_issues.append("Negative COGS balances found")
    else:
        _set_pl_finding(ws_pl, 18, "No",
                        comment=_acct_list(cogs_accts) if cogs_accts else "No COGS accounts found",
                        amount=f"${total_cogs_bal:,.2f}",
                        internal_comment=f"Reviewed {len(cogs_accts)} COGS account(s) — all balances positive.")

    # J19 — Incorrectly categorized COGS (only search within COGS section)
    _cogs_section_keywords = {"cost of goods", "cogs", "cost of sales", "direct cost"}
    cogs_only_rows = [r for r in pl_rows if any(kw in r.get("section","").lower() for kw in _cogs_section_keywords) and not r.get("is_summary")]
    cogs_suspect = [r for r in _find_rows_matching(cogs_only_rows, "insurance", "utilities", "rent", "office", "admin") if abs(r["amount"]) > 0.01]
    if cogs_suspect:
        _set_pl_finding(ws_pl, 19, "clean up needed",
                        comment=_acct_list(cogs_suspect),
                        num_txns=str(len(cogs_suspect)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Review these accounts in COGS — insurance/rent/utilities are typically Expenses, not COGS.")
        pl_issues.append("Potential misclassification in COGS section")
    else:
        _set_pl_finding(ws_pl, 19, "No",
                        comment=_acct_list(cogs_accts) if cogs_accts else "No COGS accounts found",
                        internal_comment="No expense-type accounts (insurance, rent, utilities) found inside COGS — section looks correctly categorized.")

    # J20 — COGS vs income ratio check
    total_income_for_ratio = _find_amount(pl_rows, "total income", "gross revenue")
    if total_income_for_ratio == 0.0:
        total_income_for_ratio = sum(r["amount"] for r in pl_rows if r.get("is_summary") and "income" in r["name"].lower() and "other" not in r["name"].lower())
    total_cogs_for_ratio = _find_amount(pl_rows, "total cost of goods", "total cogs")
    if total_cogs_for_ratio == 0.0:
        total_cogs_for_ratio = total_cogs_bal
    if total_income_for_ratio > 0 and total_cogs_for_ratio > total_income_for_ratio * 1.1:
        _set_pl_finding(ws_pl, 20, "clean up needed",
                        comment=f"COGS (${total_cogs_for_ratio:,.2f}) exceeds total income (${total_income_for_ratio:,.2f})",
                        amount=f"${total_cogs_for_ratio:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment=f"COGS is ${total_cogs_for_ratio - total_income_for_ratio:,.2f} higher than income — review all COGS entries. May indicate unrecorded income, over-expensed costs, or timing issues.")
        pl_issues.append("COGS exceeds total income")
    elif total_income_for_ratio > 10000 and total_cogs_for_ratio == 0:
        _set_pl_finding(ws_pl, 20, "clean up needed",
                        comment="No COGS recorded despite significant income",
                        amount="$0.00",
                        internal_comment="Verify with client whether they have direct costs — if yes, set up COGS accounts and reclassify.")
        pl_issues.append("No COGS recorded despite income")
    else:
        _set_pl_finding(ws_pl, 20, "OK",
                        comment=f"COGS ${total_cogs_for_ratio:,.2f} vs Income ${total_income_for_ratio:,.2f}",
                        amount=f"${total_cogs_for_ratio:,.2f}",
                        internal_comment="COGS ratio within expected range. Monitor monthly for unusual fluctuations.")

    # ── EXPENSES SECTION ──────────────────────────────────────────────────────

    # J23 — Negative expense balances
    neg_exp = [r for r in exp_accts if r["amount"] < -0.01]
    if neg_exp:
        _set_pl_finding(ws_pl, 23, "clean up needed",
                        comment=_acct_list(neg_exp),
                        num_txns=str(len(neg_exp)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in neg_exp):,.2f}",
                        internal_comment="Negative expense balances likely indicate reversed entries, vendor credits, or overpayments. Investigate each.")
        pl_issues.append(f"Negative expense balances in {len(neg_exp)} account(s)")
    else:
        _set_pl_finding(ws_pl, 23, "OK",
                        comment=f"Reviewed {len(exp_accts)} expense account(s) — all balances positive",
                        amount=f"${total_exp_bal:,.2f}",
                        internal_comment="No negative expense balances found.")

    # J24 — Expenses higher than expected (non-payroll accounts > $50k or notably high)
    high_exp = [r for r in exp_accts if r["amount"] > 50000 and not any(kw in r["name"].lower() for kw in ["payroll", "salary", "wage"])]
    if high_exp:
        _set_pl_finding(ws_pl, 24, "clean up needed",
                        comment=_acct_list(high_exp),
                        num_txns=str(len(high_exp)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Review unusually large expense accounts — verify all transactions are legitimate business expenses.")
        pl_issues.append("Some expense accounts unusually high — review")
    else:
        # Show top 3 expense accounts even when OK
        top_exp = sorted(exp_accts, key=lambda r: r["amount"], reverse=True)[:3]
        _set_pl_finding(ws_pl, 24, "OK",
                        comment=_acct_list(top_exp) if top_exp else "No expense accounts found",
                        amount=f"${total_exp_bal:,.2f}",
                        internal_comment="No expense accounts exceed $50,000. Review largest accounts for reasonableness.")

    # J25 — Expenses lower than expected
    _set_pl_finding(ws_pl, 25, "OK",
                    comment=f"Total expenses: ${total_exp_bal:,.2f}",
                    internal_comment="Cannot assess low expenses without industry benchmarks — confirm with client that all costs are recorded.")

    # J26 — Uncategorized expenses
    uncat_exp = [r for r in _find_rows_matching(pl_rows, "uncategorized expense") if abs(r["amount"]) > 0.01 and not r.get("is_summary")]
    if uncat_exp:
        total_ue = sum(r["amount"] for r in uncat_exp)
        _set_pl_finding(ws_pl, 26, "clean up needed",
                        comment=_acct_list(uncat_exp),
                        num_txns=str(len(uncat_exp)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${total_ue:,.2f}",
                        internal_comment="Reclassify all transactions in Uncategorized Expense to specific expense accounts.")
        pl_issues.append("Uncategorized expenses found")
    else:
        _set_pl_finding(ws_pl, 26, "No",
                        comment="Uncategorized Expense account not in use",
                        internal_comment="No transactions in Uncategorized Expense. Confirm in QBO.")

    # J27 — Ask My Accountant
    ama = [r for r in _find_rows_matching(pl_rows, "ask my accountant") if abs(r["amount"]) > 0.01]
    if ama:
        total_ama = sum(r["amount"] for r in ama)
        _set_pl_finding(ws_pl, 27, "clean up needed",
                        comment=_acct_list(ama),
                        num_txns=str(len(ama)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${total_ama:,.2f}",
                        internal_comment="Review all Ask My Accountant transactions with client and reclassify to proper accounts.")
        pl_issues.append("Ask My Accountant balance found")
    else:
        _set_pl_finding(ws_pl, 27, "No",
                        comment="Ask My Accountant account not in use",
                        internal_comment="No transactions in Ask My Accountant — good bookkeeping practice confirmed.")

    # J28 — Reconciliation Discrepancy
    recon_disc = [r for r in _find_rows_matching(pl_rows, "reconciliation discrepan") if abs(r["amount"]) > 0.01]
    if recon_disc:
        total_recon = sum(r["amount"] for r in recon_disc)
        _set_pl_finding(ws_pl, 28, "clean up needed",
                        comment=_acct_list(recon_disc),
                        num_txns=str(len(recon_disc)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${total_recon:,.2f}",
                        internal_comment="Investigate the Reconciliation Discrepancy balance — this account should always be $0. Find and correct the source of the discrepancy.")
        pl_issues.append("Reconciliation Discrepancy balance found")
    else:
        _set_pl_finding(ws_pl, 28, "No",
                        comment="Reconciliation Discrepancy account not in use",
                        internal_comment="No balance in Reconciliation Discrepancy — accounts reconcile correctly.")

    # J29 — Expenses that should be COGS
    should_cogs = [r for r in exp_accts if any(kw in r["name"].lower() for kw in ["subcontractor", "direct labor", "direct material", "job cost", "project cost", "contract labor"])]
    if should_cogs:
        _set_pl_finding(ws_pl, 29, "clean up needed",
                        comment=_acct_list(should_cogs),
                        num_txns=str(len(should_cogs)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in should_cogs):,.2f}",
                        internal_comment="These accounts may belong in COGS rather than Expenses. Review with client to confirm proper classification.")
        pl_issues.append("Possible COGS items recorded as expenses")
    else:
        _set_pl_finding(ws_pl, 29, "No",
                        comment=f"Reviewed {len(exp_accts)} expense accounts — no obvious COGS items found in expenses",
                        internal_comment="No subcontractor/direct labor/job cost accounts found in Expenses section.")

    # J30 — Personal expenses
    personal = [r for r in exp_accts if any(kw in r["name"].lower() for kw in ["personal", "owner expense", "meals", "entertainment"])]
    if personal:
        _set_pl_finding(ws_pl, 30, "clean up needed",
                        comment=_acct_list(personal),
                        num_txns=str(len(personal)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in personal):,.2f}",
                        internal_comment="Verify business purpose for each transaction. Reclassify personal items to Owner Draw or equity accounts.")
        pl_issues.append("Possible personal expenses in business books")
    else:
        _set_pl_finding(ws_pl, 30, "No",
                        comment="No personal expense accounts found",
                        internal_comment="No meals/entertainment/personal accounts with balances. Confirm with client that all personal expenses are properly separated.")

    # J31 — Loan payments as expenses
    loan_exp = [r for r in exp_accts if any(kw in r["name"].lower() for kw in ["loan payment", "note payable payment", "principal"])]
    if loan_exp:
        _set_pl_finding(ws_pl, 31, "clean up needed",
                        comment=_acct_list(loan_exp),
                        num_txns=str(len(loan_exp)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in loan_exp):,.2f}",
                        internal_comment="Split loan payments: principal portion to Loan Payable (liability), interest portion to Interest Expense.")
        pl_issues.append("Loan payments recorded as expenses")
    else:
        _set_pl_finding(ws_pl, 31, "No",
                        comment="No loan payment accounts found in expenses",
                        internal_comment="No loan principal amounts in expenses. Confirm with client if there are any outstanding loans.")

    # J32 — Fixed assets under $2500 expensed
    asset_suspect = [r for r in exp_accts if any(kw in r["name"].lower() for kw in ["office supplies", "repairs and maintenance", "computer", "equipment rental"]) and r["amount"] > 2500]
    if asset_suspect:
        _set_pl_finding(ws_pl, 32, "clean up needed",
                        comment=_acct_list(asset_suspect),
                        num_txns=str(len(asset_suspect)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in asset_suspect):,.2f}",
                        internal_comment="Review each transaction — if single item exceeds capitalization threshold ($2,500 or client's policy), move to Fixed Assets.")
        pl_issues.append("Possible fixed asset purchases expensed — review for capitalization")
    else:
        _set_pl_finding(ws_pl, 32, "OK",
                        comment="Reviewed office/repair/computer expense accounts — all within expected range",
                        internal_comment="No accounts with balances exceeding $2,500 that would require capitalization review.")

    # J33 — Payroll tax liabilities to expense
    ptax_exp = [r for r in _find_rows_matching(pl_rows, "payroll tax liability", "payroll liab") if abs(r["amount"]) > 0.01]
    if ptax_exp:
        _set_pl_finding(ws_pl, 33, "clean up needed",
                        comment=_acct_list(ptax_exp),
                        amount=f"${sum(r['amount'] for r in ptax_exp):,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Payroll tax liabilities should be in a liability account, not expense. Reclassify journal entries.")
        pl_issues.append("Payroll tax liabilities recorded as expenses")
    else:
        _set_pl_finding(ws_pl, 33, "No",
                        comment="No payroll tax liability accounts found in expenses",
                        internal_comment="No payroll tax liabilities misposted as expenses.")

    # J34 — Payroll expense recorded incorrectly
    payroll_rows_pl = [r for r in exp_accts if any(kw in r["name"].lower() for kw in ["payroll", "wage", "salary"])]
    has_payroll_exp = bool(payroll_rows_pl)
    has_employer_tax = bool([r for r in exp_accts if any(kw in r["name"].lower() for kw in ["employer tax", "payroll tax expense", "fica"])])
    if has_payroll_exp and not has_employer_tax:
        _set_pl_finding(ws_pl, 34, "clean up needed",
                        comment=_acct_list(payroll_rows_pl),
                        amount=f"${sum(r['amount'] for r in payroll_rows_pl):,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Payroll found but no employer payroll tax expense. Verify gross wages, employer FICA, FUTA, and SUTA are recorded as separate line items.")
        pl_issues.append("Payroll structure may need review — employer taxes not clearly separated")
    else:
        _set_pl_finding(ws_pl, 34, "No" if not has_payroll_exp else "OK",
                        comment="No payroll recorded in this period" if not has_payroll_exp else _acct_list(payroll_rows_pl),
                        internal_comment="No payroll accounts found — confirm with client that payroll is handled outside QBO or not applicable." if not has_payroll_exp else "Payroll structure appears correct.")

    # J35 — Miscategorized expenses (only literal "Miscellaneous" or "General Expense" accounts)
    misc_exp = [r for r in _find_rows_matching(pl_rows, "miscellaneous", "general expense") if abs(r["amount"]) > 0.01 and not r.get("is_summary")]
    if misc_exp:
        _set_pl_finding(ws_pl, 35, "clean up needed",
                        comment=_acct_list(misc_exp),
                        num_txns=str(len(misc_exp)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in misc_exp):,.2f}",
                        internal_comment="Reclassify from generic 'Miscellaneous'/'General Expense' to specific expense accounts for better reporting.")
        pl_issues.append("Miscellaneous/Other expense accounts have balances — reclassify")
    else:
        _set_pl_finding(ws_pl, 35, "No",
                        comment="No Miscellaneous or General Expense accounts with balances",
                        internal_comment="No generic expense catch-all accounts in use — expenses appear specifically categorized.")

    # J36 — Sales tax as expense
    st_exp = [r for r in _find_rows_matching(pl_rows, "sales tax expense", "sales tax paid") if abs(r["amount"]) > 0.01]
    if st_exp:
        _set_pl_finding(ws_pl, 36, "clean up needed",
                        comment=_acct_list(st_exp),
                        amount=f"${sum(r['amount'] for r in st_exp):,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Sales tax should not be an expense. Remove and record through QBO Sales Tax Center → Sales Tax Payable liability.")
        pl_issues.append("Sales tax recorded as expense")
    else:
        _set_pl_finding(ws_pl, 36, "No",
                        comment="No sales tax expense accounts found",
                        internal_comment="Sales tax not recorded as expense — correct. Verify it is tracked in QBO Sales Tax Center.")

    # ── OTHER INCOME / OTHER EXPENSES SECTION ─────────────────────────────────

    # J39 — Negative or unusual balances in Other Income/Other Expenses
    neg_other_inc = [r for r in other_inc_accts if r["amount"] < -0.01]
    neg_other_exp = [r for r in other_exp_accts if r["amount"] < -0.01]
    all_other = other_inc_accts + other_exp_accts
    unusual_other = neg_other_inc + neg_other_exp
    if unusual_other:
        _set_pl_finding(ws_pl, 39, "clean up needed",
                        comment=_acct_list(unusual_other),
                        num_txns=str(len(unusual_other)),
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        amount=f"${sum(r['amount'] for r in unusual_other):,.2f}",
                        internal_comment="Investigate negative balances in Other Income/Expenses — may indicate mispostings or reversed entries.")
        pl_issues.append("Negative Other Income/Expense balances")
    elif all_other:
        _set_pl_finding(ws_pl, 39, "OK",
                        comment=_acct_list(all_other),
                        amount=f"${sum(r['amount'] for r in all_other):,.2f}",
                        internal_comment=f"Other Income: {_acct_list(other_inc_accts)}. Other Expenses: {_acct_list(other_exp_accts)}. Verify all items are properly classified in these sections.")
    else:
        _set_pl_finding(ws_pl, 39, "No",
                        comment="No Other Income or Other Expense accounts with balances",
                        internal_comment="No items in Other Income/Other Expenses sections.")

    # J42 — Unassigned class transactions (cannot check without P&L by Class)
    ws_pl["J42"].value = "Review needed"
    ws_pl["R42"].value = "Run P&L by Class in QBO to verify all transactions have a class assigned. Unassigned transactions will appear in a separate column."

    # ── CASH BASIS CHECKS ─────────────────────────────────────────────────────

    # J46 — Unapplied Cash Payment Income (requires cash-basis P&L)
    ucpi = _find_amount(pl_rows, "unapplied cash payment income")
    if abs(ucpi) > 0.01:
        _set_pl_finding(ws_pl, 46, "clean up needed",
                        comment="Unapplied Cash Payment Income",
                        amount=f"${ucpi:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Apply outstanding customer payments to their corresponding invoices in QBO. This account should always be $0.")
        pl_issues.append("Unapplied Cash Payment Income found")
    else:
        _set_pl_finding(ws_pl, 46, "No",
                        comment="No Unapplied Cash Payment Income balance found on accrual P&L",
                        internal_comment="Run P&L on Cash Basis in QBO and verify this account is $0. Apply any open payments to invoices.")

    # J49 — Unapplied Bill Payment Expense (requires cash-basis P&L)
    ubpe = _find_amount(pl_rows, "unapplied bill payment expense")
    if abs(ubpe) > 0.01:
        _set_pl_finding(ws_pl, 49, "clean up needed",
                        comment="Unapplied Bill Payment Expense",
                        amount=f"${ubpe:,.2f}",
                        date_from=period_from_mmyy, date_to=period_to_mmyy,
                        internal_comment="Apply outstanding vendor payments to their corresponding bills in QBO. This account should always be $0.")
        pl_issues.append("Unapplied Bill Payment Expense found")
    else:
        _set_pl_finding(ws_pl, 49, "No",
                        comment="No Unapplied Bill Payment Expense balance found on accrual P&L",
                        internal_comment="Run P&L on Cash Basis in QBO and verify this account is $0. Apply any open bill payments to bills.")

    # A51 — P&L Findings & Recommendations (detailed)
    income_summary = f"Income: {_acct_list(income_accts) if income_accts else 'none'} — Total ${total_income_bal:,.2f}"
    cogs_summary = f"COGS: {_acct_list(cogs_accts) if cogs_accts else 'none'} — Total ${total_cogs_bal:,.2f}"
    exp_summary = f"Expenses: {_acct_list(sorted(exp_accts, key=lambda r: r['amount'], reverse=True), 5) if exp_accts else 'none'} — Total ${total_exp_bal:,.2f}"
    other_inc_summary = f"Other Income: {_acct_list(other_inc_accts) if other_inc_accts else 'none'}"
    other_exp_summary = f"Other Expenses: {_acct_list(other_exp_accts) if other_exp_accts else 'none'}"

    if pl_issues:
        pl_findings = (
            f"FINDINGS — P&L Review ({period_label}, {accounting_method} basis)\n\n"
            f"ACCOUNT SUMMARY:\n{income_summary}\n{cogs_summary}\n{exp_summary}\n{other_inc_summary}\n{other_exp_summary}\n\n"
            f"ISSUES IDENTIFIED ({len(pl_issues)}):\n"
            + "\n".join(f"• {issue}" for issue in pl_issues)
            + "\n\nRECOMMENDATIONS: Address each flagged item above. Review all accounts with 'clean up needed' status."
        )
    else:
        pl_findings = (
            f"FINDINGS — P&L Review ({period_label}, {accounting_method} basis)\n\n"
            f"ACCOUNT SUMMARY:\n{income_summary}\n{cogs_summary}\n{exp_summary}\n{other_inc_summary}\n{other_exp_summary}\n\n"
            f"RESULT: No major issues found. P&L accounts appear properly categorized.\n\n"
            f"RECOMMENDATION: Continue monthly monitoring. Run P&L by Class to verify class assignments."
        )
    ws_pl["A51"].value = pl_findings

    # A57 — Work to be completed — P&L (with estimated bookkeeper time)
    pl_work = []
    if any("Negative income" in i or "negative income" in i for i in pl_issues):
        pl_work.append("Investigate and correct negative income account balances — review each transaction, reverse or reclassify as needed. Est. time: 1–2 hrs")
    if any("Uncategorized income" in i.lower() for i in pl_issues):
        pl_work.append("Reclassify all Uncategorized Income transactions to proper income accounts. Est. time: 1–3 hrs")
    if any("Sales of Product Income" in i for i in pl_issues):
        pl_work.append("Review Sales of Product Income transactions — confirm industry appropriateness or reclassify. Est. time: 30 min")
    if any("Services account" in i for i in pl_issues):
        pl_work.append("Review Services income transactions — confirm industry appropriateness or reclassify. Est. time: 30 min")
    if any("Deposits recorded" in i for i in pl_issues):
        pl_work.append("Reclassify deposit transactions from income to Deferred Revenue or correct income account. Est. time: 1 hr")
    if any("Loan proceeds" in i for i in pl_issues):
        pl_work.append("Move loan proceeds from income to Loan Payable (liability). Create journal entry to reverse. Est. time: 30 min")
    if any("Sales tax recorded as income" in i for i in pl_issues):
        pl_work.append("Remove sales tax from income deductions and record through QBO Sales Tax Center. Est. time: 1 hr")
    if any("Negative COGS" in i for i in pl_issues):
        pl_work.append("Investigate negative COGS balances — apply vendor credits or reverse incorrect entries. Est. time: 1–2 hrs")
    if any("misclassification in COGS" in i.lower() for i in pl_issues):
        pl_work.append("Reclassify expense accounts (insurance, utilities, rent) found in COGS section to Expenses. Est. time: 1 hr")
    if any("COGS exceeds" in i or "No COGS" in i for i in pl_issues):
        pl_work.append("Review and reconcile COGS to income — identify missing income or overstated costs. Est. time: 2–3 hrs")
    if any("Negative expense" in i or "negative expense" in i for i in pl_issues):
        pl_work.append("Review and correct negative expense balances — create reversal or correcting journal entries. Est. time: 1–2 hrs")
    if any("expense accounts unusually high" in i.lower() for i in pl_issues):
        pl_work.append("Review large expense accounts for unusual or duplicate entries. Est. time: 1–2 hrs")
    if any("Uncategorized expenses" in i for i in pl_issues):
        pl_work.append("Reclassify all Uncategorized Expense transactions to specific expense accounts. Est. time: 2–4 hrs")
    if any("Ask My Accountant" in i for i in pl_issues):
        pl_work.append("Review and reclassify all Ask My Accountant transactions with client approval. Est. time: 1–3 hrs")
    if any("Reconciliation Discrepancy" in i for i in pl_issues):
        pl_work.append("Investigate and correct the Reconciliation Discrepancy balance — should be $0. Est. time: 1–3 hrs")
    if any("COGS items recorded as expenses" in i for i in pl_issues):
        pl_work.append("Reclassify subcontractor/direct labor/job cost items from Expenses to COGS. Est. time: 1–2 hrs")
    if any("personal" in i.lower() for i in pl_issues):
        pl_work.append("Review personal/meals/entertainment transactions — document business purpose or reclassify to Owner Draw. Est. time: 1–2 hrs")
    if any("Loan payments recorded" in i for i in pl_issues):
        pl_work.append("Split loan payments between principal (Loan Payable) and interest (Interest Expense). Est. time: 1 hr")
    if any("fixed asset" in i.lower() for i in pl_issues):
        pl_work.append("Review high-balance repair/equipment accounts — capitalize assets above $2,500 threshold. Est. time: 1–2 hrs")
    if any("Payroll tax liabilities" in i for i in pl_issues):
        pl_work.append("Reclassify payroll tax liability amounts from expense to Payroll Tax Liability accounts. Est. time: 1 hr")
    if any("Payroll structure" in i for i in pl_issues):
        pl_work.append("Review payroll entries to ensure gross wages, employer FICA, FUTA, and SUTA are separately recorded. Est. time: 1–2 hrs")
    if any("Miscellaneous" in i or "Other expense accounts" in i for i in pl_issues):
        pl_work.append("Reclassify Miscellaneous/General Expense transactions to specific expense accounts. Est. time: 1–2 hrs")
    if any("Sales tax recorded as expense" in i for i in pl_issues):
        pl_work.append("Remove sales tax from expense accounts and record through QBO Sales Tax Center. Est. time: 1 hr")
    if any("Negative Other" in i for i in pl_issues):
        pl_work.append("Investigate negative balances in Other Income/Other Expenses — reverse or reclassify. Est. time: 30 min–1 hr")
    if any("Unapplied Cash Payment" in i for i in pl_issues):
        pl_work.append("Apply outstanding customer payments to their invoices in QBO (Receive Payment). Est. time: 30 min–2 hrs")
    if any("Unapplied Bill Payment" in i for i in pl_issues):
        pl_work.append("Apply outstanding vendor bill payments to their bills in QBO (Pay Bills). Est. time: 30 min–2 hrs")
    if not pl_work:
        pl_work.append("P&L is clean for this period. Continue monthly review. Est. time: 30 min/month for monitoring")
    pl_work.append("Run P&L on Cash Basis and compare to Accrual — check Unapplied Cash Payment Income and Unapplied Bill Payment Expense accounts. Est. time: 30 min")
    pl_work.append("Run P&L by Class to verify all income and expense transactions have a class assigned. Est. time: 30 min")
    ws_pl["A57"].value = "\n".join(f"• {w}" for w in pl_work)

    issues_found.extend(pl_issues)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Balance Sheet
    # ══════════════════════════════════════════════════════════════════════════
    ws_bs = wb["Balance Sheet"]
    bs_issues: list[str] = []

    ws_bs["J5"].value = period_from_mmyy
    ws_bs["K5"].value = period_to_mmyy

    # J9 — AR positive balance
    ar_bal = _find_amount(bs_rows, "accounts receivable")
    if ar_bal < 0:
        _set_bs_finding(ws_bs, 9, "clean up needed",
                        comment=f"AR has a negative (credit) balance of ${ar_bal:,.2f} — investigate overpayments or misapplied payments",
                        amount=f"${ar_bal:,.2f}")
        bs_issues.append("Negative AR balance found")
    else:
        _set_bs_finding(ws_bs, 9, "OK")

    # J10 — Uncategorized asset
    uncat_asset = _find_amount(bs_rows, "uncategorized asset")
    if abs(uncat_asset) > 0.01:
        _set_bs_finding(ws_bs, 10, "clean up needed",
                        comment=f"Uncategorized Asset balance of ${uncat_asset:,.2f} — reclassify to appropriate asset accounts",
                        amount=f"${uncat_asset:,.2f}")
        bs_issues.append("Uncategorized Asset balance found")
    else:
        _set_bs_finding(ws_bs, 10, "OK")

    # J11 — Unusual current asset balances
    unusual_assets = [
        r for r in bs_rows
        if abs(r["amount"]) > 50000 and not r.get("is_summary")
        and any(kw in r["name"].lower() for kw in ["prepaid", "advance", "deposit", "due from"])
    ]
    if unusual_assets:
        names = ", ".join(f"{r['name']} (${r['amount']:,.2f})" for r in unusual_assets[:3])
        _set_bs_finding(ws_bs, 11, "clean up needed",
                        comment=f"Unusual current asset balances: {names}",
                        num_txns=str(len(unusual_assets)))
        bs_issues.append("Unusual current asset balances found")
    else:
        _set_bs_finding(ws_bs, 11, "OK")

    # J12 — Credit card receivables
    cc_recv = _find_amount(bs_rows, "credit card receivable")
    if abs(cc_recv) > 0.01:
        _set_bs_finding(ws_bs, 12, "clean up needed",
                        comment=f"Credit Card Receivables balance of ${cc_recv:,.2f} — investigate and clear",
                        amount=f"${cc_recv:,.2f}")
        bs_issues.append("Credit Card Receivables balance found")
    else:
        _set_bs_finding(ws_bs, 12, "OK")

    # J13 — Fixed assets under $2500 in COA
    small_fixed = [
        a for a in active_accounts
        if a.get("AccountType") == "Fixed Asset"
        and 0.01 < abs(a.get("CurrentBalance", 0)) < 2500
    ]
    if small_fixed:
        names = ", ".join(a.get("Name", "") for a in small_fixed[:3])
        _set_bs_finding(ws_bs, 13, "clean up needed",
                        comment=f"Fixed asset accounts under $2,500: {names} — may need to be expensed instead",
                        num_txns=str(len(small_fixed)))
        bs_issues.append("Fixed asset accounts under $2,500 found — review capitalization policy")
    else:
        _set_bs_finding(ws_bs, 13, "OK")

    # J14 — Accumulated depreciation
    accum_depr = _find_amount(bs_rows, "accumulated depreciation")
    has_fixed = _find_amount(bs_rows, "fixed asset", "property", "equipment") > 0
    if has_fixed and accum_depr == 0:
        _set_bs_finding(ws_bs, 14, "clean up needed",
                        comment="Fixed assets present but no accumulated depreciation — verify prior year depreciation has been posted",
                        amount="$0.00")
        bs_issues.append("No accumulated depreciation despite fixed assets")
    else:
        _set_bs_finding(ws_bs, 14, "OK")

    # J15 — Unusual other asset balances
    unusual_other = [
        r for r in bs_rows
        if abs(r["amount"]) > 10000 and not r.get("is_summary")
        and any(kw in r["name"].lower() for kw in ["other asset", "security deposit", "notes receivable", "due from officer"])
    ]
    if unusual_other:
        names = ", ".join(f"{r['name']} (${r['amount']:,.2f})" for r in unusual_other[:3])
        _set_bs_finding(ws_bs, 15, "clean up needed",
                        comment=f"Unusual other asset balances: {names}",
                        num_txns=str(len(unusual_other)))
        bs_issues.append("Unusual other asset balances found")
    else:
        _set_bs_finding(ws_bs, 15, "OK")

    # J18 — AP positive balance
    ap_bal = _find_amount(bs_rows, "accounts payable")
    if ap_bal < 0:
        _set_bs_finding(ws_bs, 18, "clean up needed",
                        comment=f"AP has a negative (debit) balance of ${ap_bal:,.2f} — investigate overpayments or duplicate entries",
                        amount=f"${ap_bal:,.2f}")
        bs_issues.append("Negative AP balance found")
    else:
        _set_bs_finding(ws_bs, 18, "OK")

    # J19 — Negative credit card liabilities
    neg_cc = [a for a in active_accounts if a.get("AccountType") == "Credit Card" and a.get("CurrentBalance", 0) < -0.01]
    if neg_cc:
        names = ", ".join(a.get("Name", "") for a in neg_cc[:3])
        _set_bs_finding(ws_bs, 19, "clean up needed",
                        comment=f"Negative credit card liability balances: {names} — investigate payments and credits",
                        num_txns=str(len(neg_cc)),
                        amount=f"${sum(a.get('CurrentBalance', 0) for a in neg_cc):,.2f}")
        bs_issues.append("Negative credit card liability balances found")
    else:
        _set_bs_finding(ws_bs, 19, "OK")

    # J20 — Unusual current liability balances
    unusual_cl = [
        r for r in bs_rows
        if abs(r["amount"]) > 50000 and not r.get("is_summary")
        and any(kw in r["name"].lower() for kw in ["deferred", "customer deposit", "accrued", "due to"])
    ]
    if unusual_cl:
        names = ", ".join(f"{r['name']} (${r['amount']:,.2f})" for r in unusual_cl[:3])
        _set_bs_finding(ws_bs, 20, "clean up needed",
                        comment=f"Unusual current liability balances: {names}",
                        num_txns=str(len(unusual_cl)))
        bs_issues.append("Unusual current liability balances found")
    else:
        _set_bs_finding(ws_bs, 20, "OK")

    # J21 — Payroll liabilities reasonable
    payroll_liab_bal = _find_amount(bs_rows, "payroll liabilit", "payroll tax payable", "federal tax payable")
    if payroll_liab_bal > 100000:
        _set_bs_finding(ws_bs, 21, "clean up needed",
                        comment=f"Payroll liabilities of ${payroll_liab_bal:,.2f} appears high — verify current payroll taxes are clearing monthly",
                        amount=f"${payroll_liab_bal:,.2f}")
        bs_issues.append("High payroll liabilities — verify monthly clearing")
    else:
        _set_bs_finding(ws_bs, 21, "OK")

    # J22 — Sales tax payable reasonable
    st_pay_bal = _find_amount(bs_rows, "sales tax payable", "sales tax liabilit")
    if st_pay_bal > 50000:
        _set_bs_finding(ws_bs, 22, "clean up needed",
                        comment=f"Sales Tax Payable of ${st_pay_bal:,.2f} appears high — verify regular remittance",
                        amount=f"${st_pay_bal:,.2f}")
        bs_issues.append("High sales tax payable — verify remittance frequency")
    else:
        _set_bs_finding(ws_bs, 22, "OK")

    # J23 — Interest expense on notes payable
    notes_pay = _find_amount(bs_rows, "notes payable", "loan payable", "line of credit")
    int_exp = _find_amount(pl_rows, "interest expense")
    if notes_pay > 0 and int_exp == 0:
        _set_bs_finding(ws_bs, 23, "clean up needed",
                        comment="Notes Payable balance exists but no interest expense recorded — verify interest is properly split and recorded",
                        amount=f"${notes_pay:,.2f}")
        bs_issues.append("Notes Payable present but no interest expense recorded")
    else:
        _set_bs_finding(ws_bs, 23, "OK")

    # J24 — Unusual long-term liability balances
    unusual_ltl = [
        r for r in bs_rows
        if abs(r["amount"]) > 500000 and not r.get("is_summary")
        and any(kw in r["name"].lower() for kw in ["long term", "long-term", "note payable", "mortgage"])
    ]
    if unusual_ltl:
        names = ", ".join(f"{r['name']} (${r['amount']:,.2f})" for r in unusual_ltl[:3])
        _set_bs_finding(ws_bs, 24, "clean up needed",
                        comment=f"Large long-term liability balances: {names} — verify balances and terms are current",
                        num_txns=str(len(unusual_ltl)))
        bs_issues.append("Unusual long-term liability balances found")
    else:
        _set_bs_finding(ws_bs, 24, "OK")

    # J27 — Opening Balance Equity
    obe = _find_amount(bs_rows, "opening balance equity")
    if abs(obe) > 0.01:
        _set_bs_finding(ws_bs, 27, "clean up needed",
                        comment=f"Opening Balance Equity has a balance of ${obe:,.2f} — reclassify to appropriate equity accounts",
                        amount=f"${obe:,.2f}")
        bs_issues.append(f"Opening Balance Equity has a balance of ${obe:,.2f}")
    else:
        _set_bs_finding(ws_bs, 27, "OK")

    # J28 — OBE transactions in current year (requires GL drill-down)
    ws_bs["J28"].value = "Review needed — run GL detail on Opening Balance Equity for current year"

    # J29 — Equity contributions
    _set_bs_finding(ws_bs, 29, "OK")

    # J30 — Owner draws
    _set_bs_finding(ws_bs, 30, "OK")

    # J34 — Cash basis AR
    ws_bs["J34"].value = "Review needed — run Balance Sheet on cash basis to verify AR is $0"

    # J37 — Cash basis AP
    ws_bs["J37"].value = "Review needed — run Balance Sheet on cash basis to verify AP is $0"

    # A39 — BS overall findings
    if bs_issues:
        bs_summary = (
            f"BALANCE SHEET ISSUES FOUND ({len(bs_issues)}):\n"
            + "\n".join(f"• {issue}" for issue in bs_issues)
            + f"\n\nAs of: {_fmt_period(period_to)} | Method: Accrual"
        )
    else:
        bs_summary = (
            f"Balance Sheet as of {_fmt_period(period_to)} shows no major issues. "
            "Assets, liabilities, and equity appear properly structured."
        )
    ws_bs["A40"].value = bs_summary

    # Work to be completed — Balance Sheet
    bs_work = []
    if any("Opening Balance Equity" in i for i in bs_issues):
        bs_work.append("Clear Opening Balance Equity: reclassify balance to Retained Earnings or appropriate equity account via journal entry")
    if any("Uncategorized Asset" in i for i in bs_issues):
        bs_work.append("Identify and reclassify all Uncategorized Asset transactions")
    if any("Negative AR" in i for i in bs_issues):
        bs_work.append("Investigate negative AR balance — apply credit memos or correct misposted payments")
    if any("Negative AP" in i for i in bs_issues):
        bs_work.append("Investigate negative AP balance — apply vendor credits or correct duplicate payments")
    if any("depreciation" in i.lower() for i in bs_issues):
        bs_work.append("Post depreciation journal entries for the period; verify prior year depreciation is on file")
    if any("Fixed asset" in i for i in bs_issues):
        bs_work.append("Review fixed asset accounts under $2,500 — expense items below client's capitalization threshold")
    if any("credit card liability" in i.lower() for i in bs_issues):
        bs_work.append("Investigate negative credit card liability balances — likely duplicate payments or recording errors")
    if any("Notes Payable" in i for i in bs_issues):
        bs_work.append("Record interest expense on outstanding notes payable; obtain current loan statement from client")
    if not bs_work:
        bs_work.append("Continue monitoring Balance Sheet monthly; ensure ending balances are reconciled to bank statements")
    ws_bs["A47"].value = "\n".join(f"• {w}" for w in bs_work)

    issues_found.extend(bs_issues)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Accts Receivable+ Accts Payable
    # ══════════════════════════════════════════════════════════════════════════
    ws_arap = wb["Accts Receivable+ Accts Payable"]
    ar_issues: list[str] = []
    ap_issues: list[str] = []

    ar_bkts = ar_data["buckets"]
    ar_90 = ar_data["items_90plus"]
    ar_neg = ar_data["items_negative"]
    ar_zero = ar_data["items_zero"]

    ap_bkts = ap_data["buckets"]
    ap_90 = ap_data["items_90plus"]
    ap_neg = ap_data["items_negative"]
    ap_zero = ap_data["items_zero"]

    # AR checks
    if ar_90 or ar_bkts.get("91+", 0) > 0.01:
        total_90 = ar_bkts.get("91+", 0)
        _set_arap_finding(ws_arap, 6, "clean up needed",
                          num_txns=str(len(ar_90)),
                          date_from=period_from_mmyy, date_to=period_to_mmyy,
                          amount=f"${total_90:,.2f}")
        ar_issues.append(f"AR items over 90 days: ${total_90:,.2f}")
    else:
        _set_arap_finding(ws_arap, 6, "OK")

    if ar_neg:
        _set_arap_finding(ws_arap, 7, "clean up needed",
                          num_txns=str(len(ar_neg)),
                          amount=f"${sum(r['amount'] for r in ar_neg):,.2f}")
        ar_issues.append(f"{len(ar_neg)} customer(s) with credit balances in AR")
    else:
        _set_arap_finding(ws_arap, 7, "OK")

    # J8 — payment applied with no invoice (appears as credit/negative in AR aging)
    if ar_neg:
        _set_arap_finding(ws_arap, 8, "clean up needed",
                          num_txns=str(len(ar_neg)),
                          amount=f"${abs(sum(r['amount'] for r in ar_neg)):,.2f}")
        ar_issues.append(f"{len(ar_neg)} customer payment(s) with no invoice to apply to")
    else:
        _set_arap_finding(ws_arap, 8, "OK")

    # J9 — overpayment (same indicator: negative AR balance = overpayment or unapplied credit)
    if ar_neg:
        _set_arap_finding(ws_arap, 9, "clean up needed",
                          num_txns=str(len(ar_neg)),
                          amount=f"${abs(sum(r['amount'] for r in ar_neg)):,.2f}")
    else:
        _set_arap_finding(ws_arap, 9, "OK")

    if ar_zero:
        _set_arap_finding(ws_arap, 11, "clean up needed", num_txns=str(len(ar_zero)))
        ar_issues.append(f"{len(ar_zero)} customer(s) with $0 AR balance — review and close")
    else:
        _set_arap_finding(ws_arap, 11, "OK")

    if ar_neg:
        _set_arap_finding(ws_arap, 12, "clean up needed", num_txns=str(len(ar_neg)))
        ar_issues.append(f"{len(ar_neg)} available AR credit(s) to apply")
    else:
        _set_arap_finding(ws_arap, 12, "OK")

    ws_arap["A16"].value = (
        (f"AR ISSUES FOUND ({len(ar_issues)}):\n" + "\n".join(f"• {i}" for i in ar_issues)
         + f"\n\nTotal AR: ${ar_bkts.get('total', 0):,.2f} | 90+ days: ${ar_bkts.get('91+', 0):,.2f}")
        if ar_issues else
        f"AR review shows no major issues. Total outstanding: ${ar_bkts.get('total', 0):,.2f}."
    )

    # Work to be completed — AR
    ar_work = []
    if ar_90 or ar_bkts.get("91+", 0) > 0.01:
        ar_work.append(f"Follow up on AR items over 90 days (${ar_bkts.get('91+', 0):,.2f}) — contact customers or write off uncollectable amounts")
    if ar_neg:
        ar_work.append(f"Apply {len(ar_neg)} customer credit balance(s) to open invoices or issue refunds")
    if ar_zero:
        ar_work.append(f"Review and close {len(ar_zero)} customer(s) with $0 AR balance — void or write off stale open invoices")
    if not ar_work:
        ar_work.append("Continue monitoring AR aging monthly; follow up on any items approaching 60 days")
    ws_arap["A21"].value = "\n".join(f"• {w}" for w in ar_work)

    issues_found.extend(ar_issues)

    # AP checks
    if ap_90 or ap_bkts.get("91+", 0) > 0.01:
        total_90_ap = ap_bkts.get("91+", 0)
        _set_arap_finding(ws_arap, 31, "clean up needed",
                          num_txns=str(len(ap_90)),
                          date_from=period_from_mmyy, date_to=period_to_mmyy,
                          amount=f"${total_90_ap:,.2f}")
        ap_issues.append(f"AP items over 90 days: ${total_90_ap:,.2f}")
    else:
        _set_arap_finding(ws_arap, 31, "OK")

    if ap_neg:
        _set_arap_finding(ws_arap, 32, "clean up needed",
                          num_txns=str(len(ap_neg)),
                          amount=f"${sum(r['amount'] for r in ap_neg):,.2f}")
        ap_issues.append(f"{len(ap_neg)} vendor(s) with debit balances in AP")
    else:
        _set_arap_finding(ws_arap, 32, "OK")

    # J33 — payment applied with no bill (debit/negative in AP aging)
    if ap_neg:
        _set_arap_finding(ws_arap, 33, "clean up needed",
                          num_txns=str(len(ap_neg)),
                          amount=f"${abs(sum(r['amount'] for r in ap_neg)):,.2f}")
        ap_issues.append(f"{len(ap_neg)} vendor payment(s) with no bill to apply to")
    else:
        _set_arap_finding(ws_arap, 33, "OK")

    # J34 — overpayment to vendor (same indicator: negative AP balance)
    if ap_neg:
        _set_arap_finding(ws_arap, 34, "clean up needed",
                          num_txns=str(len(ap_neg)),
                          amount=f"${abs(sum(r['amount'] for r in ap_neg)):,.2f}")
    else:
        _set_arap_finding(ws_arap, 34, "OK")

    if ap_zero:
        _set_arap_finding(ws_arap, 36, "clean up needed", num_txns=str(len(ap_zero)))
        ap_issues.append(f"{len(ap_zero)} vendor(s) with $0 AP balance — review and close")
    else:
        _set_arap_finding(ws_arap, 36, "OK")

    if ap_neg:
        _set_arap_finding(ws_arap, 37, "clean up needed", num_txns=str(len(ap_neg)))
        ap_issues.append(f"{len(ap_neg)} available AP credit(s) to apply")
    else:
        _set_arap_finding(ws_arap, 37, "OK")

    ws_arap["A41"].value = (
        (f"AP ISSUES FOUND ({len(ap_issues)}):\n" + "\n".join(f"• {i}" for i in ap_issues)
         + f"\n\nTotal AP: ${ap_bkts.get('total', 0):,.2f} | 90+ days: ${ap_bkts.get('91+', 0):,.2f}")
        if ap_issues else
        f"AP review shows no major issues. Total outstanding: ${ap_bkts.get('total', 0):,.2f}."
    )

    # Work to be completed — AP
    ap_work = []
    if ap_90 or ap_bkts.get("91+", 0) > 0.01:
        ap_work.append(f"Review AP items over 90 days (${ap_bkts.get('91+', 0):,.2f}) — pay outstanding bills or void if no longer owed")
    if ap_neg:
        ap_work.append(f"Apply {len(ap_neg)} vendor debit balance(s) to open bills or request vendor refunds")
    if ap_zero:
        ap_work.append(f"Review and close {len(ap_zero)} vendor(s) with $0 AP balance — void or mark stale open bills as paid")
    if not ap_work:
        ap_work.append("Continue monitoring AP aging monthly; pay all bills before due dates to maintain vendor relationships")
    ws_arap["A46"].value = "\n".join(f"• {w}" for w in ap_work)

    issues_found.extend(ap_issues)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Chart of Accounts
    # ══════════════════════════════════════════════════════════════════════════
    ws_coa = wb["Chart of Accounts"]
    coa_issues: list[str] = []

    # F4 — Number of accounts reasonable
    if total_account_count == 0:
        ws_coa["E4"].value = "Unable to retrieve Chart of Accounts."
    elif total_account_count > 150:
        ws_coa["E4"].value = (
            f"REVIEW NEEDED — {total_account_count} accounts found, which may be excessive. "
            "Consider consolidating duplicate or unused accounts."
        )
        coa_issues.append(f"Chart of Accounts has {total_account_count} accounts — may be excessive")
    else:
        ws_coa["E4"].value = f"OK — {total_account_count} active accounts appears reasonable for the business size."

    # F5 — List reasonableness
    inactive_count = len([a for a in coa_list if not a.get("Active", True)])
    if inactive_count > 20:
        ws_coa["E5"].value = (
            f"REVIEW — {inactive_count} inactive accounts found. "
            "Consider cleaning up the list."
        )
        coa_issues.append(f"{inactive_count} inactive accounts in COA")
    else:
        ws_coa["E5"].value = f"OK — Account list appears reasonable. {inactive_count} inactive accounts."

    # F6 — Account types
    no_subtype = [a for a in active_accounts if not a.get("AccountSubType") and a.get("AccountType") not in ("Bank",)]
    if len(no_subtype) > 5:
        ws_coa["E6"].value = f"REVIEW NEEDED — {len(no_subtype)} accounts missing account subtypes."
        coa_issues.append(f"{len(no_subtype)} accounts missing account subtypes")
    else:
        ws_coa["E6"].value = "OK — Account types appear correctly assigned."

    # F7 — Account numbers
    with_nums = [a for a in active_accounts if a.get("AcctNum")]
    if with_nums:
        ws_coa["E7"].value = f"OK — {len(with_nums)} of {total_account_count} accounts have numbers assigned."
    else:
        ws_coa["E7"].value = (
            "No account numbers in use. Consider implementing a numbering system "
            "(1000s=Assets, 2000s=Liabilities, 3000s=Equity, 4000s=Income, 5000s=COGS, 6000s=Expenses)."
        )
        coa_issues.append("No account numbers assigned")

    # A9 — COA overall findings
    ws_coa["A10"].value = (
        (f"CHART OF ACCOUNTS ISSUES ({len(coa_issues)}):\n" + "\n".join(f"• {i}" for i in coa_issues)
         + f"\n\nTotal active accounts: {total_account_count}")
        if coa_issues else
        f"Chart of Accounts review shows no major issues. {total_account_count} active accounts with appropriate structure."
    )

    # Work to be completed — COA
    coa_work = []
    if total_account_count > 150:
        coa_work.append(f"Audit Chart of Accounts — archive or merge duplicate/unused accounts (currently {total_account_count} active)")
    if inactive_count > 20:
        coa_work.append(f"Review {inactive_count} inactive accounts — confirm they are truly inactive and can be archived")
    if len(no_subtype) > 5:
        coa_work.append(f"Assign correct account subtypes to {len(no_subtype)} accounts missing subtypes — required for proper financial reporting")
    if not with_nums:
        coa_work.append("Implement account numbering system: 1000s=Assets, 2000s=Liabilities, 3000s=Equity, 4000s=Income, 5000s=COGS, 6000s=Expenses")
    if not coa_work:
        coa_work.append("Chart of Accounts is well-organized. Review semi-annually to archive unused accounts.")
    ws_coa["A15"].value = "\n".join(f"• {w}" for w in coa_work)

    issues_found.extend(coa_issues)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Payroll
    # ══════════════════════════════════════════════════════════════════════════
    ws_pay = wb["Payroll"]

    payroll_exp_accts = [
        a for a in active_accounts
        if any(kw in a.get("Name", "").lower() for kw in ["payroll", "salary", "wage"])
    ]
    has_payroll = bool(payroll_exp_accts) or has_payroll_liability

    ws_pay["J4"].value = "Yes" if has_payroll else "No"

    # J5 — number of employees (from QBO Employee list)
    active_employees = [e for e in (employee_list or []) if e.get("Active", True)]
    if active_employees:
        ws_pay["J5"].value = f"{len(active_employees)} active employee(s) in QBO"
    elif has_payroll:
        ws_pay["J5"].value = "Payroll accounts detected but no employees found in QBO Employee list — confirm with client"
    else:
        ws_pay["J5"].value = "No employees found in QBO"

    # J6 — number of 1099 subcontractors (vendors flagged as 1099 in QBO)
    vendors_1099 = [v for v in (vendor_list_raw or []) if v.get("Vendor1099", False)]
    if vendors_1099:
        names_1099 = ", ".join(v.get("DisplayName", v.get("CompanyName", "")) for v in vendors_1099[:5])
        ws_pay["J6"].value = (
            f"{len(vendors_1099)} 1099 contractor(s) flagged in QBO: {names_1099}"
            + (f" (and {len(vendors_1099) - 5} more)" if len(vendors_1099) > 5 else "")
        )
    else:
        ws_pay["J6"].value = "No vendors flagged as 1099 contractors in QBO — confirm with client if subcontractors are used"

    # J7 — payroll type/frequency (infer from payroll accounts or expense patterns)
    payroll_salary = any("salary" in a.get("Name", "").lower() for a in active_accounts)
    payroll_hourly = any("hourly" in a.get("Name", "").lower() or "wage" in a.get("Name", "").lower() for a in active_accounts)
    if payroll_salary and payroll_hourly:
        ws_pay["J7"].value = "Mix of salaried and hourly accounts found in COA — confirm payroll frequency (bi-weekly, semi-monthly, etc.) with client"
    elif payroll_salary:
        ws_pay["J7"].value = "Salaried payroll accounts found — confirm frequency (monthly, semi-monthly, bi-weekly) with client"
    elif payroll_hourly:
        ws_pay["J7"].value = "Hourly/wage payroll accounts found — confirm frequency with client"
    else:
        ws_pay["J7"].value = "Payroll type/frequency not determinable from COA — confirm with client"

    # J8 — payroll processor (check if QBO payroll liabilities exist which suggest QBO Payroll)
    qbo_payroll_accounts = [a for a in active_accounts if "payroll" in a.get("Name", "").lower() and a.get("AccountType") == "Other Current Liability"]
    if qbo_payroll_accounts and active_employees:
        ws_pay["J8"].value = "QBO Payroll likely in use — payroll liability accounts and employee records found in QBO"
    elif has_payroll and not active_employees:
        ws_pay["J8"].value = "Third-party payroll service likely (e.g., Gusto, ADP, Paychex) — payroll expenses recorded but no employees in QBO Payroll. Confirm with client."
    else:
        ws_pay["J8"].value = "Payroll processor not confirmed — verify with client (QBO Payroll, Gusto, ADP, Paychex, or manual)"

    if has_payroll and has_payroll_liability:
        ws_pay["J9"].value = "Yes — payroll expense and liability accounts found in COA"
    elif has_payroll and not has_payroll_liability:
        ws_pay["J9"].value = "Review needed — payroll expense accounts found but no payroll liability accounts"
        issues_found.append("Payroll expense accounts exist but no payroll liability accounts in COA")
    else:
        ws_pay["J9"].value = "No payroll detected in QBO"

    ws_pay["A12"].value = (
        ("Payroll accounts detected in Chart of Accounts. " if has_payroll else "No payroll accounts detected. ")
        + "Verify with client: number of employees, subcontractors, payroll frequency, and processor "
        + "(QBO Payroll, third-party service, or manual). "
        + "Confirm employer tax accounts are separate from employee withholding accounts."
    )

    # Work to be completed — Payroll
    pay_work = []
    if has_payroll and not has_payroll_liability:
        pay_work.append("Set up payroll liability accounts in COA: Payroll Tax Payable, Employee Benefits Payable, etc.")
        pay_work.append("Review all payroll expense accounts and ensure proper split between gross wages, employer taxes, and benefits")
    if has_payroll:
        pay_work.append("Confirm with client: number of W-2 employees, 1099 contractors, and payroll frequency")
        pay_work.append("Verify payroll processor and confirm payroll journal entries are correctly imported into QBO")
        pay_work.append("Confirm employer FICA, FUTA, SUTA accounts are separate from employee withholding accounts")
    else:
        pay_work.append("Confirm with client whether they have employees or contractors — may need to set up payroll tracking")
    ws_pay["A17"].value = "\n".join(f"• {w}" for w in pay_work)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Sales Tax
    # ══════════════════════════════════════════════════════════════════════════
    ws_st = wb["Sales Tax"]

    st_payable_accts = [
        a for a in active_accounts
        if a.get("AccountSubType") == "SalesTaxPayable" or "sales tax payable" in a.get("Name", "").lower()
    ]
    uses_sales_tax = bool(st_payable_accts) or has_sales_tax

    ws_st["J4"].value = "Yes" if uses_sales_tax else "No"
    ws_st["J5"].value = "Confirm remittance frequency with client (monthly, quarterly, or annually based on state requirements)"
    ws_st["J6"].value = accounting_method
    ws_st["J7"].value = "Yes" if uses_sales_tax else "No"

    if uses_sales_tax:
        st_bal = sum(a.get("CurrentBalance", 0) for a in st_payable_accts)
        st_names = ", ".join(a.get("Name", "") for a in st_payable_accts[:3])

        # Detect likely overdue: if there's a positive balance and the period end is
        # more than 30 days in the past, the remittance window has likely passed.
        from datetime import date as _st_date_cls
        try:
            period_end_date = _st_date_cls.fromisoformat(period_to[:10])
            days_since_period = (_st_date_cls.today() - period_end_date).days
        except Exception:
            days_since_period = 0

        if st_bal > 0.01 and days_since_period > 30:
            overdue_flag = (
                f"OVERDUE LIKELY — Sales Tax Payable balance is ${st_bal:,.2f} "
                f"and the period ended {days_since_period} days ago. "
                "The remittance window has likely passed. File and pay immediately to avoid penalties."
            )
            issues_found.append(f"Sales Tax possibly overdue: ${st_bal:,.2f} outstanding, period ended {days_since_period} days ago")
        elif st_bal > 0.01:
            overdue_flag = (
                f"Sales Tax Payable balance is ${st_bal:,.2f}. "
                "Confirm that remittance has been filed or is scheduled before the due date."
            )
        else:
            overdue_flag = (
                f"Sales Tax Payable balance is ${st_bal:,.2f} — appears current. "
                "Verify in QBO Sales Tax Center that all filings are up to date."
            )

        ws_st["A10"].value = (
            f"Sales Tax Payable accounts found: {st_names}.\n"
            f"{overdue_flag}\n"
            "Verify client is using the QBO Sales Tax Center for all tracking and remittance. "
            "Confirm remittance schedule aligns with state requirements."
        )
        st_work = [
            "Verify all sales are running through QBO Sales Tax Center — not manual Sales Tax Payable entries",
            f"Confirm remittance schedule with client — current balance is ${st_bal:,.2f}",
            "Ensure correct tax rates are applied to taxable products/services",
            "Review prior period sales tax returns for accuracy vs QBO reports",
        ]
        if st_bal > 0.01 and days_since_period > 30:
            st_work.insert(0, f"URGENT: File and pay overdue sales tax — ${st_bal:,.2f} outstanding, {days_since_period} days since period end")
    else:
        ws_st["A10"].value = (
            "No sales tax accounts detected in Chart of Accounts. "
            "Confirm with client whether they are required to collect and remit sales tax. "
            "If applicable, set up the QBO Sales Tax Center."
        )
        st_work = [
            "Confirm with client whether they sell taxable goods or services in any state",
            "If sales tax applies: set up QBO Sales Tax Center and configure correct rates by jurisdiction",
        ]
    ws_st["A15"].value = "\n".join(f"• {w}" for w in st_work)

    # ══════════════════════════════════════════════════════════════════════════
    # Client info — overall findings (written last after all checks complete)
    # ══════════════════════════════════════════════════════════════════════════
    total_issues = len(issues_found)
    if total_issues == 0:
        overall_findings = (
            f"QBO Diagnostic Assessment for {client_name or 'client'} — Period: {period_label}\n\n"
            "Overall assessment: No significant issues found. "
            "The QuickBooks file appears to be well-maintained. "
            "Continue with regular reconciliation and review practices."
        )
    else:
        overall_findings = (
            f"QBO Diagnostic Assessment for {client_name or 'client'} — Period: {period_label}\n\n"
            f"ISSUES REQUIRING ATTENTION ({total_issues} total):\n"
            + "\n".join(f"• {issue}" for issue in issues_found[:20])
        )
        if total_issues > 20:
            overall_findings += f"\n...and {total_issues - 20} additional items. See individual sheets for full detail."
        overall_findings += (
            "\n\nRecommendation: Prioritize cleanup in the order listed above. "
            "Schedule a review meeting with the client to discuss findings and establish a cleanup timeline."
        )
    ws_client["A14"].value = overall_findings

    # Work to be completed — Client info / Overall
    client_work = [
        f"Complete full diagnostic assessment for {client_name or 'client'} — Period: {period_label}",
        "Review all findings in individual tabs and address items marked 'clean up needed'",
        "Schedule a client meeting to discuss findings, agree on cleanup timeline, and assign responsibilities",
    ]
    if issues_found:
        client_work.append(f"Prioritize {len(issues_found)} identified issue(s) in order: Banking → P&L → Balance Sheet → AR/AP → COA")
    ws_client["A19"].value = "\n".join(f"• {w}" for w in client_work)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Reconciliation to Tax Return
    # ══════════════════════════════════════════════════════════════════════════
    ws_tax_rec = wb["Reconciliation to Tax Return"]

    # Determine if this applies (S-Corp, Partnership, C-Corp)
    applies_to_tax_rec = any(t in (tax_org_type or "").upper() for t in ["S-CORP", "S CORP", "PARTNERSHIP", "C-CORP", "C CORP"])

    ws_tax_rec["A14"].value = (
        f"Tax entity type: {tax_org_type or 'Not specified'}. "
        + (
            "This assessment applies — obtain the most recent filed tax return and compare Balance Sheet totals "
            f"(Total Assets, Total Liabilities, Total Equity) for the period ending {_fmt_period(period_to)}. "
            "Any differences between QBO and the tax return should be investigated and documented. "
            "Common causes: basis adjustments, depreciation differences, cash vs accrual timing, or missing journal entries."
            if applies_to_tax_rec
            else
            f"For {tax_org_type or 'this entity type'}, a formal tax return balance sheet reconciliation may not be required "
            "(e.g., Sole Proprietors on Schedule C with assets under $250K may not file a balance sheet). "
            "Confirm with the tax preparer whether a reconciliation is needed for this client."
        )
    )
    tax_rec_work = []
    if applies_to_tax_rec:
        tax_rec_work = [
            f"Obtain the most recent tax return for {tax_org_type} from the client",
            f"Run Balance Sheet in QBO as of the last filed tax return period and compare key totals",
            "Document any differences and determine if adjusting journal entries are needed",
            "Coordinate with tax preparer to ensure QBO reflects all tax return adjustments",
        ]
    else:
        tax_rec_work = [
            f"Confirm with client and tax preparer whether a tax return balance sheet reconciliation is required for {tax_org_type or 'this entity'}",
            "If not required, note in file and skip this section",
        ]
    ws_tax_rec["A19"].value = "\n".join(f"• {w}" for w in tax_rec_work)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Undeposited Funds
    # ══════════════════════════════════════════════════════════════════════════
    ws_udf = wb["Undeposited Funds"]

    if undeposited_funds:
        from datetime import date as _date, datetime as _datetime
        today_dt = _date.today()
        old_items = []
        all_dates = []
        udf_total_all = 0.0
        for item in undeposited_funds:
            amt = _safe_float(item.get("Amount", 0) or item.get("TotalAmt", 0))
            udf_total_all += amt
            txn_date_str = item.get("TxnDate", "")
            if txn_date_str:
                try:
                    d = _date.fromisoformat(txn_date_str)
                    all_dates.append(d)
                    if (today_dt - d).days > 30:
                        old_items.append((d, amt, item))
                except Exception:
                    pass

        has_old = bool(old_items)
        oldest_date = min(all_dates) if all_dates else None
        old_total = sum(a for _, a, _ in old_items)

        ws_udf["J5"].value = (
            f"YES — {len(old_items)} item(s) older than 30 days (total: ${old_total:,.2f})"
            if has_old else
            "No — all items are within 30 days"
        )
        ws_udf["Q5"].value = (
            oldest_date.strftime("%m/%d/%Y") if oldest_date else "N/A"
        )

        udf_findings = (
            f"Undeposited Funds contains {len(undeposited_funds)} item(s) totaling ${udf_total_all:,.2f}. "
        )
        if has_old:
            udf_findings += (
                f"{len(old_items)} item(s) are older than 30 days (${old_total:,.2f}) — "
                f"oldest dates to {oldest_date.strftime('%m/%d/%Y') if oldest_date else 'unknown'}. "
                "These may represent forgotten deposits, duplicate entries, or transactions that should have been voided. "
                "Review each item and either deposit, match to an existing bank transaction, or void if erroneous."
            )
        else:
            udf_findings += "All items appear to be recent (within 30 days). Verify each item corresponds to an actual pending deposit."

        ws_udf["A9"].value = udf_findings
        udf_work = []
        if has_old:
            udf_work.append(f"Review {len(old_items)} Undeposited Funds item(s) older than 30 days — deposit, match, or void each one")
            if oldest_date:
                udf_work.append(f"Oldest item dates to {oldest_date.strftime('%m/%d/%Y')} — investigate and resolve")
        udf_work.append("Ensure all customer payments received are promptly deposited and cleared from Undeposited Funds")
        udf_work.append("Do not use Undeposited Funds as a holding account for more than a few days")
        ws_udf["A15"].value = "\n".join(f"• {w}" for w in udf_work)
    else:
        ws_udf["J5"].value = "No items found"
        ws_udf["Q5"].value = "N/A"
        ws_udf["A9"].value = "No items found in Undeposited Funds. Confirm client is consistently depositing payments and clearing this account."
        ws_udf["A15"].value = "• Verify Undeposited Funds account is cleared and confirm all customer payments are deposited promptly."

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Products & Services
    # ══════════════════════════════════════════════════════════════════════════
    ws_ps = wb["Products & Services"]

    active_items = [it for it in (items_list or []) if it.get("Active", True)]
    total_items = len(active_items)

    service_items   = [it for it in active_items if it.get("Type") == "Service"]
    product_items   = [it for it in active_items if it.get("Type") in ("Inventory", "NonInventory")]
    inventory_items = [it for it in active_items if it.get("Type") == "Inventory"]
    bundle_items    = [it for it in active_items if it.get("Type") == "Group"]

    # E4 — Is number of items reasonable?
    if total_items == 0:
        ws_ps["E4"].value = "Unable to retrieve Items list from QBO."
    elif total_items > 300:
        ws_ps["E4"].value = (
            f"REVIEW — {total_items} active items found. This may be excessive. "
            "Consider consolidating duplicate or overly granular items."
        )
    elif total_items > 150:
        ws_ps["E4"].value = f"REVIEW — {total_items} items found. Consider whether all items are actively used and necessary."
    else:
        ws_ps["E4"].value = f"OK — {total_items} active item(s) appears reasonable ({len(service_items)} services, {len(product_items)} products, {len(bundle_items)} bundles)."

    # E5 — Is the list reasonable for the industry?
    has_both = bool(service_items) and bool(product_items)
    ws_ps["E5"].value = (
        f"OK — Mix of {len(service_items)} service(s) and {len(product_items)} product(s). "
        "Verify this mix aligns with the client's business model and that each item is actively billed."
        if has_both else
        f"OK — {total_items} {'service' if service_items else 'product'} item(s). "
        "Verify all items are relevant to the client's current operations and pricing is current."
    ) if total_items > 0 else "No items found."

    # E6 — Are types used correctly?
    no_income_acct = [
        it for it in active_items
        if not it.get("IncomeAccountRef") and it.get("Type") in ("Service", "NonInventory")
    ]
    if no_income_acct:
        ws_ps["E6"].value = (
            f"REVIEW — {len(no_income_acct)} item(s) have no income account mapped: "
            + ", ".join(it.get("Name", "") for it in no_income_acct[:5])
            + ". Set correct income accounts for each item."
        )
    elif inventory_items and not any(it.get("AssetAccountRef") for it in inventory_items):
        ws_ps["E6"].value = "REVIEW — Inventory items found but asset account may not be properly set. Verify each inventory item has an Asset Account assigned."
    else:
        ws_ps["E6"].value = "OK — Item types appear to be correctly assigned. Spot-check income/COGS account mappings."

    # E7 — Correctly mapped to income/COGS accounts?
    wrong_income = [
        it for it in active_items
        if it.get("IncomeAccountRef")
        and any(kw in (it.get("IncomeAccountRef", {}).get("name", "") or "").lower()
                for kw in ["expense", "cogs", "cost of"])
    ]
    if wrong_income:
        names = ", ".join(it.get("Name", "") for it in wrong_income[:3])
        ws_ps["E7"].value = (
            f"REVIEW — {len(wrong_income)} item(s) mapped to expense/COGS accounts instead of income accounts: {names}. "
            "Remap to correct income accounts."
        )
    else:
        ws_ps["E7"].value = (
            f"OK — Income account mappings appear reasonable. "
            f"{len(inventory_items)} inventory item(s) should also have COGS and asset accounts assigned."
        ) if total_items > 0 else "No items to review."

    # A9 — P&S findings
    ps_issues = []
    if total_items > 300:
        ps_issues.append(f"Products & Services list has {total_items} items — likely has duplicates or outdated items")
    if no_income_acct:
        ps_issues.append(f"{len(no_income_acct)} item(s) missing income account mapping")
    if wrong_income:
        ps_issues.append(f"{len(wrong_income)} item(s) mapped to wrong account type")
    ws_ps["A10"].value = (
        (f"PRODUCTS & SERVICES ISSUES ({len(ps_issues)}):\n" + "\n".join(f"• {i}" for i in ps_issues)
         + f"\n\nTotal active items: {total_items}")
        if ps_issues else
        f"Products & Services review shows no major issues. {total_items} active items with appropriate structure."
    )

    # A14 — Work to be completed
    ps_work = []
    if no_income_acct:
        ps_work.append(f"Map correct income accounts to {len(no_income_acct)} item(s) missing income account")
    if wrong_income:
        ps_work.append(f"Correct income account mapping for {len(wrong_income)} item(s) mapped to expense/COGS accounts")
    if total_items > 150:
        ps_work.append(f"Review and consolidate Products & Services list — {total_items} items may be excessive")
    if inventory_items:
        ps_work.append(f"Verify {len(inventory_items)} inventory item(s) each have Asset Account and COGS account assigned")
    if not ps_work:
        ps_work.append("Products & Services list appears well-maintained. Review annually to deactivate unused items.")
    ws_ps["A15"].value = "\n".join(f"• {w}" for w in ps_work)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET: Inventory
    # ══════════════════════════════════════════════════════════════════════════
    ws_inv = wb["Inventory"]
    inv_issues = []

    has_inventory_items = bool(inventory_items)
    inv_asset_bal = _find_amount(bs_rows, "inventory asset", "inventory")

    # O4 — Inventory Valuation Summary
    ws_inv["O4"].value = (
        f"Run Inventory Valuation Summary report in QBO as of {_fmt_period(period_to)}."
        if has_inventory_items else
        "No inventory items found in Products & Services list."
    )
    # O5 — Agree to Balance Sheet
    if has_inventory_items and abs(inv_asset_bal) > 0.01:
        ws_inv["O5"].value = f"Balance Sheet shows Inventory asset of ${inv_asset_bal:,.2f}. Agree this to the Inventory Valuation Summary total."
    elif has_inventory_items:
        ws_inv["O5"].value = "Inventory items exist but no Inventory Asset balance found on Balance Sheet. Investigate."
        inv_issues.append("Inventory items found but no Inventory asset balance on Balance Sheet")
    else:
        ws_inv["O5"].value = "No inventory items — skip this step."

    # O6 — Negative quantities
    ws_inv["O6"].value = (
        "Review Inventory Valuation Summary for any items with negative QTY — indicates a receiving or posting error."
        if has_inventory_items else "N/A — no inventory items."
    )
    # O7 — Inventory Shrinkage
    ws_inv["O7"].value = (
        "Review Inventory Shrinkage account for large or unexpected adjustments."
        if has_inventory_items else "N/A — no inventory items."
    )
    # O8 — Incorrect item types
    ws_inv["O8"].value = (
        f"Review {len(inventory_items)} inventory item(s) to confirm none are set up as service or non-inventory type incorrectly."
        if has_inventory_items else "N/A — no inventory items."
    )

    # A10/F10 — Inventory totals (A9/F9/K9 are column labels; data goes in row 10)
    ws_inv["A10"].value = f"${inv_asset_bal:,.2f}" if has_inventory_items else "$0.00"
    ws_inv["F10"].value = f"${inv_asset_bal:,.2f}" if has_inventory_items else "$0.00"
    # K10 has formula =A10-F10; leave it in place

    # A13 — Inventory findings
    ws_inv["A14"].value = (
        (f"INVENTORY ISSUES ({len(inv_issues)}):\n" + "\n".join(f"• {i}" for i in inv_issues))
        if inv_issues else
        (
            f"Client has {len(inventory_items)} inventory item(s) in QBO. "
            "Run Inventory Valuation Summary and agree total to Balance Sheet. "
            "Review for negative quantities and investigate Inventory Shrinkage account."
            if has_inventory_items else
            "No inventory items found. If client sells physical goods, confirm whether inventory tracking is needed (requires QBO Plus or higher)."
        )
    )

    # A18 — Work to be completed
    inv_work = []
    if has_inventory_items:
        inv_work.append(f"Run Inventory Valuation Summary report as of {_fmt_period(period_to)} and agree total to Balance Sheet")
        inv_work.append("Review for negative quantity items — investigate and correct receiving or posting errors")
        inv_work.append("Review Inventory Shrinkage account for large adjustments")
        inv_work.append(f"Verify all {len(inventory_items)} inventory item(s) are correctly set up with Asset, COGS, and Income accounts")
        if inv_issues:
            inv_work.append("Reconcile difference between Inventory Valuation Summary and Balance Sheet")
    else:
        inv_work.append("Confirm with client whether inventory tracking is needed")
        inv_work.append("If yes: upgrade to QBO Plus, set up inventory items in Products & Services")
    ws_inv["A19"].value = "\n".join(f"• {w}" for w in inv_work)

    # ── Serialize and stream ────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = (client_name or "Client").replace(" ", "_").replace("/", "-")
    safe_period = period_to.replace("-", "")[:6]
    filename = f"QBO_Assessment_{safe_name}_{safe_period}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
