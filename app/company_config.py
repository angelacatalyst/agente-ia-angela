"""
Per-company (QBO realm) configuration.

Allapattah defaults stay in code so existing payroll/bank rec keep working.
Other companies store overrides in `company_profiles` (created on first save).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import CompanyProfile

# Allapattah Collaborative CDC — proven working account search strings.
DEFAULT_PAYROLL_ACCOUNTS: dict[str, str] = {
    "expense_account": "Salaries & Wages",
    "payroll_vendor": "Gusto",
    "bank_account": "Payroll",
    "tax_liability_account": "Payroll Tax",
    "health_liability_account": "2136 Dental/Vision Liability",
    "tax_expense_account": "Payroll Taxes",
    "health_expense_account": "Health Benefits",
    "dental_expense_account": "Dental & Vision Plans",
    "dental_vendor": "The Guardian",
}

# Known-wrong Allapattah mappings (2135 Medical Care is health, not dental).
_DENTAL_LIABILITY_ALIASES = {
    "payroll health",
    "dental/vision liability",
    "2136 dental/vision liability",
}


def empty_profile_payload(realm_id: str, company_name: str | None = None) -> dict[str, Any]:
    return {
        "realm_id": realm_id,
        "company_name": company_name,
        "payroll_accounts": dict(DEFAULT_PAYROLL_ACCOUNTS),
        "allocation_matrix": None,
        "saved": False,
    }


def profile_to_payload(row: CompanyProfile) -> dict[str, Any]:
    saved_accounts = row.payroll_accounts or {}
    return {
        "realm_id": row.realm_id,
        "company_name": row.company_name,
        "payroll_accounts": {**DEFAULT_PAYROLL_ACCOUNTS, **saved_accounts},
        "allocation_matrix": row.allocation_matrix or None,
        "saved": True,
    }


async def load_company_profile(db: AsyncSession, realm_id: str) -> dict[str, Any]:
    row = await db.get(CompanyProfile, realm_id)
    if not row:
        return empty_profile_payload(realm_id)
    return profile_to_payload(row)


def resolve_payroll_accounts(
    incoming: dict[str, str],
    profile: dict[str, Any] | None,
) -> dict[str, str]:
    """
    Merge request query params with the saved company profile.

    Explicit non-default values from the UI win.
    Saved profile wins over hardcoded Allapattah defaults.
    Dental liability never stays on 2135 / Payroll Health / Medical Care.
    """
    saved = (profile or {}).get("payroll_accounts") or {}
    out: dict[str, str] = {}
    for key, default in DEFAULT_PAYROLL_ACCOUNTS.items():
        raw = (incoming.get(key) or "").strip()
        profile_val = (saved.get(key) or "").strip()
        if not raw or raw == default:
            out[key] = profile_val or default
        else:
            out[key] = raw

    health = out.get("health_liability_account", "")
    lowered = health.lower()
    if "2135" in health or "medical care" in lowered or lowered == "payroll health":
        out["health_liability_account"] = (
            saved.get("health_liability_account")
            or DEFAULT_PAYROLL_ACCOUNTS["health_liability_account"]
        )
    elif lowered in _DENTAL_LIABILITY_ALIASES and saved.get("health_liability_account"):
        out["health_liability_account"] = saved["health_liability_account"]

    return out
