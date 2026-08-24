"""Current-session launch plan builder; never loads historical plans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def build_current_launch_plan(
    *, session_id: str, session_date: str, source_sha: str, runtime_root: str | Path,
    instrument_manifest: Mapping[str, Any], subscription_tokens: Iterable[int], consumer_registry_path: str,
) -> dict[str, Any]:
    if instrument_manifest.get("session_date") != session_date or instrument_manifest.get("source_sha") != source_sha:
        raise ValueError("current_launch_plan_authority_mismatch")
    if instrument_manifest.get("verdict") != "PASS":
        raise ValueError("current_instrument_authority_not_pass")
    tokens = sorted({int(token) for token in subscription_tokens if int(token) > 0})
    if not tokens:
        raise ValueError("current_launch_plan_subscriptions_missing")
    plan = {
        "schema_version": 1, "session_id": session_id, "session_date": session_date,
        "source_sha": source_sha, "commit_sha": source_sha, "runtime_root": str(Path(runtime_root).resolve()),
        "sqlite_path": str(Path(runtime_root).resolve() / "db" / "live.sqlite"),
        "instrument_authority_sha256": instrument_manifest["raw_instrument_sha256"],
        "instrument_authority_path": instrument_manifest["raw_instrument_path"],
        "subscription_tokens": tokens, "final_union_tokens": tokens, "subscription_count": len(tokens),
        "consumer_registry_path": consumer_registry_path, "read_only": True,
        "broker_write_authority": False, "order_authority": False, "paper_authorized": False,
        "live_authorized": False, "execution_status": "advisory_only", "verdict": "PENDING",
    }
    return plan


def write_current_launch_plan(path: str | Path, plan: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("current_launch_plan_already_exists")
    destination.write_text(json.dumps(dict(plan), sort_keys=True, indent=2) + "\n", encoding="utf-8")
