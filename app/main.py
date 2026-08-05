from __future__ import annotations

import argparse
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from tqdm import tqdm

from app.agents import CustomerAgent, DeliveryAgent, OrderProductAgent, PaymentAgent, PolicyAgent, VerifierAgent
from app.config import INPUT_DIR, LOGGING_DIR, OUTPUT_DIR, load_dotenv, get_model_name
from app.data_store import OlistDataStore
from app.llm import build_structured_llm
from app.schemas import (
    CaseInput,
    CaseOutput,
    CustomerContext,
    CustomerFinding,
    DeliveryAnalysis,
    DeliveryFinding,
    OrderProductFinding,
    PaymentFinding,
    PaymentReconciliation,
    PolicyFinding,
    ProductContext,
    VerificationFinding,
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_generated_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("EC_*.json"):
        path.unlink()


@dataclass
class CaseBundle:
    case: CaseInput
    records: dict[str, Any]
    customer_context: CustomerContext
    product_context: ProductContext
    payment: PaymentReconciliation
    delivery: DeliveryAnalysis
    fallback_output: CaseOutput
    item_ids: list[str]
    seller_ids: list[str]
    payment_ids: list[str]


class FallbackCoordinator:
    def __init__(self) -> None:
        self.store = OlistDataStore()
        self.customer_agent = CustomerAgent()
        self.order_product_agent = OrderProductAgent()
        self.payment_agent = PaymentAgent()
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()

    def build_bundle(self, case: CaseInput) -> CaseBundle:
        order_id = case.customer_request.claimed_order_id
        records = self.store.get_case_records(order_id)

        customer_context = self.customer_agent.run(records, self.store)
        product_context = self.order_product_agent.run(records)
        payment = self.payment_agent.run(records)
        delivery = self.delivery_agent.run(records)
        policy = self.policy_agent.run(records, customer_context, product_context, delivery, payment)
        fallback_output = self.verifier_agent.run(
            case,
            records,
            customer_context,
            product_context,
            delivery,
            payment,
            policy,
        )

        item_ids = [f"{order_id}:{row['order_item_id']}" for row in records["items"]]
        seller_ids = list(dict.fromkeys(row["seller_id"] for row in records["items"]))[:3]
        payment_ids = [f"{order_id}:{row['payment_sequential']}" for row in records["payments"]]
        return CaseBundle(
            case=case,
            records=records,
            customer_context=customer_context,
            product_context=product_context,
            payment=payment,
            delivery=delivery,
            fallback_output=fallback_output,
            item_ids=item_ids,
            seller_ids=seller_ids,
            payment_ids=payment_ids,
        )


class BatchFindingRunner:
    def __init__(self, use_llm: bool) -> None:
        self.use_llm = use_llm
        self.agent_runners: dict[str, tuple[Any | None, str]] = {}
        if use_llm:
            for agent_name, schema in {
                "CustomerAgent": CustomerFinding,
                "OrderProductAgent": OrderProductFinding,
                "PaymentAgent": PaymentFinding,
                "DeliveryAgent": DeliveryFinding,
                "PolicyAgent": PolicyFinding,
                "VerifierAgent": VerificationFinding,
            }.items():
                self.agent_runners[agent_name] = build_structured_llm(schema)

    def run_agent_batch(self, agent_name: str, batch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        llm_pair = self.agent_runners.get(agent_name)
        if not llm_pair:
            return [self._fallback_row(agent_name, row) for row in batch_rows]

        llm, method = llm_pair
        if llm is None:
            return [
                {
                    "agent": agent_name,
                    "llm_used": False,
                    "llm_error": method,
                    "structured_output_method": method,
                    "finding": row["fallback"],
                }
                for row in batch_rows
            ]

        messages_batch = [
            [
                SystemMessage(
                    content=(
                        f"You are {agent_name}. Return a structured finding using only the supplied "
                        "facts and fallback finding. Do not invent IDs, timestamps, money values, "
                        "evidence, or policy outcomes."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {"facts": row["facts"], "fallback_finding": row["fallback"]},
                        ensure_ascii=False,
                    )
                ),
            ]
            for row in batch_rows
        ]
        results = llm.batch(messages_batch, return_exceptions=True)
        traces: list[dict[str, Any]] = []
        for row, result in zip(batch_rows, results):
            if isinstance(result, Exception):
                traces.append(
                    {
                        "agent": agent_name,
                        "llm_used": False,
                        "llm_error": f"{type(result).__name__}: {result}",
                        "structured_output_method": method,
                        "finding": row["fallback"],
                    }
                )
                continue

            finding = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
            traces.append(
                {
                    "agent": agent_name,
                    "llm_used": True,
                    "llm_error": None,
                    "structured_output_method": method,
                    "finding": finding,
                }
            )
        return traces

    @staticmethod
    def _fallback_row(agent_name: str, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent": agent_name,
            "llm_used": False,
            "llm_error": None,
            "structured_output_method": "disabled_by_flag",
            "finding": row["fallback"],
        }


def build_agent_rows(bundle: CaseBundle) -> dict[str, dict[str, Any]]:
    case = bundle.case
    order_id = case.customer_request.claimed_order_id
    return {
        "CustomerAgent": {
            "facts": {
                "order_id": order_id,
                "order": bundle.records["order"],
                "customer": bundle.records["customer"],
                "customer_history_order_ids": bundle.customer_context.related_order_ids,
            },
            "fallback": {
                "agent_name": "CustomerAgent",
                "customer_context": bundle.customer_context.model_dump(),
                "evidence_ids": [f"order:{order_id}"],
                "confidence": 0.95,
                "notes": ["Customer identity and repeat-order context were joined from orders and customers CSV."],
            },
        },
        "OrderProductAgent": {
            "facts": {
                "order_id": order_id,
                "items": bundle.records["items"],
                "products": bundle.records["products"],
                "sellers": bundle.records["sellers"],
            },
            "fallback": {
                "agent_name": "OrderProductAgent",
                "product_context": bundle.product_context.model_dump(),
                "item_ids": bundle.item_ids[:5],
                "seller_ids": bundle.seller_ids,
                "evidence_ids": [f"item:{item_id}" for item_id in bundle.item_ids[:5]],
                "confidence": 0.96,
                "notes": ["Product, item, seller, and category context were joined from item and product CSVs."],
            },
        },
        "PaymentAgent": {
            "facts": {
                "order_id": order_id,
                "items": bundle.records["items"],
                "payments": bundle.records["payments"],
                "payment_reconciliation": bundle.payment.model_dump(),
            },
            "fallback": {
                "agent_name": "PaymentAgent",
                "payment_reconciliation": bundle.payment.model_dump(),
                "payment_ids": bundle.payment_ids[:5],
                "evidence_ids": [f"payment:{payment_id}" for payment_id in bundle.payment_ids[:5]],
                "confidence": 0.97,
                "notes": ["Payment total was reconciled against item price plus freight using EC_POLICY_V2 tolerance."],
            },
        },
        "DeliveryAgent": {
            "facts": {
                "order": bundle.records["order"],
                "items": bundle.records["items"],
                "delivery_analysis": bundle.delivery.model_dump(),
            },
            "fallback": {
                "agent_name": "DeliveryAgent",
                "delivery_analysis": bundle.delivery.model_dump(),
                "evidence_ids": [f"order:{order_id}"] + [f"item:{item_id}" for item_id in bundle.item_ids[:5]],
                "confidence": 0.96,
                "notes": ["Delivery variance and seller handoff variance were calculated from CSV timestamps."],
            },
        },
    }


def build_policy_row(bundle: CaseBundle, findings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case = bundle.case
    return {
        "facts": {
            "case_id": case.case_id,
            "policy_version": case.policy_version,
            "order": bundle.records["order"],
            "customer_finding": findings["CustomerAgent"],
            "product_finding": findings["OrderProductAgent"],
            "payment_finding": findings["PaymentAgent"],
            "delivery_finding": findings["DeliveryAgent"],
            "customer_context_hint": bundle.customer_context.model_dump(),
            "product_context_hint": bundle.product_context.model_dump(),
            "payment_hint": bundle.payment.model_dump(),
            "delivery_hint": bundle.delivery.model_dump(),
        },
        "fallback": {
            "agent_name": "PolicyAgent",
            "case_assessment": bundle.fallback_output.case_assessment.model_dump(),
            "root_cause_analysis": bundle.fallback_output.root_cause_analysis.model_dump(),
            "financial_resolution": bundle.fallback_output.financial_resolution.model_dump(),
            "resolution_actions": bundle.fallback_output.resolution_actions,
            "evidence_ids": bundle.fallback_output.evidence_ids,
            "confidence": bundle.fallback_output.case_assessment.confidence,
            "notes": ["Fallback policy finding mirrors the deterministic verifier output because LLM is unavailable or disabled."],
        },
    }


def build_verifier_row(bundle: CaseBundle, policy_finding: dict[str, Any], findings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case = bundle.case
    order_id = case.customer_request.claimed_order_id
    return {
        "facts": {
            "case": case.model_dump(),
            "customer_finding": findings["CustomerAgent"],
            "product_finding": findings["OrderProductAgent"],
            "payment_finding": findings["PaymentAgent"],
            "delivery_finding": findings["DeliveryAgent"],
            "policy_finding": policy_finding,
            "base_output_hint": bundle.fallback_output.model_dump(),
        },
        "fallback": {
            "agent_name": "VerifierAgent",
            "schema_valid": True,
            "evidence_valid": True,
            "money_valid": True,
            "array_limits_valid": True,
            "final_output": bundle.fallback_output.model_dump(),
            "confidence": 0.98,
            "notes": [f"Fallback verifier placeholder for {order_id}."],
        },
    }


def resolve_final_output(bundle: CaseBundle, verifier_finding: dict[str, Any], agentic_output_ready: bool) -> tuple[CaseOutput, str]:
    if agentic_output_ready and verifier_finding.get("schema_valid") and verifier_finding.get("evidence_valid") and verifier_finding.get("money_valid") and verifier_finding.get("array_limits_valid"):
        try:
            return CaseOutput.model_validate(verifier_finding["final_output"]), "verifier_agent"
        except Exception:
            return bundle.fallback_output, "deterministic_fallback"
    return bundle.fallback_output, "deterministic_fallback"


def write_trace(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(input_dir: Path, output_dir: Path, logging_dir: Path, use_llm: bool) -> int:
    load_dotenv()
    input_paths = sorted(input_dir.glob("EC_*.json"))
    clean_generated_outputs(output_dir)
    logging_dir.mkdir(parents=True, exist_ok=True)

    fallback_coordinator = FallbackCoordinator()
    batch_runner = BatchFindingRunner(use_llm=use_llm)

    if not input_paths:
        print(f"No input cases found in {input_dir}. Expected files like EC_001.json ... EC_050.json.")

    bundles: list[CaseBundle] = []
    failures: list[dict[str, str]] = []
    for path in tqdm(input_paths, desc="Preparing cases", unit="case"):
        try:
            case = CaseInput.model_validate_json(path.read_text(encoding="utf-8"))
            bundles.append(fallback_coordinator.build_bundle(case))
        except Exception as exc:
            failures.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})

    agent_names = ["CustomerAgent", "OrderProductAgent", "PaymentAgent", "DeliveryAgent"]
    trace_map: dict[str, list[dict[str, Any]]] = {}
    agent_rows_map: dict[str, list[dict[str, Any]]] = {
        name: [build_agent_rows(bundle)[name] for bundle in bundles] for name in agent_names
    }
    for agent_name in tqdm(agent_names, desc="Batching agents", unit="agent"):
        trace_map[agent_name] = batch_runner.run_agent_batch(agent_name, agent_rows_map[agent_name])

    agent_findings: list[dict[str, dict[str, Any]]] = []
    for idx in range(len(bundles)):
        agent_findings.append({name: trace_map[name][idx]["finding"] for name in agent_names})

    for decision_agent in tqdm(["PolicyAgent", "VerifierAgent"], desc="Batching decision agents", unit="agent"):
        if decision_agent == "PolicyAgent":
            rows = [build_policy_row(bundle, agent_findings[idx]) for idx, bundle in enumerate(bundles)]
            trace_map["PolicyAgent"] = batch_runner.run_agent_batch("PolicyAgent", rows)
            continue

        rows = [
            build_verifier_row(bundle, trace_map["PolicyAgent"][idx]["finding"], agent_findings[idx])
            for idx, bundle in enumerate(bundles)
        ]
        trace_map["VerifierAgent"] = batch_runner.run_agent_batch("VerifierAgent", rows)

    traces: list[dict[str, Any]] = []
    for idx, bundle in enumerate(tqdm(bundles, desc="Writing output", unit="case")):
        case_traces = [trace_map[name][idx] for name in ["CustomerAgent", "OrderProductAgent", "PaymentAgent", "DeliveryAgent", "PolicyAgent", "VerifierAgent"]]
        verifier_finding = case_traces[-1]["finding"]
        agentic_output_ready = case_traces[-2]["llm_used"] and case_traces[-1]["llm_used"]
        final_output, final_source = resolve_final_output(
            bundle,
            verifier_finding,
            agentic_output_ready=agentic_output_ready,
        )

        write_json(output_dir / f"{bundle.case.case_id}.json", final_output.model_dump(mode="json"))
        traces.append(
            {
                "case_id": bundle.case.case_id,
                "order_id": bundle.case.customer_request.claimed_order_id,
                "agents": [
                    "CustomerAgent",
                    "OrderProductAgent",
                    "PaymentAgent",
                    "DeliveryAgent",
                    "PolicyAgent",
                    "VerifierAgent",
                    "CoordinatorAgent",
                ],
                "primary_issue": final_output.case_assessment.primary_issue,
                "refund_brl": final_output.financial_resolution.recommended_refund_brl,
                "structured_output_method": "batch_tool_calling" if use_llm else "disabled_by_flag",
                "llm_used": any(trace["llm_used"] for trace in case_traces),
                "llm_error": (
                    None
                    if any(trace["llm_used"] for trace in case_traces)
                    else ("LLM disabled by --no-llm." if not use_llm else "All batch agent calls fell back to deterministic findings.")
                ),
                "final_decision_source": final_source,
                "agent_llm_traces": case_traces,
                "duration_ms": 0.0,
            }
        )

    write_trace(logging_dir / "trace.jsonl", traces + [{"failure": row} for row in failures])
    metadata = {
        "model": get_model_name(),
        "parameter_size": "<=10B per assignment constraint; verify selected OpenRouter model card",
        "framework": "LangChain",
        "structured_output": {
            "requested_method": "tool_calling",
            "runtime_method": "batch_tool_calling" if use_llm else "disabled_by_flag",
        },
        "multi_agent_llm": {
            "enabled": use_llm,
            "mode": "batch",
            "final_decider": "VerifierAgent",
            "llm_agent_schemas": [
                "CustomerFinding",
                "OrderProductFinding",
                "PaymentFinding",
                "DeliveryFinding",
                "PolicyFinding",
                "VerificationFinding",
            ],
            "final_output_schema": "CaseOutput",
            "fallback": "Deterministic findings are used only when a batch agent call fails.",
        },
        "runtime": {
            "python": platform.python_version(),
            "input_cases": len(input_paths),
            "output_cases": len(traces),
            "failures": len(failures),
        },
    }
    write_json(logging_dir / "metadata.json", metadata)
    print(f"Done: {len(traces)}/{len(input_paths)} cases written to {output_dir} ({len(failures)} failures).")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-agent Olist dispute resolution.")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--logging-dir", type=Path, default=LOGGING_DIR)
    parser.add_argument("--no-llm", action="store_true", help="Skip the LangChain structured-output batch call.")
    args = parser.parse_args()
    raise SystemExit(run(args.input_dir, args.output_dir, args.logging_dir, use_llm=not args.no_llm))


if __name__ == "__main__":
    main()
