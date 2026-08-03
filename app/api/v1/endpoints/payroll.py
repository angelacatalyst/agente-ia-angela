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
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
import openpyxl

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
        # Pool 1: WELLS FARGO earmarked for 3010 only
        # Pool 2: B3 first → FIRST CITIZEN second → for Fundraising + Community Asset
        "grant_rules": [
            {
                "pool_classes": ["3010"],
                "waterfall": [
                    {"name": "WELLS FARGO", "annual_budget": 83886.94},
                ],
            },
            {
                "pool_classes": ["Fundraising", "Community Asset"],
                "waterfall": [
                    {"name": "B3",           "annual_budget": 12500.00},
                    {"name": "FIRST CITIZEN","annual_budget": 20000.00},
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
        # WELLS FARGO earmarked for 3010; MHFA covers everything else (waterfall)
        "grant_rules": [
            {
                "pool_classes": ["3010"],
                "waterfall": [
                    {"name": "WELLS FARGO", "annual_budget": 14731.92},
                ],
            },
            {
                "pool_classes": [
                    "Fundraising", "Operations", "Community Asset",
                    "ILB", "Smithsonian", "Festival del Platano",
                ],
                "waterfall": [
                    {"name": "MHFA (1)", "annual_budget": 25000.00},
                    {"name": "MHFA (2)", "annual_budget": 30000.00},
                    {"name": "MHFA (3)", "annual_budget": 25000.00},
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
        # ── EMPLOYEE allocation (Jan–Jun, appears in Gusto at $3,333.33/period) ──
        # 6 classes, covered by CITI until exhausted → PENDING
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
                    {"name": "CITI", "annual_budget": 33377.05},
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
        # CITY OF MIAMI covers all up to $56,000 → TRUIST covers the rest
        "grant_rules": [
            {
                "pool_classes": [
                    "SBRC", "La Oficina", "Negocios",
                    "Capital Readiness", "Smithsonian", "Festival del Platano",
                ],
                "waterfall": [
                    {"name": "CITY OF MIAMI", "annual_budget": 56000.00},
                    {"name": "TRUIST",         "annual_budget": 11590.00},
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
        # TRUIST covers all until exhausted → PENDING
        "grant_rules": [
            {
                "pool_classes": [
                    "SBRC", "Negocios", "Capital Readiness",
                    "ILB", "CPA", "Tradicion en Accion",
                ],
                "waterfall": [
                    {"name": "TRUIST", "annual_budget": 33631.42},
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

    for row in rows:
        r0 = str(row[0]).strip() if row[0] else ""
        r1 = str(row[1]).strip() if row[1] else ""

        if r0 == "Payroll period":
            current = {"period": r1.strip(), "payday": None, "employees": []}
        elif r0 == "Pay day" and current is not None:
            current["payday"] = r1.strip()
        elif current is not None and r0 not in (
            "", "Payroll period", "Pay day", "Last Name",
            "Payroll Totals", "Employee Earnings",
        ):
            try:
                gross = float(row[7] or 0)
            except (TypeError, ValueError):
                continue
            if not r0 or gross == 0:
                continue
            current["employees"].append({
                "last":   r0,
                "first":  str(row[1] or "").strip(),
                "dept":   str(row[2] or "").strip(),
                "gross":          gross,
                "employer_taxes": float(row[14] or 0),
                "health_allowance": float(row[17] or 0),
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
