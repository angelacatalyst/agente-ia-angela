"""Grant Tagging endpoint — upload Budget Excel, preview and apply grant assignments to QBO.

Workflow:
  GET  /grants/tag/qbo-scan  → scan QBO transactions, return unique accounts/classes/grants (diagnostic)
  POST /grants/tag/preview   → parse Excel + query QBO → return list of changes needed
  POST /grants/tag/apply     → apply confirmed changes (update CustomerRef on QBO expenses)
"""

from __future__ import annotations

import io
import logging
from typing import Any

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_qbo_client_for_realm
from app.core.security import verify_api_key

router = APIRouter(prefix="/grants", tags=["Grant Tagging"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Payroll account detection — skip these when tagging grants
# ---------------------------------------------------------------------------
_PAYROLL_KEYWORDS = {
    "payroll", "salary", "salaries", "wage", "wages",
    "benefits", "401k", "retirement", "fica", "health insurance",
    "workers comp", "workers' comp", "employment tax",
}

def _is_payroll_account(account_name: str) -> bool:
    """Return True if the account looks like a payroll/compensation account."""
    name_lower = account_name.lower()
    return any(kw in name_lower for kw in _PAYROLL_KEYWORDS)


# ---------------------------------------------------------------------------
# Pending Allocations detection
# ---------------------------------------------------------------------------
_PENDING_KEYWORDS = {"pending", "pendiente", "unassigned", "sin asignar"}

def _is_pending_allocation(customer_name: str) -> bool:
    """Return True if the CustomerRef looks like a placeholder (not a real grant)."""
    if not customer_name:
        return True  # no grant assigned at all → also pending
    name_lower = customer_name.lower()
    return any(kw in name_lower for kw in _PENDING_KEYWORDS)


# ---------------------------------------------------------------------------
# Excel parsing helpers
# ---------------------------------------------------------------------------

def _parse_setup_sheet(ws) -> tuple[dict[str, str], dict[str, dict]]:
    """Parse the SETUP sheet.

    Returns:
        programs_map: {program_name_upper → qbo_class_full_name}
        grants_map:   {grant_name → {"qbo_project": str, "funder": str, "total_available": float}}
    """
    programs_map: dict[str, str] = {}
    grants_map: dict[str, dict] = {}

    # Data starts at row 8 (rows 1-7 are title, notes, and headers)
    _PROGRAM_SKIP = {"PROGRAM", "A · PROGRAMS (CLASS IN QBO)"}
    _GRANT_SKIP   = {"GRANT (NAME USED IN THE ALLOCATIONS)", "B · GRANTS AVAILABLE FOR THE FISCAL YEAR (ONE ROW PER QBO PROJECT)"}

    for row in ws.iter_rows(min_row=8, values_only=True):
        if not row:
            continue
        # Programs are in cols A-B (indices 0-1)
        prog_name = row[0]
        prog_class = row[1]
        if (
            isinstance(prog_name, str) and prog_name.strip()
            and isinstance(prog_class, str) and prog_class.strip()
            and prog_name.strip().upper() not in _PROGRAM_SKIP
        ):
            programs_map[prog_name.strip().upper()] = prog_class.strip()

        # Grants are in cols E-J (indices 4-9)
        grant_name = row[4]
        qbo_project = row[5]
        funder = row[6]
        total_avail = row[9]
        if (
            isinstance(grant_name, str) and grant_name.strip()
            and grant_name.strip().upper() not in _GRANT_SKIP
        ):
            grants_map[grant_name.strip()] = {
                "qbo_project": str(qbo_project).strip() if qbo_project else "",
                "funder": str(funder).strip() if funder else "",
                "total_available": float(total_avail) if isinstance(total_avail, (int, float)) else 0.0,
            }

    return programs_map, grants_map


def _parse_budget_sheet(ws, grants_map: dict[str, dict]) -> list[dict]:
    """Parse the BUDGET sheet and return a list of tagging rules.

    Each rule: {
        program, account_num, account_name, line_type, description,
        annual_budget, total_assigned, status,
        grants: [(grant_name, amount), ...],
        is_simple: bool  (True = one grant covers 100%)
    }
    """
    # Row 5 is the header row — find which columns hold grant data
    header_row: list = []
    grant_col_start: int | None = None
    grant_col_names: list[str | None] = []

    for row in ws.iter_rows(min_row=5, max_row=5, values_only=True):
        header_row = list(row)
        # Grant columns start after "Status" (col X = index 23)
        for col_idx in range(24, len(header_row)):
            val = header_row[col_idx]
            if isinstance(val, str) and val.strip():
                if grant_col_start is None:
                    grant_col_start = col_idx
                break

        if grant_col_start is not None:
            for col_idx in range(grant_col_start, len(header_row)):
                val = header_row[col_idx]
                if isinstance(val, str) and val.strip():
                    grant_col_names.append(val.strip())
                elif val is None:
                    grant_col_names.append(None)
                else:
                    grant_col_names.append(str(val).strip() if val else None)

    known_grants = set(grants_map.keys())
    tagging_rules: list[dict] = []

    for row in ws.iter_rows(min_row=6, values_only=True):
        if not row:
            continue

        program = str(row[0]).strip() if row[0] else None
        line_type = str(row[2]).strip() if row[2] else None
        description = str(row[3]).strip() if row[3] else None
        account_name = str(row[4]).strip() if row[4] else None
        account_num = str(row[5]).strip() if row[5] else None
        annual_budget = float(row[19]) if isinstance(row[19], (int, float)) else 0.0
        total_assigned = float(row[21]) if isinstance(row[21], (int, float)) else 0.0
        status = str(row[23]).strip() if row[23] else None

        # Skip group/subtotal rows (no program or no account number)
        if not program or not account_num or annual_budget <= 0:
            continue

        # Read which grants cover this line
        grants_on_line: list[tuple[str, float]] = []
        if grant_col_start is not None:
            for col_offset, grant_name in enumerate(grant_col_names):
                if not grant_name:
                    continue
                col_idx = grant_col_start + col_offset
                if col_idx < len(row):
                    val = row[col_idx]
                    if val and isinstance(val, (int, float)) and float(val) > 0.001:
                        grants_on_line.append((grant_name, float(val)))

        is_simple = len(grants_on_line) == 1

        tagging_rules.append({
            "program": program,
            "account_num": account_num,
            "account_name": account_name,
            "line_type": line_type,
            "description": description,
            "annual_budget": annual_budget,
            "total_assigned": total_assigned,
            "status": status,
            "grants": grants_on_line,
            "is_simple": is_simple,
        })

    return tagging_rules


def _build_rule_index(
    tagging_rules: list[dict],
    programs_map: dict[str, str],
    grants_map: dict[str, dict],
    customer_map: dict[str, dict],
) -> tuple[dict[tuple[str, str], dict], set[tuple[str, str]]]:
    """Build a lookup index: (account_num, program_key) → rule info.

    Also returns `ambiguous_keys` — keys where the same (account, program) has
    multiple different single-grant assignments. Those should be routed to
    needs_selection (multi-grant UI) instead of auto-assigned.

    Returns: (index, ambiguous_keys)
    """
    index: dict[tuple[str, str], dict] = {}
    ambiguous_keys: set[tuple[str, str]] = set()

    for rule in tagging_rules:
        if not rule["is_simple"] or not rule["grants"]:
            continue  # multi-grant lines handled separately

        account_num = rule["account_num"]
        program_key = rule["program"].upper()
        grant_name = rule["grants"][0][0]

        # Resolve QBO project name → customer ID
        grant_info = grants_map.get(grant_name, {})
        qbo_project = grant_info.get("qbo_project", "")
        customer_id, customer_display = _resolve_customer(qbo_project, customer_map)

        key = (account_num, program_key)
        existing = index.get(key)
        if existing is None:
            index[key] = {
                "grant_name": grant_name,
                "customer_id": customer_id,
                "customer_display": customer_display,
                "account_name": rule["account_name"],
                "description": rule["description"],
                "total_assigned": rule["total_assigned"],
            }
        elif existing["grant_name"] != grant_name:
            # Same (account, program) → different grant: ambiguous, route to manual selection
            ambiguous_keys.add(key)
        # else: same grant repeated (accumulate amounts) — keep as-is

    # Remove ambiguous entries from the auto-assign index
    for k in ambiguous_keys:
        index.pop(k, None)

    return index, ambiguous_keys


def _norm_customer_name(s: str) -> str:
    """Normalize a customer name for fuzzy comparison."""
    import re
    # Normalize dashes (en-dash, em-dash → hyphen)
    s = s.replace('–', '-').replace('—', '-').replace('‒', '-')
    # Lower, collapse whitespace
    s = re.sub(r'\s+', ' ', s.lower()).strip()
    return s


def _resolve_customer(qbo_project: str, customer_map: dict) -> tuple[str | None, str | None]:
    """Resolve a QBO project name from the SETUP sheet to (customer_id, display_name).

    Strategy (most to least strict):
    1. Exact match
    2. Normalized match (ignore case/dash variants)
    3. Exact match after stripping dollar amounts in parentheses
    4. Normalized prefix (≥15 chars) — conservative, avoids false positives
    """
    import re

    if not qbo_project:
        return None, None

    # 1. Exact match
    if qbo_project in customer_map:
        c = customer_map[qbo_project]
        return c["Id"], c.get("FullyQualifiedName") or c.get("DisplayName")

    proj_norm = _norm_customer_name(qbo_project)

    # 2. Normalized full match
    for cname, cdata in customer_map.items():
        if _norm_customer_name(cname) == proj_norm:
            return cdata["Id"], cdata.get("FullyQualifiedName") or cdata.get("DisplayName")

    # 3. Strip trailing parenthetical (dollar amounts, years) and try again
    base = re.sub(r'\s*[\(\[].*[\)\]]\s*$', '', qbo_project).strip()
    if base and base != qbo_project:
        base_norm = _norm_customer_name(base)
        for cname, cdata in customer_map.items():
            cname_norm = _norm_customer_name(cname)
            if cname_norm == base_norm or cname_norm.startswith(base_norm + ' ') or cname_norm.startswith(base_norm + ':'):
                return cdata["Id"], cdata.get("FullyQualifiedName") or cdata.get("DisplayName")

    # 4. Conservative prefix match — only if prefix is at least 15 chars and UNIQUE
    prefix = proj_norm[:20] if len(proj_norm) >= 15 else None
    if prefix:
        matches = [(cname, cdata) for cname, cdata in customer_map.items()
                   if _norm_customer_name(cname).startswith(prefix)]
        if len(matches) == 1:  # only match if unambiguous
            cdata = matches[0][1]
            return cdata["Id"], cdata.get("FullyQualifiedName") or cdata.get("DisplayName")

    return None, None


def _build_multi_rule_index(
    tagging_rules: list[dict],
    grants_map: dict[str, dict],
    customer_map: dict[str, dict],
    ambiguous_keys: set[tuple[str, str]] | None = None,
) -> dict[tuple[str, str], dict]:
    """Build lookup index for multi-grant lines.

    Returns: (account_num, program_key) → {
        account_name, description,
        grant_options: [{grant_name, amount_in_budget, customer_id, customer_display}]
    }
    """
    index: dict[tuple[str, str], dict] = {}

    for rule in tagging_rules:
        if not rule["grants"]:
            continue
        # Include both explicitly multi-grant lines AND ambiguous simple-grant keys
        account_num = rule["account_num"]
        program_key = rule["program"].upper()
        key = (account_num, program_key)
        if rule["is_simple"] and (ambiguous_keys is None or key not in ambiguous_keys):
            continue  # truly simple, single-grant → handled by simple index

        grant_options = []
        for grant_name, amount in rule["grants"]:
            grant_info = grants_map.get(grant_name, {})
            qbo_project = grant_info.get("qbo_project", "")
            customer_id, customer_display = _resolve_customer(qbo_project, customer_map)
            grant_options.append({
                "grant_name": grant_name,
                "amount_in_budget": amount,
                "customer_id": customer_id,
                "customer_display": customer_display or qbo_project or grant_name,
            })

        key = (account_num, program_key)
        # Merge options if same key appears more than once
        if key in index:
            # Add any new grant options not already present
            existing_names = {g["grant_name"] for g in index[key]["grant_options"]}
            for opt in grant_options:
                if opt["grant_name"] not in existing_names:
                    index[key]["grant_options"].append(opt)
        else:
            index[key] = {
                "account_name": rule["account_name"],
                "description": rule["description"],
                "grant_options": grant_options,
            }

    return index


def _find_rule(
    account_name_qbo: str,
    class_name_qbo: str,
    rule_index: dict[tuple[str, str], dict],
) -> dict | None:
    """Find the matching rule for a QBO transaction line.

    IMPORTANT: We require BOTH account AND program/class to match.
    The same account number (e.g. 6615 Travel:Taxi) can appear in multiple
    programs with DIFFERENT grants — matching by account alone would assign
    the wrong grant. If the transaction has no class, return None (manual review).
    """
    if not class_name_qbo:
        # Cannot determine program without a class → no auto-match
        return None

    for (acct_num, prog_key), rule_info in rule_index.items():
        if _match_account_num(account_name_qbo, acct_num, rule_info.get("account_name", "")) \
                and _match_program(class_name_qbo, prog_key):
            return rule_info

    return None


def _extract_line_detail(line: dict) -> dict | None:
    """Extract account/class/customer info from a QBO Purchase Line."""
    detail = line.get("AccountBasedExpenseLineDetail")
    if not detail:
        return None

    acct_ref = detail.get("AccountRef", {})
    class_ref = detail.get("ClassRef", {})
    customer_ref = detail.get("CustomerRef", {})

    return {
        "account_id": acct_ref.get("value", ""),
        "account_name": acct_ref.get("name", ""),
        "class_id": class_ref.get("value", ""),
        "class_name": class_ref.get("name", ""),
        "customer_id": customer_ref.get("value", ""),
        "customer_name": customer_ref.get("name", ""),
        "amount": float(line.get("Amount", 0)),
    }


def _match_account_num(account_name: str, account_num: str, account_name_budget: str = "") -> bool:
    """True if the QBO account name matches the budget account.

    Tries multiple strategies:
    1. QBO name starts with account number (e.g. "6020 Office Supplies")
    2. Account numbers are identical
    3. Budget account name is a substring of QBO account name (case-insensitive)
    4. QBO account name is a substring of budget account name
    """
    if not account_name:
        return False

    # Strategy 1 & 2: exact number prefix
    if account_num:
        if account_name.startswith(account_num + " ") or account_name == account_num:
            return True

    # Strategy 3 & 4: name-based fuzzy match
    if account_name_budget:
        a_lower = account_name.lower()
        b_lower = account_name_budget.lower()
        # Remove leading account numbers from budget name for cleaner comparison
        b_clean = b_lower.lstrip("0123456789 ")
        if b_clean and len(b_clean) >= 4:
            if b_clean in a_lower or a_lower in b_lower:
                return True

    return False


def _match_program(class_name: str, program_key: str) -> bool:
    """True if the QBO class name contains the program key.

    Requires class_name to be non-empty — if the transaction has no class,
    we cannot determine which program it belongs to and should NOT auto-match
    (same account number appears in multiple programs with DIFFERENT grants).
    """
    if not class_name or not program_key:
        return False
    # QBO class names are like "Programs:SBRC" or "Programs:Capital Readiness & TA"
    # program_key is the BUDGET sheet program name, e.g. "CAPITAL READINESS & TA"
    # Normalize both: upper, collapse punctuation/spaces
    def _norm(s: str) -> str:
        return s.upper().replace("&", "AND").replace("-", " ").replace("_", " ").replace(":", " ")

    class_norm = _norm(class_name)
    prog_norm = _norm(program_key)

    # Exact substring match after normalization
    if prog_norm in class_norm:
        return True

    # Also try matching each word of the program key (≥4 chars) in the class name
    words = [w for w in prog_norm.split() if len(w) >= 4]
    if words and all(w in class_norm for w in words):
        return True

    return False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/tag/preview", summary="Preview grant tagging changes from Budget Excel")
async def preview_grant_tagging(
    file: UploadFile = File(..., description="Budget Excel file (ACDC format)"),
    realm_id: str = Form(...),
    period_start: str = Form("2026-01-01"),
    period_end: str = Form("2026-12-31"),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Upload the Budget Excel → parse grant rules → query QBO transactions →
    return a preview of which expense lines need their grant (CustomerRef) updated.

    Returns:
      - changes:  list of transactions/lines that need a grant update
      - already_correct: count of lines already tagged correctly
      - no_rule:  count of lines with no matching budget rule
      - multi_grant: list of budget lines with multiple grants (manual review needed)
    """
    content = await file.read()

    # --- Parse Excel ---
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot open Excel file: {exc}") from exc

    if "SETUP" not in wb.sheetnames or "BUDGET" not in wb.sheetnames:
        raise HTTPException(
            status_code=400,
            detail="Excel must contain SETUP and BUDGET sheets."
        )

    programs_map, grants_map = _parse_setup_sheet(wb["SETUP"])
    tagging_rules = _parse_budget_sheet(wb["BUDGET"], grants_map)

    logger.info(
        "Parsed Excel: programs=%d grants=%d rules=%d",
        len(programs_map), len(grants_map), len(tagging_rules)
    )

    # --- QBO: get customers + expenses ---
    client = await get_qbo_client_for_realm(realm_id, db)

    try:
        customers = await client.get_customers()
        customer_map: dict[str, dict] = {}
        for c in customers:
            name = c.get("FullyQualifiedName") or c.get("DisplayName", "")
            if name:
                customer_map[name] = c
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"QBO customer fetch failed: {exc}") from exc

    try:
        purchases = await client.get_all_expenses(start_date=period_start, end_date=period_end)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"QBO expense fetch failed: {exc}") from exc

    # --- Build rule indexes ---
    rule_index, ambiguous_keys = _build_rule_index(tagging_rules, programs_map, grants_map, customer_map)
    multi_rule_index = _build_multi_rule_index(tagging_rules, grants_map, customer_map, ambiguous_keys)

    logger.info(
        "Rule index: simple=%d ambiguous=%d multi=%d",
        len(rule_index), len(ambiguous_keys), len(multi_rule_index),
    )

    # --- Identify multi-grant budget lines (for the summary section) ---
    multi_grant_lines = [
        {
            "program": r["program"],
            "account_num": r["account_num"],
            "description": r["description"],
            "grants": [{"name": g[0], "amount": g[1]} for g in r["grants"]],
            "annual_budget": r["annual_budget"],
        }
        for r in tagging_rules
        if not r["is_simple"] and r["grants"]
    ]

    # --- Match QBO transactions to rules ---
    changes: list[dict] = []
    needs_selection: list[dict] = []  # multi-grant: user must choose which grant to assign
    already_correct: int = 0
    no_rule: int = 0
    no_class: int = 0        # transaction has no class → can't determine program → no auto-match
    skipped_payroll: int = 0
    pending_no_rule: list[dict] = []   # has Pending Allocations but couldn't match a rule

    for purchase in purchases:
        txn_id = purchase.get("Id", "")
        txn_date = purchase.get("TxnDate", "")
        vendor = (purchase.get("EntityRef") or {}).get("name", "")
        sync_token = purchase.get("SyncToken", "")

        for line in purchase.get("Line", []):
            detail = _extract_line_detail(line)
            if not detail:
                continue
            if detail["amount"] <= 0:
                continue

            account_name = detail["account_name"]
            class_name = detail["class_name"]
            current_customer_id = detail["customer_id"]
            current_customer_name = detail["customer_name"]

            # Skip payroll accounts
            if _is_payroll_account(account_name):
                skipped_payroll += 1
                continue

            # Find matching rule
            matched_rule = _find_rule(account_name, class_name, rule_index)

            if not matched_rule:
                # Check multi-grant index — same matching logic
                multi_matched = None
                if class_name:
                    for (acct_num, prog_key), minfo in multi_rule_index.items():
                        if _match_account_num(account_name, acct_num, minfo.get("account_name", "")) \
                                and _match_program(class_name, prog_key):
                            multi_matched = minfo
                            break

                if multi_matched:
                    # Transaction matches a multi-grant line → needs manual selection
                    needs_selection.append({
                        "purchase_id": txn_id,
                        "sync_token": sync_token,
                        "line_id": line.get("Id", ""),
                        "txn_date": txn_date,
                        "vendor": vendor,
                        "account_name": account_name,
                        "class_name": class_name,
                        "amount": detail["amount"],
                        "current_grant": current_customer_name or "(sin grant)",
                        "grant_options": multi_matched["grant_options"],
                    })
                    continue

                if not class_name:
                    no_class += 1
                else:
                    no_rule += 1
                # Even without a rule, flag Pending Allocations for manual attention
                if _is_pending_allocation(current_customer_name):
                    pending_no_rule.append({
                        "purchase_id": txn_id,
                        "txn_date": txn_date,
                        "vendor": vendor,
                        "account_name": account_name,
                        "class_name": class_name or "(sin clase)",
                        "amount": detail["amount"],
                        "current_grant": current_customer_name or "(sin grant)",
                    })
                continue

            expected_customer_id = matched_rule.get("customer_id")
            if not expected_customer_id:
                # Grant found in rules but couldn't resolve to QBO customer
                no_rule += 1
                continue

            if current_customer_id == expected_customer_id:
                already_correct += 1
                continue

            # Needs update
            changes.append({
                "purchase_id": txn_id,
                "sync_token": sync_token,
                "line_id": line.get("Id", ""),
                "txn_date": txn_date,
                "vendor": vendor,
                "account_name": account_name,
                "class_name": class_name,
                "amount": detail["amount"],
                "current_grant": current_customer_name or "(sin grant)",
                "expected_grant": matched_rule["customer_display"] or matched_rule["grant_name"],
                "expected_customer_id": expected_customer_id,
                "grant_name": matched_rule["grant_name"],
                "is_pending_allocation": _is_pending_allocation(current_customer_name),
            })

    logger.info(
        "Preview: changes=%d needs_selection=%d already_correct=%d "
        "no_rule=%d no_class=%d pending_no_rule=%d skipped_payroll=%d",
        len(changes), len(needs_selection), already_correct,
        no_rule, no_class, len(pending_no_rule), skipped_payroll,
    )

    return {
        "summary": {
            "changes_needed": len(changes),
            "needs_selection": len(needs_selection),
            "already_correct": already_correct,
            "no_rule_found": no_rule,
            "no_class_assigned": no_class,
            "pending_no_rule": len(pending_no_rule),
            "skipped_payroll": skipped_payroll,
            "multi_grant_lines": len(multi_grant_lines),
            "grants_in_excel": len(grants_map),
            "rules_parsed": len(tagging_rules),
        },
        "changes": sorted(changes, key=lambda x: (x["txn_date"], x["vendor"])),
        "needs_selection": sorted(needs_selection, key=lambda x: (x["txn_date"], x["vendor"])),
        "pending_no_rule": pending_no_rule[:100],
        "multi_grant_lines": multi_grant_lines,
        "grants_resolved": [
            {
                "grant_name": gname,
                "qbo_project": ginfo["qbo_project"],
                "customer_id": cid,
                "customer_display": cdisplay or ginfo["qbo_project"],
                "total_available": ginfo["total_available"],
            }
            for gname, ginfo in grants_map.items()
            for cid, cdisplay in [_resolve_customer(ginfo["qbo_project"], customer_map)]
            if cid  # only include grants we could resolve to a QBO customer
        ],
    }


@router.get("/tag/qbo-scan", summary="Scan QBO transactions — diagnostic view of accounts, classes and grants")
async def qbo_scan(
    realm_id: str = Query(...),
    period_start: str = Query("2026-01-01"),
    period_end: str = Query("2026-12-31"),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Scan QBO expense transactions for the period and return:
    - unique (account_name, class_name, customer_name) combinations
    - breakdown by grant: how many lines have each CustomerRef
    - how many lines have Pending Allocations or no grant

    Use this endpoint to understand what data is in QBO before running the preview,
    so you can verify that account names and class names match the Excel budget rules.
    """
    client = await get_qbo_client_for_realm(realm_id, db)

    try:
        purchases = await client.get_all_expenses(start_date=period_start, end_date=period_end)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"QBO expense fetch failed: {exc}") from exc

    # Collect unique combinations
    account_classes: dict[str, dict] = {}   # account_name → {count, classes, grants}
    grant_counts: dict[str, int] = {}       # customer_name → count of lines
    pending_lines: list[dict] = []
    total_lines = 0

    for purchase in purchases:
        txn_id = purchase.get("Id", "")
        txn_date = purchase.get("TxnDate", "")
        vendor = (purchase.get("EntityRef") or {}).get("name", "")

        for line in purchase.get("Line", []):
            detail = _extract_line_detail(line)
            if not detail or detail["amount"] <= 0:
                continue
            if _is_payroll_account(detail["account_name"]):
                continue

            total_lines += 1
            acct = detail["account_name"] or "(no account)"
            cls = detail["class_name"] or "(no class)"
            cust = detail["customer_name"] or "(sin grant)"

            # Aggregate by account
            if acct not in account_classes:
                account_classes[acct] = {"count": 0, "classes": set(), "grants": set()}
            account_classes[acct]["count"] += 1
            account_classes[acct]["classes"].add(cls)
            account_classes[acct]["grants"].add(cust)

            # Aggregate grants
            grant_counts[cust] = grant_counts.get(cust, 0) + 1

            # Flag pending
            if _is_pending_allocation(detail["customer_name"]):
                pending_lines.append({
                    "purchase_id": txn_id,
                    "txn_date": txn_date,
                    "vendor": vendor,
                    "account_name": acct,
                    "class_name": cls,
                    "amount": detail["amount"],
                    "current_grant": cust,
                })

    # Sort accounts by count
    accounts_summary = sorted(
        [
            {
                "account_name": acct,
                "line_count": info["count"],
                "classes": sorted(info["classes"]),
                "grants": sorted(info["grants"]),
            }
            for acct, info in account_classes.items()
        ],
        key=lambda x: -x["line_count"],
    )

    return {
        "total_expense_lines": total_lines,
        "pending_allocation_lines": len(pending_lines),
        "grant_breakdown": dict(sorted(grant_counts.items(), key=lambda x: -x[1])),
        "accounts_summary": accounts_summary,
        "pending_lines": pending_lines[:200],
    }


@router.post("/tag/apply", summary="Apply grant tagging changes to QBO")
async def apply_grant_tagging(
    realm_id: str,
    changes: list[dict],
    dry_run: bool = False,
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Apply the grant changes returned by /tag/preview.
    For each Purchase, updates the CustomerRef on matching lines.

    Set dry_run=true to validate without writing to QBO.
    """
    client = await get_qbo_client_for_realm(realm_id, db)

    # Group changes by purchase_id so we update each Purchase once
    purchases_to_update: dict[str, list[dict]] = {}
    for change in changes:
        pid = change["purchase_id"]
        purchases_to_update.setdefault(pid, []).append(change)

    results: list[dict] = []
    errors: list[dict] = []

    for purchase_id, line_changes in purchases_to_update.items():
        try:
            # Fetch the full current Purchase (QBO returns {"Purchase": {...}})
            raw = await client.get_purchase(purchase_id)
            purchase = raw.get("Purchase") or raw  # unwrap if nested
            sync_token = purchase.get("SyncToken", "0")

            # Build a map: line_id → expected_customer_id
            line_update_map: dict[str, dict] = {
                lc["line_id"]: {
                    "customer_id": lc["expected_customer_id"],
                    "grant_name": lc["expected_grant"],
                }
                for lc in line_changes
            }

            # Update matching lines
            updated_count = 0
            for line in purchase.get("Line", []):
                line_id = line.get("Id", "")
                update = line_update_map.get(line_id)
                if not update:
                    continue
                detail = line.get("AccountBasedExpenseLineDetail")
                if detail:
                    detail["CustomerRef"] = {"value": update["customer_id"]}
                    updated_count += 1

            if updated_count == 0:
                errors.append({
                    "purchase_id": purchase_id,
                    "error": "No matching lines found in Purchase to update",
                })
                continue

            if dry_run:
                results.append({
                    "purchase_id": purchase_id,
                    "txn_date": purchase.get("TxnDate"),
                    "lines_updated": updated_count,
                    "status": "dry_run",
                })
                continue

            # POST the updated Purchase back to QBO (full record, not sparse)
            updated = await client.update_purchase(purchase_id, sync_token, purchase, sparse=False)
            results.append({
                "purchase_id": purchase_id,
                "txn_date": purchase.get("TxnDate"),
                "lines_updated": updated_count,
                "status": "updated",
                "new_sync_token": (updated.get("Purchase") or {}).get("SyncToken"),
            })

        except Exception as exc:
            logger.warning("Failed to update purchase %s: %s", purchase_id, exc)
            errors.append({"purchase_id": purchase_id, "error": str(exc)})

    return {
        "applied": len(results),
        "errors": len(errors),
        "dry_run": dry_run,
        "results": results,
        "error_details": errors,
    }
