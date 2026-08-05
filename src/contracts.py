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
        return {
            "order_status": self.order_seller["order_status"],
            "seller_ids": list(self.order_seller["seller_ids"]),
            "late_handoff_seller_ids": list(
                self.order_seller["late_handoff_seller_ids"]
            ),
            "delivered_late": self.delivery["delivered_late"],
            "delivered_within_estimate": self.delivery[
                "delivered_within_estimate"
            ],
            "payment_row_count": len(self.payment["rows"]),
            "payment_total_brl": self.payment["payment_total_brl"],
            "freight_total_brl": self.payment["freight_total_brl"],
            "reconciled": self.payment["reconciled"],
        }

