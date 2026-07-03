"""Module 6 — SOP Builder Agent."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.agents.base import FinanceAgentBase
from app.models.schemas import SOPRequest


class SOPBuilderAgent(FinanceAgentBase):
    """
    Generates detailed Standard Operating Procedures for accounting processes.
    Output is structured for ScribeHow, Asana, and internal documentation.
    """

    module = "sop_builder"

    def _default_tools(self) -> list[BaseTool]:
        return []  # SOPs are generated from knowledge, no external tools needed

    async def build_sop(
        self,
        request: SOPRequest,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete SOP document."""
        screens = ", ".join(request.qbo_screens_involved) or "None specified"

        prompt = f"""
Create a complete Standard Operating Procedure (SOP) for the following accounting process:

PROCESS TITLE: {request.process_title}

DESCRIPTION: {request.process_description}

Frequency: {request.frequency or 'As needed'}
Responsible: {request.responsible_role or 'Accounting Staff'}
QBO Screens: {screens}
Special Notes: {request.special_notes or 'None'}

Generate a complete SOP including ALL of these sections:
1. Title
2. Purpose (why this process exists)
3. Scope (what's included and excluded)
4. Frequency (when to perform)
5. Responsible Party (who performs)
6. Required Documents/System Access (what you need before starting)
7. Step-by-Step Instructions (numbered, specific — each step = one action)
   - Include exact QBO navigation paths (e.g., "Click Accounting > Chart of Accounts")
   - Include what to look for and what fields to fill
8. Quality Checks (how to verify correctness)
9. Common Mistakes (what often goes wrong + how to avoid)
10. Best Practices (efficiency tips and internal control notes)
11. QBO Screens Reference (complete navigation guide)
12. Expected Outcome (what correct completion looks like)

Write at a level appropriate for a new bookkeeper with 1 year of experience.
Be specific and actionable. Use numbered steps.
"""
        return await self.run(prompt, context=context)

    async def build_sop_from_description(
        self,
        description: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an SOP from a free-form process description."""
        prompt = (
            f"Create a complete accounting SOP for the following process described by the user:\n\n"
            f"{description}\n\n"
            "Generate all standard SOP sections. "
            "If any detail is missing, apply accounting best practices to fill the gaps. "
            "Include specific QBO navigation paths where applicable."
        )
        return await self.run(prompt, context=context)
