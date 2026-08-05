from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from app.agent import build_model, build_system_prompt
from app.config import ROOT_DIR, load_env
from app.olist_tools import OlistCaseTools
from app.schemas import CaseOutput


class MissingAgentDependencies(RuntimeError):
    pass


def build_tools(case_tools: OlistCaseTools | None = None) -> list[Any]:
    case_tools = case_tools or OlistCaseTools()

    try:
        from langchain.tools import tool
    except Exception as exc:
        raise MissingAgentDependencies(
            "Missing LangChain. Install with: python3 -m pip install -r requirements.txt"
        ) from exc

    @tool
    def investigate_case(case_id: str) -> str:
        """Investigate an input case like EC_001 and write output/EC_001.json."""
        return json.dumps(case_tools.investigate_case_file(case_id), ensure_ascii=False)

    @tool
    def investigate_order(order_id: str) -> str:
        """Investigate a raw 32-character Olist order_id without writing an output file."""
        return json.dumps(case_tools.investigate_order("ADHOC", order_id, write_output=False), ensure_ascii=False)

    @tool
    def run_all_cases() -> str:
        """Process all input/EC_*.json files and write output JSON files."""
        return json.dumps(case_tools.run_all_cases(), ensure_ascii=False)

    return [investigate_case, investigate_order, run_all_cases]


def build_backend(root_dir: Path | None = None) -> Any:
    try:
        from deepagents.backends import LocalShellBackend
    except Exception as exc:
        raise MissingAgentDependencies(
            "Missing deepagents. Install with: python3 -m pip install -r requirements.txt"
        ) from exc

    root = (root_dir or ROOT_DIR).resolve()
    return LocalShellBackend(
        root_dir=str(root),
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(root),
        },
    )


def build_middleware(model: Any, backend: Any, resolved_datalake_dir: str) -> list[Any]:
    try:
        from deepagents.middleware.filesystem import FilesystemMiddleware
        from langchain.agents.middleware import SummarizationMiddleware, TodoListMiddleware
    except Exception as exc:
        raise MissingAgentDependencies(
            "Missing agent middleware packages. Install with: python3 -m pip install -r requirements.txt"
        ) from exc

    return [
        FilesystemMiddleware(backend=backend),
        SummarizationMiddleware(model=model, trigger=("messages", 20), keep=("messages", 10)),
        TodoListMiddleware(),
    ]


def build_agent() -> Any:
    load_env()
    try:
        from langchain.agents import create_agent
    except Exception as exc:
        raise MissingAgentDependencies(
            "Missing LangChain. Install with: python3 -m pip install -r requirements.txt"
        ) from exc

    model = build_model()
    tools = build_tools()
    resolved_datalake_dir = str((ROOT_DIR / "data").resolve())
    backend = build_backend(ROOT_DIR)

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=build_system_prompt(
            str(Path("data")),
            resolved_datalake_dir=resolved_datalake_dir,
        ),
        middleware=build_middleware(
            model=model,
            backend=backend,
            resolved_datalake_dir=resolved_datalake_dir,
        ),
        response_format=CaseOutput,
        name="lakeagent_retrieval_agent",
    )


def run(question: str) -> Any:
    agent = build_agent()
    return agent.invoke({"messages": [{"role": "user", "content": question}]})


def main() -> None:
    question = " ".join(sys.argv[1:]) or "investigate EC_001"
    try:
        result = run(question)
    except Exception as exc:
        print(f"Agent runtime error: {exc}")
        raise
    structured = result.get("structured_response")
    if structured is not None:
        if hasattr(structured, "model_dump_json"):
            print(structured.model_dump_json(indent=2))
        else:
            print(json.dumps(structured, ensure_ascii=False, indent=2))
        return

    message = result["messages"][-1]
    if hasattr(message, "content"):
        print(message.content)
    else:
        print(message.get("content", ""))


if __name__ == "__main__":
    main()
