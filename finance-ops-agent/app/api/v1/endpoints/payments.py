"""Payment Request REST endpoint."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agents.payment_request import PaymentRequestAgent
from app.core.config import get_settings
from app.core.security import verify_api_key
from app.models.schemas import PaymentRequestInput

router = APIRouter(prefix="/payments", tags=["Payment Requests"])
settings = get_settings()


@router.post("/review", summary="Review and verify a payment request")
async def review_payment(
    request: PaymentRequestInput,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Process a payment request through the full verification checklist:
    - Vendor verification
    - Documentation completeness
    - GL coding review
    - Budget availability
    - Approval verification
    - Duplicate payment check
    Returns READY TO PAY or HOLD with specific action items.
    """
    agent = PaymentRequestAgent()
    try:
        return await agent.process_payment_request(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/review/invoice", summary="Process payment request from PDF invoice")
async def review_from_invoice(
    file: UploadFile = File(...),
    approver: str = Form(""),
    _: str = Depends(verify_api_key),
) -> dict:
    """Upload a PDF invoice and get a full payment request review."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF invoices are supported")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / file.filename

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    agent = PaymentRequestAgent()
    try:
        return await agent.process_from_invoice_pdf(
            file_path=str(save_path),
            approver=approver or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if save_path.exists():
            os.remove(save_path)
