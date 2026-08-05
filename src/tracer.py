import json
import os
from datetime import datetime
from typing import Dict, Any

class Tracer:
    """Logs agent execution steps, handoffs and real LLM calls to logging/trace.jsonl."""

    def __init__(self, trace_file: str = "logging/trace.jsonl"):
        self.trace_file = trace_file
        os.makedirs(os.path.dirname(trace_file), exist_ok=True)

    def log_step(self, case_id: str, agent_name: str, action: str, input_summary: Any, output_summary: Any):
        record = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "case_id": case_id,
            "agent": agent_name,
            "action": action,
            "input_summary": input_summary,
            "output_summary": output_summary
        }
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_llm_call(self, case_id: str, agent_name: str, action: str, model: str,
                      prompt_summary: Any, result_summary: Any, usage: Dict[str, Any] = None,
                      fallback_used: bool = False):
        record = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "case_id": case_id,
            "agent": agent_name,
            "action": action,
            "type": "llm_call",
            "model": model,
            "prompt_summary": prompt_summary,
            "result_summary": result_summary,
            "usage": usage or {},
            "fallback_used": fallback_used
        }
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def reset_file(self):
        with open(self.trace_file, "w", encoding="utf-8") as f:
            pass
