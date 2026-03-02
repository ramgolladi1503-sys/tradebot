from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

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
