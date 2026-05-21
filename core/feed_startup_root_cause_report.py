from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.paths import ensure_dir, logs_dir, repo_root, reports_dir
from core.runtime_boot_identity import classify_runtime_payload_freshness

REPORT_VERSION = 1
STALE_FILE_THRESHOLD_SEC = 300.0
_FAILURE_PATTERNS = (
    "WebSocket connection upgrade failed",
    "403 - Forbidden",
    "FEED_AUTH_REQUIRED",
    "FEED_CLOSE_AUTH_REQUIRED",
    "FEED_RESTART_BLOCKED_AUTH_REQUIRED",
    "FEED_AUTH_BLOCKED",
    "FEED_CREDENTIAL_STATS",
    "kite_ws_credential_stats",
    "kite_ws_created",
    "mark_auth_required",
)


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _tail4(value: str | None) -> str | None:
    text = str(value or "")
    return text[-4:] if text else None


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


def _read_jsonl_tail(path: str | Path | None, *, max_lines: int = 400) -> list[dict[str, Any]]:
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


def _read_lines(path: str | Path | None, *, max_lines: int = 800) -> list[str]:
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
        return {"path": None, "exists": False, "age_sec": None, "fresh": False}
    target = Path(path).expanduser()
    if not target.exists():
        return {"path": str(target), "exists": False, "age_sec": None, "fresh": False}
    try:
        mtime = float(target.stat().st_mtime)
    except Exception:
        return {"path": str(target), "exists": True, "age_sec": None, "fresh": False}
    age = max(0.0, now_epoch - mtime)
    return {"path": str(target), "exists": True, "mtime_epoch": mtime, "age_sec": round(age, 3), "fresh": age <= STALE_FILE_THRESHOLD_SEC}


def _extract_ws_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if any(pattern in line for pattern in _FAILURE_PATTERNS):
            out.append(line)
    return out[-120:]


def _latest_event(rows: list[dict[str, Any]], event_name: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get("event") or row.get("kind") or "") == event_name]
    if not matches:
        return {}
    return matches[-1]


def _latest_credential_stats(rows: list[dict[str, Any]], paper_lines: list[str]) -> dict[str, Any]:
    for row in reversed(rows):
        if str(row.get("event") or "") == "FEED_CREDENTIAL_STATS":
            return dict(row)
    for line in reversed(paper_lines):
        if "kite_ws_credential_stats" in line or "FEED_CREDENTIAL_STATS" in line:
            return {"raw_line": line}
    return {}


def _latest_auth_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: float(row.get("ts_epoch") or 0.0))


def _engine_ws_error(engine_status: dict[str, Any], paper_lines: list[str]) -> str:
    reason = str(engine_status.get("auth_reason") or "")
    if reason:
        return reason
    for line in reversed(paper_lines):
        if "WebSocket connection upgrade failed" in line or "403 - Forbidden" in line:
            return line[-1000:]
    return ""


def _token_file_state(token_path: Path) -> dict[str, Any]:
    if not token_path.exists():
        return {"exists": False, "len": 0, "tail4": None, "has_whitespace": False}
    try:
        raw = token_path.read_text(encoding="utf-8")
    except Exception:
        return {"exists": True, "len": 0, "tail4": None, "has_whitespace": None, "unreadable": True}
    stripped = raw.strip()
    return {
        "exists": True,
        "len": len(stripped),
        "tail4": _tail4(stripped),
        "has_whitespace": raw != stripped or any(ch.isspace() for ch in stripped),
    }


def _env_token_state() -> dict[str, Any]:
    token = str(os.getenv("KITE_ACCESS_TOKEN", "") or "")
    stripped = token.strip()
    return {
        "present": bool(stripped),
        "len": len(stripped),
        "tail4": _tail4(stripped),
        "has_whitespace": token != stripped or any(ch.isspace() for ch in stripped),
    }


def _api_key_state() -> dict[str, Any]:
    key = str(os.getenv("KITE_API_KEY", "") or "")
    stripped = key.strip()
    return {
        "env_present": bool(stripped),
        "env_len": len(stripped),
        "env_tail4": _tail4(stripped),
        "env_has_whitespace": key != stripped or any(ch.isspace() for ch in stripped),
    }


def _ws_token_tail_from_stats(stats: dict[str, Any]) -> str | None:
    for key in ("access_token_tail4", "token_tail4"):
        value = stats.get(key)
        if value:
            return str(value)
    raw = str(stats.get("raw_line") or "")
    marker = "access_token_tail4="
    if marker in raw:
        return raw.split(marker, 1)[1].split()[0].strip()
    return None


def _primary_root_cause(*, websocket_error: str, credential_match: bool | None, latch_blocked: bool, token_file: dict[str, Any], env_token: dict[str, Any], subscriptions: int) -> str:
    if websocket_error and "403" in websocket_error and credential_match is False:
        return "ws_credential_mismatch"
    if websocket_error and "403" in websocket_error:
        return "ws_rejected_validated_credentials"
    if latch_blocked:
        return "auth_required_latch_blocking_restart"
    if not token_file.get("exists"):
        return "missing_token_file"
    if env_token.get("present") and credential_match is False:
        return "env_token_drift"
    if subscriptions <= 0:
        return "no_option_subscription_after_startup"
    return "unknown"


def build_feed_startup_root_cause_report(
    *,
    token_path: str | Path | None = None,
    runtime_health_path: str | Path | None = None,
    feed_runtime_path: str | Path | None = None,
    engine_status_path: str | Path | None = None,
    auth_health_path: str | Path | None = None,
    ws_events_path: str | Path | None = None,
    paper_log_path: str | Path | None = None,
    base_logs_dir: str | Path | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    now = float(now_epoch if now_epoch is not None else _now_epoch())
    root = repo_root()
    base = Path(base_logs_dir).expanduser() if base_logs_dir is not None else logs_dir()
    token_target = Path(token_path).expanduser() if token_path is not None else root / ".runtime" / "kite_access_token"
    runtime_target = Path(runtime_health_path).expanduser() if runtime_health_path is not None else base / "runtime_health_latest.json"
    feed_target = Path(feed_runtime_path).expanduser() if feed_runtime_path is not None else base / "feed_runtime_latest.json"
    engine_target = Path(engine_status_path).expanduser() if engine_status_path is not None else base / "engine_cycle_status.json"
    auth_target = Path(auth_health_path).expanduser() if auth_health_path is not None else base / "auth_health.jsonl"
    ws_target = Path(ws_events_path).expanduser() if ws_events_path is not None else base / "depth_ws_events.jsonl"
    paper_target = Path(paper_log_path).expanduser() if paper_log_path is not None else _latest_path(base, "paper_market_*.log")

    runtime_health = _read_json(runtime_target)
    feed_runtime = _read_json(feed_target)
    engine_status = _read_json(engine_target)

    runtime_status_freshness = {
        "runtime_health_latest": classify_runtime_payload_freshness(
            runtime_health,
            path=runtime_target,
        ),
        "feed_runtime_latest": classify_runtime_payload_freshness(
            feed_runtime,
            path=feed_target,
        ),
        "engine_cycle_status": classify_runtime_payload_freshness(
            engine_status,
            path=engine_target,
        ),
    }
    stale_runtime_inputs = [
        name
        for name, freshness in runtime_status_freshness.items()
        if not bool(freshness.get("is_current_run"))
    ]
    auth_rows = _read_jsonl_tail(auth_target)
    ws_rows = _read_jsonl_tail(ws_target)
    paper_lines = _read_lines(paper_target)

    latest_auth = _latest_auth_health(auth_rows)
    credential_stats = _latest_credential_stats(ws_rows, paper_lines)
    ws_token_tail4 = _ws_token_tail_from_stats(credential_stats)
    token_file = _token_file_state(token_target)
    env_token = _env_token_state()
    api_key = _api_key_state()
    websocket_error = _engine_ws_error(engine_status, paper_lines)
    latch_blocked = bool(_latest_event(ws_rows, "FEED_RESTART_BLOCKED_AUTH_REQUIRED"))
    engine_subscriptions = int(engine_status.get("subscribed_option_tokens_count") or 0)
    runtime_feed = runtime_health.get("feed") if isinstance(runtime_health.get("feed"), dict) else runtime_health
    runtime_subscriptions = int(runtime_feed.get("subscribed_option_tokens_count") or 0)
    feed_subscriptions = int(feed_runtime.get("subscribed_option_tokens_count") or 0)
    subscriptions = max(engine_subscriptions, runtime_subscriptions, feed_subscriptions)

    credential_match: bool | None
    if ws_token_tail4 and token_file.get("tail4"):
        credential_match = ws_token_tail4 == token_file.get("tail4")
    else:
        credential_match = None

    primary = _primary_root_cause(
        websocket_error=websocket_error,
        credential_match=credential_match,
        latch_blocked=latch_blocked,
        token_file=token_file,
        env_token=env_token,
        subscriptions=subscriptions,
    )

    return {
        "version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "mode": str(engine_status.get("market_mode") or runtime_health.get("mode") or "unknown"),
        "source": {
            "token_path": str(token_target),
            "runtime_health_path": str(runtime_target),
            "feed_runtime_path": str(feed_target),
            "engine_status_path": str(engine_target),
            "auth_health_path": str(auth_target),
            "ws_events_path": str(ws_target),
            "paper_log_path": str(paper_target) if paper_target is not None else None,
        },
        "file_freshness": {
            "runtime_health": _file_meta(runtime_target, now_epoch=now),
            "feed_runtime": _file_meta(feed_target, now_epoch=now),
            "engine_status": _file_meta(engine_target, now_epoch=now),
            "auth_health": _file_meta(auth_target, now_epoch=now),
            "ws_events": _file_meta(ws_target, now_epoch=now),
            "paper_log": _file_meta(paper_target, now_epoch=now),
        },
        "runtime_status_freshness": runtime_status_freshness,
        "stale_runtime_inputs": stale_runtime_inputs,
        "credential_sources": {
            "token_file": token_file,
            "env_token": env_token,
            "api_key": api_key,
            "latest_rest_auth": {
                "ok": latest_auth.get("ok"),
                "auth_state": latest_auth.get("auth_state"),
                "source": latest_auth.get("source"),
                "token_tail4": latest_auth.get("access_token_tail4"),
                "api_key_tail4": latest_auth.get("api_key_tail4"),
                "ts_epoch": latest_auth.get("ts_epoch"),
                "error": latest_auth.get("error"),
            },
            "latest_ws_credential_stats": credential_stats,
            "ws_token_tail4_matches_file_token_tail4": credential_match,
        },
        "engine_feed_state": {
            "auth_ok": engine_status.get("auth_ok"),
            "auth_state": engine_status.get("auth_state"),
            "auth_reason": engine_status.get("auth_reason"),
            "feed_ok": engine_status.get("feed_ok"),
            "ws_connected": engine_status.get("ws_connected"),
            "subscribed_option_tokens_count": engine_subscriptions,
            "visible_executable_count": engine_status.get("visible_executable_count"),
            "primary_blocker": engine_status.get("primary_blocker"),
        },
        "runtime_feed_state": {
            "ws_connected": runtime_feed.get("ws_connected"),
            "sla_status": runtime_feed.get("sla_status"),
            "subscribed_option_tokens_count": runtime_subscriptions,
            "subscriptions_count": runtime_feed.get("subscriptions_count"),
            "ltp_age_sec": runtime_feed.get("ltp_age_sec"),
            "depth_age_sec": runtime_feed.get("depth_age_sec"),
        },
        "feed_runtime_state": {
            "runtime_state": feed_runtime.get("runtime_state"),
            "state_machine": feed_runtime.get("state_machine"),
            "ws_connected": feed_runtime.get("ws_connected"),
            "effective_ws_connected": feed_runtime.get("effective_ws_connected"),
            "subscribed_option_tokens_count": feed_subscriptions,
            "market_open": feed_runtime.get("market_open"),
            "ts_epoch": feed_runtime.get("ts_epoch"),
        },
        "websocket_failure": {
            "error": websocket_error,
            "auth_required_latch_restart_block_seen": latch_blocked,
            "recent_failure_lines": _extract_ws_lines(paper_lines),
        },
        "decision": {
            "primary_root_cause": primary,
            "safe_to_restart_without_fix": False if primary != "unknown" else None,
            "recommended_next_action": _recommended_next_action(primary),
        },
    }


def _recommended_next_action(primary: str) -> str:
    if primary == "ws_credential_mismatch":
        return "force_websocket_to_use_canonical_file_credentials_and_log_tail_match"
    if primary == "ws_rejected_validated_credentials":
        return "inspect_kite_app_permissions_api_key_pair_and_websocket_handshake"
    if primary == "auth_required_latch_blocking_restart":
        return "clear_latch_only_after_fresh_rest_validation_and_new_token_generation"
    if primary == "missing_token_file":
        return "refresh_kite_token_before_startup"
    if primary == "env_token_drift":
        return "unset_env_token_or_make_env_token_match_file_token_before_startup"
    if primary == "no_option_subscription_after_startup":
        return "inspect_token_selection_and_subscription_attempt_path"
    return "inspect_feed_startup_root_cause_report"


def feed_startup_root_cause_report_path() -> Path:
    return ensure_dir(reports_dir()) / "feed_startup_root_cause_report.json"


def save_feed_startup_root_cause_report(report: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else feed_startup_root_cause_report_path()
    return write_json_atomic(target, json.loads(json.dumps(dict(report or {}), ensure_ascii=True, default=str)))
