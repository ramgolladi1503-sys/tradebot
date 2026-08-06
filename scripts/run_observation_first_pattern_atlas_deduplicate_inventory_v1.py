#!/usr/bin/env python3
"""Deduplicate corpus inventory entries by physical SHA-256 identity."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence


def digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def deduplicate(files: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for item in sorted(files, key=lambda value: str(value.get("path", ""))):
        identity = str(item.get("sha256") or item.get("path"))
        if identity in unique:
            duplicates.append({
                "path": item.get("path"),
                "duplicate_of": unique[identity].get("path"),
                "identity": identity,
            })
        else:
            unique[identity] = item
    return list(unique.values()), duplicates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--duplicate-report", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.inventory_json.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("Inventory does not contain files[]")
    unique, duplicates = deduplicate(files)
    result = dict(payload)
    result["files"] = unique
    result["source_file_count_before_deduplication"] = len(files)
    result["source_file_count_after_deduplication"] = len(unique)
    result["duplicate_source_count"] = len(duplicates)
    result["semantic_sha256"] = digest(unique)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    args.duplicate_report.write_text(json.dumps({"duplicates": duplicates, "semantic_sha256": digest(duplicates)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"before": len(files), "after": len(unique), "duplicates": len(duplicates)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
