"""Vendor Onboarding REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agents.vendor_onboarding import VendorOnboardingAgent
from app.core.security import verify_api_key
from app.models.schemas import VendorOnboardingInput, VendorOnboardingOutput

router = APIRouter(prefix="/vendors", tags=["Vendor Onboarding"])


@router.post("/onboard", summary="Process a new vendor onboarding")
async def onboard_vendor(
    vendor: VendorOnboardingInput,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Run the complete vendor onboarding workflow:
    - Document checklist (W-9, ACH, Insurance, Contract)
    - Risk assessment
    - 1099 determination
    - QBO vendor setup specifications
    - Asana task creation for missing docs
    - Next steps
    """
    agent = VendorOnboardingAgent()
    try:
        return await agent.onboard_vendor(vendor)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/checklist", summary="Generate vendor document checklist")
async def vendor_checklist(
    vendor_name: str,
    vendor_type: str = "corporation",
    requires_insurance: bool = False,
    estimated_annual_spend: float | None = None,
    _: str = Depends(verify_api_key),
) -> dict:
    """Get a pre-built vendor onboarding checklist without running the full workflow."""
    agent = VendorOnboardingAgent()
    try:
        return await agent.run(
            f"Generate a vendor onboarding checklist for: {vendor_name} "
            f"(Type: {vendor_type}, Requires Insurance: {requires_insurance}, "
            f"Estimated Annual Spend: ${estimated_annual_spend or 'Unknown'}). "
            "Return the complete checklist with required documents and risk assessment."
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
