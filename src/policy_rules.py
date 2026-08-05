"""Deterministic EC_POLICY_V2 rule engine (README.md section 4).

Pure function of the facts gathered by tools.gather_case_facts. No LLM
involved here on purpose: the classification is a lookup against a fixed
priority table, and doing it in code removes the risk of an LLM
misapplying priority order or inventing numbers.
"""
from __future__ import annotations

from typing import Any

ROOT_CAUSE_CODE = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}


def _pick_primary_issue(facts: dict[str, Any]) -> tuple[str, float, bool]:
    """Returns (primary_issue, confidence, used_fallback)."""
    order_status = facts["order_status"]
    payment_total = facts["payment_reconciliation"]["payment_total_brl"]
    reconciled = facts["payment_reconciliation"]["reconciled"]
    payment_count = facts["payment_count"]
    delivery_variance = facts["delivery_analysis"]["delivery_variance_hours"]
    late_seller_ids = facts["delivery_analysis"]["late_handoff_seller_ids"]

    is_late = delivery_variance is not None and delivery_variance > 0
    has_late_seller = len(late_seller_ids) > 0

    if order_status == "canceled" and payment_total > 0:
        return "canceled_order_paid", 0.97, False
    if order_status == "unavailable" and payment_total > 0:
        return "unavailable_order_paid", 0.97, False
    if is_late and has_late_seller:
        return "late_delivery_seller", 0.95, False
    if is_late and not has_late_seller:
        return "late_delivery_logistics", 0.95, False
    if payment_count >= 2 and reconciled is True:
        return "valid_split_payment", 0.95, False
    if delivery_variance is not None and delivery_variance <= 0 and reconciled is True:
        return "unsupported_late_claim", 0.95, False

    # Fallback for inputs the priority table does not explicitly cover
    # (e.g. order not yet delivered, or payment not reconciled and not late).
    # Kept deliberately conservative (no refund) and low-confidence so it is
    # easy to spot in trace.jsonl / manual review.
    if reconciled is True:
        return "unsupported_late_claim", 0.5, True
    return "unsupported_late_claim", 0.4, True


def _secondary_issues(facts: dict[str, Any]) -> list[str]:
    issues = []
    opc = facts["order_product_context"]
    if opc["item_count"] >= 2:
        issues.append("multi_item_order")
    if len(opc["all_seller_ids"]) >= 2:
        issues.append("multi_seller_order")
    if facts["payment_count"] >= 2:
        issues.append("split_payment")
    if len(facts["customer_context"]["related_order_ids"]) >= 1:
        issues.append("repeat_customer")
    if len(opc["category_names"]) >= 2:
        issues.append("multiple_categories")
    return issues


def _responsible_parties_and_refund(
    primary_issue: str, facts: dict[str, Any]
) -> tuple[list[dict[str, str]], float, str]:
    payment_total = facts["payment_reconciliation"]["payment_total_brl"]
    freight_total = facts["payment_reconciliation"]["freight_total_brl"]
    late_seller_ids = facts["delivery_analysis"]["late_handoff_seller_ids"]

    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return (
            [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
            round(payment_total, 2),
            "issue_full_refund",
        )
    if primary_issue == "late_delivery_seller":
        parties = [{"party_type": "seller", "party_id": sid} for sid in late_seller_ids[:3]]
        return parties, round(freight_total, 2), "refund_freight"
    if primary_issue == "late_delivery_logistics":
        return (
            [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}],
            round(freight_total, 2),
            "refund_freight",
        )
    if primary_issue == "valid_split_payment":
        return [], 0.0, "explain_valid_split_payment"
    return [], 0.0, "reject_late_refund"  # unsupported_late_claim


def _resolution_actions(
    primary_action: str, primary_issue: str, secondary_issues: list[str]
) -> list[str]:
    actions = [primary_action]
    if primary_issue == "late_delivery_seller":
        actions.append("review_seller_handoff")
    elif primary_issue == "late_delivery_logistics":
        actions.append("review_carrier_delay")
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        actions.append("verify_refund_completion")
    if "multi_seller_order" in secondary_issues:
        actions.append("coordinate_multi_seller_case")
    if "split_payment" in secondary_issues and primary_issue != "valid_split_payment":
        actions.append("verify_payment_allocation")
    return actions[:5]


def _evidence_ids(primary_issue: str, root_cause_code: str, facts: dict[str, Any]) -> list[str]:
    order_id = facts["order_id"]
    opc = facts["order_product_context"]
    late_seller_ids = facts["delivery_analysis"]["late_handoff_seller_ids"]

    ev = [f"order:{order_id}"]
    ev += [f"item:{iid}" for iid in opc["item_ids"]]
    ev += [f"payment:{pid}" for pid in facts["payment_ids"]]
    if primary_issue == "late_delivery_seller":
        ev += [f"seller:{sid}" for sid in late_seller_ids[:3]]
    ev.append(f"policy:{root_cause_code}")
    return ev[:20]


def apply_policy(facts: dict[str, Any]) -> dict[str, Any]:
    primary_issue, confidence, used_fallback = _pick_primary_issue(facts)
    secondary_issues = _secondary_issues(facts)
    root_cause_code = ROOT_CAUSE_CODE[primary_issue]
    responsible_parties, refund, primary_action = _responsible_parties_and_refund(
        primary_issue, facts
    )
    case_status = "action_required" if refund > 0 else "no_action"
    actions = _resolution_actions(primary_action, primary_issue, secondary_issues)
    evidence_ids = _evidence_ids(primary_issue, root_cause_code, facts)

    return {
        "case_assessment": {
            "primary_issue": primary_issue,
            "secondary_issues": secondary_issues,
            "case_status": case_status,
            "confidence": confidence,
        },
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": root_cause_code, "rank": 1}],
            "responsible_parties": responsible_parties[:3],
        },
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": round(refund, 2),
        },
        "resolution_actions": actions,
        "evidence_ids": evidence_ids,
        "_used_fallback": used_fallback,
    }
