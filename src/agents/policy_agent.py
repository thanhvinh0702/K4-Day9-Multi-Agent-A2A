from typing import Dict, Any, List

class PolicyAgent:
    """Agent implementing business rules EC_POLICY_V2 for dispute assessment."""

    def analyze(
        self,
        order_id: str,
        order_status: str,
        customer_ctx: Dict[str, Any],
        order_product_ctx: Dict[str, Any],
        payment_ctx: Dict[str, Any],
        delivery_ctx: Dict[str, Any]
    ) -> Dict[str, Any]:

        # Extracted Contexts
        payment_total = payment_ctx.get("payment_total_brl", 0.0)
        freight_total = payment_ctx.get("freight_total_brl", 0.0) or 0.0
        reconciled = payment_ctx.get("reconciled")
        is_split = payment_ctx.get("is_split_payment", False)

        is_late = delivery_ctx.get("is_late_delivery", False)
        late_sellers = delivery_ctx.get("late_handoff_seller_ids", [])

        # 1. Determine Primary Issue
        primary_issue = None
        cause_code = None
        responsible_parties = []
        recommended_refund = 0.0
        primary_action = None

        if order_status == "canceled" and payment_total > 0:
            primary_issue = "canceled_order_paid"
            cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
            recommended_refund = payment_total
            primary_action = "issue_full_refund"

        elif order_status == "unavailable" and payment_total > 0:
            primary_issue = "unavailable_order_paid"
            cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
            recommended_refund = payment_total
            primary_action = "issue_full_refund"

        elif is_late and len(late_sellers) > 0:
            primary_issue = "late_delivery_seller"
            cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
            responsible_parties = [{"party_type": "seller", "party_id": sid} for sid in late_sellers[:3]]
            recommended_refund = freight_total
            primary_action = "refund_freight"

        elif is_late and len(late_sellers) == 0:
            primary_issue = "late_delivery_logistics"
            cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
            responsible_parties = [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]
            recommended_refund = freight_total
            primary_action = "refund_freight"

        elif is_split and reconciled is True:
            primary_issue = "valid_split_payment"
            cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
            responsible_parties = []
            recommended_refund = 0.0
            primary_action = "explain_valid_split_payment"

        else:
            primary_issue = "unsupported_late_claim"
            cause_code = "DELIVERY_WITHIN_ESTIMATE"
            responsible_parties = []
            recommended_refund = 0.0
            primary_action = "reject_late_refund"

        # 2. Determine Secondary Issues (Exact business rule order)
        secondary_issues = []
        if order_product_ctx.get("is_multi_item"):
            secondary_issues.append("multi_item_order")
        if order_product_ctx.get("is_multi_seller"):
            secondary_issues.append("multi_seller_order")
        if payment_ctx.get("is_split_payment"):
            secondary_issues.append("split_payment")
        if customer_ctx.get("has_repeat_orders"):
            secondary_issues.append("repeat_customer")
        if order_product_ctx.get("has_multiple_categories"):
            secondary_issues.append("multiple_categories")

        # 3. Determine Resolution Actions (Exact business rule order)
        actions = [primary_action]
        if len(late_sellers) > 0:
            if "review_seller_handoff" not in actions:
                actions.append("review_seller_handoff")
        elif is_late and len(late_sellers) == 0:
            if "review_carrier_delay" not in actions:
                actions.append("review_carrier_delay")

        if recommended_refund > 0.0:
            if "verify_refund_completion" not in actions:
                actions.append("verify_refund_completion")

        if order_product_ctx.get("is_multi_seller"):
            if "coordinate_multi_seller_case" not in actions:
                actions.append("coordinate_multi_seller_case")

        if is_split and primary_issue != "valid_split_payment":
            if "verify_payment_allocation" not in actions:
                actions.append("verify_payment_allocation")

        # Limit actions to max 5
        actions = actions[:5]

        # 4. Generate Evidence IDs
        evidence_ids = [f"order:{order_id}"]
        for item_id in order_product_ctx.get("item_ids", []):
            evidence_ids.append(f"item:{item_id}")
        for pay_id in payment_ctx.get("payment_ids", []):
            evidence_ids.append(f"payment:{pay_id}")
        for party in responsible_parties:
            if party.get("party_type") == "seller":
                evidence_ids.append(f"seller:{party.get('party_id')}")
        evidence_ids.append(f"policy:{cause_code}")
        
        # Deduplicate and limit to max 20 evidence IDs
        seen = set()
        dedup_evidence = []
        for eid in evidence_ids:
            if eid not in seen:
                seen.add(eid)
                dedup_evidence.append(eid)
        dedup_evidence = dedup_evidence[:20]

        # 5. Financial Resolution & Case Status
        recommended_refund = round(float(recommended_refund), 2)
        case_status = "action_required" if recommended_refund > 0.0 else "no_action"
        confidence = 0.95

        return {
            "case_assessment": {
                "primary_issue": primary_issue,
                "secondary_issues": secondary_issues,
                "case_status": case_status,
                "confidence": confidence
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": cause_code, "rank": 1}],
                "responsible_parties": responsible_parties
            },
            "evidence_ids": dedup_evidence,
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": recommended_refund
            },
            "resolution_actions": actions
        }
