"""LangGraph orchestrator (the Coordinator).

Fan-out: the four domain agents (Customer, Order&Product, Payment, Delivery)
run in parallel from START, each touching only its own slice of the CSVs.
Fan-in: LangGraph waits for all four before running the Policy Agent, which
is the actual "handoff" point - policy_agent only sees the merged dossier
already sitting in shared state, never touches the CSVs directly.
The graph ends with a deterministic assemble step and the Verifier gate.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from .agents import (
    run_customer_agent,
    run_delivery_agent,
    run_order_product_agent,
    run_payment_agent,
    run_policy_agent,
)
from .trace_logger import TraceLogger
from .verifier import verify_and_fix


class CaseState(TypedDict, total=False):
    case_id: str
    claimed_order_id: str
    customer_fragment: dict[str, Any]
    order_product_fragment: dict[str, Any]
    payment_fragment: dict[str, Any]
    delivery_fragment: dict[str, Any]
    policy_fragment: dict[str, Any]
    assembled: dict[str, Any]
    final_output: dict[str, Any]


def build_graph(llm: ChatOpenAI, trace: TraceLogger):
    def node_customer(state: CaseState) -> dict:
        frag = run_customer_agent(llm, trace, state["case_id"], state["claimed_order_id"])
        return {"customer_fragment": frag.model_dump()}

    def node_order_product(state: CaseState) -> dict:
        frag = run_order_product_agent(llm, trace, state["case_id"], state["claimed_order_id"])
        return {"order_product_fragment": frag.model_dump()}

    def node_payment(state: CaseState) -> dict:
        frag = run_payment_agent(llm, trace, state["case_id"], state["claimed_order_id"])
        return {"payment_fragment": frag.model_dump()}

    def node_delivery(state: CaseState) -> dict:
        frag = run_delivery_agent(llm, trace, state["case_id"], state["claimed_order_id"])
        return {"delivery_fragment": frag.model_dump()}

    def node_policy(state: CaseState) -> dict:
        trace.log_event(
            case_id=state["case_id"],
            event_type="handoff",
            agent="coordinator",
            message="domain agent fragments merged, handing dossier off to policy_agent",
            fragments=list(
                filter(
                    None,
                    [
                        "customer_fragment" in state and "customer_context",
                        "order_product_fragment" in state and "order_product_context",
                        "payment_fragment" in state and "payment_reconciliation",
                        "delivery_fragment" in state and "delivery_analysis",
                    ],
                )
            ),
        )
        frag = run_policy_agent(llm, trace, state["case_id"], state["claimed_order_id"])
        return {"policy_fragment": frag.model_dump()}

    def node_assemble(state: CaseState) -> dict:
        cf = state["customer_fragment"]
        opf = state["order_product_fragment"]
        pf = state["payment_fragment"]
        df = state["delivery_fragment"]
        polf = state["policy_fragment"]
        assembled = {
            "case_id": state["case_id"],
            "case_assessment": polf["case_assessment"],
            "affected_entities": {
                "order_ids": opf["order_ids"],
                "item_ids": opf["item_ids"],
                "seller_ids": opf["seller_ids"],
                "payment_ids": pf["payment_ids"],
            },
            "customer_context": cf,
            "product_context": {
                "product_ids": opf["product_ids"],
                "category_names": opf["category_names"],
            },
            "delivery_analysis": df,
            "payment_reconciliation": pf["payment_reconciliation"],
            "root_cause_analysis": polf["root_cause_analysis"],
            "evidence_ids": polf["evidence_ids"],
            "financial_resolution": polf["financial_resolution"],
            "resolution_actions": polf["resolution_actions"],
        }
        return {"assembled": assembled}

    def node_verify(state: CaseState) -> dict:
        final = verify_and_fix(
            trace, state["case_id"], state["claimed_order_id"], state["assembled"]
        )
        return {"final_output": final}

    graph = StateGraph(CaseState)
    graph.add_node("customer_agent", node_customer)
    graph.add_node("order_product_agent", node_order_product)
    graph.add_node("payment_agent", node_payment)
    graph.add_node("delivery_agent", node_delivery)
    graph.add_node("policy_agent", node_policy)
    graph.add_node("assemble", node_assemble)
    graph.add_node("verify", node_verify)

    for domain_node in ("customer_agent", "order_product_agent", "payment_agent", "delivery_agent"):
        graph.add_edge(START, domain_node)
        graph.add_edge(domain_node, "policy_agent")
    graph.add_edge("policy_agent", "assemble")
    graph.add_edge("assemble", "verify")
    graph.add_edge("verify", END)

    return graph.compile()
