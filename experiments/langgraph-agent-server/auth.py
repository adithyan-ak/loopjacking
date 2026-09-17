from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import jwt
from langgraph_sdk import Auth


auth = Auth()
WORKSPACE = "loopjacking-langgraph-lab"
JWT_SECRET = os.environ.get(
    "LAB_JWT_SECRET", "loopback-only-research-secret-32-bytes-minimum"
)
SAFE_POLICY = os.environ.get("SAFE_POLICY") == "deny-update"


def _record(ctx: Auth.types.AuthContext, result: Any, detail: str) -> None:
    path = Path(os.environ["AUTH_LOG_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "identity": ctx.user.identity,
        "permissions": list(ctx.permissions),
        "resource": ctx.resource,
        "action": ctx.action,
        "result": result,
        "detail": detail,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


@auth.authenticate
async def authenticate(authorization: str | None) -> Auth.types.MinimalUserDict:
    if not authorization or not authorization.startswith("Bearer "):
        raise Auth.exceptions.HTTPException(status_code=401, detail="missing bearer token")
    try:
        claims = jwt.decode(
            authorization.removeprefix("Bearer "), JWT_SECRET, algorithms=["HS256"]
        )
    except jwt.PyJWTError as exc:
        raise Auth.exceptions.HTTPException(status_code=401, detail="invalid bearer token") from exc
    return {
        "identity": claims["sub"],
        "permissions": claims.get("permissions", []),
    }


@auth.on
async def authorize(ctx: Auth.types.AuthContext, value: dict[str, Any]) -> Any:
    identity = ctx.user.identity
    member = identity in {"maker", "approver"}

    if not member:
        _record(ctx, False, "not a workspace member")
        return False

    if ctx.resource == "assistants" and ctx.action in {"read", "search"}:
        _record(ctx, True, "workspace members may read the experiment assistant")
        return True

    if ctx.resource == "threads" and ctx.action == "create":
        if identity != "maker":
            _record(ctx, False, "only maker creates experiment threads")
            return False
        value.setdefault("metadata", {})["workspace"] = WORKSPACE
        _record(ctx, True, "maker creates a workspace-scoped thread")
        return True

    if ctx.resource == "threads" and ctx.action in {"read", "search"}:
        result = {"workspace": WORKSPACE}
        _record(ctx, result, "member read filtered to experiment workspace")
        return result

    if ctx.resource == "threads" and ctx.action == "create_run":
        kwargs = value.get("kwargs") or {}
        command = kwargs.get("command")
        if identity == "maker":
            allowed = command is None or (
                not SAFE_POLICY
                and
                isinstance(command, dict)
                and "update" in command
                and command.get("resume") is None
            )
            detail = (
                "maker may request work; safe policy denies state updates and resume"
                if SAFE_POLICY
                else "maker may request work or update state, never resume"
            )
            _record(ctx, allowed, detail)
            return {"workspace": WORKSPACE} if allowed else False
        allowed = (
            isinstance(command, dict)
            and command.get("resume") is not None
            and command.get("update") is None
        )
        _record(ctx, allowed, "approver may resume, never update state")
        return {"workspace": WORKSPACE} if allowed else False

    _record(ctx, False, "default deny")
    return False
