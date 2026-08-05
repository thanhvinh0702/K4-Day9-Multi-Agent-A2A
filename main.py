import os
import glob
import json
import zipfile
from dotenv import load_dotenv
from src.data_loader import DataLoader
from src.tracer import Tracer
from src.agents.coordinator_agent import CoordinatorAgent
from src.generate_inputs import generate_50_input_cases
from src.llm_client import LLMClient, MODEL_NAME, MODEL_PARAM_SIZE, MODEL_PROVIDER


def main():
    load_dotenv()

    print("=" * 60)
    print("Starting Multi-Agent E-commerce Dispute Resolution System")
    print("=" * 60)

    data_dir = "data"
    input_dir = "input"
    output_dir = "output"
    logging_dir = "logging"

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(logging_dir, exist_ok=True)

    input_files = sorted(glob.glob(os.path.join(input_dir, "EC_*.json")))
    if len(input_files) < 50:
        print("Input files missing or incomplete. Generating 50 input cases from Olist dataset...")
        generate_50_input_cases(data_dir=data_dir, input_dir=input_dir)
        input_files = sorted(glob.glob(os.path.join(input_dir, "EC_*.json")))

    print(f"Found {len(input_files)} input cases.")

    try:
        llm_client = LLMClient()
        print(f"LLM client ready: provider={MODEL_PROVIDER} model={MODEL_NAME} ({MODEL_PARAM_SIZE} params)")
    except RuntimeError as e:
        llm_client = None
        print(f"WARNING: running WITHOUT a real LLM ({e}). "
              f"Policy/Verifier/Coordinator will fall back to deterministic-only values.")

    data_loader = DataLoader(data_dir=data_dir)
    tracer = Tracer(trace_file=os.path.join(logging_dir, "trace.jsonl"))
    tracer.reset_file()

    coordinator = CoordinatorAgent(data_loader=data_loader, tracer=tracer, llm_client=llm_client)

    print("Processing dispute resolution cases...")
    processed_count = 0
    for file_path in input_files:
        with open(file_path, "r", encoding="utf-8") as f:
            case_input = json.load(f)

        case_id = case_input.get("case_id")
        verified_output = coordinator.process_case(case_input)

        out_path = os.path.join(output_dir, f"{case_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(verified_output, f, ensure_ascii=False, indent=2)

        processed_count += 1
        if processed_count % 10 == 0 or processed_count == len(input_files):
            print(f"Processed {processed_count}/{len(input_files)} cases.")

    metadata_content = {
        "model": MODEL_NAME if llm_client else f"{MODEL_NAME} (unavailable this run — deterministic fallback used)",
        "parameter_size": MODEL_PARAM_SIZE,
        "provider": MODEL_PROVIDER,
        "framework": "Custom Hybrid Deterministic-Rule + LLM-Verified Multi-Agent System (Python)",
        "runtime": "Python 3.13",
        "total_cases_processed": processed_count,
        "policy_version": "EC_POLICY_V2",
    }

    metadata_path = os.path.join(logging_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata_content, f, ensure_ascii=False, indent=2)

    print(f"Metadata written to {metadata_path}.")

    zip_path = "output.zip"
    output_jsons = sorted(glob.glob(os.path.join(output_dir, "EC_*.json")))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for json_file in output_jsons:
            arcname = os.path.basename(json_file)
            zf.write(json_file, arcname=arcname)

    print(f"Created submission archive '{zip_path}' containing {len(output_jsons)} JSON files.")
    print("=" * 60)
    print("Multi-Agent System Execution Completed Successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
