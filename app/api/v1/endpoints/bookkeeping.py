"""
Bookkeeping Cleanup Endpoint
Surfaces QBO transactions that need attention:
  - Uncategorized expenses (Uncategorized Expense / Ask My Accountant)
  - Bank fees without proper account/class assignment
  - Expenses missing Class or Customer (grant) on any line
Provides AI-powered categorization suggestions and applies them back to QBO.
"""
from __future__ import annotations

import json
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_qbo_client_for_realm
from app.core.logging import get_logger

router = APIRouter(prefix="/bookkeeping", tags=["bookkeeping"])
logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Known bank fee vendor keywords (case-insensitive match)
# ─────────────────────────────────────────────────────────────────────────────
BANK_FEE_KEYWORDS = {
    "bank fee", "service charge", "monthly fee", "wire fee", "transfer fee",
    "ramp", "stripe fee", "paypal fee", "square fee", "overdraft",
    "maintenance fee", "account fee",
}

BANK_FEE_ACCOUNTS = {
    "bank charges", "bank fees", "bank service", "service charge",
    "6200", "6210",  # common chart of accounts codes for bank fees
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_bank_fee(txn: dict) -> bool:
    """Heuristic: is this transaction likely a bank fee?"""
    vendor = (txn.get("EntityRef", {}).get("name", "") or "").lower()
    memo = (txn.get("PrivateNote", "") or "").lower()
    doc = (txn.get("DocNumber", "") or "").lower()

    for kw in BANK_FEE_KEYWORDS:
        if kw in vendor or kw in memo or kw in doc:
            return True

    # Check if any line account looks like a bank fee account
    for line in txn.get("Line", []):
        detail = line.get("AccountBasedExpenseLineDetail", {})
        acct_name = (detail.get("AccountRef", {}).get("name", "") or "").lower()
        for kw in BANK_FEE_ACCOUNTS:
            if kw in acct_name:
                return True

    return False


def _needs_class(txn: dict) -> bool:
    """True if any expense line is missing a ClassRef."""
    for line in txn.get("Line", []):
        if line.get("DetailType") != "AccountBasedExpenseLineDetail":
            continue
        detail = line.get("AccountBasedExpenseLineDetail", {})
        if not detail.get("ClassRef"):
            return True
    return False


def _needs_customer(txn: dict) -> bool:
    """True if any expense line is missing a CustomerRef (grant)."""
    for line in txn.get("Line", []):
        if line.get("DetailType") != "AccountBasedExpenseLineDetail":
            continue
        detail = line.get("AccountBasedExpenseLineDetail", {})
        if not detail.get("CustomerRef"):
            return True
    return False


def _is_uncategorized(txn: dict) -> bool:
    """True if the payment account or any line account is Uncategorized."""
    UNCATEGORIZED = {"uncategorized expense", "uncategorized asset", "ask my accountant"}
    acct_name = (txn.get("AccountRef", {}).get("name", "") or "").lower()
    if acct_name in UNCATEGORIZED:
        return True
    for line in txn.get("Line", []):
        detail = line.get("AccountBasedExpenseLineDetail", {})
        line_acct = (detail.get("AccountRef", {}).get("name", "") or "").lower()
        if line_acct in UNCATEGORIZED:
            return True
    return False


def _classify_issue(txn: dict) -> list[str]:
    issues = []
    if _is_uncategorized(txn):
        issues.append("uncategorized")
    if _is_bank_fee(txn):
        issues.append("bank_fee")
    if _needs_class(txn):
        issues.append("missing_class")
    if _needs_customer(txn):
        issues.append("missing_grant")
    return issues


def _serialize_txn(txn: dict) -> dict:
    lines_summary = []
    for line in txn.get("Line", []):
        if line.get("DetailType") != "AccountBasedExpenseLineDetail":
            continue
        detail = line.get("AccountBasedExpenseLineDetail", {})
        lines_summary.append({
            "id":          line.get("Id"),
            "amount":      line.get("Amount"),
            "description": line.get("Description", ""),
            "account_id":  detail.get("AccountRef", {}).get("value"),
            "account":     detail.get("AccountRef", {}).get("name"),
            "class_id":    detail.get("ClassRef", {}).get("value"),
            "class":       detail.get("ClassRef", {}).get("name"),
            "customer_id": detail.get("CustomerRef", {}).get("value"),
            "customer":    detail.get("CustomerRef", {}).get("name"),
        })
    return {
        "id":           txn.get("Id"),
        "sync_token":   txn.get("SyncToken"),
        "date":         txn.get("TxnDate"),
        "doc_number":   txn.get("DocNumber"),
        "vendor":       txn.get("EntityRef", {}).get("name"),
        "vendor_id":    txn.get("EntityRef", {}).get("value"),
        "total":        txn.get("TotalAmt"),
        "memo":         txn.get("PrivateNote", ""),
        "payment_account": txn.get("AccountRef", {}).get("name"),
        "lines":        lines_summary,
        "issues":       _classify_issue(txn),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /bookkeeping/review
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/review")
async def get_review_transactions(
    realm_id: str = Query(...),
    start_date: str = Query("2025-01-01"),
    end_date: str = Query("2025-12-31"),
    filter: str = Query(
        "all",
        description="all | uncategorized | bank_fee | missing_class | missing_grant",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return all QBO expenses that need attention in the date range:
    uncategorized, likely bank fees, missing class, or missing grant.
    """
    qbo = await get_qbo_client_for_realm(realm_id, db)
    if not qbo:
        raise HTTPException(401, f"No QBO connection for realm {realm_id}.")

    try:
        all_txns = await qbo.get_purchases_by_date(start_date, end_date)
    except Exception as e:
        raise HTTPException(502, f"Error fetching QBO transactions: {e}")

    # Fetch reference data for dropdowns
    try:
        qbo_accounts    = await qbo.get_chart_of_accounts()
        qbo_classes     = await qbo.get_classes()
        qbo_customers   = await qbo.get_customers()
        qbo_vendors     = await qbo.get_vendors()
    except Exception as e:
        raise HTTPException(502, f"Error fetching QBO reference data: {e}")

    # Filter transactions that have at least one issue
    needs_review = [t for t in all_txns if _classify_issue(t)]

    # Apply secondary filter
    if filter != "all":
        needs_review = [t for t in needs_review if filter in _classify_issue(t)]

    serialized = [_serialize_txn(t) for t in needs_review]

    # Count by issue type
    counts = {
        "total":           len(serialized),
        "uncategorized":   sum(1 for t in serialized if "uncategorized"  in t["issues"]),
        "bank_fee":        sum(1 for t in serialized if "bank_fee"       in t["issues"]),
        "missing_class":   sum(1 for t in serialized if "missing_class"  in t["issues"]),
        "missing_grant":   sum(1 for t in serialized if "missing_grant"  in t["issues"]),
    }

    return {
        "transactions":  serialized,
        "counts":        counts,
        "date_range":    {"from": start_date, "to": end_date},
        "reference": {
            "accounts":  [{"id": a["Id"], "name": a.get("FullyQualifiedName") or a["Name"], "type": a.get("AccountType")} for a in qbo_accounts],
            "classes":   [{"id": c["Id"], "name": c["Name"]} for c in qbo_classes],
            "customers": [{"id": c["Id"], "name": c.get("DisplayName") or c.get("FullyQualifiedName")} for c in qbo_customers],
            "vendors":   [{"id": v["Id"], "name": v.get("DisplayName") or v.get("CompanyName")} for v in qbo_vendors],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /bookkeeping/ai-suggest
# ─────────────────────────────────────────────────────────────────────────────

class AISuggestRequest(BaseModel):
    realm_id: str
    transaction_id: str
    vendor: str | None = None
    memo: str | None = None
    amount: float | None = None
    date: str | None = None
    current_account: str | None = None
    available_accounts: list[dict] = []
    available_classes: list[dict] = []
    available_customers: list[dict] = []


@router.post("/ai-suggest")
async def ai_suggest_categorization(body: AISuggestRequest) -> dict:
    """
    Use Claude to suggest the best account, class, and grant (customer)
    for a transaction based on its vendor, memo, and amount.
    """
    accts_str    = "\n".join(f"  - {a['name']} (id: {a['id']})" for a in body.available_accounts[:60])
    classes_str  = "\n".join(f"  - {c['name']} (id: {c['id']})" for c in body.available_classes)
    customers_str= "\n".join(f"  - {c['name']} (id: {c['id']})" for c in body.available_customers[:40])

    prompt = f"""You are a nonprofit bookkeeper for Allapattah Collaborative CDC.
Analyze this QBO transaction and suggest the best categorization.

Transaction:
  Vendor: {body.vendor or "Unknown"}
  Memo/Description: {body.memo or "(none)"}
  Amount: ${body.amount or 0:.2f}
  Date: {body.date or "unknown"}
  Current Account: {body.current_account or "Uncategorized"}

Available Accounts (QBO Chart of Accounts):
{accts_str}

Available Classes (programs/departments):
{classes_str}

Available Customers/Grants:
{customers_str}

Respond ONLY with a JSON object like this (no other text):
{{
  "account_id": "<qbo account id or null>",
  "account_name": "<account name>",
  "class_id": "<qbo class id or null>",
  "class_name": "<class name or null>",
  "customer_id": "<qbo customer id or null>",
  "customer_name": "<grant/customer name or null>",
  "confidence": "high|medium|low",
  "reasoning": "<1-2 sentence explanation>"
}}

Rules:
- For bank fees/charges → use a Bank Fees or similar expense account, no class/grant needed
- For payroll-related → suggest payroll account
- If you cannot determine class or grant, set those to null
- Pick the closest matching account from the list provided
- confidence: high = obvious match, medium = reasonable guess, low = uncertain"""

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Extract JSON if wrapped in markdown
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestion = json.loads(raw)
    except Exception as e:
        raise HTTPException(500, f"AI suggestion failed: {e}")

    return {
        "transaction_id": body.transaction_id,
        "suggestion": suggestion,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /bookkeeping/categorize
# ─────────────────────────────────────────────────────────────────────────────

class LineUpdate(BaseModel):
    line_id: str
    account_id: str | None = None
    class_id: str | None = None
    customer_id: str | None = None

class CategorizeRequest(BaseModel):
    realm_id: str
    transaction_id: str
    sync_token: str
    line_updates: list[LineUpdate]
    memo: str | None = None


@router.post("/categorize")
async def categorize_transaction(
    body: CategorizeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Apply account/class/customer updates to a QBO Purchase via sparse update.
    Fetches the current transaction, applies the updates, and saves.
    """
    qbo = await get_qbo_client_for_realm(body.realm_id, db)
    if not qbo:
        raise HTTPException(401, f"No QBO connection for realm {body.realm_id}.")

    # Fetch current transaction to get all lines
    try:
        txn_resp = await qbo.get_purchase(body.transaction_id)
        txn = txn_resp.get("Purchase", txn_resp)
    except Exception as e:
        raise HTTPException(502, f"Error fetching transaction: {e}")

    # Build updated lines
    line_update_map = {u.line_id: u for u in body.line_updates}
    updated_lines = []
    for line in txn.get("Line", []):
        lid = str(line.get("Id", ""))
        if lid in line_update_map and line.get("DetailType") == "AccountBasedExpenseLineDetail":
            upd = line_update_map[lid]
            detail = line.get("AccountBasedExpenseLineDetail", {})
            if upd.account_id:
                detail["AccountRef"] = {"value": upd.account_id}
            if upd.class_id:
                detail["ClassRef"] = {"value": upd.class_id}
            elif upd.class_id is None and "class_id" in upd.model_fields_set:
                detail.pop("ClassRef", None)
            if upd.customer_id:
                detail["CustomerRef"] = {"value": upd.customer_id}
            line = {**line, "AccountBasedExpenseLineDetail": detail}
        updated_lines.append(line)

    updates: dict = {"Line": updated_lines}
    if body.memo is not None:
        updates["PrivateNote"] = body.memo

    try:
        result = await qbo.update_purchase(body.transaction_id, body.sync_token, updates)
        updated_txn = result.get("Purchase", {})
        return {
            "success":    True,
            "id":         updated_txn.get("Id"),
            "doc_number": updated_txn.get("DocNumber"),
            "total":      updated_txn.get("TotalAmt"),
            "message":    "Transaction updated successfully in QBO.",
        }
    except Exception as e:
        raise HTTPException(502, f"Error updating transaction in QBO: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /bookkeeping/categorize-batch
# ─────────────────────────────────────────────────────────────────────────────

class BatchItem(BaseModel):
    transaction_id: str
    sync_token: str
    line_updates: list[LineUpdate]
    memo: str | None = None

class BatchCategorizeRequest(BaseModel):
    realm_id: str
    items: list[BatchItem]


@router.post("/categorize-batch")
async def categorize_batch(
    body: BatchCategorizeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply categorizations to multiple transactions at once."""
    qbo = await get_qbo_client_for_realm(body.realm_id, db)
    if not qbo:
        raise HTTPException(401, f"No QBO connection for realm {body.realm_id}.")

    results = []
    errors  = []

    for item in body.items:
        try:
            txn_resp = await qbo.get_purchase(item.transaction_id)
            txn = txn_resp.get("Purchase", txn_resp)

            line_update_map = {u.line_id: u for u in item.line_updates}
            updated_lines = []
            for line in txn.get("Line", []):
                lid = str(line.get("Id", ""))
                if lid in line_update_map and line.get("DetailType") == "AccountBasedExpenseLineDetail":
                    upd = line_update_map[lid]
                    detail = line.get("AccountBasedExpenseLineDetail", {})
                    if upd.account_id:
                        detail["AccountRef"] = {"value": upd.account_id}
                    if upd.class_id:
                        detail["ClassRef"] = {"value": upd.class_id}
                    if upd.customer_id:
                        detail["CustomerRef"] = {"value": upd.customer_id}
                    line = {**line, "AccountBasedExpenseLineDetail": detail}
                updated_lines.append(line)

            updates: dict = {"Line": updated_lines}
            if item.memo is not None:
                updates["PrivateNote"] = item.memo

            result = await qbo.update_purchase(item.transaction_id, item.sync_token, updates)
            results.append({
                "transaction_id": item.transaction_id,
                "success": True,
                "doc_number": result.get("Purchase", {}).get("DocNumber"),
            })
        except Exception as e:
            errors.append({"transaction_id": item.transaction_id, "error": str(e)})

    return {
        "updated": len(results),
        "errors":  len(errors),
        "results": results,
        "error_details": errors,
    }
