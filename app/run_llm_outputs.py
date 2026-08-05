from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path

from app.config import ROOT_DIR, get_model_name
from app.lakeagent import build_agent, MissingAgentDependencies
from app.olist_tools import METADATA_PATH, TRACE_PATH
from app.schemas import CaseOutput

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    def tqdm(iterable, **_kwargs):  # type: ignore
        return iterable


INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"


def _question(case_id: str) -> str:
    return (
        f"Investigate case {case_id}. "
        f"Use the investigate_case tool, then return the final structured response "
        f"matching the CaseOutput schema exactly."
    )


def main() -> None:
    try:
        agent = build_agent()
    except MissingAgentDependencies as exc:
        raise SystemExit(str(exc))

    case_files = sorted(INPUT_DIR.glob("EC_*.json"))
    TRACE_PATH.write_text("", encoding="utf-8")
    OUTPUT_DIR.mkdir(exist_ok=True)

    processed = []
    for path in tqdm(case_files, desc="LLM cases", total=len(case_files)):
        result = agent.invoke({"messages": [{"role": "user", "content": _question(path.stem)}]})
        structured = result.get("structured_response")
        if structured is None:
            raise RuntimeError(f"No structured response returned for {path.stem}")

        if isinstance(structured, CaseOutput):
            payload = structured.model_dump()
        else:
            payload = CaseOutput.model_validate(structured).model_dump()

        (OUTPUT_DIR / f"{path.stem}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        processed.append(path.stem)

        with TRACE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "case_id": path.stem,
                "mode": "llm-agent",
                "model": get_model_name(),
            }, ensure_ascii=False) + "\n")

    metadata = {
        "model": get_model_name(),
        "parameter_size": "<=10B or provider model as configured",
        "framework": "LangChain create_agent + tool calling + structured output",
        "runtime": {
            "python": platform.python_version(),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "processed_cases": len(processed),
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"processed": len(processed), "case_ids": processed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
