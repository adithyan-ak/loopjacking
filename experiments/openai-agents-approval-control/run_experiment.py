#!/usr/bin/env python3
"""Native serialized-approval mutation control for the OpenAI Agents SDK."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from agents import Agent, RunState, Runner, function_tool, set_tracing_disabled
from agents.testing import ScriptedModel, assistant_message, function_call


A = {"amount": 20, "recipient": "alice", "request_id": "A"}
B = {"amount": 2000, "recipient": "mallory", "request_id": "B"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Case:
    def __init__(self, call: dict[str, Any], call_id: str) -> None:
        self.ledger: list[dict[str, Any]] = []

        @function_tool(needs_approval=True)
        def transfer(amount: int, recipient: str, request_id: str) -> str:
            """Record a harmless mock transfer."""
            entry = {"amount": amount, "recipient": recipient, "request_id": request_id}
            self.ledger.append(entry)
            return json.dumps(entry, sort_keys=True)

        self.model = ScriptedModel(
            [
                [function_call("transfer", call, call_id=call_id)],
                [assistant_message("done")],
            ]
        )
        self.agent = Agent(
            name="approval-control-agent",
            instructions="Call the transfer tool exactly once.",
            tools=[transfer],
            model=self.model,
        )


def mutate_raw_invocation_a_to_b(value: Any, call_id: str) -> int:
    """Change every serialized raw function-call copy, not the canonical ledger."""
    changed = 0
    if isinstance(value, dict):
        if value.get("type") == "function_call" and value.get("call_id") == call_id:
            if isinstance(value.get("arguments"), str):
                value["arguments"] = json.dumps(B, separators=(",", ":"))
                changed += 1
        for child in value.values():
            changed += mutate_raw_invocation_a_to_b(child, call_id)
    elif isinstance(value, list):
        for child in value:
            changed += mutate_raw_invocation_a_to_b(child, call_id)
    return changed


async def approved_snapshot(case_id: str) -> tuple[Case, dict[str, Any], dict[str, Any]]:
    call_id = f"call-{case_id}"
    case = Case(A, call_id)
    result = await Runner.run(case.agent, "Record exact action A")
    if len(result.interruptions) != 1:
        raise AssertionError(f"Expected one approval interruption, got {len(result.interruptions)}")
    interruption = result.interruptions[0]
    raw = interruption.raw_item
    reviewed = json.loads(raw.arguments)
    if reviewed != A or raw.call_id != call_id:
        raise AssertionError(f"Approval prompt was not exact A: {raw}")
    state = result.to_state()
    state.approve(interruption)
    payload = state.to_json()
    approval_record = payload["context"]["approvals"]["transfer"]
    invocation_record = payload["context"]["tool_invocations"][call_id]
    receipt = {
        "call_id": call_id,
        "reviewed_action": reviewed,
        "approval_record": copy.deepcopy(approval_record),
        "canonical_invocation_record": copy.deepcopy(invocation_record),
    }
    return case, payload, receipt


async def honest_case(case_id: str, snapshots: Path) -> dict[str, Any]:
    case, payload, receipt = await approved_snapshot(case_id)
    write_json(snapshots / f"{case_id}-approved-a.json", payload)
    restored = await RunState.from_json(case.agent, copy.deepcopy(payload))
    result = await Runner.run(case.agent, restored)
    passed = result.final_output == "done" and case.ledger == [A]
    return {
        "trial": case_id,
        **receipt,
        "restored": True,
        "final_output": result.final_output,
        "ledger": case.ledger,
        "oracle_pass": passed,
    }


async def mutation_case(case_id: str, snapshots: Path) -> dict[str, Any]:
    case, payload, receipt = await approved_snapshot(case_id)
    write_json(snapshots / f"{case_id}-approved-a.json", payload)
    mutated = copy.deepcopy(payload)
    changed_copies = mutate_raw_invocation_a_to_b(mutated, receipt["call_id"])
    write_json(snapshots / f"{case_id}-mutated-b.json", mutated)
    error: dict[str, str] | None = None
    restored = False
    try:
        state = await RunState.from_json(case.agent, copy.deepcopy(mutated))
        restored = True
        await Runner.run(case.agent, state)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    passed = (
        restored
        and changed_copies > 0
        and error is not None
        and error["type"] == "ModelBehaviorError"
        and "reused a tool call ID for a different invocation" in error["message"]
        and case.ledger == []
    )
    return {
        "trial": case_id,
        **receipt,
        "mutated_action": B,
        "raw_invocation_copies_changed": changed_copies,
        "canonical_invocation_record_after_mutation": copy.deepcopy(
            mutated["context"]["tool_invocations"][receipt["call_id"]]
        ),
        "restored": restored,
        "error": error,
        "ledger": case.ledger,
        "oracle_pass": passed,
    }


async def direct_b_case() -> dict[str, Any]:
    case = Case(B, "call-direct-b")
    result = await Runner.run(case.agent, "Record exact action B")
    reviewed = json.loads(result.interruptions[0].raw_item.arguments)
    return {
        "trial": "control_direct_b_unapproved",
        "reviewed_action": reviewed,
        "interruptions": len(result.interruptions),
        "ledger": case.ledger,
        "oracle_pass": len(result.interruptions) == 1 and reviewed == B and case.ledger == [],
    }


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    honest = [row for row in trials if row["trial"].startswith("control_honest_a_")]
    attacks = [row for row in trials if row["trial"].startswith("attack_mutated_b_")]
    direct = next(row for row in trials if row["trial"] == "control_direct_b_unapproved")
    honest_pass = sum(row["oracle_pass"] is True for row in honest)
    attack_rejected = sum(row["oracle_pass"] is True for row in attacks)
    strict = (
        honest_pass == len(honest) == 3
        and attack_rejected == len(attacks) == 3
        and direct["oracle_pass"] is True
    )
    return {
        "interpretation": "ordinary_per_call_approval_is_action_bound" if strict else "indeterminate",
        "strict_negative_control_pass": strict,
        "honest_a_pass": honest_pass,
        "honest_a_total": len(honest),
        "mutated_b_rejected": attack_rejected,
        "mutated_b_total": len(attacks),
        "direct_b_unapproved_pass": direct["oracle_pass"] is True,
        "completed_trials": len(trials),
        "total_trials": 7,
    }


def source_receipts() -> dict[str, Any]:
    import agents

    root = Path(agents.__file__).resolve().parent
    names = ["_tool_invocation.py", "run_context.py", "run_state.py", "testing/model.py", "tool.py"]
    return {
        name: {"sha256": sha256(root / name), "size": (root / name).stat().st_size}
        for name in names
    }


def harness_receipts() -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    names = ["README.md", "run.sh", "run_experiment.py"]
    return {
        "files": {
            name: {"sha256": sha256(root / name), "size": (root / name).stat().st_size}
            for name in names
        },
    }


def installed_packages() -> list[dict[str, str]]:
    rows = [
        {"name": dist.metadata.get("Name") or "unknown", "version": dist.version}
        for dist in metadata.distributions()
    ]
    return sorted(rows, key=lambda row: (row["name"].lower(), row["version"]))


def write_hashes(evidence_dir: Path) -> None:
    rows = []
    for item in sorted(path for path in evidence_dir.rglob("*") if path.is_file() and path.name != "SHA256SUMS"):
        rows.append(f"{sha256(item)}  {item.relative_to(evidence_dir)}")
    (evidence_dir / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    set_tracing_disabled(True)

    version = metadata.version("openai-agents")
    started = datetime.now(timezone.utc)
    evidence_dir = (args.output_root / f"openai-agents-{version}" / started.strftime("%Y%m%dT%H%M%SZ")).resolve()
    snapshots = evidence_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=False)

    trials: list[dict[str, Any]] = []
    for index in range(1, 4):
        trials.append(await honest_case(f"control_honest_a_{index}", snapshots))
    for index in range(1, 4):
        trials.append(await mutation_case(f"attack_mutated_b_{index}", snapshots))
    trials.append(await direct_b_case())
    summary = summarize(trials)

    write_json(evidence_dir / "results.json", {"summary": summary, "trials": trials})
    write_json(evidence_dir / "source-receipts.json", source_receipts())
    write_json(evidence_dir / "harness-checksums.json", harness_receipts())
    write_json(evidence_dir / "installed-packages.json", installed_packages())
    write_json(
        evidence_dir / "manifest.json",
        {
            "experiment": "openai-agents-serialized-approval-control",
            "execution_scope": "released package with local deterministic fixtures",
            "started_at": started.isoformat(),
            "finished_at": utc_now(),
            "target": {"package": "openai-agents", "version": version},
            "python": sys.version,
            "platform": platform.platform(),
            "model": "agents.testing.ScriptedModel (shipped deterministic local model)",
            "checkpoint": "ordinary function-tool per-call approval for exact A",
            "mutation": "replace all serialized raw invocation copies with B while preserving call ID and canonical approval/invocation records",
            "external_effects": "none; local deterministic model and in-memory mock ledger only",
            "summary": summary,
        },
    )
    write_json(
        evidence_dir / "claim.json",
        {
            "claim": (
                f"Released openai-agents=={version} rejected a same-call-ID raw invocation mutation "
                "from approved A to B after RunState serialization and restoration, while unchanged "
                "approved A executed."
            ),
            "target": f"openai-agents=={version}",
            "result": summary["interpretation"],
            "reproduction_command": "bash experiments/openai-agents-approval-control/run.sh",
            "oracle": {
                "honest_a": "three serialized approved-A states restore and execute exact A",
                "mutated_b": "three same-call-ID A-to-B raw invocation mutations raise ModelBehaviorError and execute nothing",
                "direct_b": "unapproved B pauses and executes nothing",
                "strict_negative_control_pass": summary["strict_negative_control_pass"],
            },
            "limitations": [
                "This tests ordinary function-tool per-call approval in one current released SDK version, not every approval mode or historical version.",
                "The mutation preserves the original canonical approval and invocation records; arbitrary forgery of every serialized state field is outside this experiment.",
                "The deterministic model and harmless ledger are experiment fixtures; approval serialization, restoration, and enforcement are SDK code.",
                "This is a negative control and does not establish an OpenAI Agents SDK vulnerability.",
            ],
            "contradicting_evidence": [
                "The SDK exposes intentional sticky approval with always_approve=True; that distinct policy was not tested or characterized as per-call approval."
            ],
            "verified_at": utc_now(),
            "next_falsifying_experiment": (
                "If a future release changes per-call binding, rerun this matrix and require mutated B to remain non-executing."
            ),
        },
    )
    write_hashes(evidence_dir)
    print(json.dumps({"evidence_dir": str(evidence_dir), "summary": summary}, indent=2))
    return 0 if summary["strict_negative_control_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
