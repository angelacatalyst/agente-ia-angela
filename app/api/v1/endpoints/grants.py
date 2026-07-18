"""Grant Compliance REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.grant_compliance import GrantComplianceAgent
from app.core.security import verify_api_key
from app.models.schemas import GrantComplianceRequest, GrantComplianceResponse

router = APIRouter(prefix="/grants", tags=["Grant Compliance"])


@router.post("/audit", summary="Audit grant compliance for one or more grants")
async def audit_grants(
    request: GrantComplianceRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Perform a grant compliance audit:
    - Budget vs actual by grant
    - Allowable / unallowable costs
    - Payroll allocation check
    - Grant period compliance
    - Documentation review
    """
    agent = GrantComplianceAgent()
    try:
        return await agent.audit_all_grants(
            realm_id=request.realm_id,
            grant_names=request.grant_names,
            period_start=request.period_start,
            period_end=request.period_end,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/audit/single", summary="Audit a single grant in detail")
async def audit_single_grant(
    realm_id: str,
    grant_name: str,
    period_start: str,
    period_end: str,
    _: str = Depends(verify_api_key),
) -> dict:
    """Deep-dive compliance audit for a single grant."""
    agent = GrantComplianceAgent()
    try:
        return await agent.audit_grant(
            realm_id=realm_id,
            grant_name=grant_name,
            period_start=period_start,
            period_end=period_end,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
