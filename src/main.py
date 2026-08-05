from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from tqdm import tqdm

from src.config import LLMSettings, load_dotenv
from src.datastore import OlistDataStore
from src.llm import OpenRouterClient
from src.openrouter_policy import OpenRouterPolicyAgent
from src.resolver import resolve_case
from src.trace import TraceWriter


def commit_file(staged: Path, target: Path) -> None:
    """Copy verified bytes into the target so Windows keeps target-directory access."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(staged.read_bytes())


def validate_submission_zip(path: Path, expected_names: list[str]) -> None:
    """Hard-gate the exact submission layout required by the assignment."""
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        if names != expected_names:
            raise ValueError(
                "Submission ZIP must contain exactly the 50 JSON files at ZIP root; "
                f"expected {len(expected_names)} entries, found {len(names)}"
            )
        for name in names:
            if "/" in name or "\\" in name or not name.endswith(".json"):
                raise ValueError(f"Invalid submission ZIP entry: {name}")
            json.loads(archive.read(name).decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve Olist dispute cases")
    parser.add_argument("--input-dir", default="input/input")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--trace", default="logging/trace.jsonl")
    parser.add_argument("--metadata", default="logging/metadata.json")
    parser.add_argument("--zip", default="output.zip")
    parser.add_argument(
        "--case",
        help="Run one case such as EC_001 to validate configuration before all 50",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable OpenRouter for offline deterministic development tests",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    try:
        settings = LLMSettings.from_env(disabled_by_cli=args.no_llm)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    case_paths = sorted(input_dir.glob("EC_*.json"))
    if args.case:
        requested = args.case if args.case.endswith(".json") else f"{args.case}.json"
        case_paths = [path for path in case_paths if path.name == requested]
    if not case_paths:
        raise SystemExit(f"No matching EC_*.json files found in {input_dir}")
    store = OlistDataStore(args.data_dir)
    issues: Counter[str] = Counter()
    llm = OpenRouterClient(settings) if settings.enabled and settings.api_key else None
    openrouter_policy = OpenRouterPolicyAgent(llm)
    llm_matches = 0
    llm_fallbacks = 0
    llm_request_failures = 0
    llm_policy_mismatches = 0
    llm_unavailable = 0
    claims_checked = 0
    claims_supported = 0
    claims_rejected = 0
    with tempfile.TemporaryDirectory(
        prefix=".ec_run_", dir=output_dir.parent
    ) as temporary:
        stage_root = Path(temporary)
        staged_output = stage_root / "output"
        staged_output.mkdir()
        staged_trace = stage_root / "trace.jsonl"
        staged_metadata = stage_root / "metadata.json"
        staged_zip = stage_root / "output.zip"
        with TraceWriter(staged_trace) as trace:
            progress = tqdm(
                case_paths,
                total=len(case_paths),
                desc="Processing cases",
                unit="case",
                dynamic_ncols=True,
            )
            for path in progress:
                case = json.loads(path.read_text(encoding="utf-8"))
                progress.set_postfix_str(f"current={case['case_id']}", refresh=True)
                result, run_info = resolve_case(case, store, trace, openrouter_policy)
                llm_matches += int(run_info["llm_matched"])
                llm_fallbacks += int(run_info["llm_fallback"])
                llm_request_failures += int(run_info["llm_request_failed"])
                llm_policy_mismatches += int(run_info["llm_policy_mismatch"])
                llm_unavailable += int(run_info["llm_unavailable"])
                claims_checked += int(run_info["claim_checked"])
                claims_supported += int(run_info["claim_supported"])
                claims_rejected += int(run_info["claim_rejected"])
                primary_issue = result["case_assessment"]["primary_issue"]
                issues[primary_issue] += 1
                target = staged_output / path.name
                target.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                progress.set_postfix_str(
                    f"done={case['case_id']} issue={primary_issue}", refresh=True
                )
        metadata = {
            "model": settings.model if llm else "deterministic-fallback",
            "parameter_size": settings.parameter_size if llm else "N/A",
            "provider": "OpenRouter" if llm else "none",
            "framework": "deterministic-openrouter-policy-multi-agent",
            "runtime": "Python standard library",
            "policy_version": "EC_POLICY_V2",
            "case_count": len(case_paths),
            "llm_requested": settings.enabled,
            "llm_enabled": llm is not None,
            "llm_calls": llm.call_count if llm else 0,
            "llm_policy_matches": llm_matches,
            "llm_fallbacks": llm_fallbacks,
            "llm_request_failures": llm_request_failures,
            "llm_policy_mismatches": llm_policy_mismatches,
            "llm_unavailable_cases": llm_unavailable,
            "customer_claims_checked": claims_checked,
            "customer_claims_supported": claims_supported,
            "customer_claims_rejected": claims_rejected,
            "prompt_tokens": llm.prompt_tokens if llm else 0,
            "completion_tokens": llm.completion_tokens if llm else 0,
        }
        staged_metadata.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if not args.case:
            with zipfile.ZipFile(
                staged_zip, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for case_path in case_paths:
                    staged_path = staged_output / case_path.name
                    archive.write(staged_path, arcname=staged_path.name)
            validate_submission_zip(staged_zip, [path.name for path in case_paths])

        # Commit only after every case, verifier, metadata and ZIP step succeeds.
        output_dir.mkdir(parents=True, exist_ok=True)
        for case_path in case_paths:
            commit_file(staged_output / case_path.name, output_dir / case_path.name)
        trace_path = Path(args.trace)
        commit_file(staged_trace, trace_path)
        metadata_path = Path(args.metadata)
        commit_file(staged_metadata, metadata_path)
        if not args.case:
            zip_path = Path(args.zip)
            commit_file(staged_zip, zip_path)
            print(f"Created submission ZIP: {zip_path}")
    print(f"Generated and verified {len(case_paths)} files in {output_dir}")
    for issue, count in sorted(issues.items()):
        print(f"  {issue}: {count}")


if __name__ == "__main__":
    main()
