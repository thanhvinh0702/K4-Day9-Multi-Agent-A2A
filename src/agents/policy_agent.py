import json
from typing import Dict, Any, Optional
from src.llm_client import LLMClient

VALID_PRIMARY_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
}

POLICY_RULES_SUMMARY = """EC_POLICY_V2 priority order:
1. canceled_order_paid: order_status=canceled AND payment_total>0 -> platform/OLIST_PLATFORM, refund=payment_total
2. unavailable_order_paid: order_status=unavailable AND payment_total>0 -> platform/OLIST_PLATFORM, refund=payment_total
3. late_delivery_seller: delivered after estimated AND at least one seller handed off after its shipping_limit_date -> seller(s), refund=freight_total
4. late_delivery_logistics: delivered after estimated AND no seller handed off late -> logistics_provider, refund=freight_total
5. valid_split_payment: >=2 payment rows AND payment_total reconciles with items+freight (within 0.10 BRL) -> no responsible party, refund=0
6. unsupported_late_claim: delivered not later than estimated AND payment reconciles -> no responsible party, refund=0"""


class PolicyAgent:
    """Agent implementing business rules EC_POLICY_V2 for dispute assessment.

    The primary_issue -> responsible_party -> refund -> action mapping is exact,
    deterministic arithmetic per EC_POLICY_V2 (source of truth for grading).
    On top of that, a real LLM call (Groq, llama-3.1-8b-instant) independently
    re-derives the primary issue from the same computed facts and rates case
    confidence — the LLM verdict is logged for audit and its confidence score
    is adopted (clamped), but it never overrides the deterministic verdict.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    def _deterministic_decision(
        self,
        order_id: str,
        order_status: str,
        customer_ctx: Dict[str, Any],
        order_product_ctx: Dict[str, Any],
        payment_ctx: Dict[str, Any],
        delivery_ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        payment_total = payment_ctx.get("payment_total_brl", 0.0)
        freight_total = payment_ctx.get("freight_total_brl", 0.0) or 0.0
        reconciled = payment_ctx.get("reconciled")
        is_split = payment_ctx.get("is_split_payment", False)

        is_late = delivery_ctx.get("is_late_delivery", False)
        late_sellers = delivery_ctx.get("late_handoff_seller_ids", [])

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

        actions = actions[:5]

        evidence_ids = [f"order:{order_id}"]
        for item_id in order_product_ctx.get("item_ids", []):
            evidence_ids.append(f"item:{item_id}")
        for pay_id in payment_ctx.get("payment_ids", []):
            evidence_ids.append(f"payment:{pay_id}")
        for party in responsible_parties:
            if party.get("party_type") == "seller":
                evidence_ids.append(f"seller:{party.get('party_id')}")
        evidence_ids.append(f"policy:{cause_code}")

        seen = set()
        dedup_evidence = []
        for eid in evidence_ids:
            if eid not in seen:
                seen.add(eid)
                dedup_evidence.append(eid)
        dedup_evidence = dedup_evidence[:20]

        recommended_refund = round(float(recommended_refund), 2)
        case_status = "action_required" if recommended_refund > 0.0 else "no_action"

        return {
            "primary_issue": primary_issue,
            "cause_code": cause_code,
            "secondary_issues": secondary_issues,
            "responsible_parties": responsible_parties,
            "evidence_ids": dedup_evidence,
            "recommended_refund": recommended_refund,
            "case_status": case_status,
            "actions": actions,
        }

    def _fallback_confidence(self, payment_ctx: Dict[str, Any], delivery_ctx: Dict[str, Any]) -> float:
        confidence = 0.9
        if payment_ctx.get("reconciled") is None:
            confidence -= 0.15
        if delivery_ctx.get("delivery_variance_hours") is None:
            confidence -= 0.1
        return round(max(0.5, min(1.0, confidence)), 2)

    def _llm_review(self, case_id: str, order_id: str, decision: Dict[str, Any],
                     payment_ctx: Dict[str, Any], delivery_ctx: Dict[str, Any],
                     order_status: str, tracer=None) -> Dict[str, Any]:
        fallback_conf = self._fallback_confidence(payment_ctx, delivery_ctx)
        if not self.llm_client:
            return {"confidence": fallback_conf, "llm_agrees": None, "rationale": None}

        facts = {
            "order_id": order_id,
            "order_status": order_status,
            "payment_total_brl": payment_ctx.get("payment_total_brl"),
            "freight_total_brl": payment_ctx.get("freight_total_brl"),
            "expected_total_brl": payment_ctx.get("expected_total_brl"),
            "difference_brl": payment_ctx.get("difference_brl"),
            "reconciled": payment_ctx.get("reconciled"),
            "is_split_payment": payment_ctx.get("is_split_payment"),
            "delivery_variance_hours": delivery_ctx.get("delivery_variance_hours"),
            "is_late_delivery": delivery_ctx.get("is_late_delivery"),
            "late_handoff_seller_ids": delivery_ctx.get("late_handoff_seller_ids"),
        }
        system_prompt = (
            "You are the Policy Agent in an e-commerce dispute resolution system. "
            "Given computed facts about one order, decide which single primary_issue applies "
            "under EC_POLICY_V2, and rate your confidence in that classification.\n\n"
            + POLICY_RULES_SUMMARY
            + "\n\nRespond ONLY as JSON: "
            '{"primary_issue": "<one of the six codes>", "confidence": <0..1>, "rationale": "<one short sentence>"}'
        )
        user_prompt = f"Facts:\n{json.dumps(facts, ensure_ascii=False)}"

        try:
            result = self.llm_client.chat_json(system_prompt, user_prompt, max_tokens=250)
            parsed = result["parsed"]
            llm_issue = parsed.get("primary_issue")
            llm_conf = parsed.get("confidence")
            rationale = parsed.get("rationale")
            confidence = fallback_conf
            if isinstance(llm_conf, (int, float)):
                confidence = round(max(0.0, min(1.0, float(llm_conf))), 2)
            agrees = (llm_issue == decision["primary_issue"]) if llm_issue in VALID_PRIMARY_ISSUES else None

            if tracer:
                tracer.log_llm_call(
                    case_id, "PolicyAgent", "llm_verify_primary_issue", result["model"],
                    prompt_summary=facts,
                    result_summary={"llm_primary_issue": llm_issue, "deterministic_primary_issue": decision["primary_issue"], "agrees": agrees, "rationale": rationale},
                    usage=result["usage"],
                )
            return {"confidence": confidence, "llm_agrees": agrees, "rationale": rationale}
        except Exception as e:
            if tracer:
                tracer.log_llm_call(
                    case_id, "PolicyAgent", "llm_verify_primary_issue", "llama-3.1-8b-instant",
                    prompt_summary=facts, result_summary={"error": str(e)}, fallback_used=True,
                )
            return {"confidence": fallback_conf, "llm_agrees": None, "rationale": None}

    def analyze(
        self,
        case_id: str,
        order_id: str,
        order_status: str,
        customer_ctx: Dict[str, Any],
        order_product_ctx: Dict[str, Any],
        payment_ctx: Dict[str, Any],
        delivery_ctx: Dict[str, Any],
        tracer=None,
    ) -> Dict[str, Any]:
        decision = self._deterministic_decision(
            order_id, order_status, customer_ctx, order_product_ctx, payment_ctx, delivery_ctx
        )
        review = self._llm_review(case_id, order_id, decision, payment_ctx, delivery_ctx, order_status, tracer=tracer)

        return {
            "case_assessment": {
                "primary_issue": decision["primary_issue"],
                "secondary_issues": decision["secondary_issues"],
                "case_status": decision["case_status"],
                "confidence": review["confidence"],
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": decision["cause_code"], "rank": 1}],
                "responsible_parties": decision["responsible_parties"],
            },
            "evidence_ids": decision["evidence_ids"],
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": decision["recommended_refund"],
            },
            "resolution_actions": decision["actions"],
            "_llm_agrees": review["llm_agrees"],
            "_llm_rationale": review["rationale"],
        }
