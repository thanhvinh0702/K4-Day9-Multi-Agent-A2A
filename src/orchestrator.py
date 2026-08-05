from __future__ import annotations

from src.agents.customer_agent import CustomerAgent
from src.agents.delivery_agent import DeliveryAgent
from src.agents.order_product_agent import OrderProductAgent
from src.agents.payment_agent import PaymentAgent
from src.datastore import OlistDataStore
from src.policy import PolicyAgent
from src.trace import TraceWriter
from src.verifier import VerifierAgent


class CoordinatorAgent:
    name = "coordinator_agent"

    def __init__(self, store: OlistDataStore, trace: TraceWriter):
        self.store = store
        self.trace = trace
        self.customer_agent = CustomerAgent(store)
        self.order_agent = OrderProductAgent(store)
        self.payment_agent = PaymentAgent(store)
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent(store)

    def process(self, case: dict) -> dict:
        case_id = case["case_id"]
        if case.get("policy_version") != "EC_POLICY_V2":
            raise ValueError(f"Unsupported policy in {case_id}")
        order_id = case["customer_request"]["claimed_order_id"]
        order = self.store.orders.get(order_id)
        if not order:
            raise ValueError(f"Order not found for {case_id}: {order_id}")

        self.trace.handoff(case_id, self.name, "domain_agents", {"order_id": order_id})
        customer = self.customer_agent.investigate(order)
        self.trace.handoff(
            case_id,
            self.customer_agent.name,
            self.name,
            {"related_order_count": len(customer["related_order_ids"])},
        )
        order_facts = self.order_agent.investigate(order)
        self.trace.handoff(
            case_id,
            self.order_agent.name,
            self.payment_agent.name,
            {
                "item_count": len(order_facts["items"]),
                "seller_count": len(order_facts["seller_ids"]),
            },
        )
        payment = self.payment_agent.reconcile(order_id, order_facts)
        self.trace.handoff(
            case_id,
            self.payment_agent.name,
            self.policy_agent.name,
            {
                "payment_total_brl": payment["payment_total_brl"],
                "reconciled": payment["reconciled"],
            },
        )
        delivery = self.delivery_agent.analyze(order, order_facts)
        self.trace.handoff(
            case_id,
            self.delivery_agent.name,
            self.policy_agent.name,
            {
                "delivery_variance_hours": delivery["delivery_variance_hours"],
                "late_handoff_seller_ids": delivery["late_handoff_seller_ids"],
            },
        )
        decision = self.policy_agent.decide(
            order, customer, order_facts, payment, delivery
        )
        self.trace.handoff(
            case_id,
            self.policy_agent.name,
            self.name,
            {
                "primary_issue": decision["primary_issue"],
                "recommended_refund_brl": decision["recommended_refund_brl"],
            },
        )
        output = self._assemble(
            case, order_facts, customer, payment, delivery, decision
        )
        verification = self.verifier_agent.verify(case, output)
        self.trace.handoff(
            case_id, self.verifier_agent.name, self.name, verification
        )
        return output

    @staticmethod
    def _assemble(
        case: dict,
        order_facts: dict,
        customer: dict,
        payment: dict,
        delivery: dict,
        decision: dict,
    ) -> dict:
        order_id = case["customer_request"]["claimed_order_id"]
        cause = decision["cause_code"]
        item_ids = order_facts["item_ids"][:5]
        payment_ids = payment["payment_ids"][:5]
        affected_sellers = order_facts["seller_ids"][:3]
        evidence = [f"order:{order_id}"]
        evidence.extend(f"item:{value}" for value in item_ids)
        evidence.extend(f"payment:{value}" for value in payment_ids)
        if decision["primary_issue"] == "late_delivery_seller":
            evidence.extend(
                f"seller:{seller_id}"
                for seller_id in delivery["late_handoff_seller_ids"][:3]
            )
        evidence.append(f"policy:{cause}")
        return {
            "case_id": case["case_id"],
            "case_assessment": {
                "primary_issue": decision["primary_issue"],
                "secondary_issues": decision["secondary_issues"],
                "case_status": decision["case_status"],
                "confidence": decision["confidence"],
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids,
                "seller_ids": affected_sellers,
                "payment_ids": payment_ids,
            },
            "customer_context": {
                "customer_unique_id": customer["customer_unique_id"],
                "related_order_ids": customer["related_order_ids"],
            },
            "product_context": {
                "product_ids": order_facts["product_ids"][:5],
                "category_names": order_facts["category_names"][:5],
            },
            "delivery_analysis": {
                key: delivery[key]
                for key in (
                    "delivered_at",
                    "estimated_delivery_at",
                    "carrier_handoff_at",
                    "delivery_variance_hours",
                    "seller_handoff_analysis",
                    "late_handoff_seller_ids",
                )
            },
            "payment_reconciliation": {
                "currency": "BRL",
                "item_total_brl": order_facts["item_total_brl"],
                "freight_total_brl": order_facts["freight_total_brl"],
                "expected_total_brl": payment["expected_total_brl"],
                "payment_total_brl": payment["payment_total_brl"],
                "difference_brl": payment["difference_brl"],
                "reconciled": payment["reconciled"],
                "payment_types": payment["payment_types"],
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": cause, "rank": 1}],
                "responsible_parties": decision["responsible_parties"],
            },
            "evidence_ids": evidence[:20],
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": decision["recommended_refund_brl"],
            },
            "resolution_actions": decision["actions"],
        }

