import json
from types import SimpleNamespace

from core import runtime_health
from core.runtime_truth_integrity import truth_hash_from_mapping


def test_runtime_health_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_health, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {
            "state": "OK",
            "market_open": True,
            "ltp": {"age_sec": 1.0},
            "depth": {"age_sec": 2.0},
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        runtime_health,
        "get_feed_debug",
        lambda now_epoch=None: {
            "ws_connected": True,
            "subscribed_tokens_count": 2,
            "last_tick_age_sec": 1.5,
            "transport_state": "CONNECTED",
            "transport_reason": "ws_connected",
            "transport_healthy": True,
        },
    )

    exec_engine = SimpleNamespace(
        kill_switch_triggered=False,
        kill_switch_reason=None,
        get_last_spread_decision=lambda: {"spread_pct": 0.01},
        get_reconciliation_status=lambda: {"daemon_running": True, "last_cycle_ts_epoch": 123.0},
    )
    risk_state = SimpleNamespace(mode="NORMAL", daily_pnl_pct=0.01, open_risk_pct=0.02)
    orch = SimpleNamespace(execution_engine=exec_engine, risk_state=risk_state)

    payload = runtime_health.get_runtime_health(orchestrator=orch, now_epoch=123.0)
    assert "ts_epoch" in payload
    assert "mode" in payload
    assert "market_open" in payload
    assert "feed" in payload
    assert "execution" in payload
    assert "risk" in payload
    assert "recon" in payload
    assert payload["feed"]["transport_state"] == "CONNECTED"
    assert payload["feed"]["transport_healthy"] is True
    assert payload["feed"]["feed_ok"] is None
    assert payload["feed"]["execution_feed_ready"] is None


def test_runtime_health_publishes_orchestrator_warmup_proof(monkeypatch):
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {"state": "OK", "market_open": True, "ltp": {"age_sec": 1.0}, "depth": {"age_sec": 1.0}, "reasons": []},
    )
    monkeypatch.setattr(
        runtime_health,
        "get_feed_debug",
        lambda now_epoch=None: {
            "ws_connected": True,
            "subscribed_tokens_count": 2,
            "last_tick_age_sec": 1.0,
            "last_depth_age_sec": 1.0,
            "option_ticks_verified": True,
            "verified_option_symbols": ["NIFTY"],
            "missing_option_symbols": [],
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "LIVE",
            "transport_state": "CONNECTED",
            "transport_healthy": True,
        },
    )
    orch = SimpleNamespace(
        _pilot_unlock_clean_cycles=3,
        execution_engine=SimpleNamespace(
            kill_switch_triggered=False,
            kill_switch_reason=None,
            get_last_spread_decision=lambda: {},
            get_reconciliation_status=lambda: {},
        ),
        risk_state=SimpleNamespace(mode="NORMAL", daily_pnl_pct=0.0, open_risk_pct=0.0),
    )

    payload = runtime_health.get_runtime_health(orchestrator=orch, now_epoch=123.0)

    assert payload["feed"]["warmup_clean_cycles"] == 3
    assert payload["feed"]["warmup_required_clean_cycles"] == 3
    assert "WARMUP_INCOMPLETE" not in payload["feed"]["full_feed_proof_blockers"]


def test_runtime_health_keeps_missing_warmup_proof_fail_closed(monkeypatch):
    monkeypatch.setattr(runtime_health, "get_freshness_status", lambda force=False: {"state": "OK", "market_open": True, "ltp": {}, "depth": {}, "reasons": []})
    monkeypatch.setattr(runtime_health, "get_feed_debug", lambda now_epoch=None: {"ws_connected": True, "feed_truth_state": "LIVE", "transport_state": "CONNECTED"})
    orch = SimpleNamespace(execution_engine=SimpleNamespace(kill_switch_triggered=False, kill_switch_reason=None, get_last_spread_decision=lambda: {}, get_reconciliation_status=lambda: {}), risk_state=SimpleNamespace(mode="NORMAL", daily_pnl_pct=0.0, open_risk_pct=0.0))

    payload = runtime_health.get_runtime_health(orchestrator=orch, now_epoch=123.0)

    assert payload["feed"]["warmup_clean_cycles"] is None
    assert "WARMUP_INCOMPLETE" in payload["feed"]["full_feed_proof_blockers"]


def test_runtime_health_emits_truth_integrity_alert_on_snapshot_hash_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_health, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime_health, "logs_dir", lambda: tmp_path)
    captured_events = []
    monkeypatch.setattr(
        runtime_health,
        "append_event",
        lambda *args, **kwargs: captured_events.append((args, kwargs)),
    )
    monkeypatch.setattr(
        runtime_health,
        "get_freshness_status",
        lambda force=False: {
            "state": "OK",
            "market_open": True,
            "ltp": {"age_sec": 1.0},
            "depth": {"age_sec": 2.0},
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        runtime_health,
        "get_feed_debug",
        lambda now_epoch=None: {
            "ws_connected": True,
            "subscribed_tokens_count": 2,
            "last_tick_age_sec": 1.5,
            "transport_state": "CONNECTED",
            "transport_reason": "ws_connected",
            "transport_healthy": True,
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "live",
            "transport_heartbeat_epoch": 123.0,
            "transport_heartbeat_age_sec": 0.0,
            "transport_heartbeat_state": "CONNECTED",
        },
    )

    feed_runtime_payload = {
        "ts_epoch": 123.0,
        "ws_connected": True,
        "subscribed_tokens_count": 2,
        "intended_tokens_count": 2,
        "last_ws_tick_epoch": 123.0,
        "last_tick_age_sec": 1.5,
        "last_depth_epoch": 122.0,
        "last_depth_age_sec": 2.0,
        "runtime_state": "RUNNING",
        "transport_state": "CONNECTED",
        "transport_reason": "ws_connected",
        "transport_healthy": True,
        "feed_truth_state": "LIVE",
        "feed_truth_reason_code": "LIVE",
        "feed_truth_strict_live": True,
        "transport_heartbeat_epoch": 123.0,
        "transport_heartbeat_age_sec": 0.0,
        "transport_heartbeat_state": "CONNECTED",
    }
    feed_runtime_payload["snapshot_hash"] = "0" * 64
    feed_runtime_payload["snapshot_hash_version"] = 1
    (tmp_path / "feed_runtime_latest.json").write_text(json.dumps(feed_runtime_payload), encoding="utf-8")

    exec_engine = SimpleNamespace(
        kill_switch_triggered=False,
        kill_switch_reason=None,
        get_last_spread_decision=lambda: {"spread_pct": 0.01},
        get_reconciliation_status=lambda: {"daemon_running": True, "last_cycle_ts_epoch": 123.0},
    )
    risk_state = SimpleNamespace(mode="NORMAL", daily_pnl_pct=0.01, open_risk_pct=0.02)
    orch = SimpleNamespace(execution_engine=exec_engine, risk_state=risk_state)

    payload = runtime_health.get_runtime_health(orchestrator=orch, now_epoch=123.0)
    expected_hash = truth_hash_from_mapping(
        feed_runtime_payload,
        exclude_keys=(
            "snapshot_hash",
            "snapshot_hash_version",
            "transport_heartbeat",
            "transport_heartbeat_epoch",
            "transport_heartbeat_age_sec",
            "transport_heartbeat_source",
            "transport_heartbeat_state",
            "transport_heartbeat_reason",
            "truth_integrity_alerts",
            "truth_integrity_alert_count",
            "truth_integrity_status",
        ),
    )
    assert payload["feed"]["truth_integrity_status"] == "ALERT"
    assert payload["feed"]["snapshot_hash_expected"] == expected_hash
    assert payload["feed"]["snapshot_hash_match"] is False
    assert payload["feed"]["truth_integrity_alert_count"] >= 1
    assert any(alert["code"] == "SNAPSHOT_HASH_MISMATCH" for alert in payload["feed"]["truth_integrity_alerts"])
    assert captured_events and captured_events[0][0][0] == "runtime_truth_integrity_alert"
