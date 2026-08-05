"""Verifier Agent: deterministic guardrail, no LLM call.

Re-derives ground truth directly from tools/policy_rules and overwrites any
section of the assembled draft that could have drifted during the LLM
"structured_format" step (rounding, dropped nulls, reordered arrays, ...).
This is a deliberate design choice: correctness of numbers/ids/limits is
enforced by code, not by asking an LLM to double-check itself. It then
schema-validates the result and checks every evidence id actually resolves
against the source CSVs before a file is allowed to be written.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from . import policy_rules
from .data_layer import get_data
from .schemas import FinalOutput
from .tools import gather_case_facts
from .trace_logger import TraceLogger


def _evidence_exists(data, eid: str) -> bool:
    parts = eid.split(":")
    kind = parts[0]
    rest = parts[1:]
    if kind == "order" and len(rest) == 1:
        return data.get_order(rest[0]) is not None
    if kind == "item" and len(rest) == 2:
        order_id, item_id = rest
        return any(str(it["order_item_id"]) == str(item_id) for it in data.get_items(order_id))
    if kind == "payment" and len(rest) == 2:
        order_id, seq = rest
        return any(str(p["payment_sequential"]) == str(seq) for p in data.get_payments(order_id))
    if kind == "seller" and len(rest) == 1:
        return data.get_seller(rest[0]) is not None
    if kind == "policy" and len(rest) == 1:
        return rest[0] in policy_rules.ROOT_CAUSE_CODE.values()
    return False


def verify_and_fix(
    trace: TraceLogger, case_id: str, claimed_order_id: str, assembled: dict[str, Any]
) -> dict[str, Any]:
    facts = gather_case_facts(claimed_order_id)
    policy_truth = policy_rules.apply_policy(facts)
    used_fallback = policy_truth.pop("_used_fallback", False)
    opc = facts["order_product_context"]

    fixed = dict(assembled)
    fixed["payment_reconciliation"] = facts["payment_reconciliation"]
    fixed["delivery_analysis"] = facts["delivery_analysis"]
    fixed["case_assessment"] = policy_truth["case_assessment"]
    fixed["root_cause_analysis"] = policy_truth["root_cause_analysis"]
    fixed["financial_resolution"] = policy_truth["financial_resolution"]
    fixed["resolution_actions"] = policy_truth["resolution_actions"]
    fixed["evidence_ids"] = policy_truth["evidence_ids"]
    fixed["affected_entities"] = {
        "order_ids": opc["order_ids"],
        "item_ids": opc["item_ids"],
        "seller_ids": opc["seller_ids"],
        "payment_ids": facts["payment_ids"],
    }
    fixed["customer_context"] = facts["customer_context"]
    fixed["product_context"] = {
        "product_ids": opc["product_ids"],
        "category_names": opc["category_names"],
    }

    data = get_data()
    bad_evidence = [eid for eid in fixed["evidence_ids"] if not _evidence_exists(data, eid)]
    if bad_evidence:
        fixed["evidence_ids"] = [e for e in fixed["evidence_ids"] if e not in bad_evidence]

    try:
        validated = FinalOutput(**fixed)
    except ValidationError as e:
        trace.log_event(
            case_id=case_id, event_type="verifier_check", status="error", detail=str(e)
        )
        raise

    trace.log_event(
        case_id=case_id,
        event_type="verifier_check",
        status="ok" if not bad_evidence else "auto_fixed",
        dropped_evidence_ids=bad_evidence,
        used_policy_fallback=used_fallback,
    )
    return validated.model_dump()
