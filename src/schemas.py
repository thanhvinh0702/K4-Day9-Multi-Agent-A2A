"""Pydantic models: structured-output targets for the LLM agents, and the
final output schema (README.md section 6) used by the Verifier to validate
before a file is written.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---- per-agent fragments (structured_output targets) ----------------------


class CustomerFragment(BaseModel):
    customer_unique_id: Optional[str]
    related_order_ids: list[str] = Field(default_factory=list, max_length=5)


class OrderProductFragment(BaseModel):
    order_ids: list[str] = Field(max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=3)
    product_ids: list[str] = Field(default_factory=list, max_length=5)
    category_names: list[str] = Field(default_factory=list, max_length=5)


class PaymentReconciliation(BaseModel):
    currency: str
    item_total_brl: float
    freight_total_brl: float
    expected_total_brl: Optional[float]
    payment_total_brl: float
    difference_brl: Optional[float]
    reconciled: Optional[bool]
    payment_types: list[str] = Field(default_factory=list)


class PaymentFragment(BaseModel):
    payment_ids: list[str] = Field(default_factory=list, max_length=5)
    payment_reconciliation: PaymentReconciliation


class SellerHandoff(BaseModel):
    seller_id: str
    shipping_limit_at: Optional[str]
    handoff_variance_hours: Optional[float]
    late_handoff: bool


class DeliveryFragment(BaseModel):
    delivered_at: Optional[str]
    estimated_delivery_at: Optional[str]
    carrier_handoff_at: Optional[str]
    delivery_variance_hours: Optional[float]
    seller_handoff_analysis: list[SellerHandoff] = Field(default_factory=list)
    late_handoff_seller_ids: list[str] = Field(default_factory=list)


PRIMARY_ISSUES = Literal[
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]


class CaseAssessment(BaseModel):
    primary_issue: PRIMARY_ISSUES
    secondary_issues: list[str] = Field(default_factory=list)
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)


class RankedCause(BaseModel):
    cause_code: str
    rank: int


class ResponsibleParty(BaseModel):
    party_type: str
    party_id: str


class RootCauseAnalysis(BaseModel):
    ranked_causes: list[RankedCause] = Field(default_factory=list, max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(default_factory=list, max_length=3)


class FinancialResolution(BaseModel):
    currency: str
    recommended_refund_brl: float


class PolicyFragment(BaseModel):
    case_assessment: CaseAssessment
    root_cause_analysis: RootCauseAnalysis
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(default_factory=list, max_length=5)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


# ---- final output schema (README.md section 6) -----------------------------


class AffectedEntities(BaseModel):
    order_ids: list[str] = Field(max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=3)
    payment_ids: list[str] = Field(default_factory=list, max_length=5)


class CustomerContext(BaseModel):
    customer_unique_id: Optional[str]
    related_order_ids: list[str] = Field(default_factory=list, max_length=5)


class ProductContext(BaseModel):
    product_ids: list[str] = Field(default_factory=list, max_length=5)
    category_names: list[str] = Field(default_factory=list, max_length=5)


class FinalOutput(BaseModel):
    case_id: str
    case_assessment: CaseAssessment
    affected_entities: AffectedEntities
    customer_context: CustomerContext
    product_context: ProductContext
    delivery_analysis: DeliveryFragment
    payment_reconciliation: PaymentReconciliation
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(default_factory=list, max_length=5)
