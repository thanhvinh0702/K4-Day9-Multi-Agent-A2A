from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR, get_model_name, load_env
from app.olist_tools import OlistCaseTools
from app.schemas import CaseOutput


def build_system_prompt(datalake_dir: str, resolved_datalake_dir: str | None = None) -> str:
    resolved = resolved_datalake_dir or datalake_dir
    return f"""You are lakeagent_retrieval_agent for an Olist e-commerce dispute dataset.

You answer in Vietnamese. Use tools before making claims about an order or case.
The dataset lives at: {resolved}

Core rules:
- Read case inputs from input/EC_*.json.
- Investigate the claimed_order_id against CSV rows.
- Apply EC_POLICY_V2 exactly.
- Prefer CSV evidence over assumptions.
- When the user asks for one case, call investigate_case.
- When the user gives a raw 32-character order_id, call investigate_order.
- When the user asks to process all cases, call run_all_cases.
- Final answers must be structured and conform to the CaseOutput schema.
"""


def build_model() -> Any:
    load_env()
    model_name = get_model_name()
    api_key = os.environ.get("OPENROUTER_API_KEY")

    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        if "/" in model_name and ":" not in model_name:
            return f"openrouter:{model_name}"
        return model_name

    if api_key:
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
        )
    return ChatOpenAI(model=model_name, temperature=0)


class DisputeAgent:
    def __init__(self) -> None:
        load_env()
        self.tools = OlistCaseTools()
        self.agent_graph = self._try_create_agent()

    def build_tools(self) -> list[Any]:
        try:
            from langchain.tools import tool
        except Exception:
            tool = None

        def investigate_case_raw(case_id: str) -> str:
            """Investigate an input case such as EC_001 and write its output JSON."""
            return json.dumps(self.tools.investigate_case_file(case_id), ensure_ascii=False)

        def investigate_order_raw(order_id: str) -> str:
            """Investigate a raw Olist order_id without requiring an input file."""
            return json.dumps(self.tools.investigate_order("ADHOC", order_id, write_output=False), ensure_ascii=False)

        def run_all_cases_raw() -> str:
            """Investigate all EC_*.json files and write output JSON files."""
            return json.dumps(self.tools.run_all_cases(), ensure_ascii=False)

        if not tool:
            return [investigate_case_raw, investigate_order_raw, run_all_cases_raw]

        return [
            tool("investigate_case")(investigate_case_raw),
            tool("investigate_order")(investigate_order_raw),
            tool("run_all_cases")(run_all_cases_raw),
        ]

    def build_middleware(self, model: Any) -> list[Any]:
        middleware = []
        try:
            from deepagents.backends import StateBackend
            from deepagents.middleware.filesystem import FilesystemMiddleware
            middleware.append(FilesystemMiddleware(backend=StateBackend()))
        except Exception:
            pass

        try:
            from langchain.agents.middleware import SummarizationMiddleware, TodoListMiddleware
            middleware.extend([
                SummarizationMiddleware(model=model, trigger=("messages", 20), keep=("messages", 10)),
                TodoListMiddleware(),
            ])
        except Exception:
            pass
        return middleware

    def _try_create_agent(self) -> Any | None:
        try:
            from langchain.agents import create_agent
        except Exception:
            return None

        model = build_model()
        tools = self.build_tools()
        resolved_datalake_dir = str((ROOT_DIR / "data").resolve())
        return create_agent(
            model=model,
            tools=tools,
            system_prompt=build_system_prompt(
                str(Path("data")),
                resolved_datalake_dir=resolved_datalake_dir,
            ),
            middleware=self.build_middleware(model),
            response_format=CaseOutput,
            name="lakeagent_retrieval_agent",
        )

    def ask(self, question: str) -> dict[str, Any]:
        if self.agent_graph and os.environ.get("OPENROUTER_API_KEY"):
            result = self.agent_graph.invoke({"messages": [{"role": "user", "content": question}]})
            structured = result.get("structured_response")
            if structured is not None:
                return {"mode": "langchain-create-agent", "answer": structured}
            message = result["messages"][-1]
            content = message.content if hasattr(message, "content") else message.get("content", "")
            return {"mode": "langchain-create-agent", "answer": content}

        if "all" in question.lower() or "50" in question:
            return {"mode": "local-tools", "answer": self.tools.run_all_cases()}

        case_match = re.search(r"EC_\d{3}", question, re.IGNORECASE)
        if case_match:
            case_id = case_match.group(0).upper()
            return {"mode": "local-tools", "answer": self.tools.investigate_case_file(case_id)}

        order_match = re.search(r"\b[a-f0-9]{32}\b", question)
        if order_match:
            return {
                "mode": "local-tools",
                "answer": self.tools.investigate_order("ADHOC", order_match.group(0), write_output=False),
            }

        return {
            "mode": "local-tools",
            "answer": (
                "Hãy hỏi theo dạng 'investigate EC_001', đưa trực tiếp order_id, "
                "hoặc 'run all 50 cases'. Nếu cài deepagents thì agent sẽ dùng LLM + tools."
            ),
        }
