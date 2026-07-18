"""Transaction Coding REST endpoint."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agents.transaction_coder import TransactionCoderAgent
from app.core.config import get_settings
from app.core.security import verify_api_key
from app.models.schemas import TransactionCodingRequest, TransactionCodingResponse

router = APIRouter(prefix="/transactions", tags=["Transaction Coder"])
settings = get_settings()


@router.post("/code", summary="Code a list of transactions for QBO")
async def code_transactions(
    request: TransactionCodingRequest,
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Categorize a batch of transactions with:
    - QBO Account / Category
    - Grant / Program / Class / Project (for nonprofits)
    - Confidence level and reasoning
    """
    agent = TransactionCoderAgent()
    try:
        return await agent.code_transactions(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/code/upload", summary="Code transactions from uploaded CSV/Excel file")
async def code_from_upload(
    file: UploadFile = File(...),
    organization_type: str = Form("nonprofit"),
    active_grants: str = Form(""),
    active_programs: str = Form(""),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Upload a CSV or Excel file (bank export, Ramp export, etc.)
    and get back fully coded transactions ready for QBO.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Use CSV or Excel.",
        )

    # Save uploaded file
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / file.filename

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    grants = [g.strip() for g in active_grants.split(",") if g.strip()]
    programs = [p.strip() for p in active_programs.split(",") if p.strip()]

    agent = TransactionCoderAgent()
    try:
        result = await agent.code_from_file(
            file_path=str(save_path),
            organization_type=organization_type,
            active_grants=grants,
            active_programs=programs,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        # Clean up uploaded file
        if save_path.exists():
            os.remove(save_path)
