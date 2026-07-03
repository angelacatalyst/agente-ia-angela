"""QBO Auditor REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.qbo_auditor import QBOAuditorAgent
from app.core.security import verify_api_key
from app.models.schemas import AuditReportRequest, AuditReportResponse

router = APIRouter(prefix="/audit", tags=["QBO Auditor"])


@router.post("/run", summary="Run a full QBO accounting audit")
async def run_audit(
    request: AuditReportRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Run a comprehensive QuickBooks Online accounting audit.

    Reviews: Balance Sheet, P&L, AR/AP Aging, Undeposited Funds,
    Journal Entries. Returns prioritized risk findings.
    """
    agent = QBOAuditorAgent()
    try:
        result = await agent.run_full_audit(
            realm_id=request.realm_id,
            as_of_date=request.as_of_date,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask", summary="Ask the QBO Auditor a specific question")
async def ask_auditor(
    realm_id: str,
    question: str,
    _: str = Depends(verify_api_key),
) -> dict:
    """Ask the QBO Auditor any accounting-specific question about the QBO file."""
    agent = QBOAuditorAgent()
    try:
        result = await agent.run(
            f"For QBO realm {realm_id}: {question}"
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
