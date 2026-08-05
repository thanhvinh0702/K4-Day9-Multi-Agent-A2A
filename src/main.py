from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src import MODEL_NAME
from src.datastore import OlistDataStore
from src.orchestrator import CoordinatorAgent
from src.trace import TraceWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve Olist dispute cases")
    parser.add_argument("--input-dir", default="input/input")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--trace", default="logging/trace.jsonl")
    parser.add_argument("--metadata", default="logging/metadata.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    case_paths = sorted(input_dir.glob("EC_*.json"))
    if not case_paths:
        raise SystemExit(f"No EC_*.json files found in {input_dir}")
    store = OlistDataStore(args.data_dir)
    issues: Counter[str] = Counter()
    with TraceWriter(args.trace) as trace:
        coordinator = CoordinatorAgent(store, trace)
        for path in case_paths:
            case = json.loads(path.read_text(encoding="utf-8"))
            result = coordinator.process(case)
            issues[result["case_assessment"]["primary_issue"]] += 1
            target = output_dir / path.name
            target.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    metadata = {
        "model": MODEL_NAME,
        "parameter_size": "N/A",
        "framework": "custom-python-multi-agent",
        "runtime": "Python standard library",
        "policy_version": "EC_POLICY_V2",
        "case_count": len(case_paths),
    }
    metadata_path = Path(args.metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated and verified {len(case_paths)} files in {output_dir}")
    for issue, count in sorted(issues.items()):
        print(f"  {issue}: {count}")


if __name__ == "__main__":
    main()

