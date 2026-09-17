from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable


ACTION_MESSAGE_ID = "approval-action"
TOOL_CALL_ID = "transfer-call"
A = {"amount": 20, "destination": "approved-vendor", "request_id": "req-001"}
B = {"amount": 2000, "destination": "attacker-sink", "request_id": "req-001"}


def _append_jsonl(env_name: str, record: dict[str, Any]) -> None:
    path = Path(os.environ[env_name])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


@tool
def mock_wire_transfer(
    amount: int,
    destination: str,
    request_id: str,
    runtime: ToolRuntime,
) -> str:
    """Append an authorized synthetic transfer to a harmless local ledger."""
    configurable = runtime.config.get("configurable", {})
    permissions = list(configurable.get("langgraph_auth_permissions") or [])
    actor = configurable.get("langgraph_auth_user_id")
    record = {
        "actor": actor,
        "thread_id": configurable.get("thread_id"),
        "amount": amount,
        "destination": destination,
        "request_id": request_id,
        "tool_call_id": runtime.tool_call_id,
        "permissions": permissions,
        "authorized": "wire:execute" in permissions,
    }
    _append_jsonl("ATTEMPTS_PATH", record)
    if "wire:execute" not in permissions:
        raise PermissionError(f"{actor!r} lacks wire:execute")
    _append_jsonl("LEDGER_PATH", record)
    return f"recorded synthetic transfer {request_id}"


class DeterministicTransferModel(BaseChatModel):
    """No-network model fixture: emits A, or B only for the direct-B control."""

    @property
    def _llm_type(self) -> str:
        return "deterministic-transfer-model"

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if any(isinstance(message, ToolMessage) for message in messages):
            response = AIMessage(content="done", id="final-response")
        else:
            direct_b = any(
                isinstance(message, HumanMessage) and "DIRECT_B" in str(message.content)
                for message in messages
            )
            args = B if direct_b else A
            response = AIMessage(
                content="",
                id=ACTION_MESSAGE_ID,
                tool_calls=[
                    {
                        "name": "mock_wire_transfer",
                        "args": args,
                        "id": TOOL_CALL_ID,
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=response)])


graph = create_agent(
    model=DeterministicTransferModel(),
    tools=[mock_wire_transfer],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "mock_wire_transfer": {"allowed_decisions": ["approve", "reject"]}
            }
        )
    ],
)
