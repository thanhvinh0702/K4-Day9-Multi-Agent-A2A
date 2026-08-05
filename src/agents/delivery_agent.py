from __future__ import annotations

from src.utils import hours_between, is_after


class DeliveryAgent:
    name = "delivery_agent"

    def analyze(self, order: dict[str, str], order_facts: dict) -> dict:
        delivered_at = order["order_delivered_customer_date"] or None
        estimated_at = order["order_estimated_delivery_date"] or None
        carrier_at = order["order_delivered_carrier_date"] or None
        delivery_variance = hours_between(delivered_at or "", estimated_at or "")
        seller_analysis = []
        late_sellers = []
        for seller_id in order_facts["seller_ids"]:
            shipping_limit = order_facts["shipping_limits"].get(seller_id)
            variance = hours_between(carrier_at or "", shipping_limit or "")
            late = is_after(carrier_at, shipping_limit)
            seller_analysis.append(
                {
                    "seller_id": seller_id,
                    "shipping_limit_at": shipping_limit,
                    "handoff_variance_hours": variance,
                    "late_handoff": late,
                }
            )
            if late:
                late_sellers.append(seller_id)
        return {
            "delivered_at": delivered_at,
            "estimated_delivery_at": estimated_at,
            "carrier_handoff_at": carrier_at,
            "delivery_variance_hours": delivery_variance,
            "seller_handoff_analysis": seller_analysis,
            "late_handoff_seller_ids": late_sellers,
            "delivered_late": is_after(delivered_at, estimated_at),
        }
