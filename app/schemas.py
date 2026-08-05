from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PrimaryIssue = Literal[
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]
SecondaryIssue = Literal[
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
]
CaseStatus = Literal["action_required", "no_action"]
CauseCode = Literal[
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
]
PartyType = Literal["platform", "seller", "logistics_provider"]


class CustomerRequest(BaseModel):
    language: str
    message: str
    claimed_order_id: str


class InvestigationScope(BaseModel):
    include_customer_history: bool = True
    include_product_context: bool = True


class CaseInput(BaseModel):
    case_id: str
    customer_request: CustomerRequest
    investigation_scope: InvestigationScope
    policy_version: str


class CaseAssessment(BaseModel):
    primary_issue: PrimaryIssue
    secondary_issues: list[SecondaryIssue] = Field(max_length=5)
    case_status: CaseStatus
    confidence: float = Field(ge=0, le=1)


class AffectedEntities(BaseModel):
    order_ids: list[str] = Field(max_length=5)
    item_ids: list[str] = Field(max_length=5)
    seller_ids: list[str] = Field(max_length=3)
    payment_ids: list[str] = Field(max_length=5)


class CustomerContext(BaseModel):
    customer_unique_id: str | None
    related_order_ids: list[str] = Field(max_length=5)


class ProductContext(BaseModel):
    product_ids: list[str] = Field(max_length=5)
    category_names: list[str] = Field(max_length=5)


class SellerHandoff(BaseModel):
    seller_id: str
    shipping_limit_at: str | None
    handoff_variance_hours: float | None
    late_handoff: bool


class DeliveryAnalysis(BaseModel):
    delivered_at: str | None
    estimated_delivery_at: str | None
    carrier_handoff_at: str | None
    delivery_variance_hours: float | None
    seller_handoff_analysis: list[SellerHandoff]
    late_handoff_seller_ids: list[str]


class PaymentReconciliation(BaseModel):
    currency: Literal["BRL"] = "BRL"
    item_total_brl: float | None
    freight_total_brl: float | None
    expected_total_brl: float | None
    payment_total_brl: float
    difference_brl: float | None
    reconciled: bool | None
    payment_types: list[str]


class RankedCause(BaseModel):
    cause_code: CauseCode
    rank: int = Field(ge=1, le=3)


class ResponsibleParty(BaseModel):
    party_type: PartyType
    party_id: str


class RootCauseAnalysis(BaseModel):
    ranked_causes: list[RankedCause] = Field(max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(max_length=3)


class FinancialResolution(BaseModel):
    currency: Literal["BRL"] = "BRL"
    recommended_refund_brl: float


class CaseOutput(BaseModel):
    case_id: str
    case_assessment: CaseAssessment
    affected_entities: AffectedEntities
    customer_context: CustomerContext
    product_context: ProductContext
    delivery_analysis: DeliveryAnalysis
    payment_reconciliation: PaymentReconciliation
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(max_length=20)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(max_length=5)


class CustomerFinding(BaseModel):
    agent_name: Literal["CustomerAgent"] = "CustomerAgent"
    customer_context: CustomerContext
    evidence_ids: list[str] = Field(max_length=10)
    confidence: float = Field(ge=0, le=1)
    notes: list[str] = Field(max_length=5)


class OrderProductFinding(BaseModel):
    agent_name: Literal["OrderProductAgent"] = "OrderProductAgent"
    product_context: ProductContext
    item_ids: list[str] = Field(max_length=5)
    seller_ids: list[str] = Field(max_length=3)
    evidence_ids: list[str] = Field(max_length=10)
    confidence: float = Field(ge=0, le=1)
    notes: list[str] = Field(max_length=5)


class PaymentFinding(BaseModel):
    agent_name: Literal["PaymentAgent"] = "PaymentAgent"
    payment_reconciliation: PaymentReconciliation
    payment_ids: list[str] = Field(max_length=5)
    evidence_ids: list[str] = Field(max_length=10)
    confidence: float = Field(ge=0, le=1)
    notes: list[str] = Field(max_length=5)


class DeliveryFinding(BaseModel):
    agent_name: Literal["DeliveryAgent"] = "DeliveryAgent"
    delivery_analysis: DeliveryAnalysis
    evidence_ids: list[str] = Field(max_length=10)
    confidence: float = Field(ge=0, le=1)
    notes: list[str] = Field(max_length=5)


class PolicyFinding(BaseModel):
    agent_name: Literal["PolicyAgent"] = "PolicyAgent"
    case_assessment: CaseAssessment
    root_cause_analysis: RootCauseAnalysis
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(max_length=5)
    evidence_ids: list[str] = Field(max_length=20)
    confidence: float = Field(ge=0, le=1)
    notes: list[str] = Field(max_length=5)


class VerificationFinding(BaseModel):
    agent_name: Literal["VerifierAgent"] = "VerifierAgent"
    schema_valid: bool
    evidence_valid: bool
    money_valid: bool
    array_limits_valid: bool
    final_output: CaseOutput
    confidence: float = Field(ge=0, le=1)
    notes: list[str] = Field(max_length=5)
