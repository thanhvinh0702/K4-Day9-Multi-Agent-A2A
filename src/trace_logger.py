"""Append-only JSONL trace writer for logging/trace.jsonl.

start_run() truncates the file once per batch run (README.md requires only
the latest run, not accumulated history across runs). log_event() appends
one JSON object per call and is thread-safe since LangGraph may execute the
four domain agent nodes concurrently within a superstep.
"""
from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


class TraceLogger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def start_run(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.path.write_text("", encoding="utf-8")

    def log_event(self, **fields: Any) -> None:
        event = {"timestamp": _now_iso(), **fields}
        line = json.dumps(event, ensure_ascii=False, default=_json_default)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
