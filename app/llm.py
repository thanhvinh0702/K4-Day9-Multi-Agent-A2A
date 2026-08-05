from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.config import get_model_name, get_openrouter_base_url, get_openrouter_key
from app.schemas import CaseOutput


def build_structured_llm(schema: Any = CaseOutput) -> tuple[Any | None, str]:
    api_key = get_openrouter_key()
    if not api_key:
        return None, "disabled_missing_OPENROUTER_API_KEY"

    llm = ChatOpenAI(
        model=get_model_name(),
        api_key=api_key,
        base_url=get_openrouter_base_url(),
        temperature=0,
        max_retries=1,
        timeout=60,
    )
    try:
        return llm.with_structured_output(schema, method="tool_calling"), "tool_calling"
    except ValueError:
        return llm.with_structured_output(schema, method="function_calling"), "function_calling_tool_calling_compat"
