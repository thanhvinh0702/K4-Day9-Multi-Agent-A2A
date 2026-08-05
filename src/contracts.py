from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CaseFactBundle:
    """Immutable handoff envelope shared by both policy branches."""

    case_id: str
    order_seller: dict[str, Any]
    payment: dict[str, Any]
    delivery: dict[str, Any]
    customer: dict[str, Any]

    def policy_facts(self) -> dict[str, Any]:
        order_status = self.order_seller["order_status"]
        delivered_late = self.delivery["delivered_late"]
        delivered_within_estimate = self.delivery["delivered_within_estimate"]
        late_sellers = list(self.order_seller["late_handoff_seller_ids"])
        payment_row_count = len(self.payment["rows"])
        payment_total_brl = self.payment["payment_total_brl"]
        reconciled = self.payment["reconciled"]
        return {
            "order_status": order_status,
            "seller_ids": list(self.order_seller["seller_ids"]),
            "late_handoff_seller_ids": late_sellers,
            "delivered_late": delivered_late,
            "delivered_within_estimate": delivered_within_estimate,
            "payment_row_count": payment_row_count,
            "payment_total_brl": payment_total_brl,
            "freight_total_brl": self.payment["freight_total_brl"],
            "reconciled": reconciled,
            "rule_match_flags": {
                "canceled_order_paid": order_status == "canceled"
                and payment_total_brl > 0,
                "unavailable_order_paid": order_status == "unavailable"
                and payment_total_brl > 0,
                "late_delivery_seller": bool(delivered_late and late_sellers),
                "late_delivery_logistics": bool(delivered_late),
                "valid_split_payment": payment_row_count >= 2
                and reconciled is True,
                "unsupported_late_claim": delivered_within_estimate
                and reconciled is True,
            },
        }
