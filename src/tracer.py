import json
import os
from datetime import datetime
from typing import Dict, Any

class Tracer:
    """Logs agent execution steps and handoffs to logging/trace.jsonl."""

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

    def reset_file(self):
        with open(self.trace_file, "w", encoding="utf-8") as f:
            pass
