import json

from config import config as cfg
from core.gate_status_log import append_gate_status, build_gate_status_record, gate_status_path
from core.orchestrator import Orchestrator
import core.orchestrator as orchestrator_module


def test_gate_status_logs_gate_reasons(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(cfg, "INDICATOR_STALE_SEC", 120, raising=False)

    market_data = {
        "symbol": "NIFTY",
        "ltp": 25722.2,
        "ltp_source": "token_map_nifty",
        "ltp_ts_epoch": 1771401100.25,
        "indicators_ok": False,
        "indicators_age_sec": None,
        "indicator_last_update_epoch": None,
        "ohlc_bars_count": 0,
        "ohlc_last_bar_epoch": None,
        "compute_indicators_error": "ValueError:test",
        "missing_inputs": ["ohlc_buffer_empty", "ltp_missing"],
        "primary_regime": "NEUTRAL",
        "regime_probs": {"NEUTRAL": 0.61, "TREND": 0.39},
        "regime_entropy": 0.77,
        "unstable_regime_flag": True,
    }
    reasons = ["indicators_missing"]

    record = build_gate_status_record(
        market_data=market_data,
        gate_allowed=False,
        gate_family=None,
        gate_reasons=reasons,
        stage="indicator_gate",
    )
    append_gate_status(record, desk_id="TEST")

    path = gate_status_path("TEST")
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    row = rows[-1]
    assert row["symbol"] == "NIFTY"
    assert row["execution_mode"] == "SIM"
    assert row["kite_use_api"] is True
    assert row["gate_reasons"] == reasons
    assert row["gate_allowed"] is False
    assert row["ltp_source"] == "token_map_nifty"
    assert row["regime_probs_max"] == 0.61
    assert row["ohlc_bars_count"] == 0
    assert row["compute_indicators_error"] == "ValueError:test"
    assert row["indicator_inputs_ok"] is False
    assert isinstance(row["indicators_age_sec"], (int, float))
    assert row["indicator_missing_inputs"] == ["ohlc_buffer_empty", "ltp_missing", "never_computed"]
    assert row["missing_inputs"] == ["ohlc_buffer_empty", "ltp_missing", "never_computed"]


def test_gate_status_once_per_stage_symbol_cycle(monkeypatch):
    calls = []

    def _fake_append(record, desk_id=None):
        calls.append((record.get("symbol"), record.get("stage"), desk_id))

    monkeypatch.setattr(orchestrator_module, "append_gate_status", _fake_append)
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch._gate_status_cycle_seen = set()
    md = {
        "symbol": "NIFTY",
        "ltp": 25000.0,
        "ltp_source": "live",
        "ltp_ts_epoch": 1.0,
        "indicators_ok": True,
        "indicators_age_sec": 1.0,
    }
    orch._append_gate_status(md, gate_allowed=False, gate_family=None, gate_reasons=["r1"], stage="indicator_gate")
    orch._append_gate_status(md, gate_allowed=False, gate_family=None, gate_reasons=["r1"], stage="indicator_gate")
    orch._append_gate_status(md, gate_allowed=True, gate_family="DEFINED_RISK", gate_reasons=["r2"], stage="strategy_gate")

    assert calls == [
        ("NIFTY", "indicator_gate", "TEST"),
        ("NIFTY", "strategy_gate", "TEST"),
    ]


def test_gate_status_includes_indicator_fields_for_strategy_stage():
    md = {
        "symbol": "NIFTY",
        "ltp": 25000.0,
        "ltp_source": "live",
        "ltp_ts_epoch": 1000.0,
        "indicators_ok": True,
        "indicator_inputs_ok": True,
        "indicators_age_sec": 1.2,
        "indicator_last_update_epoch": 998.8,
        "indicator_missing_inputs": [],
        "ohlc_seeded": True,
        "ohlc_bars_count": 40,
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.99},
        "regime_entropy": 0.01,
        "unstable_regime_flag": False,
    }
    row = build_gate_status_record(
        market_data=md,
        gate_allowed=True,
        gate_family="DEFINED_RISK",
        gate_reasons=[],
        stage="strategy_gate",
    )
    assert row["stage"] == "strategy_gate"
    assert row["indicator_inputs_ok"] is True
    assert isinstance(row["indicators_age_sec"], (int, float))
    assert row["indicator_last_update_epoch"] == 998.8
    assert row["indicator_missing_inputs"] == []
    assert row["ohlc_seeded"] is True
    assert row["ohlc_bars_count"] == 40
