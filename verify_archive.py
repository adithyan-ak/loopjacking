#!/usr/bin/env python3
"""Verify the public Loopjacking evidence archive without running experiments."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent

AGNO = {
    "agno-2.5.5/20260830T205035Z": False,
    "agno-2.5.6/20260830T205038Z": True,
    "agno-2.9.0/20260830T205029Z": True,
    "agno-3.0.1/20260830T205032Z": True,
    "agno-3.0.2/20260830T205101Z": True,
    "agno-3.0.3/20260830T205355Z": True,
    "agno-3.0.6/20260907T090624Z": True,
    "agno-3.0.9/20260910T074852Z": True,
}

LANGGRAPH_POSITIVE = {
    "langgraph-api-0.7.5",
    "langgraph-api-0.7.103",
    "langgraph-api-0.8.7",
    "langgraph-api-0.9.1",
    "langgraph-api-0.10.3",
    "langgraph-api-0.11.4",
    "langgraph-api-0.12.4",
    "langgraph-api-0.12.6",
    "langgraph-api-0.12.9",
    "langgraph-api-0.13.2",
    "langgraph-api-0.13.4",
    "langgraph-api-0.14.0",
    "langgraph-api-0.13.2-linux-inmem",
}

OPENAI = {
    "openai-agents-0.22.0/20260910T074941Z",
    "openai-agents-0.22.2/20260910T074929Z",
}

DENY_BYTES = {
    b"/users/",
    b"/private/",
    b"akoffsec",
    b"vince",
    b"cert/cc",
    b"loopjacking-" + b"internal",
    b"whitepaper/loopjacking.tex",
    b"experiment_" + b"revision",
    b"ats-",
    b"codex/",
    b"native-" + b"run",
    b"wire-" + b"run",
    b"source-" + b"verified",
    b"external-" + b"confirmed",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_entries(manifest: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    failures: list[str] = []
    for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            expected, name = raw.split(None, 1)
        except ValueError:
            failures.append(f"{manifest}:{number}: malformed checksum line")
            continue
        name = name.lstrip("* ")
        if name in entries:
            failures.append(f"{manifest}:{number}: duplicate path {name}")
        entries[name] = expected
    return entries, failures


def verify_manifest(manifest: Path, base: Path) -> list[str]:
    if not manifest.is_file():
        return [f"missing checksum manifest: {manifest}"]
    entries, failures = manifest_entries(manifest)
    for name, expected in entries.items():
        target = base / name
        if not target.is_file():
            failures.append(f"{manifest}: missing {name}")
        elif sha256(target) != expected:
            failures.append(f"{manifest}: digest mismatch {name}")
    return failures


def verify_root_manifest() -> list[str]:
    manifest = ROOT / "CHECKSUMS.sha256"
    failures = verify_manifest(manifest, ROOT)
    entries, parse_failures = manifest_entries(manifest)
    failures.extend(parse_failures)
    actual = {
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(ROOT).parts
        and "__pycache__" not in path.relative_to(ROOT).parts
        and path.suffix != ".pyc"
        and path.name != "CHECKSUMS.sha256"
    }
    listed = set(entries)
    for name in sorted(actual - listed):
        failures.append(f"CHECKSUMS.sha256: unlisted file {name}")
    for name in sorted(listed - actual):
        failures.append(f"CHECKSUMS.sha256: stale entry {name}")
    return failures


def verify_bundle_manifest(bundle: Path) -> list[str]:
    return verify_manifest(bundle / "SHA256SUMS", bundle)


def verify_agno(bundle: Path, expected_positive: bool) -> list[str]:
    data = json.loads((bundle / "results.json").read_text(encoding="utf-8"))
    summary = data["summary"]
    common = (
        summary["completed_trials"] == summary["total_trials"] == 23
        and summary["attack_observed"] == summary["attack_total"] == 5
        and summary["honest_a_pass"] == summary["honest_a_total"] == 5
        and summary["custom_safe_control_pass"] is True
    )
    if expected_positive:
        outcome = (
            summary["strict_trace_supported"] is True
            and summary["pending_rbac_pass"] is True
            and summary["direct_b_denied_pass"] == summary["direct_b_total"] == 3
        )
    else:
        outcome = (
            summary["strict_trace_supported"] is False
            and summary["direct_b_denied_pass"] == 0
            and summary["direct_b_total"] == 3
        )
    return [] if common and outcome else [f"{bundle}: Agno oracle mismatch"]


def verify_langgraph(bundle: Path) -> list[str]:
    data = json.loads((bundle / "results.json").read_text(encoding="utf-8"))
    name = bundle.name
    if name == "langgraph-api-0.7.4":
        ok = (
            data.get("strict_positive") is False
            and data.get("state_is_exact_B") is False
            and data.get("ledger_has_exact_B") is False
        )
    elif name == "langgraph-api-0.13.2-safe-policy":
        ok = (
            data.get("safe_policy_negative") is True
            and data.get("mutation_denied") is True
            and data.get("ledger_has_exact_B") is False
            and data.get("ledger_has_A") is True
        )
    else:
        ok = (
            data.get("strict_positive") is True
            and data.get("review_is_exact_A") is True
            and data.get("state_is_exact_B") is True
            and data.get("ledger_has_exact_B") is True
            and data.get("attack_ledger_has_A") is False
            and data.get("direct_b_ledger_has_B") is False
            and data.get("control_ledger_has_A") is True
            and data.get("outsider_status") == 403
        )
    return [] if ok else [f"{bundle}: LangGraph oracle mismatch"]


def verify_langgraph_range(path: Path, count: int, positive: int, first_negative: bool) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    observed_positive = sum(
        row.get("command_extractor_present") is True
        and row.get("command_forwarded_to_run") is True
        and row.get("map_cmd_forwards_update") is True
        and row.get("map_cmd_forwards_resume") is True
        for row in records
    )
    ok = data.get("release_count") == len(records) == count and observed_positive == positive
    if first_negative:
        first = records[0] if records else {}
        ok = ok and first.get("version") == "0.7.4" and first.get("command_extractor_present") is False
    return [] if ok else [f"{path}: LangGraph range oracle mismatch"]


def verify_openai(bundle: Path) -> list[str]:
    data = json.loads((bundle / "results.json").read_text(encoding="utf-8"))
    summary = data["summary"]
    ok = (
        summary.get("strict_negative_control_pass") is True
        and summary.get("honest_a_pass") == summary.get("honest_a_total") == 3
        and summary.get("mutated_b_rejected") == summary.get("mutated_b_total") == 3
        and summary.get("direct_b_unapproved_pass") is True
        and summary.get("completed_trials") == summary.get("total_trials") == 7
    )
    return [] if ok else [f"{bundle}: OpenAI Agents control oracle mismatch"]


def verify_openclaw_native(bundle: Path, expected_attack: bool) -> list[str]:
    trials = json.loads((bundle / "results.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    if len(trials) != 3:
        return [f"{bundle}: expected three native trials"]
    for index, trial in enumerate(trials, 1):
        view = trial.get("exactApprovalView", {}).get("request", {}).get("command")
        understood = trial.get("humanDecision", {}).get("understoodA")
        underlying = trial.get("completeUnderlyingRequest", {}).get("command")
        attack = trial.get("attack", {})
        direct = trial.get("controls", {}).get("directB", {})
        unchanged = trial.get("controls", {}).get("unchangedA", {})
        resolver = trial.get("productResolutionWithRawA", {})
        common = (
            trial.get("expectedAttack") is expected_attack
            and view == understood == '$0 "$1"'
            and isinstance(underlying, list)
            and len(underlying) == 5
            and trial.get("completeUnderlyingRequest", {}).get("preparedBeforeApproval") is True
            and direct.get("rpcOk") is False
            and direct.get("markerCreated") is False
            and unchanged.get("rpcOk") is True
        )
        if expected_attack:
            outcome = (
                resolver.get("ok") is True
                and resolver.get("cmdText") == view
                and attack.get("rpcOk") is True
                and attack.get("reachedNode") is True
                and attack.get("markerCreated") is True
            )
        else:
            outcome = (
                resolver.get("ok") is False
                and resolver.get("details", {}).get("code") == "RAW_COMMAND_MISMATCH"
                and attack.get("rpcOk") is False
                and attack.get("reachedNode") is False
                and attack.get("markerCreated") is False
            )
        if not common or not outcome:
            failures.append(f"{bundle}: native trial {index} oracle mismatch")
    return failures


def verify_openclaw_range(bundle: Path) -> list[str]:
    result = json.loads((bundle / "results.json").read_text(encoding="utf-8"))
    boundary = json.loads((bundle / "source-boundary.json").read_text(encoding="utf-8"))
    resolution = result.get("productResolutionWithRawA", {})
    derived = result.get("productDerivedApprovalTextWithoutRaw", {})
    ok = (
        result.get("executed") is False
        and resolution.get("ok") is False
        and resolution.get("details", {}).get("code") == "RAW_COMMAND_MISMATCH"
        and derived.get("ok") is True
        and derived.get("commandText") == result.get("canonicalOperationB")
        and boundary.get("contains_fix_commit") is True
        and boundary.get("fix_commit") == "0f0a680d3df81739ea5088a2f88e65f938b7936b"
    )
    return [] if ok else [f"{bundle}: OpenClaw source-check oracle mismatch"]


def privacy_scan() -> list[str]:
    failures: list[str] = []
    slot_pattern = re.compile(rb"\b(?:l1|l2|n1|r1|f1)\b")
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(ROOT).parts:
            continue
        if "__pycache__" in path.relative_to(ROOT).parts or path.suffix == ".pyc":
            continue
        if path == Path(__file__).resolve():
            continue
        data = path.read_bytes().lower()
        for pattern in DENY_BYTES:
            if pattern in data:
                failures.append(f"{path}: contains denied public token {pattern.decode(errors='replace')}")
        if slot_pattern.search(data):
            failures.append(f"{path}: contains preparation-only evidence-slot label")
    return failures


def main() -> int:
    failures: list[str] = []
    failures.extend(verify_root_manifest())

    agno_root = ROOT / "evidence" / "agno-agentos"
    for relative, expected in AGNO.items():
        bundle = agno_root / relative
        failures.extend(verify_bundle_manifest(bundle))
        failures.extend(verify_agno(bundle, expected))

    langgraph_root = ROOT / "evidence" / "langgraph-agent-server"
    langgraph_bundles = {"langgraph-api-0.7.4", "langgraph-api-0.13.2-safe-policy"} | LANGGRAPH_POSITIVE
    for name in sorted(langgraph_bundles):
        bundle = langgraph_root / name
        failures.extend(verify_bundle_manifest(bundle))
        failures.extend(verify_langgraph(bundle))
    for name in ["range-scan", "range-scan-0.13.3-0.13.4"]:
        failures.extend(verify_bundle_manifest(langgraph_root / name))
    failures.extend(verify_langgraph_range(langgraph_root / "range-scan" / "release-source-scan.json", 129, 128, True))
    failures.extend(verify_langgraph_range(langgraph_root / "range-scan-0.13.3-0.13.4" / "release-source-scan.json", 2, 2, False))

    openai_root = ROOT / "evidence" / "openai-agents-approval-control"
    for relative in sorted(OPENAI):
        bundle = openai_root / relative
        failures.extend(verify_bundle_manifest(bundle))
        failures.extend(verify_openai(bundle))

    openclaw_root = ROOT / "evidence" / "openclaw-approval-binding"
    for version, expected in [("2026.2.23", True), ("2026.2.24", False)]:
        bundle = openclaw_root / f"openclaw-{version}" / "20260910T073218Z"
        failures.extend(verify_bundle_manifest(bundle))
        failures.extend(verify_openclaw_native(bundle, expected))
    for version in ["2026.5.12", "2026.5.16-beta.7", "2026.5.18"]:
        bundle = openclaw_root / f"openclaw-{version}" / "20260910T073218Z"
        failures.extend(verify_bundle_manifest(bundle))
        failures.extend(verify_openclaw_range(bundle))

    failures.extend(privacy_scan())
    report = {
        "agno_bundles": len(AGNO),
        "langgraph_native_and_control_bundles": len(langgraph_bundles),
        "langgraph_range_scans": 2,
        "openclaw_native_bundles": 2,
        "openclaw_source_checks": 3,
        "openai_agents_control_bundles": len(OPENAI),
        "failures": failures,
        "status": "pass" if not failures else "fail",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
