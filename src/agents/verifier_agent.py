import json
from typing import Dict, Any, Optional
from src.llm_client import LLMClient


class VerifierAgent:
    """Agent responsible for strict schema validation, array boundary enforcement,
    and null handling before a case is written to output/.

    The deterministic checks below are the source of truth for schema
    compliance (array limits, null constraints) since grading needs exact
    values. On top of that, a real LLM call (Groq, llama-3.1-8b-instant)
    audits the assembled case for internal-consistency red flags (e.g.
    case_status vs refund mismatch, empty evidence for an action_required
    case) and the finding is logged to trace.jsonl for a human reviewer;
    it does not mutate the already-verified numeric/schema fields.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    def verify_and_clean(self, case_id: str, raw_output: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(raw_output)
        cleaned["case_id"] = case_id

        ca = cleaned.get("case_assessment", {})
        conf = float(ca.get("confidence", 0.95))
        ca["confidence"] = max(0.0, min(1.0, conf))
        ca["secondary_issues"] = ca.get("secondary_issues", [])[:5]
        cleaned["case_assessment"] = ca

        ae = cleaned.get("affected_entities", {})
        ae["order_ids"] = ae.get("order_ids", [])[:5]
        ae["item_ids"] = ae.get("item_ids", [])[:5]
        ae["seller_ids"] = ae.get("seller_ids", [])[:3]
        ae["payment_ids"] = ae.get("payment_ids", [])[:5]
        cleaned["affected_entities"] = ae

        cc = cleaned.get("customer_context", {})
        cc["related_order_ids"] = cc.get("related_order_ids", [])[:5]
        cleaned["customer_context"] = cc

        pc = cleaned.get("product_context", {})
        pc["product_ids"] = pc.get("product_ids", [])[:5]
        pc["category_names"] = pc.get("category_names", [])[:5]
        cleaned["product_context"] = pc

        da = cleaned.get("delivery_analysis", {})
        da["seller_handoff_analysis"] = da.get("seller_handoff_analysis", [])[:5]
        da["late_handoff_seller_ids"] = da.get("late_handoff_seller_ids", [])[:3]
        cleaned["delivery_analysis"] = da

        pr = cleaned.get("payment_reconciliation", {})
        if not ae["item_ids"]:
            pr["expected_total_brl"] = None
            pr["difference_brl"] = None
            pr["reconciled"] = None
        cleaned["payment_reconciliation"] = pr

        rc = cleaned.get("root_cause_analysis", {})
        rc["ranked_causes"] = rc.get("ranked_causes", [])[:3]
        rc["responsible_parties"] = rc.get("responsible_parties", [])[:3]
        cleaned["root_cause_analysis"] = rc

        cleaned["evidence_ids"] = cleaned.get("evidence_ids", [])[:20]
        cleaned["resolution_actions"] = cleaned.get("resolution_actions", [])[:5]

        return cleaned

    def llm_audit(self, case_id: str, cleaned_output: Dict[str, Any], tracer=None) -> Dict[str, Any]:
        if not self.llm_client:
            return {"issues_found": [], "audited": False}

        audit_view = {
            "primary_issue": cleaned_output.get("case_assessment", {}).get("primary_issue"),
            "case_status": cleaned_output.get("case_assessment", {}).get("case_status"),
            "confidence": cleaned_output.get("case_assessment", {}).get("confidence"),
            "recommended_refund_brl": cleaned_output.get("financial_resolution", {}).get("recommended_refund_brl"),
            "evidence_ids_count": len(cleaned_output.get("evidence_ids", [])),
            "responsible_parties": cleaned_output.get("root_cause_analysis", {}).get("responsible_parties"),
            "reconciled": cleaned_output.get("payment_reconciliation", {}).get("reconciled"),
        }
        system_prompt = (
            "You are the Verifier Agent auditing a finished dispute-resolution case for "
            "internal consistency. Flag ONLY real contradictions, such as: case_status is "
            "action_required but recommended_refund_brl is 0; case_status is no_action but "
            "recommended_refund_brl is greater than 0; there is a responsible party but zero "
            "evidence_ids. If nothing is wrong, return an empty list.\n"
            'Respond ONLY as JSON: {"issues_found": ["<short description>", ...]}'
        )
        user_prompt = f"Case summary:\n{json.dumps(audit_view, ensure_ascii=False)}"

        try:
            result = self.llm_client.chat_json(system_prompt, user_prompt, max_tokens=200)
            issues = result["parsed"].get("issues_found", [])
            if tracer:
                tracer.log_llm_call(
                    case_id, "VerifierAgent", "llm_consistency_audit", result["model"],
                    prompt_summary=audit_view, result_summary={"issues_found": issues}, usage=result["usage"],
                )
            return {"issues_found": issues, "audited": True}
        except Exception as e:
            if tracer:
                tracer.log_llm_call(
                    case_id, "VerifierAgent", "llm_consistency_audit", "llama-3.1-8b-instant",
                    prompt_summary=audit_view, result_summary={"error": str(e)}, fallback_used=True,
                )
            return {"issues_found": [], "audited": False}
