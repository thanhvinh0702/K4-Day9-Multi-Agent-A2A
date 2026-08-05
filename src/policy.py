from __future__ import annotations


POLICY = {
    "canceled_order_paid": {
        "cause": "ORDER_CANCELED_AFTER_PAYMENT",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "action": "issue_full_refund",
    },
    "unavailable_order_paid": {
        "cause": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "action": "issue_full_refund",
    },
    "late_delivery_seller": {
        "cause": "SELLER_HANDOFF_AFTER_LIMIT",
        "party_type": "seller",
        "action": "refund_freight",
    },
    "late_delivery_logistics": {
        "cause": "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "party_type": "logistics_provider",
        "party_id": "LOGISTICS_PROVIDER",
        "action": "refund_freight",
    },
    "valid_split_payment": {
        "cause": "MULTIPLE_PAYMENTS_RECONCILED",
        "action": "explain_valid_split_payment",
    },
    "unsupported_late_claim": {
        "cause": "DELIVERY_WITHIN_ESTIMATE",
        "action": "reject_late_refund",
    },
}


class PolicyAgent:
    name = "policy_agent"

    def decide(
        self,
        order: dict[str, str],
        customer: dict,
        order_facts: dict,
        payment: dict,
        delivery: dict,
    ) -> dict:
        status = order["order_status"]
        paid = payment["payment_total"] > 0
        if status == "canceled" and paid:
            issue = "canceled_order_paid"
        elif status == "unavailable" and paid:
            issue = "unavailable_order_paid"
        elif delivery["delivered_late"] and delivery["late_handoff_seller_ids"]:
            issue = "late_delivery_seller"
        elif delivery["delivered_late"]:
            issue = "late_delivery_logistics"
        elif payment["split_payment"] and payment["reconciled"] is True:
            issue = "valid_split_payment"
        elif not delivery["delivered_late"] and payment["reconciled"] is True:
            issue = "unsupported_late_claim"
        else:
            raise ValueError(
                f"No EC_POLICY_V2 primary issue matches order {order['order_id']}"
            )

        secondary = []
        if order_facts["multi_item_order"]:
            secondary.append("multi_item_order")
        if order_facts["multi_seller_order"]:
            secondary.append("multi_seller_order")
        if payment["split_payment"]:
            secondary.append("split_payment")
        if customer["repeat_customer"]:
            secondary.append("repeat_customer")
        if order_facts["multiple_categories"]:
            secondary.append("multiple_categories")

        spec = POLICY[issue]
        if issue in {"canceled_order_paid", "unavailable_order_paid"}:
            refund = payment["payment_total_brl"]
        elif issue in {"late_delivery_seller", "late_delivery_logistics"}:
            refund = order_facts["freight_total_brl"]
        else:
            refund = 0.0

        if issue == "late_delivery_seller":
            parties = [
                {"party_type": "seller", "party_id": seller_id}
                for seller_id in delivery["late_handoff_seller_ids"][:3]
            ]
        elif "party_type" in spec:
            parties = [
                {
                    "party_type": spec["party_type"],
                    "party_id": spec["party_id"],
                }
            ]
        else:
            parties = []

        actions = [spec["action"]]
        if issue == "late_delivery_seller":
            actions.append("review_seller_handoff")
        elif issue == "late_delivery_logistics":
            actions.append("review_carrier_delay")
        if refund > 0:
            actions.append("verify_refund_completion")
        if order_facts["multi_seller_order"]:
            actions.append("coordinate_multi_seller_case")
        if payment["split_payment"] and issue != "valid_split_payment":
            actions.append("verify_payment_allocation")

        return {
            "primary_issue": issue,
            "secondary_issues": secondary,
            "case_status": "action_required" if refund > 0 else "no_action",
            "confidence": 1.0,
            "cause_code": spec["cause"],
            "responsible_parties": parties,
            "recommended_refund_brl": refund,
            "actions": actions[:5],
        }

