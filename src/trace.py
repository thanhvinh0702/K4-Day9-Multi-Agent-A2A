from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TraceWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8", newline="\n")

    def handoff(
        self,
        case_id: str,
        from_agent: str,
        to_agent: str,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "case_id": case_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "event": "handoff",
            "payload": payload,
        }
        self.handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.handle.flush()

    def policy_comparison(
        self,
        case_id: str,
        deterministic: dict[str, Any],
        llm_decision: dict[str, Any] | None,
        matched: bool,
        fallback_reason: str | None,
    ) -> None:
        """Record LLM-versus-code comparison without credentials or raw data."""
        event = {
            "case_id": case_id,
            "agent": "openrouter_policy_agent",
            "event": "policy_comparison",
            "deterministic_primary_issue": deterministic["primary_issue"],
            "llm_decision": llm_decision,
            "matched": matched,
            "decision_source": "llm_confidence_only" if matched else "deterministic",
            "fallback_reason": fallback_reason,
        }
        self.handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()

    def __enter__(self) -> "TraceWriter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
