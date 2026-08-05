from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CaseAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_issue: str
    secondary_issues: list[str] = Field(default_factory=list)
    case_status: Literal["action_required", "no_action"]
    confidence: float


class AffectedEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_ids: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    seller_ids: list[str] = Field(default_factory=list)
    payment_ids: list[str] = Field(default_factory=list)


class CustomerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_unique_id: Optional[str] = None
    related_order_ids: list[str] = Field(default_factory=list)


class ProductContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(default_factory=list)
    category_names: list[str] = Field(default_factory=list)


class SellerHandoffAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seller_id: str
    shipping_limit_at: Optional[str] = None
    handoff_variance_hours: Optional[float] = None
    late_handoff: bool


class DeliveryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivered_at: Optional[str] = None
    estimated_delivery_at: Optional[str] = None
    carrier_handoff_at: Optional[str] = None
    delivery_variance_hours: Optional[float] = None
    seller_handoff_analysis: list[SellerHandoffAnalysis] = Field(default_factory=list)
    late_handoff_seller_ids: list[str] = Field(default_factory=list)


class PaymentReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = "BRL"
    item_total_brl: Optional[float] = None
    freight_total_brl: Optional[float] = None
    expected_total_brl: Optional[float] = None
    payment_total_brl: Optional[float] = None
    difference_brl: Optional[float] = None
    reconciled: Optional[bool] = None
    payment_types: list[str] = Field(default_factory=list)


class RankedCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause_code: str
    rank: int


class ResponsibleParty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_type: str
    party_id: str


class RootCauseAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranked_causes: list[RankedCause] = Field(default_factory=list)
    responsible_parties: list[ResponsibleParty] = Field(default_factory=list)


class FinancialResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = "BRL"
    recommended_refund_brl: Optional[float] = None


class CaseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    case_assessment: CaseAssessment
    affected_entities: AffectedEntities
    customer_context: CustomerContext
    product_context: ProductContext
    delivery_analysis: DeliveryAnalysis
    payment_reconciliation: PaymentReconciliation
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(default_factory=list)

