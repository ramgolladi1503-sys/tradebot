from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.paths import ensure_dir, logs_dir, reports_dir

REPORT_VERSION = 1
STALE_FILE_THRESHOLD_SEC = 300.0
_AUTH_ERROR_PATTERNS = (
    "AUTH_REQUIRED",
    "WebSocket connection upgrade failed",
    "403 - Forbidden",
    "403",
    "Forbidden",
    "FEED_AUTH_REQUIRED",
    "FEED_CLOSE_AUTH_REQUIRED",
    "FEED_RESTART_BLOCKED_AUTH_REQUIRED",
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


def _read_jsonl_tail(path: str | Path | None, *, max_lines: int = 200) -> list[dict[str, Any]]:
    if path is None:
        return []
    target = Path(path).expanduser()
    if not target.exists():
        return []
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_lines(path: str | Path | None, *, max_lines: int = 500) -> list[str]:
    if path is None:
        return []
    target = Path(path).expanduser()
    if not target.exists():
        return []
    try:
        return target.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return []


def _latest_path(base_dir: Path, pattern: str) -> Path | None:
    try:
        paths = sorted(base_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
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
        "fresh": age <= STALE_FILE_THRESHOLD_SEC,
    }


def _json_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _latest_auth_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: float(row.get("ts_epoch") or 0.0))


def _auth_events_with_required(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        text = json.dumps(row, sort_keys=True, default=str)
        if "AUTH_REQUIRED" in text or "TokenException" in text:
            matches.append(row)
    return matches[-10:]


def _extract_error_lines(lines: list[str]) -> list[str]:
    matches: list[str] = []
    for line in lines:
        if any(pattern in line for pattern in _AUTH_ERROR_PATTERNS):
            matches.append(line)
    return matches[-80:]


def _has_websocket_auth_failure(*, engine_status: dict[str, Any], paper_lines: list[str]) -> bool:
    engine_text = json.dumps(engine_status, sort_keys=True, default=str)
    combined = "\n".join([engine_text, *paper_lines])
    return "WebSocket connection upgrade failed" in combined or "403 - Forbidden" in combined or "403" in combined and "Forbidden" in combined


def _truth_conflicts(
    *,
    latest_auth: dict[str, Any],
    engine_status: dict[str, Any],
    runtime_health: dict[str, Any],
    feed_runtime: dict[str, Any],
    file_freshness: dict[str, dict[str, Any]],
) -> list[str]:
    conflicts: list[str] = []
    rest_ok = latest_auth.get("ok") is True and str(latest_auth.get("auth_state") or "").upper() == "OK"
    engine_auth_required = str(engine_status.get("auth_state") or "").upper() == "AUTH_REQUIRED"
    if rest_ok and engine_auth_required:
        conflicts.append("rest_auth_ok_but_engine_auth_required")
    engine_feed_ok = engine_status.get("feed_ok")
    runtime_ws = _json_value(runtime_health.get("feed", {}) if isinstance(runtime_health.get("feed"), dict) else runtime_health, "ws_connected")
    feed_ws = feed_runtime.get("ws_connected")
    if runtime_ws is not None and feed_ws is not None and runtime_ws != feed_ws:
        conflicts.append("runtime_health_ws_disagrees_with_feed_runtime")
    if file_freshness.get("feed_runtime", {}).get("fresh") is False and file_freshness.get("engine_status", {}).get("fresh") is True:
        conflicts.append("feed_runtime_file_stale_but_engine_status_fresh")
    runtime_subs = _json_value(runtime_health.get("feed", {}) if isinstance(runtime_health.get("feed"), dict) else runtime_health, "subscribed_option_tokens_count")
    engine_subs = engine_status.get("subscribed_option_tokens_count")
    feed_subs = feed_runtime.get("subscribed_option_tokens_count")
    if len({value for value in (runtime_subs, engine_subs, feed_subs) if value is not None}) > 1:
        conflicts.append("subscription_counts_disagree")
    if engine_feed_ok is False and rest_ok:
        conflicts.append("rest_auth_ok_but_engine_feed_not_ok")
    return conflicts


def _primary_blocker(*, websocket_failed: bool, conflicts: list[str], engine_status: dict[str, Any], feed_runtime_meta: dict[str, Any]) -> str:
    if websocket_failed:
        return "websocket_auth_failed"
    if "rest_auth_ok_but_engine_auth_required" in conflicts:
        return "auth_truth_conflict"
    if feed_runtime_meta.get("fresh") is False:
        return "stale_feed_runtime_truth"
    if engine_status.get("feed_ok") is False:
        return "feed_not_ok"
    if int(engine_status.get("subscribed_option_tokens_count") or 0) <= 0:
        return "no_option_subscriptions"
    return str(engine_status.get("primary_blocker") or "unknown")


def build_runtime_truth_breakdown(
    *,
    runtime_health_path: str | Path | None = None,
    feed_runtime_path: str | Path | None = None,
    engine_status_path: str | Path | None = None,
    auth_health_path: str | Path | None = None,
    auth_events_path: str | Path | None = None,
    paper_log_path: str | Path | None = None,
    base_logs_dir: str | Path | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Build a read-only report comparing runtime auth/feed truth sources."""

    now = float(now_epoch if now_epoch is not None else _now_epoch())
    base = Path(base_logs_dir).expanduser() if base_logs_dir is not None else logs_dir()
    runtime_health_target = Path(runtime_health_path).expanduser() if runtime_health_path is not None else base / "runtime_health_latest.json"
    feed_runtime_target = Path(feed_runtime_path).expanduser() if feed_runtime_path is not None else base / "feed_runtime_latest.json"
    engine_status_target = Path(engine_status_path).expanduser() if engine_status_path is not None else base / "engine_cycle_status.json"
    auth_health_target = Path(auth_health_path).expanduser() if auth_health_path is not None else base / "auth_health.jsonl"
    auth_events_target = Path(auth_events_path).expanduser() if auth_events_path is not None else base / "auth_events.jsonl"
    paper_log_target = Path(paper_log_path).expanduser() if paper_log_path is not None else _latest_path(base, "paper_market_*.log")

    runtime_health = _read_json(runtime_health_target)
    feed_runtime = _read_json(feed_runtime_target)
    engine_status = _read_json(engine_status_target)
    auth_health_rows = _read_jsonl_tail(auth_health_target)
    auth_event_rows = _read_jsonl_tail(auth_events_target)
    paper_lines = _read_lines(paper_log_target)
    latest_auth = _latest_auth_health(auth_health_rows)
    file_freshness = {
        "runtime_health": _file_meta(runtime_health_target, now_epoch=now),
        "feed_runtime": _file_meta(feed_runtime_target, now_epoch=now),
        "engine_status": _file_meta(engine_status_target, now_epoch=now),
        "auth_health": _file_meta(auth_health_target, now_epoch=now),
        "auth_events": _file_meta(auth_events_target, now_epoch=now),
        "paper_log": _file_meta(paper_log_target, now_epoch=now),
    }
    websocket_failed = _has_websocket_auth_failure(engine_status=engine_status, paper_lines=paper_lines)
    conflicts = _truth_conflicts(
        latest_auth=latest_auth,
        engine_status=engine_status,
        runtime_health=runtime_health,
        feed_runtime=feed_runtime,
        file_freshness=file_freshness,
    )
    primary = _primary_blocker(
        websocket_failed=websocket_failed,
        conflicts=conflicts,
        engine_status=engine_status,
        feed_runtime_meta=file_freshness["feed_runtime"],
    )
    runtime_feed = runtime_health.get("feed") if isinstance(runtime_health.get("feed"), dict) else runtime_health

    return {
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "mode": str(engine_status.get("market_mode") or runtime_health.get("mode") or "unknown"),
        "source": {
            "runtime_health_path": str(runtime_health_target),
            "feed_runtime_path": str(feed_runtime_target),
            "engine_status_path": str(engine_status_target),
            "auth_health_path": str(auth_health_target),
            "auth_events_path": str(auth_events_target),
            "paper_log_path": str(paper_log_target) if paper_log_target is not None else None,
        },
        "file_freshness": file_freshness,
        "rest_auth": {
            "latest_ok": latest_auth.get("ok"),
            "latest_auth_state": latest_auth.get("auth_state"),
            "latest_source": latest_auth.get("source"),
            "latest_ts_epoch": latest_auth.get("ts_epoch"),
            "latest_user_id_present": bool(latest_auth.get("user_id")),
            "latest_error": latest_auth.get("error"),
        },
        "engine_truth": {
            "auth_ok": engine_status.get("auth_ok"),
            "auth_state": engine_status.get("auth_state"),
            "auth_reason": engine_status.get("auth_reason"),
            "feed_ok": engine_status.get("feed_ok"),
            "ws_connected": engine_status.get("ws_connected"),
            "market_open": engine_status.get("market_open"),
            "subscribed_option_tokens_count": engine_status.get("subscribed_option_tokens_count"),
            "visible_executable_count": engine_status.get("visible_executable_count"),
            "primary_blocker": engine_status.get("primary_blocker"),
        },
        "runtime_feed_truth": {
            "feed_ok": runtime_feed.get("feed_ok"),
            "ws_connected": runtime_feed.get("ws_connected"),
            "sla_status": runtime_feed.get("sla_status"),
            "subscribed_option_tokens_count": runtime_feed.get("subscribed_option_tokens_count"),
            "subscribed_tokens_count": runtime_feed.get("subscribed_tokens_count"),
            "subscriptions_count": runtime_feed.get("subscriptions_count"),
            "ltp_age_sec": runtime_feed.get("ltp_age_sec"),
            "depth_age_sec": runtime_feed.get("depth_age_sec"),
        },
        "feed_runtime_truth": {
            "feed_ok": feed_runtime.get("feed_ok"),
            "ws_connected": feed_runtime.get("ws_connected"),
            "effective_ws_connected": feed_runtime.get("effective_ws_connected"),
            "runtime_state": feed_runtime.get("runtime_state"),
            "state_machine": feed_runtime.get("state_machine"),
            "subscribed_option_tokens_count": feed_runtime.get("subscribed_option_tokens_count"),
            "subscribed_tokens_count": feed_runtime.get("subscribed_tokens_count"),
            "market_open": feed_runtime.get("market_open"),
            "ts_epoch": feed_runtime.get("ts_epoch"),
        },
        "websocket": {
            "auth_failed": websocket_failed,
            "error_lines": _extract_error_lines(paper_lines),
        },
        "auth_events": {
            "recent_required_or_token_exception": _auth_events_with_required(auth_event_rows),
        },
        "truth_conflicts": conflicts,
        "decision": {
            "primary_blocker": primary,
            "safe_to_restart_without_fix": False if primary in {"websocket_auth_failed", "auth_truth_conflict", "stale_feed_runtime_truth", "feed_not_ok"} else None,
            "recommended_next_action": _recommended_next_action(primary),
        },
    }


def _recommended_next_action(primary: str) -> str:
    if primary == "websocket_auth_failed":
        return "inspect_kite_depth_ws_auth_latch_and_websocket_credentials_before_restart"
    if primary == "auth_truth_conflict":
        return "separate_rest_auth_status_from_feed_websocket_auth_status"
    if primary == "stale_feed_runtime_truth":
        return "refresh_or_stop_using_stale_feed_runtime_latest_as_current_truth"
    if primary == "feed_not_ok":
        return "fix_feed_connection_and_option_subscriptions_before_paper_run"
    if primary == "no_option_subscriptions":
        return "fix_option_token_resolution_and_subscription_before_paper_run"
    return "inspect_runtime_truth_report"


def runtime_truth_breakdown_report_path() -> Path:
    return ensure_dir(reports_dir()) / "runtime_truth_breakdown.json"


def save_runtime_truth_breakdown(report: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else runtime_truth_breakdown_report_path()
    return write_json_atomic(target, json.loads(json.dumps(dict(report or {}), ensure_ascii=True, default=str)))
