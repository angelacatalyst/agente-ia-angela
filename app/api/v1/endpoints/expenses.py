"""
Expenses Grant Management Endpoint
Lists QBO Purchase (Expense) transactions and allows bulk-updating
the CustomerRef (grant) on their line items.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.dependencies import get_qbo_client_for_realm

router = APIRouter(prefix="/expenses", tags=["expenses"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_grant(purchase: dict) -> str | None:
    """Return the CustomerRef name from the first line that has one, or None."""
    for line in purchase.get("Line", []):
        detail = line.get("AccountBasedExpenseLineDetail", {})
        cref = detail.get("CustomerRef")
        if cref:
            return cref.get("name") or cref.get("value")
    return None


def _extract_grant_id(purchase: dict) -> str | None:
    """Return the CustomerRef value (ID) from the first line that has one, or None."""
    for line in purchase.get("Line", []):
        detail = line.get("AccountBasedExpenseLineDetail", {})
        cref = detail.get("CustomerRef")
        if cref and cref.get("value"):
            return cref["value"]
    return None


def _extract_classes(purchase: dict) -> list[str]:
    """Return unique class names from all lines."""
    classes: list[str] = []
    for line in purchase.get("Line", []):
        detail = line.get("AccountBasedExpenseLineDetail", {})
        cls = detail.get("ClassRef")
        if cls and (name := cls.get("name")):
            if name not in classes:
                classes.append(name)
    return classes


def _serialize_expense(p: dict) -> dict:
    """Flatten a QBO Purchase into a UI-friendly dict."""
    grant = _extract_grant(p)
    grant_id = _extract_grant_id(p)
    return {
        "id":          p["Id"],
        "sync_token":  p.get("SyncToken", "0"),
        "date":        p.get("TxnDate", ""),
        "vendor":      (p.get("EntityRef") or {}).get("name") or "",
        "memo":        p.get("PrivateNote") or p.get("DocNumber") or "",
        "amount":      p.get("TotalAmt", 0),
        "classes":     _extract_classes(p),
        "grant":       grant,
        "grant_id":    grant_id,
        "payment_type": p.get("PaymentType", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /expenses  — list expenses with optional filters
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
async def list_expenses(
    realm_id:      str  = Query(...),
    date_from:     str  = Query(..., description="YYYY-MM-DD"),
    date_to:       str  = Query(..., description="YYYY-MM-DD"),
    no_grant_only: bool = Query(False, description="Return only expenses without a grant assigned"),
) -> dict:
    """
    Return Purchase (Expense) transactions for a date range.
    Optionally filter to only those without a grant (CustomerRef).
    """
    try:
        qbo = await get_qbo_client_for_realm(realm_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        purchases = await qbo.get_all_expenses(start_date=date_from, end_date=date_to)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"QBO error: {e}")

    expenses = [_serialize_expense(p) for p in purchases]

    if no_grant_only:
        expenses = [e for e in expenses if not e["grant"]]

    return {
        "total":    len(expenses),
        "expenses": expenses,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /expenses/customers — list QBO customers (grants) for the dropdown
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/customers")
async def list_customers(realm_id: str = Query(...)) -> dict:
    """Return active QBO Customers (grants) for the grant-picker dropdown."""
    try:
        qbo = await get_qbo_client_for_realm(realm_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        customers = await qbo.get_customers(active=True)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"QBO error: {e}")

    return {
        "customers": [
            {"id": c["Id"], "name": c.get("DisplayName") or c.get("FullyQualifiedName") or c["Id"]}
            for c in customers
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /expenses/bulk-update-grant — assign grant to multiple expenses
# ─────────────────────────────────────────────────────────────────────────────

class GrantUpdate(BaseModel):
    expense_id:  str
    customer_id: str   # QBO Customer Id (the grant)
    customer_name: str = ""


class BulkUpdateRequest(BaseModel):
    realm_id: str
    updates:  list[GrantUpdate]


@router.patch("/bulk-update-grant")
async def bulk_update_grant(body: BulkUpdateRequest) -> dict:
    """
    For each expense in `updates`: fetch the full Purchase from QBO,
    set CustomerRef on every AccountBasedExpenseLineDetail line,
    then re-post it (full update, not sparse, to preserve bank-feed links).
    """
    try:
        qbo = await get_qbo_client_for_realm(body.realm_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    updated: list[dict] = []
    errors:  list[str]  = []

    async def _update_one(upd: GrantUpdate) -> None:
        try:
            # 1. Fetch current purchase
            resp = await qbo.get_purchase(upd.expense_id)
            purchase: dict[str, Any] = resp.get("Purchase", resp)
            sync_token = purchase.get("SyncToken", "0")

            # 2. Update CustomerRef on every AccountBasedExpenseLineDetail line
            for line in purchase.get("Line", []):
                detail = line.get("AccountBasedExpenseLineDetail")
                if detail is not None:
                    detail["CustomerRef"] = {"value": upd.customer_id}

            # 3. Also set at header level (some QBO clients use this)
            purchase["CustomerRef"] = {"value": upd.customer_id}

            # 4. Full update (not sparse) — required for bank-feed transactions
            # Remove read-only fields that QBO rejects on write
            for ro_field in ("MetaData", "LinkedTxn", "TxnSource"):
                purchase.pop(ro_field, None)

            await qbo.update_purchase(upd.expense_id, sync_token, purchase)
            updated.append({
                "id":            upd.expense_id,
                "grant_id":      upd.customer_id,
                "grant_name":    upd.customer_name,
            })
        except Exception as e:
            errors.append(f"Expense {upd.expense_id}: {e}")

    # Run up to 5 updates concurrently
    BATCH = 5
    for i in range(0, len(body.updates), BATCH):
        batch = body.updates[i : i + BATCH]
        await asyncio.gather(*[_update_one(u) for u in batch])

    return {
        "updated": updated,
        "errors":  errors,
        "summary": {
            "total":    len(body.updates),
            "success":  len(updated),
            "failed":   len(errors),
        },
    }
