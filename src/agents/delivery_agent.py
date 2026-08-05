from __future__ import annotations

from src.utils import hours_between, is_after


class DeliveryAgent:
    name = "delivery_agent"

    def analyze(self, order: dict[str, str]) -> dict:
        delivered_at = order["order_delivered_customer_date"] or None
        estimated_at = order["order_estimated_delivery_date"] or None
        carrier_at = order["order_delivered_carrier_date"] or None
        delivery_variance = hours_between(delivered_at or "", estimated_at or "")
        delivered_late = is_after(delivered_at, estimated_at)
        return {
            "delivered_at": delivered_at,
            "estimated_delivery_at": estimated_at,
            "carrier_handoff_at": carrier_at,
            "delivery_variance_hours": delivery_variance,
            "delivered_late": delivered_late,
            "delivered_within_estimate": bool(delivered_at and estimated_at)
            and not delivered_late,
        }
