"""Canonical current-session composition root for read-only live observation.

This module prepares one session and then hands ownership to the established
observer runtime.  It does not implement a second feed, persistence layer, or
execution path.  Downstream consumer stages are emitted as PENDING until
runtime evidence advances them.
"""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.kite_read_only_observation_runtime import run_observation, safe_environment, safety_contract
from core.live_consumer_contract import CANONICAL_CONSUMERS, validate_consumer_registry, write_consumer_registry
from core.live_runtime_artifacts import write_pending_runtime_artifacts
from core.live_session_manifest import LiveSessionManifest, write_session_manifest
from core.read_only_instrument_authority import build_instrument_authority, fetch_current_instruments
from core.read_only_launch_plan import build_current_launch_plan, write_current_launch_plan
from core.read_only_strategy_registry import write_strategy_registry
from core.read_only_sidecar_manager import write_sidecar_health
from core.runtime_paths import write_runtime_path_authority


PIPELINE_STAGES = (
    "SOURCE_READY", "AUTH_READY", "INSTRUMENT_AUTHORITY_READY", "FEED_READY",
    "PERSISTENCE_READY", "REGIME_READY", "STRATEGIES_READY", "CAS_READY",
    "CANDIDATES_READY", "OPTION_SURFACE_READY", "ELIGIBILITY_READY",
    "RANKING_READY", "ADVISORY_READY", "SIDECARS_READY", "E2E_READY",
)


def _source_sha() -> str:
    value = str(os.environ.get("TRADEBOT_COMMIT_SHA") or "").strip()
    if len(value) != 40:
        raise RuntimeError("READ_ONLY_SOURCE_SHA_REQUIRED")
    return value


def _write_stage_state(root: Path, *, session_id: str, source_sha: str, current: str, verdict: str) -> None:
    payload = {
        "schema_version": 1, "session_id": session_id, "source_sha": source_sha,
        "pipeline_stages": list(PIPELINE_STAGES), "current_stage": current,
        "verdict": verdict, "runtime_validated": False, "e2e_ready": False,
        "read_only": True, "broker_write_authority": False,
        "order_authority": False, "paper_authorized": False,
        "live_execution_authorized": False, "broker_order_calls": 0,
    }
    destination = root / "pipeline_stage_state.json"
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


def prepare_current_session(
    *, session_date: str, runtime_root: Path, token_path: Path,
    subscription_tokens: Iterable[int], pipeline_sha: str | None = None,
) -> dict[str, Any]:
    if session_date != date.today().isoformat():
        raise RuntimeError("READ_ONLY_SESSION_DATE_NOT_CURRENT")
    if not token_path.is_file() or (token_path.stat().st_mode & 0o077):
        raise RuntimeError("READ_ONLY_TOKEN_METADATA_INVALID")
    source_sha = _source_sha()
    resolved_pipeline_sha = str(pipeline_sha or source_sha)
    if len(resolved_pipeline_sha) != 40:
        raise RuntimeError("READ_ONLY_PIPELINE_SHA_INVALID")
    env = safe_environment()
    safety_contract(env, child_command=["run_read_only_live_pipeline"], child_pid=None)
    os.environ.update(env)
    from core.auth import get_kite_client
    client = get_kite_client(repo_root_path=Path(__file__).resolve().parents[1])
    client.profile()
    client.margins()
    session_id = str(os.environ.get("RUN_ID") or f"kite-read-only-{session_date}")
    runtime_root.mkdir(parents=True, exist_ok=True)
    write_runtime_path_authority(
        runtime_root / "runtime_path_authority.json",
        source_sha=source_sha,
        session_root=runtime_root,
    )
    validate_consumer_registry(CANONICAL_CONSUMERS)
    registry_path = runtime_root / "CONSUMERS.json"
    write_consumer_registry(
        registry_path, session_id=session_id, source_sha=source_sha,
        canonical_strategy_ids=("CAS_SW_RUNTIME_V2_1514",),
    )
    write_strategy_registry(runtime_root / "STRATEGY_REGISTRY.json", session_id=session_id, source_sha=source_sha)
    write_sidecar_health(
        registry_path=Path(__file__).resolve().parents[1] / "docs" / "LIVE_PR_SIDECAR_REGISTRY.json",
        output_path=runtime_root / "SIDECAR_HEALTH.json",
        main_session_id=session_id, source_sha=source_sha,
    )
    write_pending_runtime_artifacts(
        runtime_root, session_id=session_id, source_sha=source_sha,
        include_instrument_authority=False,
    )
    rows = fetch_current_instruments(client)
    authority = build_instrument_authority(
        rows=rows, session_date=session_date, source_sha=source_sha, output_root=runtime_root,
    )
    plan = build_current_launch_plan(
        session_id=session_id, session_date=session_date, source_sha=source_sha,
        runtime_root=runtime_root, instrument_manifest=authority,
        subscription_tokens=subscription_tokens, consumer_registry_path=str(registry_path),
    )
    plan["pipeline_sha"] = resolved_pipeline_sha
    plan["advisory_queue_path"] = str(runtime_root / "advisory_queue.jsonl")
    write_current_launch_plan(runtime_root / "launch_plan.json", plan)
    manifest = LiveSessionManifest(
        session_date=session_date, session_id=session_id, source_sha=source_sha,
        observer_sha=source_sha, observer_pid=os.getpid(), runtime_root=str(runtime_root.resolve()),
        sqlite_path=plan["sqlite_path"], instrument_master_path=authority["raw_instrument_path"],
        instrument_master_sha=authority["raw_instrument_sha256"], auth_state="PASS",
        feed_state="PENDING", persistence_state="PENDING", subscription_count=plan["subscription_count"],
        consumer_registry=tuple(CANONICAL_CONSUMERS), pipeline_sha=resolved_pipeline_sha,
        consumer_registry_path=str(registry_path), advisory_queue_path=plan["advisory_queue_path"],
    )
    write_session_manifest(runtime_root / "SESSION_MANIFEST.json", manifest)
    _write_stage_state(runtime_root, session_id=session_id, source_sha=source_sha, current="AUTH_READY", verdict="PENDING")
    return plan


def run_pipeline(*, session_date: str, runtime_root: Path, token_path: Path,
                 subscription_tokens: Iterable[int], max_runtime_sec: float | None = None) -> int:
    plan = prepare_current_session(
        session_date=session_date, runtime_root=runtime_root, token_path=token_path,
        subscription_tokens=subscription_tokens,
    )
    return run_observation(
        launch_plan=plan, output_root=runtime_root, token_path=token_path,
        session_date=session_date, max_runtime_sec=max_runtime_sec,
    )
