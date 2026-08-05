from typing import Dict, Any
from src.data_loader import DataLoader
from src.agents.customer_agent import CustomerAgent
from src.agents.order_product_agent import OrderProductAgent
from src.agents.payment_agent import PaymentAgent
from src.agents.delivery_agent import DeliveryAgent
from src.agents.policy_agent import PolicyAgent
from src.agents.verifier_agent import VerifierAgent
from src.tracer import Tracer

class CoordinatorAgent:
    """Master Coordinator Agent that orchestrates multi-agent investigation and output generation."""

    def __init__(self, data_loader: DataLoader, tracer: Tracer):
        self.data_loader = data_loader
        self.tracer = tracer

        self.customer_agent = CustomerAgent(data_loader)
        self.order_product_agent = OrderProductAgent(data_loader)
        self.payment_agent = PaymentAgent(data_loader)
        self.delivery_agent = DeliveryAgent(data_loader)
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()

    def process_case(self, case_input: Dict[str, Any]) -> Dict[str, Any]:
        case_id = case_input.get("case_id")
        cust_req = case_input.get("customer_request", {})
        claimed_order_id = cust_req.get("claimed_order_id")

        # 1. Fetch main order record
        order_info = self.data_loader.get_order(claimed_order_id)
        if not order_info:
            order_info = {
                "order_id": claimed_order_id,
                "customer_id": "",
                "order_status": "unknown"
            }

        customer_id = str(order_info.get("customer_id", ""))
        order_status = str(order_info.get("order_status", ""))

        # Agent Handoff 1: Customer Agent
        self.tracer.log_step(case_id, "CustomerAgent", "lookup_identity", {"customer_id": customer_id}, "started")
        customer_ctx = self.customer_agent.analyze(customer_id, claimed_order_id)
        self.tracer.log_step(case_id, "CustomerAgent", "lookup_identity_complete", {}, {"related_orders_count": len(customer_ctx["related_order_ids"])})

        # Agent Handoff 2: Order & Product Agent
        self.tracer.log_step(case_id, "OrderProductAgent", "extract_items_and_products", {"claimed_order_id": claimed_order_id}, "started")
        op_ctx = self.order_product_agent.analyze(claimed_order_id)
        self.tracer.log_step(case_id, "OrderProductAgent", "extract_complete", {}, {"items_count": len(op_ctx["items"])})

        # Agent Handoff 3: Payment Agent
        self.tracer.log_step(case_id, "PaymentAgent", "reconcile_payments", {"claimed_order_id": claimed_order_id}, "started")
        payment_ctx = self.payment_agent.analyze(claimed_order_id, op_ctx["items"])
        self.tracer.log_step(case_id, "PaymentAgent", "reconcile_complete", {}, {"reconciled": payment_ctx["reconciled"]})

        # Agent Handoff 4: Delivery Agent
        self.tracer.log_step(case_id, "DeliveryAgent", "audit_delivery_and_handoff", {"claimed_order_id": claimed_order_id}, "started")
        delivery_ctx = self.delivery_agent.analyze(order_info, op_ctx["items"])
        self.tracer.log_step(case_id, "DeliveryAgent", "audit_complete", {}, {"is_late": delivery_ctx["is_late_delivery"]})

        # Agent Handoff 5: Policy Agent
        self.tracer.log_step(case_id, "PolicyAgent", "evaluate_policy_rules", {"policy_version": "EC_POLICY_V2"}, "started")
        policy_out = self.policy_agent.analyze(
            claimed_order_id,
            order_status,
            customer_ctx,
            op_ctx,
            payment_ctx,
            delivery_ctx
        )
        self.tracer.log_step(case_id, "PolicyAgent", "evaluation_complete", {}, {"primary_issue": policy_out["case_assessment"]["primary_issue"]})

        # Assemble full raw output dictionary
        raw_output = {
            "case_id": case_id,
            "case_assessment": policy_out["case_assessment"],
            "affected_entities": {
                "order_ids": [claimed_order_id],
                "item_ids": op_ctx["item_ids"],
                "seller_ids": op_ctx["seller_ids"],
                "payment_ids": payment_ctx["payment_ids"]
            },
            "customer_context": {
                "customer_unique_id": customer_ctx["customer_unique_id"],
                "related_order_ids": customer_ctx["related_order_ids"]
            },
            "product_context": {
                "product_ids": op_ctx["product_ids"],
                "category_names": op_ctx["category_names"]
            },
            "delivery_analysis": {
                "delivered_at": delivery_ctx["delivered_at"],
                "estimated_delivery_at": delivery_ctx["estimated_delivery_at"],
                "carrier_handoff_at": delivery_ctx["carrier_handoff_at"],
                "delivery_variance_hours": delivery_ctx["delivery_variance_hours"],
                "seller_handoff_analysis": delivery_ctx["seller_handoff_analysis"],
                "late_handoff_seller_ids": delivery_ctx["late_handoff_seller_ids"]
            },
            "payment_reconciliation": {
                "currency": payment_ctx["currency"],
                "item_total_brl": payment_ctx["item_total_brl"],
                "freight_total_brl": payment_ctx["freight_total_brl"],
                "expected_total_brl": payment_ctx["expected_total_brl"],
                "payment_total_brl": payment_ctx["payment_total_brl"],
                "difference_brl": payment_ctx["difference_brl"],
                "reconciled": payment_ctx["reconciled"],
                "payment_types": payment_ctx["payment_types"]
            },
            "root_cause_analysis": policy_out["root_cause_analysis"],
            "evidence_ids": policy_out["evidence_ids"],
            "financial_resolution": policy_out["financial_resolution"],
            "resolution_actions": policy_out["resolution_actions"]
        }

        # Agent Handoff 6: Verifier Agent
        self.tracer.log_step(case_id, "VerifierAgent", "schema_validation", {}, "started")
        verified_output = self.verifier_agent.verify_and_clean(case_id, raw_output)
        self.tracer.log_step(case_id, "VerifierAgent", "schema_validation_complete", {}, "verified")

        return verified_output
