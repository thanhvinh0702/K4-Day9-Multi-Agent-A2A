import os
import glob
import json

def test_all_outputs(output_dir="output"):
    files = sorted(glob.glob(os.path.join(output_dir, "EC_*.json")))
    assert len(files) == 50, f"Expected 50 output files, found {len(files)}"

    valid_primary_issues = {
        "canceled_order_paid",
        "unavailable_order_paid",
        "late_delivery_seller",
        "late_delivery_logistics",
        "valid_split_payment",
        "unsupported_late_claim"
    }

    valid_secondary_issues = {
        "multi_item_order",
        "multi_seller_order",
        "split_payment",
        "repeat_customer",
        "multiple_categories"
    }

    valid_root_causes = {
        "SELLER_HANDOFF_AFTER_LIMIT",
        "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "ORDER_CANCELED_AFTER_PAYMENT",
        "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "MULTIPLE_PAYMENTS_RECONCILED",
        "DELIVERY_WITHIN_ESTIMATE"
    }

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        case_id = data.get("case_id")
        assert case_id is not None, f"Missing case_id in {fpath}"

        # 1. Assessment
        ca = data.get("case_assessment", {})
        assert ca.get("primary_issue") in valid_primary_issues, f"Invalid primary issue {ca.get('primary_issue')} in {fpath}"
        for sec in ca.get("secondary_issues", []):
            assert sec in valid_secondary_issues, f"Invalid secondary issue {sec} in {fpath}"
        assert ca.get("case_status") in {"action_required", "no_action"}, f"Invalid case status in {fpath}"
        assert 0.0 <= ca.get("confidence", 0) <= 1.0, f"Invalid confidence in {fpath}"

        # 2. Affected entities limits
        ae = data.get("affected_entities", {})
        assert len(ae.get("order_ids", [])) <= 5
        assert len(ae.get("item_ids", [])) <= 5
        assert len(ae.get("seller_ids", [])) <= 3
        assert len(ae.get("payment_ids", [])) <= 5

        # 3. Customer & Product context limits
        cc = data.get("customer_context", {})
        assert len(cc.get("related_order_ids", [])) <= 5
        pc = data.get("product_context", {})
        assert len(pc.get("product_ids", [])) <= 5
        assert len(pc.get("category_names", [])) <= 5

        # 4. Delivery analysis limits
        da = data.get("delivery_analysis", {})
        assert len(da.get("seller_handoff_analysis", [])) <= 5
        assert len(da.get("late_handoff_seller_ids", [])) <= 3

        # 5. Root cause analysis
        rc = data.get("root_cause_analysis", {})
        assert len(rc.get("ranked_causes", [])) <= 3
        assert len(rc.get("responsible_parties", [])) <= 3

        # 6. Evidence & Actions limits
        assert len(data.get("evidence_ids", [])) <= 20
        assert len(data.get("resolution_actions", [])) <= 5

        # Check evidence prefix format
        for eid in data.get("evidence_ids", []):
            assert any(eid.startswith(prefix) for prefix in ["order:", "item:", "payment:", "seller:", "policy:"]), f"Invalid evidence ID format {eid} in {fpath}"

    print(f"All {len(files)} output JSON files PASSED strict validation!")

if __name__ == "__main__":
    test_all_outputs()
