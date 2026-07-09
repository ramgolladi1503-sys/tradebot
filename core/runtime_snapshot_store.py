from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import config as cfg
from core.events import write_json_atomic, write_json_atomic_if_changed
from core.latest_artifact_freshness_guard import (
    DEFAULT_MAX_AGE_SECONDS,
    LatestArtifactFreshnessDecision,
    assess_latest_artifact_freshness,
)
from core.paths import repo_logs_dir, runtime_dir


SNAPSHOT_WRAPPER_SCHEMA_VERSION = 1

MARKET_SNAPSHOT_PATH = runtime_dir() / "market_snapshot.json"
ADVISORY_LATEST_PATH = runtime_dir() / "advisory_latest.json"
TOP_OPPORTUNITIES_LATEST_PATH = runtime_dir() / "top_opportunities_latest.json"
RANKED_PIPELINE_LATEST_PATH = runtime_dir() / "opportunities" / "ranked_pipeline_latest.json"
RANKED_VS_LEGACY_LATEST_PATH = runtime_dir() / "opportunities" / "ranked_vs_legacy_latest.json"
FEED_RUNTIME_LATEST_PATH = runtime_dir() / "feed_runtime_latest.json"
TOKEN_RESOLUTION_LATEST_PATH = runtime_dir() / "token_resolution_latest.json"
RISK_SNAPSHOT_PATH = runtime_dir() / "risk_snapshot.json"


def snapshot_generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_snapshot_envelope(
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> dict[str, Any]:
    return {
        "schema_version": int(schema_version),
        "generated_at": str(generated_at or snapshot_generated_at()),
        "producer": str(producer or "unknown"),
        "payload": payload,
    }


def write_snapshot_atomic(
    path: str | Path,
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> Path:
    target = Path(path).expanduser()
    envelope = build_snapshot_envelope(
        payload=payload,
        producer=producer,
        generated_at=generated_at,
        schema_version=schema_version,
    )
    if bool(getattr(cfg, "RUNTIME_SNAPSHOT_WRITE_DEDUP_ENABLE", True)):
        written_path, _changed = write_json_atomic_if_changed(target, envelope)
        return written_path
    return write_json_atomic(target, envelope)


def write_top_opportunities_snapshots(
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> tuple[Path, Path]:
    """Write top opportunities latest snapshot to both runtime and repo-local logs.

    This is a snapshot envelope (same schema as write_snapshot_atomic). It is read-only
    and must not alter any trading decisions.
    """
    runtime_path = write_snapshot_atomic(
        runtime_dir() / "top_opportunities_latest.json",
        payload=payload,
        producer=producer,
        generated_at=generated_at,
        schema_version=schema_version,
    )
    logs_path = write_snapshot_atomic(
        repo_logs_dir() / "top_opportunities_latest.json",
        payload=payload,
        producer=producer,
        generated_at=generated_at,
        schema_version=schema_version,
    )
    return runtime_path, logs_path


def write_ranked_pipeline_snapshot(
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> Path:
    target = RANKED_PIPELINE_LATEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    return write_snapshot_atomic(
        target,
        payload=payload,
        producer=producer,
        generated_at=generated_at,
        schema_version=schema_version,
    )


def write_ranked_vs_legacy_snapshot(
    *,
    payload: Any,
    producer: str,
    generated_at: str | None = None,
    schema_version: int = SNAPSHOT_WRAPPER_SCHEMA_VERSION,
) -> Path:
    target = RANKED_VS_LEGACY_LATEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    return write_snapshot_atomic(
        target,
        payload=payload,
        producer=producer,
        generated_at=generated_at,
        schema_version=schema_version,
    )


def read_snapshot(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("snapshot_envelope_not_object")
    return raw


def read_snapshot_with_freshness(
    path: str | Path,
    *,
    artifact_name: str | None = None,
    now_epoch: float | None = None,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Read a snapshot and attach EDGE-50 freshness evidence.

    The helper is read-only. It does not change the existing read_snapshot()
    contract, write files, call brokers, or make runtime decisions.
    """
    target = Path(path).expanduser()
    name = str(artifact_name or target.name)
    try:
        snapshot = read_snapshot(target)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        decision = assess_latest_artifact_freshness(
            name,
            path=target,
            now_epoch=now_epoch,
            max_age_seconds=max_age_seconds,
        )
        return _snapshot_freshness_payload(None, decision)

    freshness_payload = _snapshot_freshness_input(snapshot)
    decision = assess_latest_artifact_freshness(
        name,
        path=target,
        payload=freshness_payload,
        now_epoch=now_epoch,
        max_age_seconds=max_age_seconds,
    )
    return _snapshot_freshness_payload(snapshot, decision)


def _snapshot_freshness_payload(
    snapshot: dict[str, Any] | None,
    decision: LatestArtifactFreshnessDecision,
) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_WRAPPER_SCHEMA_VERSION,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "snapshot": snapshot,
        "freshness": decision.to_payload(),
        "fresh": bool(decision.fresh),
        "blockers": list(decision.reasons if not decision.fresh else ()),
    }


def _snapshot_freshness_input(snapshot: dict[str, Any]) -> dict[str, Any]:
    generated_at = snapshot.get("generated_at")
    generated_epoch = _parse_snapshot_epoch(generated_at)
    payload: dict[str, Any] = {
        "source_generated_at": generated_at,
        "producer": snapshot.get("producer"),
    }
    if generated_epoch is not None:
        payload["generated_epoch"] = generated_epoch
    return payload


def _parse_snapshot_epoch(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return float(parsed.timestamp())
