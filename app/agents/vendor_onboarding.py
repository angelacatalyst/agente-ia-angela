"""Module 5 — Vendor Onboarding Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.models.schemas import VendorOnboardingInput
from app.tools.asana_tools import ASANA_TOOLS
from app.tools.file_tools import FILE_TOOLS


class VendorOnboardingAgent(FinanceAgentBase):
    """
    Manages new vendor onboarding: document checklist, risk assessment,
    QBO setup verification, and Asana task creation.
    """

    module = "vendor_onboarding"

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        super().__init__(extra_tools=(qbo_tools or []) + list(ASANA_TOOLS))

    def _default_tools(self) -> list[BaseTool]:
        return list(FILE_TOOLS)

    async def onboard_vendor(
        self,
        vendor: VendorOnboardingInput,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the complete vendor onboarding workflow."""
        prompt = f"""
Process this new vendor onboarding request:

VENDOR INFORMATION:
- Name: {vendor.vendor_name}
- Type: {vendor.vendor_type}
- Services: {vendor.services_provided}
- Estimated Annual Spend: ${vendor.estimated_annual_spend:,.2f if vendor.estimated_annual_spend else 'Unknown'}
- Requires Insurance: {vendor.requires_insurance}

DOCUMENT STATUS:
- W-9 on file: {vendor.has_w9}
- ACH Authorization on file: {vendor.has_ach}
- Certificate of Insurance on file: {vendor.has_insurance}
- Signed Contract on file: {vendor.has_contract}

Contact: {vendor.contact_email or 'Not provided'} | {vendor.contact_phone or 'Not provided'}
Notes: {vendor.notes or 'None'}

Please:
1. Complete the vendor onboarding checklist with ✅/❌ status for each item
2. Assess vendor risk level (HIGH/MEDIUM/LOW)
3. Identify all missing documents
4. Determine if 1099 reporting will be required
5. Provide QBO vendor setup specifications (exact fields to enter)
6. Create an Asana task for any missing documents (use the Asana tool)
7. List next steps in priority order
8. Flag any conflicts of interest or red flags

Return a complete onboarding report.
"""
        return await self.run(prompt, context=context)
