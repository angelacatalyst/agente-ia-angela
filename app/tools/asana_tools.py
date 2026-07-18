"""LangChain tools wrapping the Asana client."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.integrations.asana.client import AsanaClient

_client = AsanaClient()


@tool
async def create_asana_task(
    name: str,
    notes: str = "",
    due_on: str = "",
    assignee: str = "",
) -> str:
    """Create a task in Asana.
    Args:
        name: Task name/title.
        notes: Task description or notes.
        due_on: Due date YYYY-MM-DD (optional).
        assignee: Asana user GID or email (optional).
    """
    task = await _client.create_task(
        name=name,
        notes=notes,
        due_on=due_on or None,
        assignee=assignee or None,
    )
    return json.dumps({"task_gid": task["gid"], "name": task["name"]})


@tool
async def create_vendor_onboarding_task_asana(
    vendor_name: str,
    missing_documents: str,
    due_on: str = "",
) -> str:
    """Create a vendor onboarding checklist task in Asana.
    Args:
        vendor_name: Name of the vendor being onboarded.
        missing_documents: JSON list of missing document names.
        due_on: Target completion date YYYY-MM-DD.
    """
    docs: list[str] = json.loads(missing_documents)
    task = await _client.create_vendor_onboarding_task(
        vendor_name=vendor_name,
        missing_docs=docs,
        due_on=due_on or None,
    )
    return json.dumps({"task_gid": task["gid"], "name": task["name"]})


@tool
async def create_payment_request_task_asana(
    vendor: str,
    amount: float,
    invoice_number: str = "",
    notes: str = "",
    due_on: str = "",
) -> str:
    """Create a payment request follow-up task in Asana.
    Args:
        vendor: Vendor name.
        amount: Invoice amount in dollars.
        invoice_number: Invoice number (optional).
        notes: Additional context.
        due_on: Due date YYYY-MM-DD.
    """
    task = await _client.create_payment_request_task(
        vendor=vendor,
        amount=amount,
        invoice_number=invoice_number or None,
        notes=notes,
        due_on=due_on or None,
    )
    return json.dumps({"task_gid": task["gid"], "name": task["name"]})


@tool
async def complete_asana_task(task_gid: str) -> str:
    """Mark an Asana task as complete.
    Args:
        task_gid: The GID of the Asana task to complete.
    """
    result = await _client.complete_task(task_gid)
    return json.dumps({"completed": result.get("completed", True)})


@tool
async def add_asana_comment(task_gid: str, comment: str) -> str:
    """Add a comment/note to an existing Asana task.
    Args:
        task_gid: The GID of the Asana task.
        comment: Comment text to add.
    """
    result = await _client.add_comment(task_gid, comment)
    return json.dumps({"story_gid": result.get("gid")})


@tool
async def list_asana_projects() -> str:
    """List all Asana projects in the workspace."""
    projects = await _client.list_projects()
    return json.dumps([{"gid": p["gid"], "name": p["name"]} for p in projects])


ASANA_TOOLS = [
    create_asana_task,
    create_vendor_onboarding_task_asana,
    create_payment_request_task_asana,
    complete_asana_task,
    add_asana_comment,
    list_asana_projects,
]
