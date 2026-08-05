from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from tqdm import tqdm

from app.agents import CustomerAgent, DeliveryAgent, OrderProductAgent, PaymentAgent, PolicyAgent, VerifierAgent
from app.config import INPUT_DIR, LOGGING_DIR, OUTPUT_DIR, load_dotenv, get_model_name
from app.data_store import OlistDataStore
from app.llm import build_structured_llm
from app.schemas import CaseInput, CaseOutput


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_generated_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("EC_*.json"):
        path.unlink()


class CoordinatorAgent:
    def __init__(self, use_llm: bool) -> None:
        self.store = OlistDataStore()
        self.customer_agent = CustomerAgent()
        self.order_product_agent = OrderProductAgent()
        self.payment_agent = PaymentAgent()
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()
        self.structured_llm, self.structured_method = build_structured_llm() if use_llm else (None, "disabled_by_flag")

    def investigate(self, case: CaseInput) -> tuple[CaseOutput, dict[str, Any]]:
        started = time.time()
        order_id = case.customer_request.claimed_order_id
        records = self.store.get_case_records(order_id)

        customer_context = self.customer_agent.run(records, self.store)
        product_context = self.order_product_agent.run(records)
        payment = self.payment_agent.run(records)
        delivery = self.delivery_agent.run(records)
        policy = self.policy_agent.run(records, customer_context, product_context, delivery, payment)
        deterministic = self.verifier_agent.run(case, records, customer_context, product_context, delivery, payment, policy)

        llm_used = False
        llm_error = None
        output = deterministic
        if self.structured_llm is not None:
            try:
                output = self._structured_format(case, deterministic)
                llm_used = True
            except Exception as exc:
                llm_error = f"{type(exc).__name__}: {exc}"

        trace = {
            "case_id": case.case_id,
            "order_id": order_id,
            "agents": [
                "CustomerAgent",
                "OrderProductAgent",
                "PaymentAgent",
                "DeliveryAgent",
                "PolicyAgent",
                "VerifierAgent",
                "CoordinatorAgent",
            ],
            "primary_issue": output.case_assessment.primary_issue,
            "refund_brl": output.financial_resolution.recommended_refund_brl,
            "structured_output_method": self.structured_method,
            "llm_used": llm_used,
            "llm_error": llm_error,
            "duration_ms": round((time.time() - started) * 1000, 2),
        }
        return output, trace

    def _structured_format(self, case: CaseInput, deterministic: CaseOutput) -> CaseOutput:
        payload = deterministic.model_dump()
        messages = [
            SystemMessage(
                content=(
                    "You are the verifier agent for EC_POLICY_V2. Return exactly the provided "
                    "case JSON in the CaseOutput schema. Do not add facts, evidence, money, "
                    "or actions that are not present in the JSON."
                )
            ),
            HumanMessage(
                content=(
                    f"Case {case.case_id}. Validate and emit this output using tool-calling "
                    f"structured output:\n{json.dumps(payload, ensure_ascii=False)}"
                )
            ),
        ]
        result = self.structured_llm.invoke(messages)
        if isinstance(result, CaseOutput):
            return result
        return CaseOutput.model_validate(result)


def run(input_dir: Path, output_dir: Path, logging_dir: Path, use_llm: bool) -> int:
    load_dotenv()
    input_paths = sorted(input_dir.glob("EC_*.json"))
    clean_generated_outputs(output_dir)
    logging_dir.mkdir(parents=True, exist_ok=True)

    coordinator = CoordinatorAgent(use_llm=use_llm)
    traces = []
    failures = []

    if not input_paths:
        print(f"No input cases found in {input_dir}. Expected files like EC_001.json ... EC_050.json.")

    for path in tqdm(input_paths, desc="Investigating cases", unit="case"):
        try:
            case = CaseInput.model_validate_json(path.read_text(encoding="utf-8"))
            output, trace = coordinator.investigate(case)
            write_json(output_dir / path.name, output.model_dump(mode="json"))
            traces.append(trace)
        except Exception as exc:  # keep the batch auditable instead of hiding partial failure
            failures.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})

    trace_path = logging_dir / "trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as handle:
        for row in traces:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        for row in failures:
            handle.write(json.dumps({"failure": row}, ensure_ascii=False) + "\n")

    metadata = {
        "model": get_model_name(),
        "parameter_size": "<=10B per assignment constraint; verify selected OpenRouter model card",
        "framework": "LangChain",
        "structured_output": {
            "requested_method": "tool_calling",
            "runtime_method": coordinator.structured_method,
        },
        "runtime": {
            "python": platform.python_version(),
            "input_cases": len(input_paths),
            "output_cases": len(traces),
            "failures": len(failures),
        },
    }
    write_json(logging_dir / "metadata.json", metadata)
    print(
        f"Done: {len(traces)}/{len(input_paths)} cases written to {output_dir} "
        f"({len(failures)} failures)."
    )
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-agent Olist dispute resolution.")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--logging-dir", type=Path, default=LOGGING_DIR)
    parser.add_argument("--no-llm", action="store_true", help="Skip the LangChain structured-output LLM call.")
    args = parser.parse_args()
    raise SystemExit(run(args.input_dir, args.output_dir, args.logging_dir, use_llm=not args.no_llm))


if __name__ == "__main__":
    main()
