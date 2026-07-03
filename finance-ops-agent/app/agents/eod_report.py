"""Module 7 — End-of-Day Report Agent."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.models.schemas import EODRequest


class EODReportAgent(FinanceAgentBase):
    """
    Transforms raw daily work notes into structured, professional
    End-of-Day reports ready to share with supervisors or clients.
    """

    module = "eod_report"

    def _default_tools(self) -> list[BaseTool]:
        return []

    async def generate_eod(
        self,
        request: EODRequest,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a structured EOD report from raw notes."""
        report_date = request.date or date.today().strftime("%B %d, %Y")

        prompt = f"""
Transform these raw work notes into a professional End-of-Day (EOD) report.

DATE: {report_date}

RAW NOTES:
{request.raw_notes}

Generate a complete EOD report with these exact sections:

📅 DATE: {report_date}

✅ WINS (completed tasks — quantify where possible):
[List each accomplishment]

🚧 ROADBLOCKS (what prevented completion — include who can unblock):
[List each blocker with resolution path]

📋 PRIORITIES FOR TOMORROW (numbered by urgency):
[Numbered priority list]

⏳ PENDING ITEMS (started but not finished):
[Items in progress]

📞 FOLLOW-UPS REQUIRED (who needs to respond or take action):
[Specific follow-up items with person responsible]

📊 SUMMARY (2-3 sentences for executive review):
[Brief summary]

Use accounting terminology appropriately.
Keep each item concise (1-2 sentences max).
Format for easy reading — this may be sent to a supervisor or client.
"""
        return await self.run(prompt, context=context)
