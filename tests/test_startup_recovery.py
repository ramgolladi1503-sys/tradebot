import json
from pathlib import Path

from core import startup_recovery


def test_reap_stale_runtime_locks_removes_dead_pid_locks(tmp_path):
    locks_dir = tmp_path / "locks"
    logs_dir = tmp_path / "logs"
    locks_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    stale_lock = locks_dir / "live_monitoring.lock"
    stale_lock.write_text(
        json.dumps(
            {
                "locked": True,
                "name": "live_monitoring.lock",
                "pid": 999999,
                "reason": "ACTIVE",
                "timestamp_epoch": 1_700_000_000.0,
            }
        ),
        encoding="utf-8",
    )

    payload = startup_recovery.reap_stale_runtime_locks(
        lock_dir=locks_dir,
        logs_root=logs_dir,
        pid_alive=lambda pid: False,
    )

    assert payload["reaped_count"] == 1
    assert payload["stale_locks"][0]["lock_name"] == "live_monitoring.lock"
    assert not stale_lock.exists()
    event_lines = (logs_dir / "startup_recovery.jsonl").read_text(encoding="utf-8").splitlines()
    assert event_lines


def test_publish_auth_blocked_startup_state_zeroes_visibility_and_sets_auth_required(tmp_path):
    runtime_root = tmp_path / ".runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)

    payload = startup_recovery.publish_auth_blocked_startup_state(
        reason="profile_error:TokenException",
        source="run_live.validate_token",
        runtime_root=runtime_root,
    )

    assert payload["auth_state"] == "AUTH_REQUIRED"
    suggestions = json.loads((logs_root / "suggestions_status.json").read_text(encoding="utf-8"))
    engine = json.loads((logs_root / "engine_cycle_status.json").read_text(encoding="utf-8"))
    feed = json.loads((logs_root / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    health = json.loads((logs_root / "runtime_health_latest.json").read_text(encoding="utf-8"))
    auth_state = json.loads((runtime_root / "auth_state.json").read_text(encoding="utf-8"))

    assert suggestions["auth_state"] == "AUTH_REQUIRED"
    assert suggestions["auth_ok"] is False
    assert suggestions["visible_suggestion_count"] == 0
    assert suggestions["visible_executable_count"] == 0
    assert engine["auth_state"] == "AUTH_REQUIRED"
    assert engine["visible_suggestion_count"] == 0
    assert engine["visible_executable_count"] == 0
    assert feed["runtime_state"] == "AUTH_BLOCKED"
    assert feed["ws_connected"] is False
    assert health["feed"]["runtime_state"] == "AUTH_BLOCKED"
    assert health["feed"]["ws_connected"] is False
    assert auth_state["status"] == "AUTH_REQUIRED"
