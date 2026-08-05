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

    def close(self) -> None:
        self.handle.close()

    def __enter__(self) -> "TraceWriter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

