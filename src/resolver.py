from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from src.agents.delivery_agent import DeliveryAgent
from src.agents.order_seller_agent import OrderSellerAgent
from src.agents.payment_agent import PaymentAgent
from src.datastore import OlistDataStore
from src.contracts import CaseFactBundle
from src.openrouter_policy import OpenRouterPolicyAgent
from src.policy import DeterministicPolicyAgent
from src.trace import TraceWriter
from src.verifier import VerifierAgent, normalize_llm_decision


def _customer_context(store: OlistDataStore, order: dict[str, str]) -> dict:
    customer = store.customers.get(order["customer_id"])
    if not customer:
        raise ValueError(f"Customer not found: {order['customer_id']}")
    unique_id = customer["customer_unique_id"]
    related = [
        order_id
        for order_id in store.orders_by_customer_unique.get(unique_id, [])
        if order_id != order["order_id"]
    ]
    return {
        "customer_unique_id": unique_id,
        "related_order_ids": related[:5],
        "repeat_customer": bool(related),
    }


def resolve_case(
    case: dict,
    store: OlistDataStore,
    trace: TraceWriter,
    openrouter_policy: OpenRouterPolicyAgent,
) -> tuple[dict, dict]:
    """Coordinator function: initialize agents and resolve exactly one case."""
    case_id = case["case_id"]
    if case.get("policy_version") != "EC_POLICY_V2":
        raise ValueError(f"Unsupported policy in {case_id}")
    order_id = case["customer_request"]["claimed_order_id"]
    order = store.orders.get(order_id)
    if not order:
        raise ValueError(f"Order not found for {case_id}: {order_id}")

    order_agent = OrderSellerAgent(store)
    payment_agent = PaymentAgent(store)
    delivery_agent = DeliveryAgent()
    deterministic_agent = DeterministicPolicyAgent()
    verifier_agent = VerifierAgent(store)

    task = {"order_id": order_id, "policy_version": case["policy_version"]}
    for agent in (order_agent, payment_agent, delivery_agent):
        trace.handoff(case_id, "coordinator", agent.name, task)

    with ThreadPoolExecutor(max_workers=3) as pool:
        order_future = pool.submit(order_agent.analyze, order)
        payment_future = pool.submit(payment_agent.analyze, order_id)
        delivery_future = pool.submit(delivery_agent.analyze, order)
        order_seller = order_future.result()
        payment = payment_future.result()
        delivery = delivery_future.result()

    trace.handoff(
        case_id,
        order_agent.name,
        "fact_bundle_builder",
        {
            "order_status": order_seller["order_status"],
            "seller_ids": order_seller["seller_ids"],
            "item_ids": order_seller["item_ids"],
            "late_handoff_item_ids": order_seller["late_handoff_item_ids"],
            "late_handoff_seller_ids": order_seller["late_handoff_seller_ids"],
        },
    )

    trace.handoff(
        case_id,
        payment_agent.name,
        "fact_bundle_builder",
        {
            "item_total_brl": payment["item_total_brl"],
            "freight_total_brl": payment["freight_total_brl"],
            "payment_total_brl": payment["payment_total_brl"],
            "difference_brl": payment["difference_brl"],
            "reconciled": payment["reconciled"],
            "payment_row_count": len(payment["rows"]),
        },
    )

    trace.handoff(
        case_id,
        delivery_agent.name,
        "fact_bundle_builder",
        {
            "delivered_at": delivery["delivered_at"],
            "estimated_delivery_at": delivery["estimated_delivery_at"],
            "delivery_variance_hours": delivery["delivery_variance_hours"],
            "delivered_late": delivery["delivered_late"],
            "delivered_within_estimate": delivery["delivered_within_estimate"],
        },
    )

    customer = _customer_context(store, order)
    facts = CaseFactBundle(
        case_id=case_id,
        order_seller=order_seller,
        payment=payment,
        delivery=delivery,
        customer=customer,
    )
    policy_facts = facts.policy_facts()
    trace.handoff(
        case_id, "fact_bundle_builder", deterministic_agent.name, policy_facts
    )
    trace.handoff(
        case_id, "fact_bundle_builder", openrouter_policy.name, policy_facts
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        deterministic_future = pool.submit(deterministic_agent.decide, facts)
        llm_future = pool.submit(openrouter_policy.propose, case_id, policy_facts)
        deterministic = deterministic_future.result()
        llm_decision, llm_error = llm_future.result()

    trace.handoff(
        case_id,
        deterministic_agent.name,
        "policy_comparator",
        {
            "primary_issue": deterministic["primary_issue"],
            "cause_code": deterministic["cause_code"],
            "responsible_parties": deterministic["responsible_parties"],
            "recommended_refund_brl": deterministic["recommended_refund_brl"],
            "primary_action": deterministic["actions"][0],
        },
    )
    trace.handoff(
        case_id,
        openrouter_policy.name,
        "policy_comparator",
        {"decision": llm_decision, "error": llm_error},
    )
    normalized, llm_matched = normalize_llm_decision(deterministic, llm_decision)
    trace.policy_comparison(
        case_id=case_id,
        deterministic=deterministic,
        llm_decision=llm_decision,
        matched=llm_matched,
        fallback_reason=llm_error,
    )

    trace.handoff(
        case_id,
        "policy_comparator",
        verifier_agent.name,
        {
            "primary_issue": normalized["primary_issue"],
            "decision_source": "llm_confidence_only" if llm_matched else "deterministic",
        },
    )
    output = verifier_agent.build_output(
        case, order_seller, payment, delivery, customer, normalized
    )
    trace.handoff(
        case_id,
        verifier_agent.name,
        "coordinator",
        {"valid": True, "llm_matched": llm_matched},
    )
    return output, {
        "llm_matched": llm_matched,
        "llm_fallback": llm_decision is None or not llm_matched,
        "llm_unavailable": llm_error == "missing_api_key_or_llm_disabled",
        "llm_request_failed": llm_decision is None
        and llm_error != "missing_api_key_or_llm_disabled",
        "llm_policy_mismatch": llm_decision is not None and not llm_matched,
    }
