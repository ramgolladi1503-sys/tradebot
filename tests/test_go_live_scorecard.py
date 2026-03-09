from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

def test_go_live_scorecard_fails_when_health_gate_fails(tmp_path: Path, monkeypatch):
    import core.go_live_scorecard as scorecard_mod

    logs_root = tmp_path / "runtime" / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    monkeypatch.setattr(
        scorecard_mod,
        "run_health_gate",
        lambda desk, strict: {
            "exit_code": 2,
            "report_json_path": str(logs_root / "health_gate_report.json"),
            "report_md_path": str(logs_root / "health_gate_report.md"),
        },
    )
    monkeypatch.setattr(scorecard_mod, "scan_canonical_path_violations", lambda: [])
    monkeypatch.setattr(scorecard_mod.lifecycle, "active_thread_names", lambda: [])

    events: list[dict] = []

    def _append_event(event_type, payload, **kwargs):
        events.append({"type": event_type, "payload": dict(payload or {})})

    def _read_events(event_type=None, run_id=None, **kwargs):
        out = list(events)
        if event_type is not None:
            out = [row for row in out if str(row.get("type")) == str(event_type)]
        if run_id is not None:
            out = [row for row in out if str((row.get("payload") or {}).get("run_id")) == str(run_id)]
        return out

    monkeypatch.setattr(scorecard_mod, "append_event", _append_event)
    monkeypatch.setattr(scorecard_mod, "read_events", _read_events)
    monkeypatch.setattr(scorecard_mod, "build_recon", lambda rows: {"trade_count": 1, "status": "ok", "trades": rows})
    monkeypatch.setattr(scorecard_mod, "get_freshness_status", lambda force=False: {"market_open": True, "ok": True, "state": "OK"})

    monkeypatch.setattr(scorecard_mod, "scan_open_incidents", lambda: {"path": str(logs_root / "incidents.jsonl"), "open_incidents": []})

    report = scorecard_mod.GoLiveScorecard().run("DEFAULT")

    assert report["status"] == "FAIL"
    codes = {str(item.get("code")) for item in report.get("failures", [])}
    assert "HEALTH_GATE_STRICT_P0" in codes
    assert Path(report["report_json_path"]).exists()
    written = json.loads(Path(report["report_json_path"]).read_text(encoding="utf-8"))
    assert written["status"] == "FAIL"


def test_go_live_scorecard_feed_freshness_block_when_market_open(tmp_path: Path, monkeypatch):
    import core.go_live_scorecard as scorecard_mod

    logs_root = tmp_path / "runtime" / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    monkeypatch.setattr(scorecard_mod, "run_health_gate", lambda desk, strict: {"exit_code": 0})
    monkeypatch.setattr(scorecard_mod, "scan_canonical_path_violations", lambda: [])
    monkeypatch.setattr(scorecard_mod.lifecycle, "active_thread_names", lambda: [])
    monkeypatch.setattr(scorecard_mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(scorecard_mod, "read_events", lambda *args, **kwargs: [{"type": "go_live_scorecard_probe", "payload": {"run_id": "x"}}])
    monkeypatch.setattr(scorecard_mod, "build_recon", lambda rows: {"trade_count": 1, "status": "ok"})
    monkeypatch.setattr(
        scorecard_mod,
        "get_freshness_status",
        lambda force=False: {"market_open": True, "ok": False, "state": "STALE", "reasons": ["ltp_stale"]},
    )

    monkeypatch.setattr(scorecard_mod, "scan_open_incidents", lambda: {"path": str(logs_root / "incidents.jsonl"), "open_incidents": []})

    report = scorecard_mod.GoLiveScorecard().run("DEFAULT")

    assert report["status"] == "FAIL"
    codes = {str(item.get("code")) for item in report.get("failures", [])}
    assert "FEED_FRESHNESS_P0" in codes


def test_arm_trade_blocks_when_go_live_scorecard_fails(monkeypatch):
    import scripts.arm_trade as arm_trade

    importlib.reload(arm_trade)
    monkeypatch.setattr(arm_trade.cfg, "CONFIG_APPROVAL_ENFORCE_ON_ARM", False, raising=False)
    called = {"arm": False}

    class _FakeScorecard:
        def run(self, desk_id: str):
            del desk_id
            return {
                "status": "FAIL",
                "report_json_path": "/tmp/go_live_scorecard.json",
                "report_md_path": "/tmp/go_live_scorecard.md",
                "failures": [{"code": "HEALTH_GATE_STRICT_P0"}],
            }

    monkeypatch.setattr(arm_trade, "GoLiveScorecard", lambda: _FakeScorecard())

    def _fake_arm(*args, **kwargs):
        called["arm"] = True
        return True, "approval_armed"

    monkeypatch.setattr(arm_trade, "arm_order_intent", _fake_arm)
    monkeypatch.setattr(sys, "argv", ["arm_trade.py", "--payload-hash", "deadbeef"])

    code = arm_trade.main()
    assert code == 2
    assert called["arm"] is False


def test_go_live_scorecard_adds_regime_monitor_warning(tmp_path: Path, monkeypatch):
    import core.go_live_scorecard as scorecard_mod

    logs_root = tmp_path / "runtime" / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("LOG_DIR", str(logs_root))

    monkeypatch.setattr(scorecard_mod, "run_health_gate", lambda desk, strict: {"exit_code": 0})
    monkeypatch.setattr(scorecard_mod, "scan_canonical_path_violations", lambda: [])
    monkeypatch.setattr(scorecard_mod.lifecycle, "active_thread_names", lambda: [])
    monkeypatch.setattr(scorecard_mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(scorecard_mod, "read_events", lambda *args, **kwargs: [{"type": "go_live_scorecard_probe", "payload": {"run_id": "x"}}])
    monkeypatch.setattr(scorecard_mod, "build_recon", lambda rows: {"trade_count": 1, "status": "ok"})
    monkeypatch.setattr(
        scorecard_mod,
        "get_freshness_status",
        lambda force=False: {"market_open": False, "ok": True, "state": "PLANNING"},
    )
    monkeypatch.setattr(scorecard_mod, "scan_open_incidents", lambda: {"path": str(logs_root / "incidents.jsonl"), "open_incidents": []})
    monkeypatch.setattr(
        scorecard_mod,
        "get_regime_monitor_status",
        lambda prefer_disk=True: {
            "sample_count": 64,
            "collapsed": True,
            "severe": True,
            "accuracy": 0.28,
            "confidence_correlation": -0.31,
            "collapse_streak": 4,
        },
    )

    report = scorecard_mod.GoLiveScorecard().run("DEFAULT")
    warning_codes = {str(item.get("code")) for item in report.get("warnings", [])}
    assert "REGIME_MONITOR_COLLAPSE_P1" in warning_codes


def test_arm_trade_requires_confirmation_phrase(monkeypatch, tmp_path):
    import scripts.arm_trade as arm_trade

    importlib.reload(arm_trade)
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(arm_trade.cfg, "ARMING_REQUIRE_HEALTH_PASS_RECENT", True, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "CONFIG_APPROVAL_ENFORCE_ON_ARM", False, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "ARMING_HEALTH_PASS_MAX_AGE_SEC", 1800.0, raising=False)
    monkeypatch.setattr(
        arm_trade.cfg,
        "ARMING_COOLDOWN_STATE_PATH",
        str(logs_root / "arming_cooldown.json"),
        raising=False,
    )

    report_path = logs_root / "health_gate_report.json"
    report_path.write_text(
        json.dumps(
            {
                "pass": True,
                "exit_code": 0,
                "issues": [],
                "generated_ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    class _ScorecardPass:
        def run(self, desk_id: str):
            del desk_id
            return {"status": "PASS", "failures": []}

    called = {"arm": 0}

    def _fake_arm(*args, **kwargs):
        called["arm"] += 1
        return True, "approval_armed"

    monkeypatch.setattr(arm_trade, "GoLiveScorecard", lambda: _ScorecardPass())
    monkeypatch.setattr(arm_trade, "arm_order_intent", _fake_arm)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "NO")
    monkeypatch.setattr(sys, "argv", ["arm_trade.py", "--payload-hash", "deadbeef"])

    code = arm_trade.main()
    assert code == 2
    assert called["arm"] == 0


def test_arm_trade_blocks_when_health_gate_pass_is_stale(monkeypatch, tmp_path):
    import scripts.arm_trade as arm_trade

    importlib.reload(arm_trade)
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(arm_trade.cfg, "ARMING_REQUIRE_HEALTH_PASS_RECENT", True, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "CONFIG_APPROVAL_ENFORCE_ON_ARM", False, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "ARMING_HEALTH_PASS_MAX_AGE_SEC", 1800.0, raising=False)
    monkeypatch.setattr(
        arm_trade.cfg,
        "ARMING_COOLDOWN_STATE_PATH",
        str(logs_root / "arming_cooldown.json"),
        raising=False,
    )

    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    report_path = logs_root / "health_gate_report.json"
    report_path.write_text(
        json.dumps({"pass": True, "exit_code": 0, "issues": [], "generated_ts": stale_ts}),
        encoding="utf-8",
    )

    class _ScorecardPass:
        def run(self, desk_id: str):
            del desk_id
            return {"status": "PASS", "failures": []}

    called = {"arm": 0}

    def _fake_arm(*args, **kwargs):
        called["arm"] += 1
        return True, "approval_armed"

    monkeypatch.setattr(arm_trade, "GoLiveScorecard", lambda: _ScorecardPass())
    monkeypatch.setattr(arm_trade, "arm_order_intent", _fake_arm)
    monkeypatch.setattr(
        sys,
        "argv",
        ["arm_trade.py", "--payload-hash", "deadbeef", "--confirm-text", "YES I UNDERSTAND"],
    )

    code = arm_trade.main()
    assert code == 2
    assert called["arm"] == 0


def test_arm_trade_enforces_p0_cooldown_between_attempts(monkeypatch, tmp_path):
    import scripts.arm_trade as arm_trade

    importlib.reload(arm_trade)
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(arm_trade.cfg, "ARMING_REQUIRE_HEALTH_PASS_RECENT", False, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "CONFIG_APPROVAL_ENFORCE_ON_ARM", False, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "ARMING_P0_COOLDOWN_SEC", 1800.0, raising=False)
    monkeypatch.setattr(
        arm_trade.cfg,
        "ARMING_COOLDOWN_STATE_PATH",
        str(logs_root / "arming_cooldown.json"),
        raising=False,
    )

    calls = {"scorecard": 0, "arm": 0}

    class _ScorecardFirstFailThenPass:
        def run(self, desk_id: str):
            del desk_id
            calls["scorecard"] += 1
            if calls["scorecard"] == 1:
                return {
                    "status": "FAIL",
                    "failures": [{"code": "HEALTH_GATE_STRICT_P0"}],
                    "report_json_path": str(logs_root / "go_live_scorecard.json"),
                    "report_md_path": str(logs_root / "go_live_scorecard.md"),
                }
            return {"status": "PASS", "failures": []}

    def _fake_arm(*args, **kwargs):
        calls["arm"] += 1
        return True, "approval_armed"

    monkeypatch.setattr(arm_trade, "GoLiveScorecard", lambda: _ScorecardFirstFailThenPass())
    monkeypatch.setattr(arm_trade, "arm_order_intent", _fake_arm)
    monkeypatch.setattr(arm_trade, "now_utc_epoch", lambda: 1_700_000_000.0)

    monkeypatch.setattr(sys, "argv", ["arm_trade.py", "--payload-hash", "deadbeef"])
    first_code = arm_trade.main()
    assert first_code == 2
    assert calls["scorecard"] == 1
    assert calls["arm"] == 0

    cooldown_path = logs_root / "arming_cooldown.json"
    assert cooldown_path.exists()
    cooldown_state = json.loads(cooldown_path.read_text(encoding="utf-8"))
    assert "HEALTH_GATE_STRICT_P0" in list(cooldown_state.get("reason_codes") or [])

    monkeypatch.setattr(sys, "argv", ["arm_trade.py", "--payload-hash", "deadbeef"])
    second_code = arm_trade.main()
    assert second_code == 2
    # Cooldown check should block before a second scorecard run.
    assert calls["scorecard"] == 1
    assert calls["arm"] == 0


def test_arm_trade_blocks_when_config_hash_mismatch(monkeypatch):
    import scripts.arm_trade as arm_trade

    importlib.reload(arm_trade)
    monkeypatch.setattr(arm_trade.cfg, "ARMING_REQUIRE_HEALTH_PASS_RECENT", False, raising=False)
    monkeypatch.setattr(arm_trade.cfg, "CONFIG_APPROVAL_ENFORCE_ON_ARM", True, raising=False)

    class _ScorecardPass:
        def run(self, desk_id: str):
            del desk_id
            return {"status": "PASS", "failures": []}

    called = {"arm": 0}

    def _fake_arm(*args, **kwargs):
        called["arm"] += 1
        return True, "approval_armed"

    monkeypatch.setattr(arm_trade, "GoLiveScorecard", lambda: _ScorecardPass())
    monkeypatch.setattr(arm_trade, "check_config_approval", lambda desk_id=None: {
        "ok": False,
        "reason": "approval_hash_mismatch",
        "approved_hash": "aaa",
        "current_hash": "bbb",
        "path": "/tmp/approved_config.json",
    })
    monkeypatch.setattr(arm_trade, "arm_order_intent", _fake_arm)
    monkeypatch.setattr(
        sys,
        "argv",
        ["arm_trade.py", "--payload-hash", "deadbeef", "--confirm-text", "YES I UNDERSTAND"],
    )
    code = arm_trade.main()
    assert code == 2
    assert called["arm"] == 0
