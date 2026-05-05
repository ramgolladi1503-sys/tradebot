from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from core.auth_manager import set_auth_required_state
from core.events import write_json_atomic
from core.paths import locks_dir, logs_dir, runtime_dir


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except Exception:
        return False


def _append_startup_recovery_event(log_root: Path, payload: dict[str, Any]) -> None:
    path = log_root / "startup_recovery.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def reap_stale_runtime_locks(
    *,
    lock_dir: Path | str | None = None,
    logs_root: Path | str | None = None,
    pid_alive: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    target_lock_dir = Path(lock_dir) if lock_dir is not None else locks_dir()
    target_logs_root = Path(logs_root) if logs_root is not None else logs_dir()
    target_lock_dir.mkdir(parents=True, exist_ok=True)
    target_logs_root.mkdir(parents=True, exist_ok=True)
    alive_fn = pid_alive or _pid_alive
    stale_locks: list[dict[str, Any]] = []
    now_epoch = time.time()

    for lock_path in sorted(target_lock_dir.glob("*.lock")):
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        pid = payload.get("pid")
        try:
            pid_val = int(pid)
        except Exception:
            pid_val = None
        if pid_val is None or alive_fn(pid_val):
            continue
        stale = {
            "lock_name": lock_path.name,
            "lock_path": str(lock_path),
            "pid": pid_val,
            "previous_reason": str(payload.get("reason") or ""),
            "timestamp_epoch": payload.get("timestamp_epoch") or payload.get("acquired_at_epoch"),
        }
        try:
            lock_path.unlink(missing_ok=True)
            stale["action"] = "unlinked"
        except Exception as exc:
            stale["action"] = "unlink_failed"
            stale["error"] = str(exc)
        stale_locks.append(stale)

    result = {
        "ts_epoch": now_epoch,
        "reaped_count": len(stale_locks),
        "stale_locks": stale_locks,
    }
    if stale_locks:
        _append_startup_recovery_event(
            target_logs_root,
            {
                "event": "STALE_RUNTIME_LOCKS_REAPED",
                **result,
            },
        )
    return result


def publish_auth_blocked_startup_state(
    *,
    reason: str,
    source: str,
    runtime_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(runtime_root) if runtime_root is not None else runtime_dir()
    target_logs_root = root / "logs"
    target_logs_root.mkdir(parents=True, exist_ok=True)
    now_epoch = time.time()
    ts_local = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now_epoch))
    repo_root_path = root.parent if root.name == ".runtime" else root
    auth_payload = set_auth_required_state(
        reason=reason,
        source=source,
        repo_root_path=repo_root_path,
    )
    auth_state = str(auth_payload.get("status") or "AUTH_REQUIRED").strip().upper()
    blocker = "AUTH_REQUIRED"

    suggestions_payload = {
        "ts_epoch": now_epoch,
        "ts_local": ts_local,
        "status": "blocked",
        "reason": "auth_blocked",
        "subreason": str(reason or ""),
        "primary_blocker": blocker,
        "market_mode": "LIVE",
        "market_open": False,
        "suggestion_count": 0,
        "current_cycle_candidates_seen": 0,
        "current_cycle_candidates_enqueued": 0,
        "current_cycle_suggestion_count": 0,
        "visible_suggestion_count": 0,
        "visible_advisory_count": 0,
        "visible_queue_only_count": 0,
        "visible_executable_count": 0,
        "feed_ok": False,
        "ws_connected": False,
        "auth_ok": False,
        "auth_state": auth_state,
        "auth_reason": str(reason or ""),
        "subscribed_option_tokens_count": 0,
        "missing_option_tokens_count": 0,
    }
    engine_payload = {
        "ts_epoch": now_epoch,
        "cycle_ok": False,
        "cycle_stage": "blocked",
        "market_mode": "LIVE",
        "market_open": False,
        "reason": "auth_blocked",
        "subreason": str(reason or ""),
        "symbols_scanned": 0,
        "candidates_seen": 0,
        "candidates_blocked": 0,
        "candidates_enqueued": 0,
        "cycle_trade_build_attempts": 0,
        "current_cycle_candidates_seen": 0,
        "current_cycle_candidates_enqueued": 0,
        "current_cycle_suggestion_count": 0,
        "visible_suggestion_count": 0,
        "visible_advisory_count": 0,
        "visible_queue_only_count": 0,
        "visible_executable_count": 0,
        "top_blockers": [{"reason": blocker, "count": 1}],
        "primary_blocker": blocker,
        "feed_ok": False,
        "ws_connected": False,
        "auth_ok": False,
        "auth_state": auth_state,
        "auth_reason": str(reason or ""),
        "subscribed_option_tokens_count": 0,
        "missing_option_tokens_count": 0,
        "last_error": str(reason or ""),
    }
    feed_payload = {
        "ts_epoch": now_epoch,
        "runtime_state": "AUTH_BLOCKED",
        "state_machine": {"state": "DOWN", "reason": "auth_blocked"},
        "ws_connected": False,
        "feed_ok": False,
        "last_error": str(reason or ""),
        "subscribed_option_tokens_count": 0,
        "missing_option_tokens_count": 0,
        "option_feed_block_reason_by_symbol": {
            "NIFTY": blocker,
            "BANKNIFTY": blocker,
            "SENSEX": blocker,
        },
        "option_active_blockers_by_symbol": {
            "NIFTY": [blocker],
            "BANKNIFTY": [blocker],
            "SENSEX": [blocker],
        },
    }
    runtime_health_payload = {
        "ts_epoch": now_epoch,
        "snapshot_ts_epoch": now_epoch,
        "snapshot_age_sec": 0.0,
        "mode": "LIVE",
        "market_open": False,
        "feed": {
            "runtime_state": "AUTH_BLOCKED",
            "ws_connected": False,
            "sla_status": "FAIL",
            "sla_state": "LIVE",
            "allow_stale_quotes": False,
            "blockers": [blocker],
            "reasons": [blocker],
            "ltp_required": True,
            "depth_required": True,
            "subscribed_option_tokens_count": 0,
            "subscribed_tokens_count": 0,
            "subscriptions_count": 0,
            "missing_option_tokens_count": 0,
        },
        "execution": {
            "kill_switch_triggered": False,
            "kill_switch_reason": None,
        },
        "risk": {
            "daily_pnl_pct": 0.0,
            "open_risk_pct": 0.0,
            "hard_halt": False,
        },
        "recon": {
            "daemon_running": False,
            "last_cycle_ts_epoch": None,
        },
    }

    write_json_atomic(target_logs_root / "suggestions_status.json", suggestions_payload)
    write_json_atomic(target_logs_root / "engine_cycle_status.json", engine_payload)
    write_json_atomic(target_logs_root / "feed_runtime_latest.json", feed_payload)
    write_json_atomic(target_logs_root / "runtime_health_latest.json", runtime_health_payload)
    _append_startup_recovery_event(
        target_logs_root,
        {
            "event": "STARTUP_AUTH_BLOCKED_STATE_WRITTEN",
            "ts_epoch": now_epoch,
            "reason": str(reason or ""),
            "source": str(source or ""),
            "auth_state": auth_state,
        },
    )
    return {
        "auth_ok": False,
        "auth_state": auth_state,
        "auth_reason": str(reason or ""),
        "runtime_state": "AUTH_BLOCKED",
    }
