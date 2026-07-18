"""
Direct QBO data endpoints — returns structured JSON for frontend pages.
No AI processing; raw data from QBOClient queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_qbo_client_for_realm
from app.core.logging import get_logger
from app.core.security import verify_api_key

router = APIRouter(prefix="/qbo/data", tags=["QBO Data"])
logger = get_logger(__name__)


def _require_realm(realm_id: str | None) -> str:
    if not realm_id:
        raise HTTPException(status_code=400, detail="realm_id is required")
    return realm_id


async def _get_client(realm_id: str, db: AsyncSession) -> Any:
    client = await get_qbo_client_for_realm(realm_id, db)
    if not client:
        raise HTTPException(status_code=404, detail=f"No QBO connection found for realm {realm_id}")
    return client


# ── Dashboard (Controller page) ───────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    realm_id: str = Query(..., description="QBO realm/company ID"),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns KPI summary for the Controller dashboard:
    cash position (from Balance Sheet), AR outstanding, AP due, plus open invoices and bills.
    """
    client = await _get_client(realm_id, db)
    errors: list[str] = []

    # Fetch in parallel-ish (sequential is fine since QBO rate limits)
    try:
        balance_sheet = await client.get_balance_sheet()
    except Exception as e:
        logger.warning("Balance sheet fetch failed", error=str(e))
        balance_sheet = {}
        errors.append("balance_sheet")

    try:
        ar_aging = await client.get_ar_aging()
    except Exception as e:
        logger.warning("AR aging fetch failed", error=str(e))
        ar_aging = {}
        errors.append("ar_aging")

    try:
        ap_aging = await client.get_ap_aging()
    except Exception as e:
        logger.warning("AP aging fetch failed", error=str(e))
        ap_aging = {}
        errors.append("ap_aging")

    try:
        open_invoices = await client.get_invoices(unpaid_only=True)
    except Exception as e:
        logger.warning("Invoices fetch failed", error=str(e))
        open_invoices = []
        errors.append("invoices")

    try:
        open_bills = await client.get_bills(unpaid_only=True)
    except Exception as e:
        logger.warning("Bills fetch failed", error=str(e))
        open_bills = []
        errors.append("bills")

    # ── Extract cash from Balance Sheet ──────────────────────────────────────
    cash_total = _extract_bs_value(balance_sheet, ["Bank Accounts", "Cash and cash equivalents", "Cash", "Checking"])

    # ── Extract AR total from AR Aging ────────────────────────────────────────
    ar_total = _extract_aging_total(ar_aging)

    # ── Extract AP total from AP Aging ────────────────────────────────────────
    ap_total = _extract_aging_total(ap_aging)

    # ── Build alerts from open invoices ───────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    alerts: list[dict] = []
    for inv in open_invoices[:10]:
        due_str = inv.get("DueDate") or inv.get("TxnDate", "")
        balance = float(inv.get("Balance", 0) or 0)
        if balance <= 0:
            continue
        try:
            due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
            days_overdue = (today - due_date).days
            if days_overdue > 0:
                doc_num = inv.get("DocNumber") or inv.get("Id", "")
                customer = inv.get("CustomerRef", {}).get("name", "Unknown")
                alerts.append({
                    "level": "high" if days_overdue > 30 else "medium",
                    "text": f"Invoice #{doc_num} from {customer} overdue by {days_overdue} days — ${balance:,.2f}",
                })
        except Exception:
            pass

    # Overdue bills alert
    for bill in open_bills[:5]:
        due_str = bill.get("DueDate") or bill.get("TxnDate", "")
        balance = float(bill.get("Balance", 0) or 0)
        if balance <= 0:
            continue
        try:
            due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
            days_overdue = (today - due_date).days
            if days_overdue > 0:
                vendor = bill.get("VendorRef", {}).get("name", "Unknown vendor")
                alerts.append({
                    "level": "medium",
                    "text": f"Bill from {vendor} overdue by {days_overdue} days — ${balance:,.2f}",
                })
        except Exception:
            pass

    if not alerts:
        alerts = [{"level": "low", "text": "No overdue invoices or bills found"}]

    # ── Build priorities from data ─────────────────────────────────────────────
    priorities: list[str] = []
    if open_invoices:
        high_inv = [i for i in open_invoices if float(i.get("Balance", 0) or 0) > 0]
        if high_inv:
            priorities.append(f"Review {len(high_inv)} open invoice(s) totaling ${sum(float(i.get('Balance', 0) or 0) for i in high_inv):,.0f}")
    if open_bills:
        priorities.append(f"Process {len(open_bills)} unpaid bill(s)")
    if not priorities:
        priorities = ["All accounts current — no urgent action required"]

    return {
        "kpis": [
            {
                "label": "Cash Position",
                "value": f"${cash_total:,.0f}" if cash_total is not None else "—",
                "raw": cash_total,
                "source": "Balance Sheet",
            },
            {
                "label": "AR Outstanding",
                "value": f"${ar_total:,.0f}" if ar_total is not None else "—",
                "raw": ar_total,
                "source": "AR Aging",
            },
            {
                "label": "AP Outstanding",
                "value": f"${ap_total:,.0f}" if ap_total is not None else "—",
                "raw": ap_total,
                "source": "AP Aging",
            },
            {
                "label": "Open Invoices",
                "value": str(len(open_invoices)),
                "raw": len(open_invoices),
                "source": "QBO",
            },
        ],
        "alerts": alerts[:6],
        "priorities": priorities[:6],
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Vendors ──────────────────────────────────────────────────────────────────

@router.get("/vendors")
async def get_vendors(
    realm_id: str = Query(...),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Returns active vendors from QBO."""
    client = await _get_client(realm_id, db)
    try:
        vendors = await client.get_vendors(active=True)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"QBO error: {e}") from e

    rows = []
    for v in vendors:
        balance = v.get("Balance", 0) or 0
        rows.append({
            "id": v.get("Id", ""),
            "name": v.get("DisplayName") or v.get("CompanyName") or v.get("PrintOnCheckName") or "Unknown",
            "email": (v.get("PrimaryEmailAddr") or {}).get("Address", ""),
            "phone": (v.get("PrimaryPhone") or {}).get("FreeFormNumber", ""),
            "balance": float(balance),
            "balance_formatted": f"${float(balance):,.2f}",
            "active": v.get("Active", True),
            "vendor_1099": v.get("Vendor1099", False),
            "currency": (v.get("CurrencyRef") or {}).get("value", "USD"),
        })

    return {"vendors": rows, "total": len(rows), "fetched_at": datetime.now(timezone.utc).isoformat()}


# ── Bills (Payments page) ─────────────────────────────────────────────────────

@router.get("/bills")
async def get_bills(
    realm_id: str = Query(...),
    unpaid_only: bool = Query(True),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Returns bills from QBO, defaulting to unpaid only."""
    client = await _get_client(realm_id, db)
    try:
        bills = await client.get_bills(unpaid_only=unpaid_only)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"QBO error: {e}") from e

    today = datetime.now(timezone.utc).date()
    rows = []
    for b in bills:
        balance = float(b.get("Balance", 0) or 0)
        if unpaid_only and balance <= 0:
            continue
        due_str = b.get("DueDate") or b.get("TxnDate", "")
        status = "pending"
        try:
            due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
            if (today - due_date).days > 0:
                status = "overdue"
        except Exception:
            pass

        rows.append({
            "id": b.get("Id", ""),
            "vendor": (b.get("VendorRef") or {}).get("name", "Unknown"),
            "amount": float(b.get("TotalAmt", 0) or 0),
            "amount_formatted": f"${float(b.get('TotalAmt', 0) or 0):,.2f}",
            "balance": balance,
            "balance_formatted": f"${balance:,.2f}",
            "due_date": due_str[:10] if due_str else "",
            "txn_date": (b.get("TxnDate") or "")[:10],
            "status": status,
            "doc_number": b.get("DocNumber") or b.get("Id", ""),
        })

    return {"bills": rows, "total": len(rows), "fetched_at": datetime.now(timezone.utc).isoformat()}


# ── Transactions (recent purchases/expenses) ──────────────────────────────────

@router.get("/transactions")
async def get_transactions(
    realm_id: str = Query(...),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Returns open invoices and unpaid bills as a combined transaction view."""
    client = await _get_client(realm_id, db)

    invoices: list[dict] = []
    bills: list[dict] = []

    try:
        invoices = await client.get_invoices(unpaid_only=False)
    except Exception as e:
        logger.warning("Invoices fetch failed", error=str(e))

    try:
        bills = await client.get_bills(unpaid_only=False)
    except Exception as e:
        logger.warning("Bills fetch failed", error=str(e))

    rows = []

    for inv in invoices[:50]:
        rows.append({
            "date": (inv.get("TxnDate") or "")[:10],
            "payee": (inv.get("CustomerRef") or {}).get("name", "Unknown"),
            "amount": f"+${float(inv.get('TotalAmt', 0) or 0):,.2f}",
            "type": "Invoice",
            "status": "Open" if float(inv.get("Balance", 0) or 0) > 0 else "Paid",
            "doc_number": inv.get("DocNumber") or inv.get("Id", ""),
        })

    for bill in bills[:50]:
        rows.append({
            "date": (bill.get("TxnDate") or "")[:10],
            "payee": (bill.get("VendorRef") or {}).get("name", "Unknown"),
            "amount": f"-${float(bill.get('TotalAmt', 0) or 0):,.2f}",
            "type": "Bill",
            "status": "Unpaid" if float(bill.get("Balance", 0) or 0) > 0 else "Paid",
            "doc_number": bill.get("DocNumber") or bill.get("Id", ""),
        })

    # Sort by date desc
    rows.sort(key=lambda r: r["date"], reverse=True)

    return {"transactions": rows[:100], "total": len(rows), "fetched_at": datetime.now(timezone.utc).isoformat()}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_bs_value(report: dict, labels: list[str]) -> float | None:
    """
    Walk QBO Balance Sheet report rows looking for any of the given labels.
    Returns the sum value if found, None otherwise.
    """
    try:
        rows = report.get("Rows", {}).get("Row", [])
        total = _walk_rows_for_labels(rows, labels)
        return total
    except Exception:
        return None


def _walk_rows_for_labels(rows: list, labels: list[str]) -> float | None:
    for row in rows:
        # Check header
        header = row.get("Header", {})
        col_data = header.get("ColData", [])
        row_label = col_data[0].get("value", "") if col_data else ""
        if any(lbl.lower() in row_label.lower() for lbl in labels):
            # Try to get summary value
            summary = row.get("Summary", {})
            s_cols = summary.get("ColData", [])
            if len(s_cols) > 1:
                try:
                    return float(s_cols[1].get("value") or 0)
                except Exception:
                    pass

        # Recurse into sub-rows
        sub_rows = row.get("Rows", {}).get("Row", [])
        if sub_rows:
            result = _walk_rows_for_labels(sub_rows, labels)
            if result is not None:
                return result

        # Check ColData directly (leaf row)
        col_data_row = row.get("ColData", [])
        if col_data_row:
            row_label2 = col_data_row[0].get("value", "") if col_data_row else ""
            if any(lbl.lower() in row_label2.lower() for lbl in labels):
                try:
                    return float(col_data_row[1].get("value") or 0)
                except Exception:
                    pass

    return None


def _extract_aging_total(report: dict) -> float | None:
    """Extract total from AR/AP aging report summary."""
    try:
        rows = report.get("Rows", {}).get("Row", [])
        for row in rows:
            summary = row.get("Summary", {})
            col_data = summary.get("ColData", [])
            label = col_data[0].get("value", "") if col_data else ""
            if "total" in label.lower():
                # Last column is grand total
                if len(col_data) > 1:
                    # Sum all numeric columns
                    total = 0.0
                    for col in col_data[1:]:
                        try:
                            total += float(col.get("value") or 0)
                        except Exception:
                            pass
                    return total
        # Fallback: look in Columns summary
        col_data = report.get("Columns", {}).get("Column", [])
        return None
    except Exception:
        return None
