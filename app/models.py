from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PurchaseRequest(ApiModel):
    request_id: str
    request_date: date
    supplier_name: str
    category: str
    amount_try: Decimal = Field(gt=0)
    received_quotes: int = Field(ge=0)
    offered_lead_time_days: int = Field(ge=0)

    @field_serializer("amount_try")
    def serialize_amount_try(self, value: Decimal) -> str:
        return format(value, "f")


class SupplierRecord(ApiModel):
    supplier_name: str
    quality_score: int = Field(ge=0, le=100)
    iso_9001_expiry_date: date
    status: str
    risk_flag: str


class PurchaseAnalysis(ApiModel):
    historical_median_try: Decimal
    variance_percent: Decimal
    display_variance_percent: Decimal
    standard_lead_time_days: int
    lead_time_variance_days: int

    @field_serializer(
        "historical_median_try",
        "variance_percent",
        "display_variance_percent",
    )
    def serialize_decimal_fields(self, value: Decimal) -> str:
        return format(value, "f")


class Citation(ApiModel):
    document_id: str
    version: str
    title: str
    section_id: str
    section_title: str
    status: str
    effective_from: date


class PolicyDecision(ApiModel):
    decision_status: Literal[
        "APPROVED", "CONDITIONAL_REVIEW", "REJECTED", "INSUFFICIENT_EVIDENCE"
    ]
    finance_approval_required: bool
    alternative_quote_missing: bool
    certificate_status: Literal["VALID", "EXPIRED", "MISSING"]
    lead_time_variance_days: int
    blocking_reasons: list[str]
    warnings: list[str]
    applicable_rule_ids: list[str]


class ApprovalRecord(ApiModel):
    approval_id: str
    request_id: str
    action_type: str
    requested_by: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]
    approved_by: str | None = None
    created_at: datetime
    updated_at: datetime


class AuditEvent(ApiModel):
    event_id: str
    timestamp: datetime
    event_type: str
    actor: str
    request_id: str | None = None
    approval_id: str | None = None
    trace_id: str
    details: dict[str, Any]


class TicketResult(ApiModel):
    ticket_id: str
    status: Literal["OPEN", "ALREADY_PROCESSED"]
    request_id: str
    duplicate_created: bool = False


class ActionPreview(ApiModel):
    approval_id: str
    target_system: str
    operation: str
    idempotency_key: str
    payload: dict[str, object]
    required_role: str


class AnalysisResponse(ApiModel):
    request: PurchaseRequest
    supplier: SupplierRecord
    analysis: PurchaseAnalysis
    decision: PolicyDecision
    citations: list[Citation]
    approval: ApprovalRecord
    explanation: str
    trace_id: str


class PolicySection(ApiModel):
    section_id: str
    title: str
    body: str


class PolicyDocument(ApiModel):
    document_id: str
    title: str
    version: str
    status: str
    document_type: str
    effective_from: date
    effective_to: date | None = None
    superseded_by: str | None = None
    allowed_roles: list[str]
    file_path: str
    trusted_for_retrieval: bool
    sections: list[PolicySection]

    def section(self, section_id: str) -> PolicySection:
        for section in self.sections:
            if section.section_id == section_id:
                return section
        raise KeyError(f"Section {section_id!r} not found in {self.document_id}")
