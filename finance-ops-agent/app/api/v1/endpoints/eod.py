"""End-of-Day Report REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.eod_report import EODReportAgent
from app.core.security import verify_api_key
from app.models.schemas import EODRequest, EODResponse

router = APIRouter(prefix="/eod", tags=["End-of-Day Reports"])


@router.post("/generate", summary="Generate an End-of-Day report")
async def generate_eod(
    request: EODRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Transform raw work notes into a professional EOD report with:
    - Wins (quantified accomplishments)
    - Roadblocks (with resolution path)
    - Priorities for tomorrow (numbered by urgency)
    - Pending items
    - Follow-ups required
    - Executive summary
    """
    agent = EODReportAgent()
    try:
        return await agent.generate_eod(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
