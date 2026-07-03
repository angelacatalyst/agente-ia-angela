"""Fractional Controller REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.controller import ControllerAgent
from app.core.security import verify_api_key
from app.models.schemas import ControllerRequest, ControllerResponse

router = APIRouter(prefix="/controller", tags=["Controller Dashboard"])


@router.post("/briefing", summary="Generate a controller morning briefing")
async def morning_briefing(
    request: ControllerRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Generate a comprehensive controller morning briefing:
    - Today's top priorities (ranked)
    - Financial risks (HIGH/MEDIUM/LOW)
    - Key metrics (cash, AR, AP, burn rate)
    - Month-end close checklist status
    - Strategic recommendations
    - Executive narrative summary
    """
    agent = ControllerAgent()
    try:
        return await agent.morning_briefing(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/month-end", summary="Run a month-end close review")
async def month_end_review(
    realm_id: str,
    month: str,
    year: str,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Comprehensive month-end close review covering:
    bank reconciliations, AR/AP, payroll, grants, JEs,
    and financial statement analysis.
    """
    agent = ControllerAgent()
    try:
        return await agent.month_end_review(realm_id, month, year)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask", summary="Ask the Controller a financial question")
async def ask_controller(
    realm_id: str,
    question: str,
    _: str = Depends(verify_api_key),
) -> dict:
    """Ask any controller-level accounting or financial question."""
    agent = ControllerAgent()
    try:
        return await agent.run(
            f"For QBO realm {realm_id}, as the controller: {question}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
