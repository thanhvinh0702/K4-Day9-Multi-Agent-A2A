"""Batch runner: input/input/EC_*.json -> output/EC_*.json, with a fresh
logging/trace.jsonl for this run (README.md: only the latest run, no
append across runs).
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from .config import INPUT_DIR, MODEL_NAME, OPENAI_API_KEY, OUTPUT_DIR, TRACE_PATH
from .graph import build_graph
from .trace_logger import TraceLogger


def _load_case_input(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_fallback_output(case_id: str, claimed_order_id: str | None) -> dict[str, Any]:
    """Used only if a case blows up unexpectedly, so the batch always yields 50 files."""
    return {
        "case_id": case_id,
        "case_assessment": {
            "primary_issue": "unsupported_late_claim",
            "secondary_issues": [],
            "case_status": "no_action",
            "confidence": 0.0,
        },
        "affected_entities": {
            "order_ids": [claimed_order_id] if claimed_order_id else [],
            "item_ids": [],
            "seller_ids": [],
            "payment_ids": [],
        },
        "customer_context": {"customer_unique_id": None, "related_order_ids": []},
        "product_context": {"product_ids": [], "category_names": []},
        "delivery_analysis": {
            "delivered_at": None,
            "estimated_delivery_at": None,
            "carrier_handoff_at": None,
            "delivery_variance_hours": None,
            "seller_handoff_analysis": [],
            "late_handoff_seller_ids": [],
        },
        "payment_reconciliation": {
            "currency": "BRL",
            "item_total_brl": 0.0,
            "freight_total_brl": 0.0,
            "expected_total_brl": None,
            "payment_total_brl": 0.0,
            "difference_brl": None,
            "reconciled": None,
            "payment_types": [],
        },
        "root_cause_analysis": {"ranked_causes": [], "responsible_parties": []},
        "evidence_ids": [],
        "financial_resolution": {"currency": "BRL", "recommended_refund_brl": 0.0},
        "resolution_actions": ["reject_late_refund"],
    }


def run_batch() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing - set it in .env")

    trace = TraceLogger(TRACE_PATH)
    trace.start_run()

    llm = ChatOpenAI(model=MODEL_NAME, api_key=OPENAI_API_KEY, temperature=0)
    app = build_graph(llm, trace)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    input_files = sorted(INPUT_DIR.glob("EC_*.json"))
    print(f"Found {len(input_files)} input cases in {INPUT_DIR}")

    for path in input_files:
        case = _load_case_input(path)
        case_id = case["case_id"]
        claimed_order_id = case["customer_request"]["claimed_order_id"]
        t0 = time.time()
        try:
            result = app.invoke({"case_id": case_id, "claimed_order_id": claimed_order_id})
            final_output = result["final_output"]
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - batch must not die on one bad case
            trace.log_event(
                case_id=case_id,
                event_type="error",
                claimed_order_id=claimed_order_id,
                message=str(exc),
                traceback=traceback.format_exc(),
            )
            final_output = _build_fallback_output(case_id, claimed_order_id)
            status = "error_fallback"

        out_path = OUTPUT_DIR / f"{case_id}.json"
        out_path.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
        duration_ms = int((time.time() - t0) * 1000)
        trace.log_event(
            case_id=case_id,
            event_type="final_output",
            status=status,
            output_file=out_path.name,
            duration_ms=duration_ms,
        )
        print(f"[{status}] {case_id} -> {out_path.name} ({duration_ms}ms)")


if __name__ == "__main__":
    run_batch()
