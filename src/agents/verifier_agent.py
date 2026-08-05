from typing import Dict, Any

class VerifierAgent:
    """Agent responsible for strict schema validation, array boundary enforcement, and data sanitization."""

    def verify_and_clean(self, case_id: str, raw_output: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(raw_output)
        cleaned["case_id"] = case_id

        # 1. Validate case assessment
        ca = cleaned.get("case_assessment", {})
        conf = float(ca.get("confidence", 0.95))
        ca["confidence"] = max(0.0, min(1.0, conf))
        ca["secondary_issues"] = ca.get("secondary_issues", [])[:5]
        cleaned["case_assessment"] = ca

        # 2. Validate affected entities
        ae = cleaned.get("affected_entities", {})
        ae["order_ids"] = ae.get("order_ids", [])[:5]
        ae["item_ids"] = ae.get("item_ids", [])[:5]
        ae["seller_ids"] = ae.get("seller_ids", [])[:3]
        ae["payment_ids"] = ae.get("payment_ids", [])[:5]
        cleaned["affected_entities"] = ae

        # 3. Validate customer context
        cc = cleaned.get("customer_context", {})
        cc["related_order_ids"] = cc.get("related_order_ids", [])[:5]
        cleaned["customer_context"] = cc

        # 4. Validate product context
        pc = cleaned.get("product_context", {})
        pc["product_ids"] = pc.get("product_ids", [])[:5]
        pc["category_names"] = pc.get("category_names", [])[:5]
        cleaned["product_context"] = pc

        # 5. Validate delivery analysis
        da = cleaned.get("delivery_analysis", {})
        da["seller_handoff_analysis"] = da.get("seller_handoff_analysis", [])[:5]
        da["late_handoff_seller_ids"] = da.get("late_handoff_seller_ids", [])[:3]
        cleaned["delivery_analysis"] = da

        # 6. Validate payment reconciliation null constraints for empty items
        pr = cleaned.get("payment_reconciliation", {})
        if not ae["item_ids"]:
            pr["expected_total_brl"] = None
            pr["difference_brl"] = None
            pr["reconciled"] = None
        cleaned["payment_reconciliation"] = pr

        # 7. Validate root cause analysis
        rc = cleaned.get("root_cause_analysis", {})
        rc["ranked_causes"] = rc.get("ranked_causes", [])[:3]
        rc["responsible_parties"] = rc.get("responsible_parties", [])[:3]
        cleaned["root_cause_analysis"] = rc

        # 8. Validate evidence IDs, actions
        cleaned["evidence_ids"] = cleaned.get("evidence_ids", [])[:20]
        cleaned["resolution_actions"] = cleaned.get("resolution_actions", [])[:5]

        return cleaned
