from __future__ import annotations

from src.llm import OpenRouterClient


class OpenRouterPolicyAgent:
    name = "openrouter_policy_agent"

    def __init__(self, client: OpenRouterClient | None):
        self.client = client
        self.fallback_count = 0

    def propose(
        self,
        case_id: str,
        facts: dict,
        customer_request: dict | None = None,
    ) -> tuple[dict | None, str | None]:
        if self.client is None:
            self.fallback_count += 1
            return None, "missing_api_key_or_llm_disabled"
        try:
            return self.client.decide_policy(case_id, facts, customer_request), None
        except Exception as exc:  # deterministic policy must remain available
            self.fallback_count += 1
            return None, f"{type(exc).__name__}: {exc}"
