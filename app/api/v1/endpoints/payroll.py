"""
Payroll Allocation Endpoint
Processes Gusto payroll exports and applies the stored allocation matrix
with WATERFALL grant coverage logic:
  - Each grant covers a pool of classes until its annual budget is exhausted
  - When a grant runs out, the next grant in priority order takes over
  - If all grants for a pool are exhausted → PENDING
  - Some grants are earmarked to specific classes (e.g. WELLS FARGO → 3010 only)
"""
from __future__ import annotations

import io
import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
import openpyxl

from app.core.dependencies import get_db, get_qbo_client_for_realm

router = APIRouter(prefix="/payroll", tags=["payroll"])

# ─────────────────────────────────────────────────────────────────────────────
# Allocation Matrix
#
# grant_rules: list of "pools" — each pool is a group of classes covered by
#   the same waterfall of grants.
#   pool_classes : which classes belong to this pool
#   waterfall    : grants in priority order; each has name + annual_budget.
#                  The first grant covers until exhausted, then the next, etc.
#                  If all exhausted → amount goes to PENDING.
# ─────────────────────────────────────────────────────────────────────────────
ALLOCATION_MATRIX: dict[str, dict] = {
    "Santander": {
        "full_name": "Santander Arguelles",
        "title": "Chief Asset Preservation Officer",
        "gusto_last": "Arguelles",
        "gusto_first": "Santander",
        "classes": {
            "Fundraising":      0.08,
            "3010":             0.72,
            "Community Asset":  0.20,
        },
        # B3 Living Cities 2026 ($12,500) → First Citizen Bank ($20,000) → 3010 Predevelopment Grant
        "grant_rules": [
            {
                "pool_classes": ["Fundraising", "3010", "Community Asset"],
                "waterfall": [
                    {"name": "B3 Living Cities 2026",     "annual_budget": 12500.00},
                    {"name": "First Citizen Bank",         "annual_budget": 20000.00},
                    {"name": "3010 Predevelopment Grant",  "annual_budget": 500000.00},
                ],
            },
        ],
        "dental_vision_employer": 24.37,
    },

    "Mileyka": {
        "full_name": "Mileyka Burgos-Flores",
        "title": "Chief Executive Officer",
        "gusto_last": "Burgos-Flores",
        "gusto_first": "Mileyka",
        "classes": {
            "Fundraising":        0.40,
            "Operations":         0.25,
            "3010":               0.10,
            "Community Asset":    0.05,
            "ILB":                0.10,
            "Smithsonian":        0.05,
            "Festival del Platano": 0.05,
        },
        # 3C MHA 25-26 Q1 ($30k) → 3C MHA 25-26 Q2 ($25k) → MHFA 2026-2027 Q4-26 ($12.5k, after 3C $25k exhausted) → 3010 Predevelopment
        "grant_rules": [
            {
                "pool_classes": [
                    "Fundraising", "Operations", "3010", "Community Asset",
                    "ILB", "Smithsonian", "Festival del Platano",
                ],
                "waterfall": [
                    {"name": "3C MHA 25-26 Q1",          "annual_budget": 30000.00},
                    {"name": "3C MHA 25-26 Q2",          "annual_budget": 25000.00},
                    {"name": "MHFA 2026-2027",            "annual_budget": 12500.00},
                    {"name": "3010 Predevelopment Grant", "annual_budget": 500000.00},
                ],
            },
        ],
        "dental_vision_employer": 24.37,
    },

    "Meysa": {
        "full_name": "Meysa Arguelles",
        "title": "Director of Impact",
        "gusto_last": "Arguelles",
        "gusto_first": "Meysa",
        # ── EMPLOYEE allocation (Jan–Jun) — Citi Community Progress Grant 2024-2026
        "classes": {
            "Operations":   0.10,
            "Fundraising":  0.10,
            "SBRC":         0.30,
            "La Oficina":   0.05,
            "Negocios":     0.20,
            "Bus C":        0.25,
        },
        "grant_rules": [
            {
                "pool_classes": [
                    "Operations", "Fundraising", "SBRC",
                    "La Oficina", "Negocios", "Bus C",
                ],
                "waterfall": [
                    {"name": "Citi Community Progress Grant", "annual_budget": 200000.00},
                ],
            },
        ],
        "dental_vision_employer": 24.37,
        # ── CONTRACTOR allocation (Jul 15–Dec, NOT in Gusto — fixed $4,100/mo) ──
        # Different classes and different % from the employee allocation
        "contractor": {
            "monthly_amount": 4100.00,
            "start_date": "2026-07-15",
            "classes": {
                "SBRC":     0.40,
                "Negocios": 0.20,
                "Bus C":    0.40,
            },
            "grant_rules": [
                {
                    "pool_classes": ["SBRC", "Negocios", "Bus C"],
                    "waterfall": [
                        {"name": "TRUIST", "annual_budget": 24600.00},  # $4,100 × 6 mo
                    ],
                },
            ],
        },
        "note": "Empleada Jan–Jun: CITI (6 clases). Contratista Jul 15–Dic: TRUIST $4,100/mes (SBRC 40%, Negocios 20%, Bus C 40%). El contrato NO aparece en Gusto.",
    },

    "Drelly": {
        "full_name": "Drelly Rios",
        "title": "Program Manager, Small Business Growth",
        "gusto_last": "Rios",
        "gusto_first": "Drelly",
        "classes": {
            "SBRC":               0.10,
            "La Oficina":         0.20,
            "Negocios":           0.10,
            "Capital Readiness":  0.20,
            "Smithsonian":        0.20,
            "Festival del Platano": 0.20,
        },
        # City of Miami District 1 - MFE Funds $200,000 covers all classes
        "grant_rules": [
            {
                "pool_classes": [
                    "SBRC", "La Oficina", "Negocios",
                    "Capital Readiness", "Smithsonian", "Festival del Platano",
                ],
                "waterfall": [
                    {"name": "City of Miami District 1 MFE", "annual_budget": 200000.00},
                ],
            },
        ],
        "dental_vision_employer": 0.00,
    },

    "Maricarmen": {
        "full_name": "Maricarmen Buraschi",
        "title": "Community Navigator",
        "gusto_last": "Buraschi",
        "gusto_first": "Maricarmen",
        "classes": {
            "SBRC":               0.20,
            "Negocios":           0.15,
            "Capital Readiness":  0.20,
            "ILB":                0.10,
            "CPA":                0.15,
            "Tradicion en Accion": 0.20,
        },
        # Truist Foundation $100,000 Q1 2026 covers all classes
        "grant_rules": [
            {
                "pool_classes": [
                    "SBRC", "Negocios", "Capital Readiness",
                    "ILB", "CPA", "Tradicion en Accion",
                ],
                "waterfall": [
                    {"name": "Truist Foundation", "annual_budget": 100000.00},
                ],
            },
        ],
        "dental_vision_employer": 0.00,
    },

    "Fernando": {
        "full_name": "Fernando Ortiz",
        "title": "Climate & Sustainability Program Manager",
        "gusto_last": "Ortiz",
        "gusto_first": "Fernando",
        "classes": {
            "ILB":                0.10,
            "CPA":                0.30,
            "Tradición":          0.30,
            "Smithsonian":        0.15,
            "Festival del Platano": 0.15,
        },
        # JPM CHASE → LATINOS → ROBERT WOOD (waterfall for all classes)
        "grant_rules": [
            {
                "pool_classes": [
                    "ILB", "CPA", "Tradición",
                    "Smithsonian", "Festival del Platano",
                ],
                "waterfall": [
                    {"name": "JPM CHASE",   "annual_budget": 25000.00},
                    {"name": "LATINOS",     "annual_budget": 25000.00},
                    {"name": "ROBERT WOOD", "annual_budget": 5200.00},
                ],
            },
        ],
        "note": "Salary: $4,000/mo Jan-Jun, $5,200/mo Jul-Dec. Not yet in Gusto.",
        "dental_vision_employer": 0.00,
    },
}

# Lookup by (last, first) → matrix key
_GUSTO_LOOKUP: dict[tuple[str, str], str] = {
    (v["gusto_last"].lower(), v["gusto_first"].lower()): k
    for k, v in ALLOCATION_MATRIX.items()
}


# ─────────────────────────────────────────────────────────────────────────────
# Gusto parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_gusto(data: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    periods: list[dict] = []
    current: dict | None = None
    header_map: dict[str, int] = {}

    def _hget(col_name: str, fallback_idx: int, *aliases: str) -> float:
        for name in (col_name, *aliases):
            if name in header_map:
                try:
                    return float(row[header_map[name]] or 0)
                except (TypeError, ValueError):
                    pass
        try:
            return float(row[fallback_idx] or 0)
        except (TypeError, ValueError):
            return 0.0

    for row in rows:
        r0 = str(row[0]).strip() if row[0] else ""
        r1 = str(row[1]).strip() if row[1] else ""

        if r0 == "Payroll period":
            current = {"period": r1.strip(), "payday": None, "employees": []}
            header_map = {}
        elif r0 == "Pay day" and current is not None:
            # openpyxl may return a date/datetime object or a string
            from datetime import datetime as _dt, date as _date
            raw = row[1]
            if isinstance(raw, (_dt, _date)):
                current["payday"] = raw.strftime("%Y-%m-%d")
            else:
                raw_str = str(raw).strip() if raw else ""
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                    try:
                        current["payday"] = _dt.strptime(raw_str, fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        pass
                else:
                    current["payday"] = raw_str
        elif r0 == "Last Name" and current is not None:
            header_map = {str(c).strip(): i for i, c in enumerate(row) if c is not None}
        elif current is not None and r0 not in (
            "", "Payroll period", "Pay day", "Last Name",
            "Payroll Totals", "Employee Earnings",
        ):
            gross = _hget("Gross Earnings", 7)
            if not r0 or gross == 0:
                continue
            current["employees"].append({
                "last":   r0,
                "first":  str(row[1] or "").strip(),
                "dept":   str(row[2] or "").strip(),
                "gross":             gross,
                "employee_taxes":    _hget("Employee Taxes", 9),
                "employer_taxes":    _hget("Employer Taxes", 14),
                "employee_dental":   _hget("Insurance Vision and Dental (Employee Post-Tax Deduction)", 8, "Vision and Dental"),
                "health_allowance":  _hget("None", 17, "Health Allowance", "Medical"),
            })
        elif r0 == "Payroll Totals" and current is not None:
            periods.append(current)
            current = None

    return periods


# ─────────────────────────────────────────────────────────────────────────────
# Waterfall allocation engine
# ─────────────────────────────────────────────────────────────────────────────

def _apply_waterfall(periods: list[dict]) -> tuple[list[dict], dict]:
    """
    Process periods in order, tracking cumulative grant spend.
    Returns enriched periods + final budget_status per employee.
    """
    # Initialize cumulative budget remaining per employee per grant
    budget_remaining: dict[str, dict[str, float]] = {}
    for key, profile in ALLOCATION_MATRIX.items():
        budget_remaining[key] = {}
        for pool in profile.get("grant_rules", []):
            for g in pool["waterfall"]:
                budget_remaining[key][g["name"]] = g["annual_budget"]

    results = []

    for period in periods:
        enriched_emps = []
        period_grant_totals: dict[str, float] = {}
        period_class_totals: dict[str, float] = {}
        unmatched = []

        for emp in period["employees"]:
            key = _GUSTO_LOOKUP.get(
                (emp["last"].lower(), emp["first"].lower())
            )
            if not key:
                unmatched.append(f"{emp['first']} {emp['last']}")
                enriched_emps.append({**emp, "matrix_key": None, "allocation": None})
                continue

            profile = ALLOCATION_MATRIX[key]
            dental = profile.get("dental_vision_employer", 0.0)
            total_cost = emp["gross"] + emp["employer_taxes"] + emp["health_allowance"] + dental

            # ── Step 1: calculate dollar amount per class ──────────────────
            class_amounts: dict[str, float] = {
                cls: round(total_cost * pct, 4)
                for cls, pct in profile["classes"].items()
            }

            # ── Step 2: apply waterfall per pool ──────────────────────────
            # grant_charges[grant_name] = amount charged this period
            grant_charges: dict[str, float] = {}
            pending_amount = 0.0
            # class → which grant covered it (for display)
            class_grant_coverage: dict[str, str] = {}

            for pool in profile.get("grant_rules", []):
                pool_cost = sum(class_amounts.get(c, 0.0) for c in pool["pool_classes"])
                remaining = pool_cost

                for g in pool["waterfall"]:
                    gname = g["name"]
                    available = budget_remaining[key].get(gname, 0.0)
                    if available <= 0 or remaining <= 0:
                        continue
                    used = min(remaining, available)
                    budget_remaining[key][gname] = round(available - used, 4)
                    grant_charges[gname] = round(grant_charges.get(gname, 0.0) + used, 4)
                    remaining = round(remaining - used, 4)
                    if remaining <= 0:
                        break

                if remaining > 0.005:   # more than half a cent → PENDING
                    pending_amount = round(pending_amount + remaining, 4)
                    grant_charges["PENDING"] = round(
                        grant_charges.get("PENDING", 0.0) + remaining, 4
                    )

            # Assign class → grant label for display (proportional to class cost)
            for pool in profile.get("grant_rules", []):
                pool_cost = sum(class_amounts.get(c, 0.0) for c in pool["pool_classes"])
                if pool_cost == 0:
                    for c in pool["pool_classes"]:
                        class_grant_coverage[c] = "—"
                    continue
                # Determine which grant(s) this pool drew from
                pool_grants_used = [
                    g["name"] for g in pool["waterfall"]
                    if grant_charges.get(g["name"], 0) > 0
                ]
                if "PENDING" in grant_charges and pending_amount > 0:
                    pool_grants_used.append("PENDING")
                label = " → ".join(pool_grants_used) if pool_grants_used else "PENDING"
                for c in pool["pool_classes"]:
                    class_grant_coverage[c] = label

            # Build per-class breakdown dict
            class_breakdown: dict[str, dict] = {}
            for cls, amt in class_amounts.items():
                pct = profile["classes"][cls]
                class_breakdown[cls] = {
                    "pct":             pct,
                    "amount":          round(amt, 2),
                    "salary_portion":  round(emp["gross"] * pct, 2),
                    "taxes_portion":   round(emp["employer_taxes"] * pct, 2),
                    "health_portion":  round(emp["health_allowance"] * pct, 2),
                    "dental_portion":  round(dental * pct, 2),
                    "benefits_portion": round((emp["health_allowance"] + dental) * pct, 2),
                    "grant":           class_grant_coverage.get(cls, "—"),
                }
                period_class_totals[cls] = round(
                    period_class_totals.get(cls, 0.0) + amt, 2
                )

            # Round grant charges
            grant_charges = {k: round(v, 2) for k, v in grant_charges.items()}

            # Accumulate period-level grant totals
            for gname, amt in grant_charges.items():
                period_grant_totals[gname] = round(
                    period_grant_totals.get(gname, 0.0) + amt, 2
                )

            # Budget snapshot after this period
            budget_snapshot = {
                gname: round(budget_remaining[key].get(gname, 0.0), 2)
                for pool in profile.get("grant_rules", [])
                for g in pool["waterfall"]
                for gname in [g["name"]]
            }

            enriched_emps.append({
                **emp,
                "matrix_key":            key,
                "title":                 profile["title"],
                "full_name":             profile["full_name"],
                "total_cost":            round(total_cost, 2),
                "dental_vision_employer": dental,
                "allocation": {
                    "classes":       class_breakdown,
                    "grant_charges": grant_charges,
                    "pending":       round(pending_amount, 2),
                },
                "budget_remaining": budget_snapshot,
                "note": profile.get("note"),
            })

        results.append({
            **period,
            "employees":           enriched_emps,
            "period_class_totals": {k: round(v, 2) for k, v in period_class_totals.items()},
            "period_grant_totals": {k: round(v, 2) for k, v in period_grant_totals.items()},
            "period_total_cost":   round(
                sum(e.get("total_cost", 0) for e in enriched_emps), 2
            ),
            "unmatched_employees": unmatched,
        })

    # Final budget status per employee
    budget_status = {
        key: {
            gname: {
                "original": g["annual_budget"],
                "remaining": round(budget_remaining[key].get(gname, 0.0), 2),
                "used": round(g["annual_budget"] - budget_remaining[key].get(gname, 0.0), 2),
                "exhausted": budget_remaining[key].get(gname, 0.0) <= 0,
            }
            for pool in profile.get("grant_rules", [])
            for g in pool["waterfall"]
            for gname in [g["name"]]
        }
        for key, profile in ALLOCATION_MATRIX.items()
    }

    return results, budget_status


# ─────────────────────────────────────────────────────────────────────────────
# Journal Entry builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_journal_entry(period_data: dict) -> dict:
    lines = []
    for emp in period_data["employees"]:
        if not emp.get("allocation"):
            continue
        for cls, data in emp["allocation"]["classes"].items():
            lines.append({
                "type":        "debit",
                "account":     "Salaries & Wages Expense",
                "class":       cls,
                "customer":    data["grant"],
                "employee":    emp.get("full_name", f"{emp['first']} {emp['last']}"),
                "description": f"{period_data['period']} – {emp.get('title', emp['first'])} / {cls}",
                "amount":      data["amount"],
            })

    total = round(sum(l["amount"] for l in lines), 2)
    return {
        "date":        period_data.get("payday", ""),
        "memo":        f"Payroll allocation – {period_data['period']}",
        "total":       total,
        "debit_lines": lines,
        "credit_line": {
            "type":        "credit",
            "account":     "Wages Payable",
            "description": f"Payroll {period_data['period']}",
            "amount":      total,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/matrix")
async def get_matrix() -> dict:
    return {
        "matrix": {
            k: {
                "full_name":   v["full_name"],
                "title":       v["title"],
                "classes":     v["classes"],
                "grant_rules": v["grant_rules"],
                "contractor":  v.get("contractor"),   # None for most employees
                "note":        v.get("note"),
            }
            for k, v in ALLOCATION_MATRIX.items()
        },
        "employee_count": len(ALLOCATION_MATRIX),
    }


@router.post("/process")
async def process_payroll(
    file: UploadFile = File(...),
    period_index: Optional[int] = Query(None),
    include_journal_entry: bool = Query(False),
) -> dict:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "Please upload a .xlsx file from Gusto.")

    data = await file.read()
    try:
        raw_periods = _parse_gusto(data)
    except Exception as e:
        raise HTTPException(422, f"Could not parse Gusto file: {e}")

    if not raw_periods:
        raise HTTPException(422, "No pay periods found in the uploaded file.")

    enriched, budget_status = _apply_waterfall(raw_periods)

    if period_index is not None:
        if period_index < 0 or period_index >= len(enriched):
            raise HTTPException(404, f"Period {period_index} out of range (0–{len(enriched)-1}).")
        result_periods = [enriched[period_index]]
    else:
        result_periods = enriched

    response: dict = {
        "total_periods": len(raw_periods),
        "periods":       result_periods,
        "budget_status": budget_status,
    }

    if include_journal_entry:
        response["journal_entries"] = [
            _build_journal_entry(p) for p in result_periods
        ]

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Class name aliases — short codes used in the matrix → full QBO class names
# ─────────────────────────────────────────────────────────────────────────────

CLASS_NAME_ALIASES: dict[str, str] = {
    "CPA":  "Community Planning Academy",
    "ILB":  "Impact Leadership Bootcamp",
}

# QBO customer name for lines that have no grant assigned yet
PENDING_GRANT_NAME = "Pending Allocations Grant"

# ─────────────────────────────────────────────────────────────────────────────
# QBO Bill helpers — fuzzy name matching + bill line builder
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_name(s: str) -> str:
    """Lowercase, strip accents/punctuation, collapse spaces."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _best_qbo_match(
    target: str,
    items: list[dict],
    name_key: str = "Name",
) -> dict | None:
    """Fuzzy-match *target* against a list of QBO entities."""
    tn = _normalize_name(target)
    if not tn:
        return None
    # 1. exact
    for item in items:
        cn = _normalize_name(item.get(name_key) or "")
        if cn and cn == tn:
            return item
    # 2. one string contains the other — skip empty candidates to avoid
    #    false positives (empty string is always a substring in Python)
    for item in items:
        cn = _normalize_name(item.get(name_key) or "")
        if cn and (cn in tn or tn in cn):
            return item
    # 3. all significant words present in the candidate
    words = [w for w in tn.split() if len(w) > 2]
    if words:
        for item in items:
            cn = _normalize_name(item.get(name_key) or "")
            if cn and all(w in cn for w in words):
                return item
    return None


def _get_expense_lines_for_emp(emp: dict) -> list[dict]:
    """
    Return flat list of {cls, grant, amount} for one employee.
    Splits each class cost proportionally across the grants that covered its pool.
    """
    rows: list[dict] = []
    key = emp.get("matrix_key")
    if not key or not emp.get("allocation"):
        return rows

    profile = ALLOCATION_MATRIX[key]
    class_amounts = {
        cls: data["amount"]
        for cls, data in emp["allocation"]["classes"].items()
    }
    grant_charges = emp["allocation"]["grant_charges"]

    for pool in profile.get("grant_rules", []):
        pool_classes = pool["pool_classes"]
        pool_total = sum(class_amounts.get(c, 0.0) for c in pool_classes)
        if pool_total == 0:
            continue

        pool_grants: list[tuple[str, float]] = []
        for g in pool["waterfall"]:
            amt = grant_charges.get(g["name"], 0.0)
            if amt > 0:
                pool_grants.append((g["name"], amt))

        pool_covered = sum(a for _, a in pool_grants)
        pool_pending = round(pool_total - pool_covered, 4)
        if pool_pending > 0.005:
            pool_grants.append(("PENDING", pool_pending))

        for cls in pool_classes:
            class_amt = class_amounts.get(cls, 0.0)
            if class_amt == 0:
                continue
            ratio = class_amt / pool_total
            for gname, pool_grant_amt in pool_grants:
                line_amt = round(pool_grant_amt * ratio, 2)
                if line_amt > 0:
                    rows.append({"cls": cls, "grant": gname, "amount": line_amt})

    return rows


def _get_allocation_ratios(emp: dict) -> list[dict]:
    """Return [{cls, grant, ratio}] where ratio is fraction of total allocation."""
    raw = _get_expense_lines_for_emp(emp)
    total = sum(r["amount"] for r in raw)
    if not total:
        return []
    return [{"cls": r["cls"], "grant": r["grant"], "ratio": r["amount"] / total} for r in raw]


def _make_allocation_lines(
    ratios: list[dict],
    base_amount: float,
    account_id: str,
    class_map: dict[str, str],
    customer_map: dict[str, str],
    description: str,
    start_id: int = 1,
) -> tuple[list[dict], list[str], int]:
    """Build QBO expense lines from allocation ratios × base_amount."""
    lines: list[dict] = []
    warnings: list[str] = []
    line_id = start_id
    for r in ratios:
        cls = r["cls"]
        gname = r["grant"]
        amt = round(r["ratio"] * base_amount, 2)
        if amt == 0:
            continue
        if gname == "PENDING":
            cid = customer_map.get("PENDING")
            customer_ref = {"value": cid} if cid else None
            if not cid:
                warnings.append(f"PENDING — 'Pending Allocations Grant' not found in QBO, posted without customer.")
        else:
            cid = customer_map.get(gname)
            if not cid:
                warnings.append(f"Grant '{gname}' not found in QBO — line skipped.")
                continue
            customer_ref = {"value": cid}
        class_id = class_map.get(cls)
        detail: dict = {"AccountRef": {"value": account_id}}
        if class_id:
            detail["ClassRef"] = {"value": class_id}
        else:
            warnings.append(f"Class '{cls}' not in QBO — posted without class.")
        if customer_ref:
            detail["CustomerRef"] = customer_ref
        detail["BillableStatus"] = "NotBillable"
        lines.append({
            "Id": str(line_id),
            "DetailType": "AccountBasedExpenseLineDetail",
            "Amount": amt,
            "Description": description,
            "AccountBasedExpenseLineDetail": detail,
        })
        line_id += 1
    return lines, warnings, line_id


def _get_bill_lines(period: dict) -> list[dict]:
    """Kept for compatibility — flat list across all employees."""
    rows: list[dict] = []
    for emp in period["employees"]:
        emp_name = emp.get("full_name", f"{emp['first']} {emp['last']}")
        for row in _get_expense_lines_for_emp(emp):
            rows.append({**row, "employee_name": emp_name, "description": f"{emp_name} / {row['cls']}"})
    return rows


def _build_qbo_expense_payloads(
    period: dict,
    bank_account_id: str,
    vendor_id: str,
    dental_vendor_id: str | None,
    expense_account_id: str,
    tax_expense_account_id: str,
    health_expense_account_id: str,
    dental_expense_account_id: str,
    class_map: dict[str, str],
    customer_map: dict[str, str],
    tax_liability_id: str | None,
    health_liability_id: str | None,
    department_map: dict[str, str] | None = None,  # employee full_name → QBO dept Id
) -> tuple[list[dict], list[str]]:
    """
    Build 4 QBO Purchase (Expense) payloads per employee:
      A) Salary (6110)  — gross by class/grant, minus employee taxes & dental liabilities
      B) Taxes  (6130)  — employer taxes by class/grant, plus clearing employee tax liability
      C) Health (6155)  — health allowance by class/grant
      D) Dental (6152)  — dental employer by class/grant, minus dental liability (nets $0)
    """
    all_payloads: list[dict] = []
    all_warnings: list[str] = []

    for emp in period["employees"]:
        if not emp.get("allocation") or not emp.get("matrix_key"):
            if emp.get("allocation") is None:
                all_warnings.append(
                    f"{emp.get('first', '')} {emp.get('last', '')} not in matrix — skipped."
                )
            continue

        emp_name  = emp.get("full_name", f"{emp['first']} {emp['last']}")
        period_str = period.get("period", "")
        payday    = period.get("payday", "")
        ratios    = _get_allocation_ratios(emp)
        if not ratios:
            all_warnings.append(f"{emp_name}: no allocation ratios — skipped.")
            continue

        gross           = round(emp.get("gross", 0.0), 2)
        employee_taxes  = round(emp.get("employee_taxes", 0.0), 2)
        employer_taxes  = round(emp.get("employer_taxes", 0.0), 2)
        employee_dental = round(emp.get("employee_dental", 0.0), 2)
        health          = round(emp.get("health_allowance", 0.0), 2)
        dental_employer = round(emp.get("dental_vision_employer", 0.0), 2)

        raw_period = re.sub(r"[^A-Za-z0-9\-_]", "-", period_str)
        key_short  = re.sub(r"[^A-Za-z0-9]", "", emp.get("matrix_key", ""))[:6]
        doc_base   = f"PR-{key_short}-{raw_period}"[:18]

        dept_id = (department_map or {}).get(emp_name) or (department_map or {}).get(emp.get("title", ""))

        def _make_payload(
            doc_suffix: str,
            private_note: str,
            lines: list[dict],
            use_vendor_id: str,
        ) -> dict:
            payload: dict = {
                "PaymentType": "Cash",
                "AccountRef":  {"value": bank_account_id},
                "EntityRef":   {"value": use_vendor_id, "type": "Vendor"},
                "TxnDate":     payday,
                "DocNumber":   f"{doc_base}-{doc_suffix}",
                "PrivateNote": private_note,
                "Line": lines,
            }
            if dept_id:
                payload["DepartmentRef"] = {"value": dept_id}
            return payload

        # ── A: SALARY ────────────────────────────────────────────────────────
        if gross > 0:
            sal_lines, sal_warns, next_id = _make_allocation_lines(
                ratios, gross, expense_account_id, class_map, customer_map,
                f"{emp_name} / Payroll {period_str}", start_id=1,
            )
            # Negative: employee taxes withheld → tax liability
            if tax_liability_id and employee_taxes > 0:
                sal_lines.append({
                    "Id": str(next_id),
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": round(-employee_taxes, 2),
                    "Description": f"Employee Taxes Withheld — {emp_name}",
                    "AccountBasedExpenseLineDetail": {"AccountRef": {"value": tax_liability_id}},
                })
                next_id += 1
            # Negative: employee dental deduction → health/dental liability
            if health_liability_id and employee_dental > 0:
                sal_lines.append({
                    "Id": str(next_id),
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": round(-employee_dental, 2),
                    "Description": f"Employee Dental Deduction — {emp_name}",
                    "AccountBasedExpenseLineDetail": {"AccountRef": {"value": health_liability_id}},
                })
            if sal_lines:
                payload = _make_payload("S", f"Salary — {emp_name} — {period_str}", sal_lines, vendor_id)
                all_payloads.append({
                    "employee_name": emp_name, "expense_type": "salary",
                    "matrix_key": emp["matrix_key"], "payload": payload,
                    "warnings": sal_warns, "line_count": len(sal_lines),
                    "total": round(sum(l["Amount"] for l in sal_lines), 2),
                })
                all_warnings.extend(sal_warns)

        # ── B: PAYROLL TAXES ─────────────────────────────────────────────────
        if employer_taxes > 0:
            tax_lines, tax_warns, next_id = _make_allocation_lines(
                ratios, employer_taxes, tax_expense_account_id, class_map, customer_map,
                f"{emp_name} / Payroll Taxes {period_str}", start_id=1,
            )
            # Positive: clear employee tax liability
            if tax_liability_id and employee_taxes > 0:
                tax_lines.append({
                    "Id": str(next_id),
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": round(employee_taxes, 2),
                    "Description": f"Employee Taxes Payable — {emp_name}",
                    "AccountBasedExpenseLineDetail": {"AccountRef": {"value": tax_liability_id}},
                })
            if tax_lines:
                payload = _make_payload("T", f"Payroll Taxes — {emp_name} — {period_str}", tax_lines, vendor_id)
                all_payloads.append({
                    "employee_name": emp_name, "expense_type": "taxes",
                    "matrix_key": emp["matrix_key"], "payload": payload,
                    "warnings": tax_warns, "line_count": len(tax_lines),
                    "total": round(sum(l["Amount"] for l in tax_lines), 2),
                })
                all_warnings.extend(tax_warns)

        # ── C: HEALTH INSURANCE ──────────────────────────────────────────────
        if health > 0:
            hlt_lines, hlt_warns, _ = _make_allocation_lines(
                ratios, health, health_expense_account_id, class_map, customer_map,
                f"{emp_name} / Health Insurance {period_str}", start_id=1,
            )
            if hlt_lines:
                payload = _make_payload("H", f"Health Insurance — {emp_name} — {period_str}", hlt_lines, vendor_id)
                all_payloads.append({
                    "employee_name": emp_name, "expense_type": "health",
                    "matrix_key": emp["matrix_key"], "payload": payload,
                    "warnings": hlt_warns, "line_count": len(hlt_lines),
                    "total": round(sum(l["Amount"] for l in hlt_lines), 2),
                })
                all_warnings.extend(hlt_warns)

        # ── D: DENTAL / VISION ───────────────────────────────────────────────
        if dental_employer > 0:
            dnt_lines, dnt_warns, next_id = _make_allocation_lines(
                ratios, dental_employer, dental_expense_account_id, class_map, customer_map,
                f"{emp_name} / Health Insurance Vision & Dental {period_str}", start_id=1,
            )
            # Negative: employer dental → health/dental liability (nets to $0)
            if health_liability_id and dental_employer > 0:
                dnt_lines.append({
                    "Id": str(next_id),
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "Amount": round(-dental_employer, 2),
                    "Description": f"Dental/Vision Liability — {emp_name}",
                    "AccountBasedExpenseLineDetail": {"AccountRef": {"value": health_liability_id}},
                })
            dnt_vendor = dental_vendor_id or vendor_id
            if dnt_lines:
                payload = _make_payload("D", f"Dental & Vision — {emp_name} — {period_str}", dnt_lines, dnt_vendor)
                all_payloads.append({
                    "employee_name": emp_name, "expense_type": "dental",
                    "matrix_key": emp["matrix_key"], "payload": payload,
                    "warnings": dnt_warns, "line_count": len(dnt_lines),
                    "total": round(sum(l["Amount"] for l in dnt_lines), 2),
                })
                all_warnings.extend(dnt_warns)

    return all_payloads, all_warnings


def _extract_http_status(exc: Exception) -> str:
    """Return HTTP status code as a string from tenacity RetryError or httpx HTTPStatusError."""
    # tenacity wraps the real exception inside last_attempt
    last = getattr(exc, "last_attempt", None)
    if last is not None:
        try:
            last.result()
        except Exception as inner:
            exc = inner
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        return str(exc.response.status_code)
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# POST /payroll/post-to-qbo
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/post-to-qbo")
async def post_payroll_to_qbo(
    file: UploadFile = File(...),
    realm_id: str = Query(..., description="QBO Company realm ID"),
    period_index: int = Query(..., description="0-based index of the pay period to post"),
    expense_account: str = Query(
        "Salaries & Wages",
        description="Expense account name in QBO (e.g. '6110 Personnel Expenses:Salaries & W')",
    ),
    payroll_vendor: str = Query("Gusto", description="Vendor/payee name in QBO"),
    bank_account: str = Query(
        "Payroll",
        description="Payment bank account name in QBO (e.g. '1112 Cash & Cash Equivalents:Payroll')",
    ),
    tax_liability_account: str = Query(
        "Payroll Tax",
        description="Payroll tax liability account (negative line). Leave blank to omit.",
    ),
    health_liability_account: str = Query(
        "Payroll Health",
        description="Health/dental liability account (negative line). Leave blank to omit.",
    ),
    tax_expense_account: str = Query(
        "Payroll Taxes",
        description="Expense account for employer taxes (e.g. '6130 Personnel Expenses:Payroll Taxes')",
    ),
    health_expense_account: str = Query(
        "Health Benefits",
        description="Expense account for health insurance (e.g. '6155')",
    ),
    dental_expense_account: str = Query(
        "Vision and Dental",
        description="Expense account for dental/vision (e.g. '6152')",
    ),
    dental_vendor: str = Query(
        "The Guardian",
        description="Vendor name for dental/vision expenses in QBO",
    ),
    dry_run: bool = Query(True, description="true = preview only; false = create Expenses in QBO"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Post a payroll period's allocations to QBO as **Expenses** (Purchases).

    Creates one Expense per employee, each paid from the payroll bank account.
    Each allocation line carries: Expense Account + Class + Customer (grant).
    Negative lines are added for employer FICA and health/dental liabilities.

    Employee name is included in every line description and in PrivateNote.

    Use dry_run=true (default) first to verify QBO name matching,
    then re-submit with dry_run=false to create the Expenses.
    """
    # ── 1. Parse + allocate ──────────────────────────────────────────────────
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "Please upload a .xlsx file from Gusto.")

    data = await file.read()
    try:
        raw_periods = _parse_gusto(data)
    except Exception as e:
        raise HTTPException(422, f"Could not parse Gusto file: {e}")

    if not raw_periods:
        raise HTTPException(422, "No pay periods found in file.")

    enriched, budget_status = _apply_waterfall(raw_periods)

    if period_index < 0 or period_index >= len(enriched):
        raise HTTPException(
            404, f"period_index {period_index} out of range (0–{len(enriched)-1})."
        )
    period = enriched[period_index]

    # ── 2. Init QBO client ────────────────────────────────────────────────────
    qbo = await get_qbo_client_for_realm(realm_id, db)
    if not qbo:
        raise HTTPException(
            401, f"No QBO connection found for realm {realm_id}. Connect QBO first."
        )

    # ── 3. Fetch QBO reference data ───────────────────────────────────────────
    try:
        qbo_vendors   = await qbo.get_vendors()
    except Exception as e:
        _status = _extract_http_status(e)
        raise HTTPException(502, f"QBO error fetching vendors (HTTP {_status}). Try reconnecting QBO in Settings.")
    try:
        qbo_accounts  = await qbo.get_chart_of_accounts()
        qbo_classes   = await qbo.get_classes()
        qbo_customers = await qbo.get_customers()
        qbo_departments = await qbo.get_departments()
    except Exception as e:
        _status = _extract_http_status(e)
        raise HTTPException(502, f"QBO error fetching reference data (HTTP {_status}): {type(e).__name__}")

    # Bank accounts are included in chart of accounts — no separate call needed
    qbo_banks = [
        a for a in qbo_accounts
        if a.get("AccountType") in ("Bank", "Credit Card")
    ]

    # ── 4. Match names → QBO IDs (also check FullyQualifiedName for sub-customers) ──
    def _match_vendor(name: str) -> dict | None:
        return (
            _best_qbo_match(name, qbo_vendors, "DisplayName")
            or _best_qbo_match(name, qbo_vendors, "CompanyName")
        )

    def _match_account(name: str, pool: list[dict]) -> dict | None:
        return (
            _best_qbo_match(name, pool, "Name")
            or _best_qbo_match(name, pool, "FullyQualifiedName")
        )

    def _match_customer(name: str) -> dict | None:
        return (
            _best_qbo_match(name, qbo_customers, "DisplayName")
            or _best_qbo_match(name, qbo_customers, "FullyQualifiedName")
            or _best_qbo_match(name, qbo_customers, "CompanyName")
        )

    vendor_match   = _match_vendor(payroll_vendor)
    account_match  = _match_account(expense_account, qbo_accounts)
    bank_match     = _match_account(bank_account, qbo_banks) or _match_account(bank_account, qbo_accounts)
    tax_match      = _match_account(tax_liability_account, qbo_accounts) if tax_liability_account.strip() else None
    health_match   = _match_account(health_liability_account, qbo_accounts) if health_liability_account.strip() else None
    tax_exp_match    = _match_account(tax_expense_account, qbo_accounts)
    health_exp_match = _match_account(health_expense_account, qbo_accounts)
    dental_exp_match = _match_account(dental_expense_account, qbo_accounts)
    dental_vendor_match = _match_vendor(dental_vendor) if dental_vendor.strip() else None

    # Collect all classes + grants used in this period
    all_classes: set[str] = set()
    all_grants: set[str] = set()
    has_pending = False
    for emp in period["employees"]:
        for row in _get_expense_lines_for_emp(emp):
            all_classes.add(row["cls"])
            if row["grant"] == "PENDING":
                has_pending = True
            else:
                all_grants.add(row["grant"])

    class_map: dict[str, str] = {}
    customer_map: dict[str, str] = {}

    for cls in sorted(all_classes):
        # Expand short codes (CPA, ILB) to full QBO class names
        qbo_cls_name = CLASS_NAME_ALIASES.get(cls, cls)
        m = (
            _best_qbo_match(qbo_cls_name, qbo_classes, "Name")
            or _best_qbo_match(qbo_cls_name, qbo_classes, "FullyQualifiedName")
            or _best_qbo_match(cls, qbo_classes, "Name")  # fallback to short name
        )
        class_map[cls] = m["Id"] if m else ""

    for g in sorted(all_grants):
        m = _match_customer(g)
        customer_map[g] = m["Id"] if m else ""

    # Always resolve the "Pending Allocations Grant" customer if any PENDING lines exist
    if has_pending:
        m = _match_customer(PENDING_GRANT_NAME)
        customer_map["PENDING"] = m["Id"] if m else ""

    lookups: dict = {
        "vendor": {
            "searched": payroll_vendor, "found": vendor_match is not None,
            "qbo_name": vendor_match.get("DisplayName") if vendor_match else None,
            "qbo_id":   vendor_match.get("Id")          if vendor_match else None,
        },
        "bank_account": {
            "searched": bank_account, "found": bank_match is not None,
            "qbo_name": bank_match.get("Name") if bank_match else None,
            "qbo_id":   bank_match.get("Id")   if bank_match else None,
        },
        "expense_account": {
            "searched": expense_account, "found": account_match is not None,
            "qbo_name": account_match.get("Name") if account_match else None,
            "qbo_id":   account_match.get("Id")   if account_match else None,
        },
        "tax_liability": {
            "searched": tax_liability_account, "found": tax_match is not None,
            "qbo_name": tax_match.get("Name") if tax_match else None,
            "qbo_id":   tax_match.get("Id")   if tax_match else None,
        },
        "health_liability": {
            "searched": health_liability_account, "found": health_match is not None,
            "qbo_name": health_match.get("Name") if health_match else None,
            "qbo_id":   health_match.get("Id")   if health_match else None,
        },
        "tax_expense": {
            "searched": tax_expense_account, "found": tax_exp_match is not None,
            "qbo_name": tax_exp_match.get("Name") if tax_exp_match else None,
            "qbo_id":   tax_exp_match.get("Id")   if tax_exp_match else None,
        },
        "health_expense": {
            "searched": health_expense_account, "found": health_exp_match is not None,
            "qbo_name": health_exp_match.get("Name") if health_exp_match else None,
            "qbo_id":   health_exp_match.get("Id")   if health_exp_match else None,
        },
        "dental_expense": {
            "searched": dental_expense_account, "found": dental_exp_match is not None,
            "qbo_name": dental_exp_match.get("Name") if dental_exp_match else None,
            "qbo_id":   dental_exp_match.get("Id")   if dental_exp_match else None,
        },
        "dental_vendor": {
            "searched": dental_vendor, "found": dental_vendor_match is not None,
            "qbo_name": dental_vendor_match.get("DisplayName") if dental_vendor_match else None,
            "qbo_id":   dental_vendor_match.get("Id")          if dental_vendor_match else None,
        },
        "classes": {
            cls: {
                "found": bool(class_map.get(cls)),
                "qbo_id": class_map.get(cls) or None,
            }
            for cls in sorted(all_classes)
        },
        "customers": {
            **{
                g: {
                    "found": bool(customer_map.get(g)),
                    "qbo_id": customer_map.get(g) or None,
                    "qbo_name": (_match_customer(g) or {}).get("DisplayName"),
                }
                for g in sorted(all_grants)
            },
            **(
                {
                    "PENDING": {
                        "found": bool(customer_map.get("PENDING")),
                        "qbo_id": customer_map.get("PENDING") or None,
                        "qbo_name": PENDING_GRANT_NAME,
                    }
                }
                if has_pending else {}
            ),
        },
    }

    # ── 5. Build per-employee expense payloads ────────────────────────────────
    global_warnings: list[str] = []
    if not vendor_match:
        global_warnings.append(f"Vendor '{payroll_vendor}' not found in QBO.")
    if not bank_match:
        global_warnings.append(f"Bank account '{bank_account}' not found in QBO.")
    if not account_match:
        global_warnings.append(f"Expense account '{expense_account}' not found in QBO.")

    # Build department map: employee title → QBO Department Id
    department_map: dict[str, str] = {}
    for emp in period["employees"]:
        key = emp.get("matrix_key")
        if not key:
            continue
        title = ALLOCATION_MATRIX.get(key, {}).get("title", "")
        full_name = ALLOCATION_MATRIX.get(key, {}).get("full_name", "")
        if title:
            dm = _best_qbo_match(title, qbo_departments, "Name") or _best_qbo_match(title, qbo_departments, "FullyQualifiedName")
            if dm:
                department_map[full_name] = dm["Id"]
                department_map[title] = dm["Id"]

    emp_payloads, payload_warnings = _build_qbo_expense_payloads(
        period,
        bank_account_id=bank_match["Id"] if bank_match else "MISSING",
        vendor_id=vendor_match["Id"] if vendor_match else "MISSING",
        dental_vendor_id=dental_vendor_match["Id"] if dental_vendor_match else None,
        expense_account_id=account_match["Id"] if account_match else "MISSING",
        tax_expense_account_id=tax_exp_match["Id"] if tax_exp_match else "MISSING",
        health_expense_account_id=health_exp_match["Id"] if health_exp_match else "MISSING",
        dental_expense_account_id=dental_exp_match["Id"] if dental_exp_match else "MISSING",
        class_map=class_map,
        customer_map=customer_map,
        tax_liability_id=tax_match["Id"] if tax_match else None,
        health_liability_id=health_match["Id"] if health_match else None,
        department_map=department_map,
    )
    all_warnings = global_warnings + payload_warnings
    ready = vendor_match is not None and bank_match is not None and account_match is not None

    if dry_run:
        return {
            "dry_run":            True,
            "period":             period["period"],
            "payday":             period["payday"],
            "period_total_cost":  period["period_total_cost"],
            "employee_count":     len(emp_payloads),
            "qbo_lookups":        lookups,
            "expenses_preview":   [
                {
                    "employee_name": ep["employee_name"],
                    "line_count":    ep["line_count"],
                    "total":         ep["total"],
                    "doc_number":    ep["payload"].get("DocNumber"),
                    "lines":         ep["payload"]["Line"][:3],   # first 3 lines for preview
                    "total_lines":   ep["line_count"],
                    "warnings":      ep["warnings"],
                }
                for ep in emp_payloads
            ],
            "total_lines":  sum(ep["line_count"] for ep in emp_payloads),
            "grand_total":  round(sum(ep["total"] for ep in emp_payloads), 2),
            "warnings":     all_warnings,
            "ready_to_post": ready and len(emp_payloads) > 0,
        }

    # ── 6. Post one Expense per employee ─────────────────────────────────────
    if not ready:
        raise HTTPException(
            422,
            "Cannot post: vendor, bank account, or expense account not found in QBO. "
            "Run dry_run=true to see which lookups are missing.",
        )
    if not emp_payloads:
        raise HTTPException(422, "No employees with postable lines. Check warnings.")

    created: list[dict] = []
    errors: list[str] = []

    for ep in emp_payloads:
        try:
            result = await qbo.create_purchase(ep["payload"])
            txn = result.get("Purchase", {})
            txn_id = txn.get("Id")
            created.append({
                "employee_name": ep["employee_name"],
                "expense_id":    txn_id,
                "doc_number":    txn.get("DocNumber"),
                "total":         txn.get("TotalAmt"),
                "line_count":    ep["line_count"],
                "qbo_link":      f"https://app.qbo.intuit.com/app/expense?txnId={txn_id}",
                "warnings":      ep["warnings"],
            })
        except Exception as e:
            errors.append(f"{ep['employee_name']}: {e}")

    return {
        "dry_run":       False,
        "period":        period["period"],
        "payday":        period["payday"],
        "expenses_created": created,
        "errors":        errors,
        "total_posted":  round(sum(c["total"] or 0 for c in created), 2),
        "qbo_lookups":   lookups,
        "warnings":      all_warnings,
        "budget_status": budget_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /payroll/void-and-repost
# Voids all payroll Expenses in a date range — both agent-created (PR-* prefix)
# AND manually-entered (vendor = Gusto or The Guardian) — then re-posts them
# from a Gusto file using the current ALLOCATION_MATRIX with correct departments.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/void-and-repost")
async def void_and_repost_historical(
    file: UploadFile = File(...),
    realm_id: str = Query(...),
    date_from: str = Query(..., description="Start date YYYY-MM-DD (e.g. 2025-01-01)"),
    date_to: str = Query(..., description="End date YYYY-MM-DD (e.g. 2025-07-31)"),
    expense_account: str = Query("Salaries & Wages"),
    payroll_vendor: str = Query("Gusto"),
    bank_account: str = Query("Payroll"),
    tax_liability_account: str = Query("Payroll Tax"),
    health_liability_account: str = Query("Payroll Health"),
    tax_expense_account: str = Query("Payroll Taxes"),
    health_expense_account: str = Query("Health Benefits"),
    dental_expense_account: str = Query("Vision and Dental"),
    dental_vendor: str = Query("The Guardian"),
    dry_run: bool = Query(True, description="true = preview only; false = void + repost"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Void all payroll Expenses in the date range — both agent-created (DocNumber
    starts with 'PR-') AND manually-entered (vendor = Gusto or The Guardian) —
    then re-post every pay period in the Gusto file that falls within that range
    using the current ALLOCATION_MATRIX percentages and correct QBO departments.

    Safe workflow:
      1. Run with dry_run=true → review what will be voided and what will be re-posted.
         The response shows each expense tagged as 'agent' or 'manual'.
      2. Run with dry_run=false → void old entries, post corrected ones.
    """
    # ── 1. Parse Gusto file ───────────────────────────────────────────────────
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "Please upload a .xlsx Gusto file.")
    data = await file.read()
    try:
        raw_periods = _parse_gusto(data)
    except Exception as e:
        raise HTTPException(422, f"Could not parse Gusto file: {e}")
    if not raw_periods:
        raise HTTPException(422, "No pay periods found in file.")

    enriched, budget_status = _apply_waterfall(raw_periods)

    # Filter periods that fall within date_from / date_to
    from datetime import date as _date
    def _in_range(payday: str) -> bool:
        try:
            d = _date.fromisoformat(payday)
            return _date.fromisoformat(date_from) <= d <= _date.fromisoformat(date_to)
        except ValueError:
            return False

    periods_in_range = [p for p in enriched if _in_range(p.get("payday", ""))]
    if not periods_in_range:
        raise HTTPException(
            422,
            f"No pay periods in the Gusto file fall within {date_from} – {date_to}. "
            f"Periods found: {[p['period'] for p in enriched]}"
        )

    # ── 2. Init QBO client ────────────────────────────────────────────────────
    qbo = await get_qbo_client_for_realm(realm_id, db)
    if not qbo:
        raise HTTPException(401, f"No QBO connection for realm {realm_id}.")

    # ── 3. Find existing payroll Expenses (agent-created AND manual) ─────────
    try:
        all_purchases = await qbo.get_purchases_by_date(date_from, date_to)
    except Exception as e:
        raise HTTPException(502, f"Error fetching QBO purchases: {e}")

    # Payroll vendors used for both agent-posted and manually-entered entries:
    #   Gusto  → 6110 Salaries & Wages, 6130 Payroll Taxes, 6155 Health Benefits
    #   The Guardian → 6152 Dental & Vision
    _PAYROLL_VENDOR_NAMES = {"gusto", "the guardian"}

    def _is_payroll_expense(p: dict) -> bool:
        # Agent-created: DocNumber starts with "PR-"
        if (p.get("DocNumber") or "").startswith("PR-"):
            return True
        # Manually-entered: vendor is Gusto or The Guardian
        vendor_name = (p.get("EntityRef", {}).get("name", "") or "").lower().strip()
        return vendor_name in _PAYROLL_VENDOR_NAMES

    agent_expenses = [p for p in all_purchases if _is_payroll_expense(p)]

    void_preview = [
        {
            "id":           p["Id"],
            "doc_number":   p.get("DocNumber") or "(manual — no DocNumber)",
            "date":         p.get("TxnDate"),
            "amount":       p.get("TotalAmt"),
            "vendor":       (p.get("EntityRef", {}).get("name", "")),
            "private_note": p.get("PrivateNote", ""),
            "source":       "agent" if (p.get("DocNumber") or "").startswith("PR-") else "manual",
        }
        for p in agent_expenses
    ]

    if dry_run:
        # Build re-post preview (same as post-to-qbo dry_run per period)
        repost_preview = []
        for period in periods_in_range:
            repost_preview.append({
                "period":     period["period"],
                "payday":     period["payday"],
                "employees":  [
                    e.get("full_name", f"{e['first']} {e['last']}")
                    for e in period["employees"] if e.get("allocation")
                ],
                "period_total_cost": period["period_total_cost"],
            })
        manual_count = sum(1 for v in void_preview if v["source"] == "manual")
        agent_count  = sum(1 for v in void_preview if v["source"] == "agent")
        return {
            "dry_run": True,
            "date_range": {"from": date_from, "to": date_to},
            "to_void": {
                "count":        len(agent_expenses),
                "agent_count":  agent_count,
                "manual_count": manual_count,
                "expenses":     void_preview,
            },
            "to_repost": {
                "period_count": len(periods_in_range),
                "periods":      repost_preview,
            },
            "message": (
                f"Will void {len(agent_expenses)} existing payroll expenses "
                f"({agent_count} agent-created with PR-* prefix, "
                f"{manual_count} manually entered via Gusto/The Guardian) "
                f"and re-post {len(periods_in_range)} periods "
                f"with current allocation percentages and correct departments. "
                f"Set dry_run=false to execute."
            ),
        }

    # ── 4. Fetch QBO reference data ───────────────────────────────────────────
    try:
        qbo_vendors     = await qbo.get_vendors()
        qbo_accounts    = await qbo.get_chart_of_accounts()
        qbo_classes     = await qbo.get_classes()
        qbo_customers   = await qbo.get_customers()
        qbo_departments = await qbo.get_departments()
    except Exception as e:
        raise HTTPException(502, f"Error fetching QBO reference data: {e}")

    qbo_banks = [a for a in qbo_accounts if a.get("AccountType") in ("Bank", "Credit Card")]

    def _mv(name: str) -> dict | None:
        return (_best_qbo_match(name, qbo_vendors, "DisplayName")
                or _best_qbo_match(name, qbo_vendors, "CompanyName"))

    def _ma(name: str, pool: list[dict]) -> dict | None:
        return (_best_qbo_match(name, pool, "Name")
                or _best_qbo_match(name, pool, "FullyQualifiedName"))

    def _mc(name: str) -> dict | None:
        return (_best_qbo_match(name, qbo_customers, "DisplayName")
                or _best_qbo_match(name, qbo_customers, "FullyQualifiedName")
                or _best_qbo_match(name, qbo_customers, "CompanyName"))

    vendor_match        = _mv(payroll_vendor)
    account_match       = _ma(expense_account, qbo_accounts)
    bank_match          = _ma(bank_account, qbo_banks) or _ma(bank_account, qbo_accounts)
    tax_match           = _ma(tax_liability_account, qbo_accounts) if tax_liability_account.strip() else None
    health_match        = _ma(health_liability_account, qbo_accounts) if health_liability_account.strip() else None
    tax_exp_match       = _ma(tax_expense_account, qbo_accounts)
    health_exp_match    = _ma(health_expense_account, qbo_accounts)
    dental_exp_match    = _ma(dental_expense_account, qbo_accounts)
    dental_vendor_match = _mv(dental_vendor) if dental_vendor.strip() else None

    if not vendor_match or not bank_match or not account_match:
        missing = []
        if not vendor_match:    missing.append(f"vendor '{payroll_vendor}'")
        if not bank_match:      missing.append(f"bank account '{bank_account}'")
        if not account_match:   missing.append(f"expense account '{expense_account}'")
        raise HTTPException(422, f"QBO lookup failed for: {', '.join(missing)}. Run dry_run=true first.")

    # ── 5. Void existing agent expenses ──────────────────────────────────────
    voided: list[dict] = []
    void_errors: list[str] = []

    for p in agent_expenses:
        try:
            await qbo.void_purchase(p["Id"], p["SyncToken"])
            voided.append({
                "id":         p["Id"],
                "doc_number": p.get("DocNumber"),
                "date":       p.get("TxnDate"),
                "amount":     p.get("TotalAmt"),
            })
        except Exception as e:
            void_errors.append(f"Could not void {p.get('DocNumber')} (id {p['Id']}): {e}")

    # ── 6. Re-post each period with current matrix ────────────────────────────
    all_created: list[dict] = []
    all_post_errors: list[str] = []
    all_warnings: list[str] = []

    for period in periods_in_range:
        # Build class + customer maps for this period
        all_classes_p: set[str] = set()
        all_grants_p: set[str] = set()
        has_pending_p = False
        for emp in period["employees"]:
            for row in _get_expense_lines_for_emp(emp):
                all_classes_p.add(row["cls"])
                if row["grant"] == "PENDING":
                    has_pending_p = True
                else:
                    all_grants_p.add(row["grant"])

        class_map_p: dict[str, str] = {}
        customer_map_p: dict[str, str] = {}
        for cls in all_classes_p:
            qbo_cls_name = CLASS_NAME_ALIASES.get(cls, cls)
            m = (_best_qbo_match(qbo_cls_name, qbo_classes, "Name")
                 or _best_qbo_match(qbo_cls_name, qbo_classes, "FullyQualifiedName")
                 or _best_qbo_match(cls, qbo_classes, "Name"))
            class_map_p[cls] = m["Id"] if m else ""
        for g in all_grants_p:
            m = _mc(g)
            customer_map_p[g] = m["Id"] if m else ""
        if has_pending_p:
            m = _mc(PENDING_GRANT_NAME)
            customer_map_p["PENDING"] = m["Id"] if m else ""

        # Department map
        department_map_p: dict[str, str] = {}
        for emp in period["employees"]:
            key = emp.get("matrix_key")
            if not key:
                continue
            title     = ALLOCATION_MATRIX.get(key, {}).get("title", "")
            full_name = ALLOCATION_MATRIX.get(key, {}).get("full_name", "")
            if title:
                dm = (_best_qbo_match(title, qbo_departments, "Name")
                      or _best_qbo_match(title, qbo_departments, "FullyQualifiedName"))
                if dm:
                    department_map_p[full_name] = dm["Id"]
                    department_map_p[title]      = dm["Id"]

        emp_payloads, payload_warns = _build_qbo_expense_payloads(
            period,
            bank_account_id=bank_match["Id"],
            vendor_id=vendor_match["Id"],
            dental_vendor_id=dental_vendor_match["Id"] if dental_vendor_match else None,
            expense_account_id=account_match["Id"],
            tax_expense_account_id=tax_exp_match["Id"] if tax_exp_match else "MISSING",
            health_expense_account_id=health_exp_match["Id"] if health_exp_match else "MISSING",
            dental_expense_account_id=dental_exp_match["Id"] if dental_exp_match else "MISSING",
            class_map=class_map_p,
            customer_map=customer_map_p,
            tax_liability_id=tax_match["Id"] if tax_match else None,
            health_liability_id=health_match["Id"] if health_match else None,
            department_map=department_map_p,
        )
        all_warnings.extend(payload_warns)

        for ep in emp_payloads:
            try:
                result = await qbo.create_purchase(ep["payload"])
                txn = result.get("Purchase", {})
                txn_id = txn.get("Id")
                all_created.append({
                    "period":        period["period"],
                    "employee_name": ep["employee_name"],
                    "expense_type":  ep["expense_type"],
                    "expense_id":    txn_id,
                    "doc_number":    txn.get("DocNumber"),
                    "total":         txn.get("TotalAmt"),
                    "qbo_link":      f"https://app.qbo.intuit.com/app/expense?txnId={txn_id}",
                })
            except Exception as e:
                all_post_errors.append(
                    f"{period['period']} / {ep['employee_name']} / {ep['expense_type']}: {e}"
                )

    return {
        "dry_run":       False,
        "date_range":    {"from": date_from, "to": date_to},
        "voided": {
            "count":  len(voided),
            "items":  voided,
            "errors": void_errors,
        },
        "reposted": {
            "count":       len(all_created),
            "items":       all_created,
            "errors":      all_post_errors,
            "total_posted": round(sum(c.get("total") or 0 for c in all_created), 2),
        },
        "warnings":      all_warnings,
        "budget_status": budget_status,
        "summary": (
            f"Voided {len(voided)} expenses, re-posted {len(all_created)} "
            f"across {len(periods_in_range)} periods."
        ),
    }
