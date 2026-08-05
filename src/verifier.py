from __future__ import annotations

from src.datastore import OlistDataStore


LIMITS = {
    ("affected_entities", "order_ids"): 5,
    ("affected_entities", "item_ids"): 5,
    ("affected_entities", "seller_ids"): 3,
    ("affected_entities", "payment_ids"): 5,
    ("customer_context", "related_order_ids"): 5,
    ("product_context", "product_ids"): 5,
    ("product_context", "category_names"): 5,
    ("root_cause_analysis", "ranked_causes"): 3,
    ("root_cause_analysis", "responsible_parties"): 3,
}


class VerifierAgent:
    name = "verifier_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def verify(self, case: dict, output: dict) -> dict:
        errors: list[str] = []
        order_id = case["customer_request"]["claimed_order_id"]
        if output["case_id"] != case["case_id"]:
            errors.append("case_id mismatch")
        if output["affected_entities"]["order_ids"] != [order_id]:
            errors.append("affected order must be the claimed order only")
        if not 0 <= output["case_assessment"]["confidence"] <= 1:
            errors.append("confidence is outside [0, 1]")
        refund = output["financial_resolution"]["recommended_refund_brl"]
        expected_status = "action_required" if refund > 0 else "no_action"
        if output["case_assessment"]["case_status"] != expected_status:
            errors.append("case_status does not match refund")
        if len(output["evidence_ids"]) > 20:
            errors.append("more than 20 evidence IDs")
        if len(output["resolution_actions"]) > 5:
            errors.append("more than 5 actions")
        for path, limit in LIMITS.items():
            if len(output[path[0]][path[1]]) > limit:
                errors.append(f"{'.'.join(path)} exceeds {limit}")
        if order_id in output["customer_context"]["related_order_ids"]:
            errors.append("claimed order appears in customer history")

        item_rows = self.store.items_by_order.get(order_id, [])
        valid_items = {
            f"{order_id}:{row['order_item_id']}" for row in item_rows
        }
        valid_payments = {
            f"{order_id}:{row['payment_sequential']}"
            for row in self.store.payments_by_order.get(order_id, [])
        }
        if not set(output["affected_entities"]["item_ids"]).issubset(valid_items):
            errors.append("invalid affected item ID")
        if not set(output["affected_entities"]["payment_ids"]).issubset(
            valid_payments
        ):
            errors.append("invalid affected payment ID")
        if not item_rows:
            reconciliation = output["payment_reconciliation"]
            for field in ("expected_total_brl", "difference_brl", "reconciled"):
                if reconciliation[field] is not None:
                    errors.append(f"{field} must be null without item rows")

        valid_evidence = {f"order:{order_id}"}
        valid_evidence.update(f"item:{value}" for value in valid_items)
        valid_evidence.update(f"payment:{value}" for value in valid_payments)
        valid_evidence.update(
            f"seller:{row['seller_id']}" for row in item_rows
        )
        cause = output["root_cause_analysis"]["ranked_causes"][0]["cause_code"]
        valid_evidence.add(f"policy:{cause}")
        if not set(output["evidence_ids"]).issubset(valid_evidence):
            errors.append("evidence contains a false-positive ID")
        if errors:
            raise ValueError(f"Verification failed for {case['case_id']}: {errors}")
        return {"valid": True, "checks": 11}

