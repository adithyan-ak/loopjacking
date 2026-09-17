from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from typing import Any


def package_root(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise RuntimeError(f"cannot locate {name}")
    if spec.origin is not None:
        return Path(spec.origin).parent
    locations = list(spec.submodule_search_locations or [])
    if len(locations) != 1:
        raise RuntimeError(f"cannot locate one package root for {name}: {locations}")
    return Path(locations[0])


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path_within_site_packages": str(path).split("site-packages/", 1)[-1],
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def definition(path: Path, name: str, class_name: str | None = None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    scope: list[ast.stmt] = tree.body
    if class_name is not None:
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        scope = cls.body
    node = next(
        (
            node
            for node in scope
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == name
        ),
        None,
    )
    result = file_record(path)
    symbol = f"{class_name + '.' if class_name else ''}{name}"
    if node is None:
        result.update({"symbol": symbol, "present": False})
        return result
    lines = text.splitlines()
    result.update(
        {
            "symbol": symbol,
            "present": True,
            "start_line": node.lineno,
            "end_line": node.end_lineno,
            "source": "\n".join(lines[node.lineno - 1 : node.end_lineno]),
        }
    )
    return result


def window(path: Path, needle: str, before: int, after: int, symbol: str) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    index = next((i for i, line in enumerate(lines) if needle in line), None)
    result = file_record(path)
    if index is None:
        result.update({"symbol": symbol, "present": False})
        return result
    start = max(0, index - before)
    end = min(len(lines), index + after + 1)
    result.update(
        {
            "symbol": symbol,
            "present": True,
            "start_line": start + 1,
            "end_line": end,
            "source": "\n".join(lines[start:end]),
        }
    )
    return result


def main() -> None:
    api = package_root("langgraph_api")
    chain = package_root("langchain")
    graph = package_root("langgraph")
    a2a = api / "api" / "a2a.py"
    command = api / "command.py"
    run = api / "models" / "run.py"
    hitl = chain / "agents" / "middleware" / "human_in_the_loop.py"
    messages = graph / "graph" / "message.py"

    receipt = {
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "langgraph-api",
                "langgraph-runtime-inmem",
                "langgraph-sdk",
                "langgraph",
                "langchain",
                "langchain-core",
            )
        },
        "source": [
            definition(a2a, "_extract_and_validate_command"),
            window(a2a, "command=command,", 8, 8, "A2A command forwarded to runs.create"),
            definition(command, "map_cmd"),
            window(
                run,
                'configurable["langgraph_auth_permissions"]',
                9,
                5,
                "authenticated run identity injection",
            ),
            definition(hitl, "_process_decision", "HumanInTheLoopMiddleware"),
            definition(hitl, "after_model", "HumanInTheLoopMiddleware"),
            definition(messages, "add_messages"),
        ],
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
