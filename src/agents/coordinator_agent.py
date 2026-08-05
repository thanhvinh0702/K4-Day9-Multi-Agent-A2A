import json
from typing import Dict, Any, Optional
from src.data_loader import DataLoader
from src.agents.customer_agent import CustomerAgent
from src.agents.order_product_agent import OrderProductAgent
from src.agents.payment_agent import PaymentAgent
from src.agents.delivery_agent import DeliveryAgent
from src.agents.policy_agent import PolicyAgent
from src.agents.verifier_agent import VerifierAgent
from src.tracer import Tracer
from src.llm_client import LLMClient


class CoordinatorAgent:
    """Master Coordinator Agent that orchestrates multi-agent investigation and output generation.

    Handoff flow: CustomerAgent, OrderProductAgent, PaymentAgent and DeliveryAgent
    each analyze one data domain deterministically from the Olist CSVs. The
    Coordinator collects their evidence and makes one real LLM call (Groq,
    llama-3.1-8b-instant) to synthesize a short investigation handoff note
    before delegating the final ruling to the Policy Agent (which itself makes
    a second LLM call to independently verify the ruling and score
    confidence). The Verifier Agent then makes a third LLM call to audit the
    assembled case for internal consistency before it is written to output/.
    """

    def __init__(self, data_loader: DataLoader, tracer: Tracer, llm_client: Optional[LLMClient] = None):
        self.data_loader = data_loader
        self.tracer = tracer
        self.llm_client = llm_client

        self.customer_agent = CustomerAgent(data_loader)
        self.order_product_agent = OrderProductAgent(data_loader)
        self.payment_agent = PaymentAgent(data_loader)
        self.delivery_agent = DeliveryAgent(data_loader)
        self.policy_agent = PolicyAgent(llm_client=llm_client)
        self.verifier_agent = VerifierAgent(llm_client=llm_client)

    def _llm_handoff_synthesis(self, case_id: str, customer_ctx: Dict[str, Any], op_ctx: Dict[str, Any],
                                payment_ctx: Dict[str, Any], delivery_ctx: Dict[str, Any]) -> None:
        if not self.llm_client:
            return
        evidence_bundle = {
            "has_repeat_orders": customer_ctx.get("has_repeat_orders"),
            "is_multi_item": op_ctx.get("is_multi_item"),
            "is_multi_seller": op_ctx.get("is_multi_seller"),
            "has_multiple_categories": op_ctx.get("has_multiple_categories"),
            "is_split_payment": payment_ctx.get("is_split_payment"),
            "reconciled": payment_ctx.get("reconciled"),
            "is_late_delivery": delivery_ctx.get("is_late_delivery"),
            "late_handoff_seller_ids": delivery_ctx.get("late_handoff_seller_ids"),
        }
        system_prompt = (
            "You are the Coordinator Agent in a multi-agent e-commerce dispute resolution "
            "system. Four domain agents (customer, order/product, payment, delivery) just "
            "handed off their evidence for one case. Write a one-sentence handoff note for "
            "the Policy Agent naming which domain(s) look decisive for this case.\n"
            'Respond ONLY as JSON: {"handoff_note": "<one short sentence>"}'
        )
        user_prompt = f"Evidence bundle:\n{json.dumps(evidence_bundle, ensure_ascii=False)}"
        try:
            result = self.llm_client.chat_json(system_prompt, user_prompt, max_tokens=150)
            note = result["parsed"].get("handoff_note")
            self.tracer.log_llm_call(
                case_id, "CoordinatorAgent", "llm_handoff_synthesis", result["model"],
                prompt_summary=evidence_bundle, result_summary={"handoff_note": note}, usage=result["usage"],
            )
        except Exception as e:
            self.tracer.log_llm_call(
                case_id, "CoordinatorAgent", "llm_handoff_synthesis", "llama-3.1-8b-instant",
                prompt_summary=evidence_bundle, result_summary={"error": str(e)}, fallback_used=True,
            )

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

        # Coordinator synthesizes the four evidence bundles (real LLM call, logged for audit only)
        self._llm_handoff_synthesis(case_id, customer_ctx, op_ctx, payment_ctx, delivery_ctx)

        # Agent Handoff 5: Policy Agent (deterministic ruling + LLM verification/confidence)
        self.tracer.log_step(case_id, "PolicyAgent", "evaluate_policy_rules", {"policy_version": "EC_POLICY_V2"}, "started")
        policy_out = self.policy_agent.analyze(
            case_id,
            claimed_order_id,
            order_status,
            customer_ctx,
            op_ctx,
            payment_ctx,
            delivery_ctx,
            tracer=self.tracer,
        )
        self.tracer.log_step(
            case_id, "PolicyAgent", "evaluation_complete", {},
            {"primary_issue": policy_out["case_assessment"]["primary_issue"], "llm_agrees": policy_out.get("_llm_agrees")}
        )

        # Assemble full raw output dictionary (schema fields only — no internal _llm_* keys)
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

        # Agent Handoff 6: Verifier Agent (deterministic schema clean + LLM consistency audit)
        self.tracer.log_step(case_id, "VerifierAgent", "schema_validation", {}, "started")
        verified_output = self.verifier_agent.verify_and_clean(case_id, raw_output)
        audit = self.verifier_agent.llm_audit(case_id, verified_output, tracer=self.tracer)
        self.tracer.log_step(case_id, "VerifierAgent", "schema_validation_complete", {}, {"status": "verified", "llm_issues_found": audit["issues_found"]})

        return verified_output
