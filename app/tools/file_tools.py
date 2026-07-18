"""File processing tools — CSV, Excel, PDF → structured data."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_core.tools import tool


def _read_csv(path: str, max_rows: int = 500) -> list[dict[str, Any]]:
    df = pd.read_csv(path, nrows=max_rows)
    df.columns = [str(c).strip() for c in df.columns]
    return df.where(pd.notna(df), None).to_dict(orient="records")  # type: ignore[return-value]


def _read_excel(path: str, sheet: str | None = None, max_rows: int = 500) -> list[dict[str, Any]]:
    df = pd.read_excel(path, sheet_name=sheet or 0, nrows=max_rows)
    df.columns = [str(c).strip() for c in df.columns]
    return df.where(pd.notna(df), None).to_dict(orient="records")  # type: ignore[return-value]


def _read_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except Exception as exc:
        return f"[PDF read error: {exc}]"


@tool
def read_csv_file(file_path: str, max_rows: int = 200) -> str:
    """Read a CSV file and return rows as JSON.
    Args:
        file_path: Absolute path to the CSV file.
        max_rows: Maximum rows to return (default 200).
    """
    rows = _read_csv(file_path, max_rows)
    return json.dumps({"rows": rows, "count": len(rows)}, default=str)


@tool
def read_excel_file(file_path: str, sheet_name: str = "", max_rows: int = 200) -> str:
    """Read an Excel (.xlsx/.xls) file and return rows as JSON.
    Args:
        file_path: Absolute path to the Excel file.
        sheet_name: Sheet name or empty string for first sheet.
        max_rows: Maximum rows to return.
    """
    rows = _read_excel(file_path, sheet_name or None, max_rows)
    return json.dumps({"rows": rows, "count": len(rows)}, default=str)


@tool
def read_pdf_file(file_path: str) -> str:
    """Extract text from a PDF file (bank statements, invoices, reports).
    Args:
        file_path: Absolute path to the PDF file.
    """
    text = _read_pdf_text(file_path)
    return json.dumps({"text": text, "chars": len(text)})


@tool
def parse_bank_export(file_path: str, bank_format: str = "auto") -> str:
    """Parse a bank export (CSV or Excel) into normalized transaction rows.
    Args:
        file_path: Path to the export file.
        bank_format: 'auto', 'chase', 'bofa', 'wells', 'generic'.
    """
    ext = Path(file_path).suffix.lower()
    if ext in {".xlsx", ".xls"}:
        rows = _read_excel(file_path)
    else:
        rows = _read_csv(file_path)

    # Normalize column names for common bank formats
    normalized = []
    for row in rows:
        keys = {k.lower().replace(" ", "_"): v for k, v in row.items() if v is not None}
        txn = {
            "date": (
                keys.get("date")
                or keys.get("transaction_date")
                or keys.get("posting_date")
                or ""
            ),
            "description": (
                keys.get("description")
                or keys.get("merchant_name")
                or keys.get("payee")
                or keys.get("memo")
                or ""
            ),
            "amount": float(
                keys.get("amount")
                or keys.get("debit")
                or keys.get("credit")
                or 0
            ),
            "type": "debit" if float(keys.get("amount", 0) or 0) < 0 else "credit",
            "raw_memo": str(keys.get("memo", "") or ""),
        }
        normalized.append(txn)

    return json.dumps({"transactions": normalized, "count": len(normalized)}, default=str)


@tool
def parse_ramp_export(file_path: str) -> str:
    """Parse a Ramp CSV export into normalized transactions ready for QBO coding.
    Args:
        file_path: Path to the Ramp export CSV.
    """
    rows = _read_csv(file_path)
    normalized = []
    for row in rows:
        txn = {
            "date": str(row.get("Date", "") or ""),
            "description": str(row.get("Merchant Name", "") or ""),
            "amount": abs(float(row.get("Amount (USD)", 0) or 0)),
            "type": "debit",
            "raw_memo": str(row.get("Memo", "") or ""),
            "employee": str(row.get("Card Holder Name", "") or ""),
            "card_last4": str(row.get("Card Last 4", "") or ""),
            "ramp_category": str(row.get("Category", "") or ""),
            "receipt_status": str(row.get("Receipt Status", "") or ""),
        }
        normalized.append(txn)

    return json.dumps({"transactions": normalized, "count": len(normalized)}, default=str)


FILE_TOOLS = [
    read_csv_file,
    read_excel_file,
    read_pdf_file,
    parse_bank_export,
    parse_ramp_export,
]
