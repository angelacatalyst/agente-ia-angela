"""LangChain tools wrapping the QBO client."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from app.core.logging import get_logger

logger = get_logger(__name__)

# NOTE: QBOClient is injected at agent build-time via a closure.
# Each tool factory receives a bound client instance.


def build_qbo_tools(client: Any) -> list:  # list[BaseTool]
    """Return a list of LangChain tools bound to a specific QBOClient instance."""

    @tool
    async def get_balance_sheet(as_of_date: str = "") -> str:
        """Fetch Balance Sheet report from QuickBooks Online.
        Args:
            as_of_date: Optional date string YYYY-MM-DD. Defaults to today.
        """
        data = await client.get_balance_sheet(as_of_date or None)
        return json.dumps(data, default=str)

    @tool
    async def get_profit_loss(start_date: str = "", end_date: str = "") -> str:
        """Fetch Profit & Loss report from QuickBooks Online.
        Args:
            start_date: Start date YYYY-MM-DD.
            end_date: End date YYYY-MM-DD.
        """
        data = await client.get_profit_loss(start_date or None, end_date or None)
        return json.dumps(data, default=str)

    @tool
    async def get_ar_aging() -> str:
        """Fetch Accounts Receivable Aging Summary from QuickBooks Online."""
        data = await client.get_ar_aging()
        return json.dumps(data, default=str)

    @tool
    async def get_ap_aging() -> str:
        """Fetch Accounts Payable Aging Summary from QuickBooks Online."""
        data = await client.get_ap_aging()
        return json.dumps(data, default=str)

    @tool
    async def get_trial_balance(as_of_date: str = "") -> str:
        """Fetch Trial Balance from QuickBooks Online."""
        data = await client.get_trial_balance(as_of_date or None)
        return json.dumps(data, default=str)

    @tool
    async def get_general_ledger(start_date: str = "", end_date: str = "") -> str:
        """Fetch General Ledger detail from QuickBooks Online."""
        data = await client.get_general_ledger(start_date or None, end_date or None)
        return json.dumps(data, default=str)

    @tool
    async def get_undeposited_funds() -> str:
        """List all transactions sitting in Undeposited Funds account."""
        data = await client.get_undeposited_funds()
        return json.dumps(data, default=str)

    @tool
    async def get_vendors(active_only: bool = True) -> str:
        """List vendors from QuickBooks Online.
        Args:
            active_only: If True, only return active vendors.
        """
        data = await client.get_vendors(active_only)
        return json.dumps(data, default=str)

    @tool
    async def get_unpaid_bills(start_date: str = "") -> str:
        """Get unpaid bills (AP) from QuickBooks Online.
        Args:
            start_date: Optional filter for bills created on/after this date.
        """
        data = await client.get_bills(start_date or None, unpaid_only=True)
        return json.dumps(data, default=str)

    @tool
    async def get_open_invoices() -> str:
        """Get open (unpaid) invoices from QuickBooks Online."""
        data = await client.get_invoices(unpaid_only=True)
        return json.dumps(data, default=str)

    @tool
    async def get_journal_entries(start_date: str = "", end_date: str = "") -> str:
        """Get Journal Entries from QuickBooks Online."""
        data = await client.get_journal_entries(start_date or None, end_date or None)
        return json.dumps(data, default=str)

    @tool
    async def get_chart_of_accounts() -> str:
        """Get the active Chart of Accounts from QuickBooks Online."""
        data = await client.get_chart_of_accounts()
        return json.dumps(data, default=str)

    @tool
    async def get_classes() -> str:
        """Get active Classes (for grant/program tracking) from QuickBooks Online."""
        data = await client.get_classes()
        return json.dumps(data, default=str)

    @tool
    async def create_vendor(
        display_name: str,
        company_name: str = "",
        email: str = "",
        tax_id: str = "",
        vendor_type: str = "1099",
    ) -> str:
        """Create a new Vendor in QuickBooks Online.
        Args:
            display_name: Vendor display name (required).
            company_name: Legal company name.
            email: Vendor email.
            tax_id: EIN or SSN.
            vendor_type: '1099' or 'W2'.
        """
        payload: dict[str, Any] = {"DisplayName": display_name}
        if company_name:
            payload["CompanyName"] = company_name
        if email:
            payload["PrimaryEmailAddr"] = {"Address": email}
        if tax_id:
            payload["TaxIdentifier"] = tax_id
        payload["Vendor1099"] = vendor_type == "1099"

        result = await client.create_vendor(payload)
        return json.dumps(result, default=str)

    @tool
    async def create_bill(
        vendor_id: str,
        txn_date: str,
        due_date: str,
        line_items: str,
    ) -> str:
        """Create a Bill in QuickBooks Online.
        Args:
            vendor_id: QBO Vendor ID.
            txn_date: Transaction date YYYY-MM-DD.
            due_date: Due date YYYY-MM-DD.
            line_items: JSON string list of {amount, description, account_id, class_id?}.
        """
        items = json.loads(line_items)
        line_data = []
        for item in items:
            line: dict[str, Any] = {
                "Amount": item["amount"],
                "DetailType": "AccountBasedExpenseLineDetail",
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": item["account_id"]},
                    "BillableStatus": "NotBillable",
                },
                "Description": item.get("description", ""),
            }
            if item.get("class_id"):
                line["AccountBasedExpenseLineDetail"]["ClassRef"] = {
                    "value": item["class_id"]
                }
            line_data.append(line)

        payload = {
            "VendorRef": {"value": vendor_id},
            "TxnDate": txn_date,
            "DueDate": due_date,
            "Line": line_data,
        }
        result = await client.create_bill(payload)
        return json.dumps(result, default=str)

    return [
        get_balance_sheet,
        get_profit_loss,
        get_ar_aging,
        get_ap_aging,
        get_trial_balance,
        get_general_ledger,
        get_undeposited_funds,
        get_vendors,
        get_unpaid_bills,
        get_open_invoices,
        get_journal_entries,
        get_chart_of_accounts,
        get_classes,
        create_vendor,
        create_bill,
    ]
