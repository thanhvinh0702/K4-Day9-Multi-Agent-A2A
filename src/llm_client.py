import os
import json
import time
from typing import Any, Dict, Optional
from openai import OpenAI

# EC_POLICY_V2 multi-agent system: every agent below uses this single model.
# llama-3.1-8b-instant has 8B parameters (<= the 10B cap in README section 9.1),
# served by Groq (OpenAI-compatible API).
MODEL_NAME = "llama-3.1-8b-instant"
MODEL_PARAM_SIZE = "8B"
MODEL_PROVIDER = "Groq"


class LLMClient:
    """Thin wrapper around the Groq OpenAI-compatible chat API used by Policy,
    Verifier and Coordinator agents for genuine LLM reasoning steps."""

    def __init__(self, api_key: Optional[str] = None, model: str = MODEL_NAME):
        api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Copy .env.example to .env and fill in a "
                "free key from https://console.groq.com/keys"
            )
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.model = model

    def chat_json(self, system_prompt: str, user_prompt: str, max_retries: int = 3, max_tokens: int = 400) -> Dict[str, Any]:
        """Call the model and parse a strict JSON object from its response."""
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                content = resp.choices[0].message.content
                usage = resp.usage
                parsed = json.loads(content)
                return {
                    "parsed": parsed,
                    "raw": content,
                    "model": self.model,
                    "usage": {
                        "prompt_tokens": usage.prompt_tokens if usage else None,
                        "completion_tokens": usage.completion_tokens if usage else None,
                    },
                }
            except Exception as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_err}")
