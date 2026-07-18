"""Module 4 — Payment Request Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.models.schemas import PaymentRequestInput
from app.tools.asana_tools import ASANA_TOOLS
from app.tools.file_tools import FILE_TOOLS


class PaymentRequestAgent(FinanceAgentBase):
    """
    Reviews and processes payment requests. Verifies approvals,
    documentation, budget availability, and coding before payment.
    """

    module = "payment_request"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=(qbo_tools or []) + list(ASANA_TOOLS))

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def process_payment_request(
        self,
        request: PaymentRequestInput,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify and process a payment request."""
        import json

        prompt = f"""
Review this payment request and complete the verification checklist:

PAYMENT REQUEST DETAILS:
- Vendor: {request.vendor_name} (ID: {request.vendor_id or 'Not in QBO'})
- Invoice #: {request.invoice_number or 'Not provided'}
- Invoice Date: {request.invoice_date}
- Due Date: {request.due_date or 'Not specified'}
- Approver: {request.approver or 'Not specified'}
- Notes: {request.notes or 'None'}

LINE ITEMS:
{json.dumps([i.model_dump() for i in request.items], indent=2)}

Supporting Docs: {', '.join(request.supporting_docs) or 'None provided'}

Please:
1. Run through the complete payment request checklist (all items ✅/❌)
2. Identify any RED FLAGS that should hold payment
3. Verify the GL coding is appropriate for each line item
4. Check if vendor exists in QBO (use QBO tools if available)
5. Calculate total amount and verify it matches line items
6. Provide a clear READY TO PAY or HOLD — DO NOT PAY decision
7. List specific action items for any missing items
8. If ready to pay, provide the formatted Bill data for QBO entry
"""
        return await self.run(prompt, context=context)

    async def process_from_invoice_pdf(
        self,
        file_path: str,
        approver: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract payment request details from a PDF invoice."""
        prompt = (
            f"Read the invoice PDF at '{file_path}'. "
            "Extract all payment request information: vendor name, invoice number, "
            "date, due date, line items, amounts, and total. "
            f"{'Approver: ' + approver if approver else ''} "
            "Then run the full payment request verification checklist. "
            "Return READY TO PAY or HOLD with complete action items."
        )
        return await self.run(prompt, context=context)
