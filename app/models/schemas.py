"""Pydantic v2 request/response schemas for all API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Shared ────────────────────────────────────────────────────────────────────

class AgentModule(str, Enum):
    qbo_auditor = "qbo_auditor"
    transaction_coder = "transaction_coder"
    grant_compliance = "grant_compliance"
    payment_request = "payment_request"
    vendor_onboarding = "vendor_onboarding"
    sop_builder = "sop_builder"
    eod_report = "eod_report"
    controller = "controller"
    orchestrator = "orchestrator"


class RiskLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    module: AgentModule = AgentModule.orchestrator
    conversation_id: uuid.UUID | None = None
    qbo_realm_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    module: AgentModule
    content: str
    tool_calls_made: list[str] = Field(default_factory=list)
    created_at: datetime


# ── QBO Auditor ───────────────────────────────────────────────────────────────

class AuditFinding(BaseModel):
    risk_level: RiskLevel
    category: str
    description: str
    amount: float | None = None
    account: str | None = None
    recommendation: str
    action_required: bool = True


class AuditReportRequest(BaseModel):
    realm_id: str
    report_types: list[str] = Field(
        default=["balance_sheet", "profit_loss", "ar_aging", "ap_aging"]
    )
    as_of_date: str | None = None  # YYYY-MM-DD


class AuditReportResponse(BaseModel):
    realm_id: str
    as_of_date: str
    high_risk: list[AuditFinding]
    warnings: list[AuditFinding]
    recommendations: list[AuditFinding]
    summary: str
    generated_at: datetime


# ── Transaction Coder ─────────────────────────────────────────────────────────

class RawTransaction(BaseModel):
    date: str
    description: str
    amount: float
    type: str = "debit"  # debit | credit
    raw_memo: str | None = None


class CodedTransaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str
    description: str
    amount: float
    vendor: str
    account: str
    account_code: str | None = None
    category: str
    grant: str | None = None
    program: str | None = None
    qbo_class: str | None = Field(None, alias="class")
    project: str | None = None
    memo: str
    confidence: ConfidenceLevel
    reasoning: str


class TransactionCodingRequest(BaseModel):
    transactions: list[RawTransaction]
    organization_type: str = "nonprofit"  # nonprofit | for-profit
    chart_of_accounts: dict[str, str] = Field(default_factory=dict)
    active_grants: list[str] = Field(default_factory=list)
    active_programs: list[str] = Field(default_factory=list)
    active_classes: list[str] = Field(default_factory=list)


class TransactionCodingResponse(BaseModel):
    coded: list[CodedTransaction]
    uncertain: list[CodedTransaction]
    total_processed: int
    high_confidence_count: int
    needs_review_count: int


# ── Grant Compliance ──────────────────────────────────────────────────────────

class GrantComplianceIssue(BaseModel):
    severity: RiskLevel
    grant_name: str
    issue_type: str
    description: str
    amount_at_risk: float | None = None
    transactions_affected: list[str] = Field(default_factory=list)
    remediation: str


class GrantComplianceRequest(BaseModel):
    realm_id: str
    grant_names: list[str]
    period_start: str  # YYYY-MM-DD
    period_end: str    # YYYY-MM-DD
    include_payroll: bool = True


class GrantComplianceResponse(BaseModel):
    period: str
    grants_reviewed: list[str]
    issues: list[GrantComplianceIssue]
    compliant_grants: list[str]
    at_risk_grants: list[str]
    summary: str
    audit_ready: bool


# ── Payment Request ───────────────────────────────────────────────────────────

class PaymentRequestItem(BaseModel):
    description: str
    amount: float
    account: str
    grant: str | None = None
    program: str | None = None


class PaymentRequestInput(BaseModel):
    vendor_name: str
    vendor_id: str | None = None
    invoice_number: str | None = None
    invoice_date: str
    due_date: str | None = None
    items: list[PaymentRequestItem]
    approver: str | None = None
    supporting_docs: list[str] = Field(default_factory=list)
    notes: str | None = None


class PaymentRequestOutput(BaseModel):
    checklist: dict[str, bool]
    missing_items: list[str]
    total_amount: float
    coding_verified: bool
    budget_available: bool | None = None
    approval_required: bool
    ready_to_pay: bool
    bill_data: dict[str, Any]
    notes: str


# ── Vendor Onboarding ─────────────────────────────────────────────────────────

class VendorOnboardingInput(BaseModel):
    vendor_name: str
    vendor_type: str  # individual | corporation | nonprofit
    services_provided: str
    estimated_annual_spend: float | None = None
    requires_insurance: bool = False
    has_w9: bool = False
    has_ach: bool = False
    has_insurance: bool = False
    has_contract: bool = False
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None


class VendorOnboardingOutput(BaseModel):
    checklist: dict[str, bool]
    missing_documents: list[str]
    risk_flags: list[str]
    onboarding_complete: bool
    asana_task_id: str | None = None
    qbo_vendor_id: str | None = None
    next_steps: list[str]


# ── SOP Builder ───────────────────────────────────────────────────────────────

class SOPRequest(BaseModel):
    process_title: str
    process_description: str
    frequency: str | None = None  # daily | weekly | monthly
    responsible_role: str | None = None
    qbo_screens_involved: list[str] = Field(default_factory=list)
    special_notes: str | None = None


class SOPResponse(BaseModel):
    title: str
    purpose: str
    scope: str
    frequency: str
    responsible: str
    required_documents: list[str]
    steps: list[dict[str, Any]]
    quality_checks: list[str]
    common_mistakes: list[str]
    best_practices: list[str]
    qbo_screens: list[str]
    expected_outcome: str
    created_at: datetime


# ── End of Day ────────────────────────────────────────────────────────────────

class EODRequest(BaseModel):
    raw_notes: str = Field(
        description="Free-form notes about what was done today",
        min_length=1,
    )
    date: str | None = None  # defaults to today


class EODResponse(BaseModel):
    date: str
    wins: list[str]
    roadblocks: list[str]
    priorities_tomorrow: list[str]
    pending_items: list[str]
    follow_ups: list[str]
    summary: str


# ── Controller Dashboard ──────────────────────────────────────────────────────

class ControllerRequest(BaseModel):
    realm_id: str
    period: str  # e.g. "June 2025"
    include_recommendations: bool = True


class Priority(BaseModel):
    rank: int
    action: str
    urgency: RiskLevel
    estimated_time: str | None = None


class ControllerResponse(BaseModel):
    period: str
    priorities: list[Priority]
    financial_risks: list[AuditFinding]
    recommendations: list[str]
    key_metrics: dict[str, Any]
    month_end_checklist: dict[str, bool]
    narrative: str
    generated_at: datetime


# ── File Upload ───────────────────────────────────────────────────────────────

class UploadedFileInfo(BaseModel):
    filename: str
    size_bytes: int
    content_type: str
    rows: int | None = None
    columns: list[str] | None = None
    preview: list[dict[str, Any]] | None = None


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    services: dict[str, str]
