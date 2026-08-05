from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from src.config import LLMSettings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
POLICY_SCHEMA = {
    "name": "policy_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "primary_issue": {"type": "string"},
            "cause_code": {"type": "string"},
            "responsible_parties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "party_type": {"type": "string"},
                        "party_id": {"type": "string"},
                    },
                    "required": ["party_type", "party_id"],
                    "additionalProperties": False,
                },
            },
            "recommended_refund_brl": {"type": "number"},
            "primary_action": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": [
            "primary_issue",
            "cause_code",
            "responsible_parties",
            "recommended_refund_brl",
            "primary_action",
            "confidence",
        ],
        "additionalProperties": False,
    },
}


class OpenRouterClient:
    def __init__(
        self,
        settings: LLMSettings,
        transport: Callable[..., Any] = urllib.request.urlopen,
    ):
        self.settings = settings
        self.transport = transport
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def decide_policy(self, case_id: str, facts: dict[str, Any]) -> dict:
        body = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the OpenRouter Policy Agent for EC_POLICY_V2. "
                        "Evaluate only the supplied computed facts. Do not invent "
                        "IDs, amounts, timestamps, or events. Apply rules in order: "
                        "(1) canceled and paid => canceled_order_paid, "
                        "ORDER_CANCELED_AFTER_PAYMENT, platform/OLIST_PLATFORM, "
                        "issue_full_refund and refund payment_total_brl; "
                        "(2) unavailable and paid => "
                        "unavailable_order_paid, ORDER_UNAVAILABLE_AFTER_PAYMENT, "
                        "platform/OLIST_PLATFORM, issue_full_refund and refund "
                        "payment_total_brl; (3) delivered "
                        "late with late_handoff_seller_ids => late_delivery_seller, "
                        "SELLER_HANDOFF_AFTER_LIMIT, seller/first late seller, "
                        "refund_freight and refund freight_total_brl; (4) delivered "
                        "late => late_delivery_logistics, "
                        "CARRIER_DELIVERED_AFTER_ESTIMATE, logistics_provider/"
                        "LOGISTICS_PROVIDER, refund_freight and refund "
                        "freight_total_brl; (5) two or more payment "
                        "rows and reconciled => valid_split_payment, "
                        "MULTIPLE_PAYMENTS_RECONCILED, empty responsible_parties, "
                        "explain_valid_split_payment and refund 0; (6) delivered "
                        "within estimate "
                        "and reconciled => unsupported_late_claim, "
                        "DELIVERY_WITHIN_ESTIMATE, empty responsible_parties, "
                        "reject_late_refund and refund 0. Return every late seller "
                        "in responsible_parties in source order. "
                        "Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"case_id": case_id, "facts": facts},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 220,
            "response_format": {"type": "json_schema", "json_schema": POLICY_SCHEMA},
        }
        request = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/olist-multi-agent-lab",
                "X-OpenRouter-Title": "K4 Day 09 Olist Multi-Agent",
            },
            method="POST",
        )
        response_data = self._send(request)
        try:
            content = response_data["choices"][0]["message"]["content"]
            decision = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("OpenRouter returned invalid policy JSON") from exc
        required = set(POLICY_SCHEMA["schema"]["required"])
        if set(decision) != required:
            raise RuntimeError("OpenRouter policy response does not match contract")
        usage = response_data.get("usage") or {}
        self.call_count += 1
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        decision["generation_id"] = response_data.get("id")
        decision["resolved_model"] = response_data.get("model", self.settings.model)
        return decision

    def _send(self, request: urllib.request.Request) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                with self.transport(request, timeout=self.settings.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    time.sleep(2**attempt)
        raise RuntimeError(
            f"OpenRouter request failed after {self.settings.max_retries + 1} attempts"
        ) from last_error
