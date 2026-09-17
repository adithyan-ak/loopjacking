"""Local AgentOS server for the Agno approval-binding experiment."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

from agno.agent import Agent
from agno.approval import approval
from agno.db.sqlite import SqliteDb
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.os import AgentOS
from agno.os.config import AuthorizationConfig
from agno.tools import tool


JWT_KEY = os.environ.get("LOOPJACKING_JWT_KEY", "loopjacking-test-key-not-a-secret")
DB_PATH = Path(os.environ["LOOPJACKING_DB_PATH"])
LEDGER_PATH = Path(os.environ["LOOPJACKING_LEDGER_PATH"])


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()


@approval
@tool(requires_confirmation=True)
def transfer(amount: int, recipient: str, request_id: str) -> str:
    """Record a harmless mock transfer after the required approval."""

    event = {
        "amount": amount,
        "recipient": recipient,
        "request_id": request_id,
        "recorded_at_ns": time.time_ns(),
    }
    _append_jsonl(LEDGER_PATH, event)
    return f"recorded:{amount}:{recipient}:{request_id}"


class DeterministicTransferModel(Model):
    """Propose A or direct-B from an explicit test message, then finish."""

    def __init__(self) -> None:
        super().__init__(id="deterministic-transfer-model", provider="local-test")

    @staticmethod
    def _response(messages: Any) -> ModelResponse:
        messages = messages or []
        if any(getattr(message, "role", None) == "tool" for message in messages):
            return ModelResponse(content="transfer flow complete", role="assistant")

        text = "\n".join(str(getattr(message, "content", "")) for message in messages)
        match = re.search(r"CASE=([A-Za-z0-9_.:-]+)", text)
        request_id = match.group(1) if match else "missing-case-id"
        direct_b = "DIRECT_B" in text
        args = {
            "amount": 2000 if direct_b else 20,
            "recipient": "attacker-sink" if direct_b else "approved-vendor",
            "request_id": request_id,
        }
        return ModelResponse(
            role="assistant",
            tool_calls=[
                {
                    "id": f"transfer-{request_id}",
                    "type": "function",
                    "function": {
                        "name": "transfer",
                        "arguments": json.dumps(args, sort_keys=True),
                    },
                }
            ],
        )

    def invoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return self._response(kwargs.get("messages"))

    async def ainvoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        return self._response(kwargs.get("messages"))

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Iterator[ModelResponse]:
        yield self._response(kwargs.get("messages"))

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ModelResponse]:
        yield self._response(kwargs.get("messages"))

    def _parse_provider_response(self, response: Any, **kwargs: Any) -> ModelResponse:
        return response

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        return response


DB_PATH.parent.mkdir(parents=True, exist_ok=True)
db = SqliteDb(db_file=str(DB_PATH))
agent = Agent(
    id="transfer-agent",
    name="Deterministic transfer agent",
    model=DeterministicTransferModel(),
    tools=[transfer],
    db=db,
    telemetry=False,
    store_events=True,
)
agent_os = AgentOS(
    id="loopjacking-agno-test",
    agents=[agent],
    db=db,
    authorization=True,
    authorization_config=AuthorizationConfig(
        verification_keys=[JWT_KEY],
        algorithm="HS256",
        admin_scope="agent_os:admin",
        user_isolation=True,
    ),
    telemetry=False,
    auto_provision_dbs=True,
)
app = agent_os.get_app()

