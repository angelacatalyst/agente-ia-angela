"""SOP Builder REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.sop_builder import SOPBuilderAgent
from app.core.security import verify_api_key
from app.models.schemas import SOPRequest, SOPResponse

router = APIRouter(prefix="/sops", tags=["SOP Builder"])


@router.post("/build", summary="Generate a complete accounting SOP")
async def build_sop(
    request: SOPRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Generate a comprehensive Standard Operating Procedure document.
    Includes purpose, scope, step-by-step instructions, QBO navigation,
    quality checks, common mistakes, and expected outcomes.
    """
    agent = SOPBuilderAgent()
    try:
        return await agent.build_sop(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/build/quick", summary="Generate SOP from a free-text description")
async def build_sop_quick(
    description: str,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Quick SOP generation from a free-text process description.
    Example: "How to create bills in QBO for vendor invoices"
    """
    agent = SOPBuilderAgent()
    try:
        return await agent.build_sop_from_description(description)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
