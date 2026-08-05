"""Generic single tool-call agent: LLM is forced to call its one bound tool,
then reformats the tool's (already-correct) result into the required
structured schema. Used by all domain agents and the policy agent so the LLM
never has to invent a number - it only decides to call the tool and shapes
the response.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from .config import MODEL_NAME
from .trace_logger import TraceLogger


def run_tool_agent(
    llm: ChatOpenAI,
    trace: TraceLogger,
    case_id: str,
    agent_name: str,
    system_prompt: str,
    human_content: str,
    tool: BaseTool,
    output_schema: type[BaseModel],
) -> BaseModel:
    llm_with_tool = llm.bind_tools([tool], tool_choice=tool.name)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]

    t0 = time.time()
    ai_msg = llm_with_tool.invoke(messages)
    trace.log_event(
        case_id=case_id,
        event_type="agent_call",
        agent=agent_name,
        model=MODEL_NAME,
        step="tool_selection",
        input=human_content,
        output=[tc["name"] for tc in ai_msg.tool_calls],
        duration_ms=int((time.time() - t0) * 1000),
        status="ok",
    )

    messages.append(ai_msg)
    for tc in ai_msg.tool_calls:
        t1 = time.time()
        result = tool.invoke(tc["args"])
        trace.log_event(
            case_id=case_id,
            event_type="tool_call",
            agent=agent_name,
            tool=tc["name"],
            input=tc["args"],
            output=result,
            duration_ms=int((time.time() - t1) * 1000),
            status="ok",
        )
        messages.append(
            ToolMessage(
                content=json.dumps(result, ensure_ascii=False, default=str),
                tool_call_id=tc["id"],
            )
        )

    structured_llm = llm.with_structured_output(output_schema)
    t2 = time.time()
    final = structured_llm.invoke(messages)
    trace.log_event(
        case_id=case_id,
        event_type="agent_call",
        agent=agent_name,
        model=MODEL_NAME,
        step="structured_format",
        output=final.model_dump(),
        duration_ms=int((time.time() - t2) * 1000),
        status="ok",
    )
    return final
