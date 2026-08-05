from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src import DEFAULT_MODEL


def load_dotenv(path: str | Path = ".env") -> None:
    """Small dependency-free .env loader; existing environment variables win."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value and value[0:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool
    api_key: str
    model: str
    parameter_size: str
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_env(cls, disabled_by_cli: bool = False) -> "LLMSettings":
        enabled = env_bool("LLM_ENABLED", True) and not disabled_by_cli
        model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip()
        if not model:
            model = DEFAULT_MODEL
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        return cls(
            enabled=enabled,
            api_key=api_key,
            model=model,
            parameter_size=os.getenv("OPENROUTER_PARAMETER_SIZE", "unknown").strip()
            or "unknown",
            timeout_seconds=int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "2")),
        )
