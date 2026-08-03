"""
Payroll Allocation Endpoint
Processes Gusto payroll exports and applies the stored allocation matrix
to produce per-class, per-grant cost breakdowns and QBO journal entry templates.
"""
from __future__ import annotations

import io
import json
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
import openpyxl

router = APIRouter(prefix="/payroll", tags=["payroll"])

# ─────────────────────────────────────────────────────────────────────────────
# Allocation Matrix (stored here; editable via PUT /payroll/matrix in v2)
# Derived from the Payroll Allocation Matrix.xlsx uploaded by Angela
# Format: first_name_key → { classes: {name: pct}, grants: [name, ...] }
# ─────────────────────────────────────────────────────────────────────────────
ALLOCATION_MATRIX: dict[str, dict] = {
    "Santander": {
        "full_name": "Santander Arguelles",
        "title": "Chief Asset Preservation Officer",
        "gusto_last": "Arguelles",
        "gusto_first": "Santander",
        "classes": {
            "Fundraising": 0.08,
            "3010": 0.72,
            "Community Asset": 0.20,
        },
        "grants": [
            {"name": "B3", "annual_budget": 12500.00, "classes": ["Fundraising"]},
            {"name": "FIRST CITIZEN", "annual_budget": 20000.00, "classes": ["Community Asset"]},
            {"name": "WELLS FARGO", "annual_budget": 83886.94, "classes": ["3010"]},
        ],
        "dental_vision_employer": 24.37,
    },
    "Mileyka": {
        "full_name": "Mileyka Burgos-Flores",
        "title": "Chief Executive Officer",
        "gusto_last": "Burgos-Flores",
        "gusto_first": "Mileyka",
        "classes": {
            "Fundraising": 0.40,
            "Operations": 0.25,
            "3010": 0.10,
            "Community Asset": 0.05,
            "ILB": 0.10,
            "Smithsonian": 0.05,
            "Festival del Platano": 0.05,
        },
        "grants": [
            {"name": "MHFA", "annual_budget": 80000.00, "classes": ["Fundraising", "Operations", "Community Asset", "ILB", "Smithsonian", "Festival del Platano"]},
            {"name": "WELLS FARGO", "annual_budget": 14731.92, "classes": ["3010"]},
        ],
        "dental_vision_employer": 24.37,
    },
    "Meysa": {
        "full_name": "Meysa Arguelles",
        "title": "Director of Impact",
        "gusto_last": "Arguelles",
        "gusto_first": "Meysa",
        "classes": {
            "Operations": 0.10,
            "Fundraising": 0.10,
            "SBRC": 0.30,
            "La Oficina": 0.05,
            "Negocios": 0.20,
            "Bus C": 0.25,
        },
        "grants": [
            {"name": "CITI", "annual_budget": 33377.05, "classes": ["Operations", "Fundraising", "SBRC", "La Oficina", "Negocios", "Bus C"]},
        ],
        "note": "CITI grant only through May. Becomes contractor from July 15 at $4,100/mo.",
        "dental_vision_employer": 24.37,
    },
    "Drelly": {
        "full_name": "Drelly Rios",
        "title": "Program Manager, Small Business Growth",
        "gusto_last": "Rios",
        "gusto_first": "Drelly",
        "classes": {
            "SBRC": 0.10,
            "La Oficina": 0.20,
            "Negocios": 0.10,
            "Capital Readiness": 0.20,
            "Smithsonian": 0.20,
            "Festival del Platano": 0.20,
        },
        "grants": [
            {"name": "CITY OF MIAMI", "annual_budget": 56000.00, "classes": ["SBRC", "La Oficina", "Negocios", "Capital Readiness"]},
            {"name": "TRUIST", "annual_budget": 11590.00, "classes": ["Smithsonian", "Festival del Platano"]},
        ],
        "dental_vision_employer": 0.00,
    },
    "Maricarmen": {
        "full_name": "Maricarmen Buraschi",
        "title": "Community Navigator",
        "gusto_last": "Buraschi",
        "gusto_first": "Maricarmen",
        "classes": {
            "SBRC": 0.20,
            "Negocios": 0.15,
            "Capital Readiness": 0.20,
            "ILB": 0.10,
            "CPA": 0.15,
            "Tradicion en Accion": 0.20,
        },
        "grants": [
            {"name": "TRUIST", "annual_budget": 33631.42, "classes": ["SBRC", "Negocios", "Capital Readiness", "ILB", "CPA", "Tradicion en Accion"]},
        ],
        "dental_vision_employer": 0.00,
    },
    "Fernando": {
        "full_name": "Fernando Ortiz",
        "title": "Climate & Sustainability Program Manager",
        "gusto_last": "Ortiz",
        "gusto_first": "Fernando",
        "classes": {
            "ILB": 0.10,
            "CPA": 0.30,
            "Tradición": 0.30,
            "Smithsonian": 0.15,
            "Festival del Platano": 0.15,
        },
        "grants": [
            {"name": "JPM CHASE", "annual_budget": 25000.00, "classes": ["ILB"]},
            {"name": "LATINOS", "annual_budget": 25000.00, "classes": ["CPA", "Tradición"]},
            {"name": "ROBERT WOOD", "annual_budget": 5200.00, "classes": ["Smithsonian", "Festival del Platano"]},
        ],
        "note": "Salary: $4,000/mo Jan-Jun, $5,200/mo Jul-Dec. Not in Gusto file yet.",
        "dental_vision_employer": 0.00,
    },
}

# Build a lookup by (last_name, first_name) → matrix key
_GUSTO_LOOKUP: dict[tuple[str, str], str] = {
    (v["gusto_last"].lower(), v["gusto_first"].lower()): k
    for k, v in ALLOCATION_MATRIX.items()
}


# ─────────────────────────────────────────────────────────────────────────────
# Gusto parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_gusto(data: bytes) -> list[dict]:
    """Return a list of pay periods, each with employee-level cost data."""
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

            emp_taxes = float(row[14] or 0)
            health = float(row[17] or 0)

            current["employees"].append({
                "last": r0,
                "first": str(row[1] or "").strip(),
                "department": str(row[2] or "").strip(),
                "gross": gross,
                "employer_taxes": emp_taxes,
                "health_allowance": health,
                "total_employer_cost": gross + emp_taxes + health,
            })

        elif r0 == "Payroll Totals" and current is not None:
            periods.append(current)
            current = None

    return periods


def _apply_allocation(periods: list[dict]) -> list[dict]:
    """Enrich each employee record with class-level allocations."""
    results = []

    for period in periods:
        enriched_employees = []
        period_class_totals: dict[str, float] = {}
        period_grant_totals: dict[str, float] = {}
        unmatched = []

        for emp in period["employees"]:
            key = (emp["last"].lower(), emp["first"].lower())
            matrix_key = _GUSTO_LOOKUP.get(key)

            if not matrix_key:
                unmatched.append(f"{emp['first']} {emp['last']}")
                enriched_employees.append({**emp, "allocation": None, "matrix_key": None})
                continue

            profile = ALLOCATION_MATRIX[matrix_key]
            total_cost = emp["total_employer_cost"]
            dental = profile.get("dental_vision_employer", 0)
            total_with_dental = total_cost + dental

            class_breakdown = {}
            for cls_name, pct in profile["classes"].items():
                amount = round(total_with_dental * pct, 2)
                class_breakdown[cls_name] = {
                    "pct": pct,
                    "amount": amount,
                    "salary_portion": round(emp["gross"] * pct, 2),
                    "taxes_portion": round(emp["employer_taxes"] * pct, 2),
                    "benefits_portion": round((emp["health_allowance"] + dental) * pct, 2),
                }
                period_class_totals[cls_name] = period_class_totals.get(cls_name, 0) + amount

            # Grant totals: sum class amounts that belong to each grant
            grant_breakdown = {}
            for grant in profile["grants"]:
                grant_amount = sum(
                    class_breakdown[c]["amount"]
                    for c in grant["classes"]
                    if c in class_breakdown
                )
                grant_breakdown[grant["name"]] = {
                    "amount": round(grant_amount, 2),
                    "annual_budget": grant.get("annual_budget"),
                    "classes": grant["classes"],
                }
                period_grant_totals[grant["name"]] = (
                    period_grant_totals.get(grant["name"], 0) + grant_amount
                )

            enriched_employees.append({
                **emp,
                "matrix_key": matrix_key,
                "title": profile["title"],
                "total_with_dental": round(total_with_dental, 2),
                "dental_vision_employer": dental,
                "allocation": {
                    "classes": class_breakdown,
                    "grants": grant_breakdown,
                },
                "note": profile.get("note"),
            })

        # Round period totals
        period_class_totals = {k: round(v, 2) for k, v in period_class_totals.items()}
        period_grant_totals = {k: round(v, 2) for k, v in period_grant_totals.items()}

        results.append({
            **period,
            "employees": enriched_employees,
            "period_class_totals": period_class_totals,
            "period_grant_totals": period_grant_totals,
            "period_total_cost": round(sum(
                e["total_employer_cost"] for e in period["employees"]
            ), 2),
            "unmatched_employees": unmatched,
        })

    return results


def _build_journal_entry(period_data: dict) -> dict:
    """Build a QBO-style journal entry for a pay period."""
    lines = []
    period_label = period_data["period"]
    payday = period_data.get("payday", "")

    for emp in period_data["employees"]:
        if not emp.get("allocation"):
            continue

        for cls_name, cls_data in emp["allocation"]["classes"].items():
            # Find which grant covers this class
            covering_grant = "Unallocated"
            for grant in ALLOCATION_MATRIX[emp["matrix_key"]]["grants"]:
                if cls_name in grant["classes"]:
                    covering_grant = grant["name"]
                    break

            lines.append({
                "type": "debit",
                "account": "Salaries & Wages Expense",
                "class": cls_name,
                "customer": covering_grant,
                "employee": emp["full_name"] if "full_name" in emp else f"{emp['first']} {emp['last']}",
                "description": f"Payroll {period_label} – {emp.get('title', emp['first'])} / {cls_name}",
                "amount": cls_data["amount"],
            })

    total_debit = round(sum(l["amount"] for l in lines), 2)

    return {
        "date": payday,
        "memo": f"Payroll allocation – {period_label}",
        "total": total_debit,
        "debit_lines": lines,
        "credit_line": {
            "type": "credit",
            "account": "Wages Payable",
            "description": f"Payroll {period_label}",
            "amount": total_debit,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/matrix")
async def get_matrix() -> dict:
    """Return the stored allocation matrix."""
    return {
        "matrix": {
            k: {
                "full_name": v["full_name"],
                "title": v["title"],
                "classes": v["classes"],
                "grants": v["grants"],
                "note": v.get("note"),
            }
            for k, v in ALLOCATION_MATRIX.items()
        },
        "employee_count": len(ALLOCATION_MATRIX),
    }


@router.post("/process")
async def process_payroll(
    file: UploadFile = File(...),
    period_index: Optional[int] = Query(None, description="0-based index of period to return (None = all)"),
    include_journal_entry: bool = Query(False),
) -> dict:
    """
    Upload a Gusto payroll Excel export.
    Returns all pay periods with class/grant allocation breakdown.
    """
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "Please upload a .xlsx file from Gusto.")

    data = await file.read()

    try:
        periods = _parse_gusto(data)
    except Exception as e:
        raise HTTPException(422, f"Could not parse Gusto file: {e}")

    if not periods:
        raise HTTPException(422, "No pay periods found in the uploaded file.")

    enriched = _apply_allocation(periods)

    # Filter to a single period if requested
    if period_index is not None:
        if period_index < 0 or period_index >= len(enriched):
            raise HTTPException(404, f"Period index {period_index} out of range (0–{len(enriched)-1}).")
        result_periods = [enriched[period_index]]
    else:
        result_periods = enriched

    response: dict = {
        "total_periods": len(periods),
        "periods": result_periods,
    }

    if include_journal_entry and result_periods:
        response["journal_entries"] = [
            _build_journal_entry(p) for p in result_periods
        ]

    return response
