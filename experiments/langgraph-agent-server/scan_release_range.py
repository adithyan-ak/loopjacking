from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import urllib.request
import zipfile
from typing import Any

from packaging.version import Version


PYPI_JSON = "https://pypi.org/pypi/langgraph-api/json"


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "loopjacking-research/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "loopjacking-research/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def function_source(text: str, name: str) -> str | None:
    tree = ast.parse(text)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            and item.name == name
        ),
        None,
    )
    if node is None:
        return None
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum", default="0.7.4")
    parser.add_argument("--maximum", default="0.13.2")
    args = parser.parse_args()

    minimum = Version(args.minimum)
    maximum = Version(args.maximum)
    project = get_json(PYPI_JSON)
    versions = sorted(
        Version(value)
        for value in project["releases"]
        if not Version(value).is_prerelease
        and minimum <= Version(value) <= maximum
    )
    records: list[dict[str, Any]] = []
    unique_extractors: dict[str, dict[str, str]] = {}
    unique_mappers: dict[str, dict[str, str]] = {}
    for version in versions:
        files = project["releases"][str(version)]
        wheel = next(item for item in files if item["packagetype"] == "bdist_wheel")
        data = get_bytes(wheel["url"])
        actual_digest = hashlib.sha256(data).hexdigest()
        expected_digest = wheel["digests"]["sha256"]
        if actual_digest != expected_digest:
            raise RuntimeError(f"wheel hash mismatch for {version}")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            a2a_path = next(
                (name for name in archive.namelist() if name.endswith("langgraph_api/api/a2a.py")),
                None,
            )
            command_path = next(
                (name for name in archive.namelist() if name.endswith("langgraph_api/command.py")),
                None,
            )
            a2a_text = archive.read(a2a_path).decode() if a2a_path else ""
            command_text = archive.read(command_path).decode() if command_path else ""
        extractor = function_source(a2a_text, "_extract_and_validate_command") if a2a_text else None
        mapper = function_source(command_text, "map_cmd") if command_text else None
        records.append(
            {
                "version": str(version),
                "upload_time": wheel["upload_time_iso_8601"],
                "wheel_filename": wheel["filename"],
                "wheel_sha256": actual_digest,
                "a2a_path": a2a_path,
                "command_path": command_path,
                "command_extractor_present": extractor is not None,
                "command_extractor_sha256": sha256_text(extractor),
                "extractor_mentions_update": bool(extractor and "update" in extractor),
                "command_forwarded_to_run": "command=command" in a2a_text,
                "map_cmd_present": mapper is not None,
                "map_cmd_sha256": sha256_text(mapper),
                "map_cmd_forwards_update": bool(mapper and "update=update" in mapper),
                "map_cmd_forwards_resume": bool(mapper and 'resume=cmd.get("resume")' in mapper),
            }
        )
        if extractor is not None:
            digest = sha256_text(extractor)
            assert digest is not None
            unique_extractors.setdefault(
                digest, {"first_seen": str(version), "source": extractor}
            )
        if mapper is not None:
            digest = sha256_text(mapper)
            assert digest is not None
            unique_mappers.setdefault(
                digest, {"first_seen": str(version), "source": mapper}
            )

    output = {
        "checked_at": "2026-08-29",
        "source": PYPI_JSON,
        "minimum": args.minimum,
        "maximum": args.maximum,
        "release_count": len(records),
        "records": records,
        "unique_command_extractors": unique_extractors,
        "unique_map_cmd_implementations": unique_mappers,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
