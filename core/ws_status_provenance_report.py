from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.feed_startup_lifecycle import read_feed_startup_lifecycle
from core.paths import ensure_dir, logs_dir, reports_dir
from core.runtime_boot_identity import RuntimeBootIdentity, classify_runtime_payload_freshness

REPORT_VERSION = 1
FRESH_WINDOW_SEC = 180.0

_START_MARKERS = (
    "start_depth_ws",
    "FEED_CREDENTIAL_STATS",
    "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF",
    "kite_ws_credential_stats",
    "kite_ws_created",
)
_FAILURE_MARKERS = (
    "WebSocket connection upgrade failed",
    "403 - Forbidden",
    "FEED_WS_AUTH_FAILURE_PROOF",
)
_PROOF_MARKERS = (
    "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF",
    "FEED_WS_AUTH_FAILURE_PROOF",
    "FEED_CREDENTIAL_STATS",
    "kite_ws_credential_stats",
    "kite_ws_created",
)


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"_unreadable": True, "path": str(target)}
    return payload if isinstance(payload, dict) else {"_non_object_json": True, "value": payload}


def _read_lines(path: str | Path | None, *, max_lines: int = 2000) -> list[str]:
    if path is None:
        return []
    target = Path(path).expanduser()
    if not target.exists():
        return []
    try:
        return target.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return []


def _read_jsonl_tail(path: str | Path | None, *, max_lines: int = 500) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in _read_lines(path, max_lines=max_lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_path(base: Path, pattern: str) -> Path | None:
    try:
        paths = sorted(base.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    except Exception:
        return None
    return paths[0] if paths else None


def _file_meta(path: Path | None, *, now_epoch: float) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "mtime_epoch": None, "age_sec": None, "fresh": False}
    target = Path(path).expanduser()
    if not target.exists():
        return {"path": str(target), "exists": False, "mtime_epoch": None, "age_sec": None, "fresh": False}
    try:
        mtime = float(target.stat().st_mtime)
    except Exception:
        return {"path": str(target), "exists": True, "mtime_epoch": None, "age_sec": None, "fresh": False}
    age = max(0.0, now_epoch - mtime)
    return {
        "path": str(target),
        "exists": True,
        "mtime_epoch": mtime,
        "age_sec": round(age, 3),
        "fresh": age <= FRESH_WINDOW_SEC,
    }


def _contains_any(lines: list[str], markers: tuple[str, ...]) -> bool:
    return any(any(marker in line for marker in markers) for line in lines)


def _matching_lines(lines: list[str], markers: tuple[str, ...], *, limit: int = 80) -> list[str]:
    matches = [line for line in lines if any(marker in line for marker in markers)]
    return matches[-limit:]


def _latest_status_reason(engine_status: dict[str, Any], suggestions_status: dict[str, Any]) -> str:
    for payload in (engine_status, suggestions_status):
        for key in ("auth_reason", "subreason", "last_error", "reason"):
            value = str(payload.get(key) or "")
            if "WebSocket connection upgrade failed" in value or "403 - Forbidden" in value:
                return value
    return ""


def _latest_auth_event_failure(auth_events: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(auth_events):
        text = json.dumps(row, sort_keys=True, default=str)
        if "WebSocket connection upgrade failed" in text or "403 - Forbidden" in text or "AUTH_REQUIRED" in text:
            return row
    return {}


def _probable_writer(engine_status: dict[str, Any], suggestions_status: dict[str, Any]) -> str:
    engine_ts = engine_status.get("ts_epoch")
    suggestions_ts = suggestions_status.get("ts_epoch")
    if engine_ts is not None and suggestions_ts is not None and engine_ts == suggestions_ts:
        return "orchestrator_status_writer_or_shared_runtime_overlay"
    if suggestions_status.get("status") == "blocked" and suggestions_status.get("primary_blocker") == "AUTH_REQUIRED":
        return "suggestions_status_writer"
    return "unknown_status_writer"


def _conclusion(
    *,
    status_has_failure: bool,
    paper_log_fresh: bool,
    depth_log_fresh: bool,
    start_seen: bool,
    proof_seen: bool,
    failure_seen_in_logs: bool,
) -> str:
    if not status_has_failure:
        return "no_failure_status"
    if start_seen and proof_seen and failure_seen_in_logs:
        return "fresh_ws_attempt_failed"
    if paper_log_fresh and not start_seen and not proof_seen:
        return "status_written_without_fresh_ws_attempt"
    if not depth_log_fresh and not proof_seen:
        return "stale_status_reused"
    return "status_provenance_unclear"


def _runtime_identity_from_status_payloads(
    *payloads: dict[str, Any],
) -> RuntimeBootIdentity | None:
    candidates: list[tuple[float, RuntimeBootIdentity]] = []

    for payload in payloads:
        if not isinstance(payload, dict):
            continue

        run_id = payload.get("run_id")
        boot_epoch = payload.get("boot_epoch")
        pid = payload.get("pid")

        if not run_id or boot_epoch is None or pid is None:
            continue

        try:
            identity = RuntimeBootIdentity(
                run_id=str(run_id),
                boot_epoch=float(boot_epoch),
                pid=int(pid),
            )
        except (TypeError, ValueError):
            continue

        try:
            ts_epoch = float(payload.get("ts_epoch") or identity.boot_epoch)
        except (TypeError, ValueError):
            ts_epoch = identity.boot_epoch

        candidates.append((ts_epoch, identity))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])[1]


def build_ws_status_provenance_report(
    *,
    engine_status_path: str | Path | None = None,
    suggestions_status_path: str | Path | None = None,
    runtime_health_path: str | Path | None = None,
    feed_runtime_path: str | Path | None = None,
    auth_health_path: str | Path | None = None,
    auth_events_path: str | Path | None = None,
    depth_log_path: str | Path | None = None,
    paper_log_path: str | Path | None = None,
    startup_recovery_path: str | Path | None = None,
    feed_startup_lifecycle_path: str | Path | None = None,
    base_logs_dir: str | Path | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    now = float(now_epoch if now_epoch is not None else _now_epoch())
    base = Path(base_logs_dir).expanduser() if base_logs_dir is not None else logs_dir()
    engine_target = Path(engine_status_path).expanduser() if engine_status_path is not None else base / "engine_cycle_status.json"
    suggestions_target = Path(suggestions_status_path).expanduser() if suggestions_status_path is not None else base / "suggestions_status.json"
    runtime_target = Path(runtime_health_path).expanduser() if runtime_health_path is not None else base / "runtime_health_latest.json"
    feed_target = Path(feed_runtime_path).expanduser() if feed_runtime_path is not None else base / "feed_runtime_latest.json"
    auth_health_target = Path(auth_health_path).expanduser() if auth_health_path is not None else base / "auth_health.jsonl"
    auth_events_target = Path(auth_events_path).expanduser() if auth_events_path is not None else base / "auth_events.jsonl"
    depth_target = Path(depth_log_path).expanduser() if depth_log_path is not None else base / "depth_ws_watchdog.log"
    paper_target = Path(paper_log_path).expanduser() if paper_log_path is not None else _latest_path(base, "paper_ws_proof_*.log") or _latest_path(base, "paper_market_*.log")
    startup_target = Path(startup_recovery_path).expanduser() if startup_recovery_path is not None else base / "startup_recovery.jsonl"
    lifecycle_target = Path(feed_startup_lifecycle_path).expanduser() if feed_startup_lifecycle_path is not None else base / "feed_startup_lifecycle_latest.json"

    engine_status = _read_json(engine_target)
    suggestions_status = _read_json(suggestions_target)
    runtime_health = _read_json(runtime_target)
    feed_runtime = _read_json(feed_target)
    feed_startup_lifecycle = read_feed_startup_lifecycle(lifecycle_target)

    observed_runtime_identity = _runtime_identity_from_status_payloads(
        engine_status,
        suggestions_status,
        runtime_health,
        feed_runtime,
    )

    runtime_status_freshness = {
        "engine_cycle_status": classify_runtime_payload_freshness(
            engine_status,
            path=engine_target,
            current=observed_runtime_identity,
        ),
        "suggestions_status": classify_runtime_payload_freshness(
            suggestions_status,
            path=suggestions_target,
            current=observed_runtime_identity,
        ),
        "runtime_health_latest": classify_runtime_payload_freshness(
            runtime_health,
            path=runtime_target,
            current=observed_runtime_identity,
        ),
        "feed_runtime_latest": classify_runtime_payload_freshness(
            feed_runtime,
            path=feed_target,
            current=observed_runtime_identity,
        ),
    }
    stale_runtime_inputs = [
        name
        for name, freshness in runtime_status_freshness.items()
        if not bool(freshness.get("is_current_run"))
    ]
    auth_events = _read_jsonl_tail(auth_events_target)
    depth_lines = _read_lines(depth_target)
    paper_lines = _read_lines(paper_target)
    startup_lines = _read_lines(startup_target)
    combined_lines = [*paper_lines, *depth_lines, *startup_lines]

    start_seen = _contains_any(combined_lines, _START_MARKERS)
    proof_seen = _contains_any(combined_lines, _PROOF_MARKERS)
    failure_seen = _contains_any(combined_lines, _FAILURE_MARKERS)
    status_reason = _latest_status_reason(engine_status, suggestions_status)
    status_has_failure = bool(status_reason)
    file_freshness = {
        "engine_status": _file_meta(engine_target, now_epoch=now),
        "suggestions_status": _file_meta(suggestions_target, now_epoch=now),
        "runtime_health": _file_meta(runtime_target, now_epoch=now),
        "feed_runtime": _file_meta(feed_target, now_epoch=now),
        "auth_health": _file_meta(auth_health_target, now_epoch=now),
        "auth_events": _file_meta(auth_events_target, now_epoch=now),
        "depth_log": _file_meta(depth_target, now_epoch=now),
        "paper_log": _file_meta(paper_target, now_epoch=now),
        "startup_recovery": _file_meta(startup_target, now_epoch=now),
        "feed_startup_lifecycle": _file_meta(lifecycle_target, now_epoch=now),
    }
    conclusion = _conclusion(
        status_has_failure=status_has_failure,
        paper_log_fresh=bool(file_freshness["paper_log"].get("fresh")),
        depth_log_fresh=bool(file_freshness["depth_log"].get("fresh")),
        start_seen=start_seen,
        proof_seen=proof_seen,
        failure_seen_in_logs=failure_seen,
    )

    decision = {
        "primary_conclusion": conclusion,
        "probable_writer": _probable_writer(engine_status, suggestions_status),
        "status_reason": status_reason,
        "safe_to_treat_status_as_fresh_ws_failure": conclusion == "fresh_ws_attempt_failed",
        "recommended_next_action": _recommended_next_action(conclusion),
    }
    if stale_runtime_inputs:
        decision = {
            "primary_conclusion": "stale_runtime_status_rejected",
            "probable_writer": "mixed_or_unversioned_runtime_status",
            "status_reason": ",".join(stale_runtime_inputs),
            "safe_to_treat_status_as_fresh_ws_failure": False,
            "recommended_next_action": "rerun_after_boot_status_versioning_or_wait_for_current_run_status_files",
        }

    return {
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "source": {
            "engine_status_path": str(engine_target),
            "suggestions_status_path": str(suggestions_target),
            "runtime_health_path": str(runtime_target),
            "feed_runtime_path": str(feed_target),
            "auth_health_path": str(auth_health_target),
            "auth_events_path": str(auth_events_target),
            "depth_log_path": str(depth_target),
            "paper_log_path": str(paper_target) if paper_target is not None else None,
            "startup_recovery_path": str(startup_target),
            "feed_startup_lifecycle_path": str(lifecycle_target),
        },
        "file_freshness": file_freshness,
        "feed_startup_lifecycle": feed_startup_lifecycle,
        "observed_runtime_identity": {
            "run_id": observed_runtime_identity.run_id if observed_runtime_identity else None,
            "boot_epoch": observed_runtime_identity.boot_epoch if observed_runtime_identity else None,
            "pid": observed_runtime_identity.pid if observed_runtime_identity else None,
        },
        "runtime_status_freshness": runtime_status_freshness,
        "stale_runtime_inputs": stale_runtime_inputs,
        "status_truth": {
            "engine_auth_state": engine_status.get("auth_state"),
            "engine_auth_ok": engine_status.get("auth_ok"),
            "engine_auth_reason": engine_status.get("auth_reason"),
            "engine_feed_ok": engine_status.get("feed_ok"),
            "engine_ws_connected": engine_status.get("ws_connected"),
            "engine_ts_epoch": engine_status.get("ts_epoch"),
            "suggestions_status": suggestions_status.get("status"),
            "suggestions_primary_blocker": suggestions_status.get("primary_blocker"),
            "suggestions_auth_reason": suggestions_status.get("auth_reason"),
            "suggestions_subreason": suggestions_status.get("subreason"),
            "suggestions_ts_epoch": suggestions_status.get("ts_epoch"),
            "runtime_feed_ok": _nested_feed_value(runtime_health, "feed_ok"),
            "runtime_ws_connected": _nested_feed_value(runtime_health, "ws_connected"),
            "feed_runtime_state": feed_runtime.get("runtime_state"),
            "feed_runtime_ws_connected": feed_runtime.get("ws_connected"),
        },
        "observed_runtime_path": {
            "fresh_process_reached_start_depth_ws": start_seen,
            "handshake_proof_seen": "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF" in "\n".join(combined_lines),
            "auth_failure_proof_seen": "FEED_WS_AUTH_FAILURE_PROOF" in "\n".join(combined_lines),
            "credential_stats_seen": "FEED_CREDENTIAL_STATS" in "\n".join(combined_lines) or "kite_ws_credential_stats" in "\n".join(combined_lines),
            "kite_ticker_created_seen": "kite_ws_created" in "\n".join(combined_lines),
            "failure_seen_in_logs": failure_seen,
            "status_has_ws_failure_reason": status_has_failure,
        },
        "evidence_lines": {
            "proof_or_start_lines": _matching_lines(combined_lines, (*_START_MARKERS, *_PROOF_MARKERS), limit=120),
            "failure_lines": _matching_lines(combined_lines, _FAILURE_MARKERS, limit=120),
            "latest_auth_event_failure": _latest_auth_event_failure(auth_events),
        },
        "decision": decision,
    }


def _nested_feed_value(payload: dict[str, Any], key: str) -> Any:
    feed = payload.get("feed")
    if isinstance(feed, dict) and key in feed:
        return feed.get(key)
    return payload.get(key)


def _recommended_next_action(conclusion: str) -> str:
    if conclusion == "fresh_ws_attempt_failed":
        return "inspect_websocket_handshake_permissions_and_provider_response"
    if conclusion == "status_written_without_fresh_ws_attempt":
        return "trace_status_writer_inputs_before_treating_ws_failure_as_fresh"
    if conclusion == "stale_status_reused":
        return "clear_or_version_stale_auth_feed_status_before_next_run"
    if conclusion == "no_failure_status":
        return "run_feed_startup_diagnostics_if_feed_still_unhealthy"
    return "inspect_status_provenance_report"


def ws_status_provenance_report_path() -> Path:
    return ensure_dir(reports_dir()) / "ws_status_provenance_report.json"


def save_ws_status_provenance_report(report: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else ws_status_provenance_report_path()
    return write_json_atomic(target, json.loads(json.dumps(dict(report or {}), ensure_ascii=True, default=str)))
