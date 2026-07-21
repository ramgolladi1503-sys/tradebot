#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SAFETY_FLAGS = {"read_only": True, "is_order_action": False, "broker_api_called": False, "execution_eligibility": False, "allowed_for_live_execution": False}
FORBIDDEN_FIELDS = {"candidate_count", "candidate_timestamp", "direction", "strategy_score", "return", "mfe", "mae", "win_rate"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def append_records(manifest: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    existing = {row["session_date"]: row for row in manifest.get("sessions", [])}
    for record in records:
        if FORBIDDEN_FIELDS.intersection(record):
            raise ValueError("strategy-specific manifest field rejected")
        old = existing.get(record["session_date"])
        if old and old != record:
            raise ValueError("identity drift")
        existing[record["session_date"]] = record
    ordered = [existing[key] for key in sorted(existing)]
    return {"sessions": ordered, "session_list_hash": hashlib.sha256(json.dumps(ordered, sort_keys=True).encode()).hexdigest(), "append_only": True, "opened": False, "safety_flags": SAFETY_FLAGS}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="research/independent_underlying_confirmation_v3/independent_session_manifest.json")
    parser.add_argument("--records", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"sessions": []}
    records = json.loads(Path(args.records).read_text())
    updated = append_records(manifest, records)
    write_json(manifest_path, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
