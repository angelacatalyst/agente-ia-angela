"""Company (QBO realm) settings — payroll COA map, optional allocation matrix."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.company_config import (
    DEFAULT_PAYROLL_ACCOUNTS,
    empty_profile_payload,
    load_company_profile,
    profile_to_payload,
)
from app.core.dependencies import get_db
from app.models.database import CompanyProfile, QBOToken

router = APIRouter(prefix="/company-profiles", tags=["Company Profiles"])


class CompanyProfileUpdate(BaseModel):
    payroll_accounts: dict[str, str] = Field(default_factory=dict)
    allocation_matrix: dict[str, Any] | None = None
    company_name: str | None = None


@router.get("")
async def get_profile(
    realm_id: str = Query(..., description="QBO realm/company ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = await db.get(QBOToken, realm_id)
    payload = await load_company_profile(db, realm_id)
    if token and not payload.get("company_name"):
        payload["company_name"] = token.company_name
    payload["defaults"] = dict(DEFAULT_PAYROLL_ACCOUNTS)
    return payload


@router.put("")
async def upsert_profile(
    body: CompanyProfileUpdate,
    realm_id: str = Query(..., description="QBO realm/company ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not realm_id.strip():
        raise HTTPException(400, "realm_id is required")

    token = await db.get(QBOToken, realm_id)
    row = await db.get(CompanyProfile, realm_id)
    now = datetime.now(timezone.utc)

    accounts = {**DEFAULT_PAYROLL_ACCOUNTS, **(body.payroll_accounts or {})}
    # Never persist the known-wrong Allapattah medical liability as dental
    health = str(accounts.get("health_liability_account") or "")
    if "2135" in health or "medical care" in health.lower() or health.lower() == "payroll health":
        accounts["health_liability_account"] = DEFAULT_PAYROLL_ACCOUNTS["health_liability_account"]

    name = body.company_name or (token.company_name if token else None)

    if row:
        row.payroll_accounts = accounts
        row.company_name = name
        row.updated_at = now
        if body.allocation_matrix is not None:
            row.allocation_matrix = body.allocation_matrix or None
    else:
        row = CompanyProfile(
            realm_id=realm_id,
            company_name=name,
            payroll_accounts=accounts,
            allocation_matrix=body.allocation_matrix or None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)

    await db.flush()
    payload = profile_to_payload(row)
    payload["defaults"] = dict(DEFAULT_PAYROLL_ACCOUNTS)
    return payload


@router.get("/defaults")
async def get_defaults() -> dict:
    return empty_profile_payload("", None) | {"defaults": dict(DEFAULT_PAYROLL_ACCOUNTS)}
