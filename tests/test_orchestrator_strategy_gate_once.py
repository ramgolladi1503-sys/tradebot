import json
import time

from config import config as cfg
import core.orchestrator as orchestrator_module
from core.decision_telemetry_health import decision_write_error_path
from core.decision_dag import (
    NODE_N3_WARMUP_DONE,
    NODE_N9_FINAL_DECISION,
)
from core.orchestrator import Orchestrator
from core.strategy_gatekeeper import GateResult
from core.live_indicator_readiness import build_live_indicator_readiness_report


def test_one_strategy_gate_record_per_symbol_per_cycle(monkeypatch):
    emitted = []
    evaluate_calls = []
    immutable_seen = []

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            try:
                market_data["__mutate__"] = True
                immutable_seen.append(False)
            except Exception:
                immutable_seen.append(True)
            evaluate_calls.append((market_data.get("symbol"), mode, market_data.get("indicators_ok")))
            return GateResult(True, "DEFINED_RISK", ["paper_neutral_routed"])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted.append(record))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    raw_market_data = [
        {
            "symbol": "NIFTY",
            "instrument": "OPT",
            "timestamp": 1,
            "market_open": True,
            "ltp_ts_epoch": 1,
            "ltp": 25000.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "indicators_ok": True,
            "indicators_age_sec": 1.0,
        },
        {
            "symbol": "NIFTY",
            "instrument": "OPT",
            "timestamp": 2,
            "market_open": True,
            "ltp_ts_epoch": 2,
            "ltp": 25010.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "indicators_ok": False,
            "indicators_age_sec": 999.0,
        },
        {
            "symbol": "BANKNIFTY",
            "instrument": "OPT",
            "timestamp": 1,
            "market_open": True,
            "ltp_ts_epoch": 1,
            "ltp": 52000.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "indicators_ok": True,
            "indicators_age_sec": 1.0,
        },
        {
            "symbol": "SENSEX",
            "instrument": "OPT",
            "timestamp": 1,
            "market_open": True,
            "ltp_ts_epoch": 1,
            "ltp": 72000.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "indicators_ok": True,
            "indicators_age_sec": 1.0,
        },
    ]
    cycle_snapshots = orch._build_cycle_market_data(raw_market_data)

    # Simulate multiple call sites in the same cycle.
    for snap in cycle_snapshots:
        orch._strategy_gate_for_symbol(snap)
        conflict_view = dict(snap)
        conflict_view["indicators_ok"] = not bool(snap.get("indicators_ok"))
        orch._strategy_gate_for_symbol(conflict_view)

    assert [row.get("symbol") for row in emitted].count("NIFTY") == 1
    assert [row.get("symbol") for row in emitted].count("BANKNIFTY") == 1
    assert [row.get("symbol") for row in emitted].count("SENSEX") == 1
    rows_by_symbol = {row.get("symbol"): row for row in emitted}
    assert rows_by_symbol["NIFTY"]["stage"] == NODE_N3_WARMUP_DONE
    assert rows_by_symbol["BANKNIFTY"]["stage"] == NODE_N9_FINAL_DECISION
    assert rows_by_symbol["SENSEX"]["stage"] == NODE_N9_FINAL_DECISION
    assert {call[0] for call in evaluate_calls} == {"BANKNIFTY", "SENSEX"}
    assert immutable_seen == [True, True]


def test_strategy_gate_logs_no_conflicting_indicator_values_within_cycle(monkeypatch):
    emitted = []

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            return GateResult(True, "DEFINED_RISK", [])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted.append(record))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    # Newer timestamp has indicators_ok=False and must be the canonical snapshot.
    cycle_snapshots = orch._build_cycle_market_data(
        [
            {
                "symbol": "NIFTY",
                "instrument": "OPT",
                "timestamp": 1,
                "market_open": True,
                "ltp_ts_epoch": 1,
                "ltp": 25000.0,
                "quote_ok": True,
                "primary_regime": "TREND",
                "indicators_ok": True,
                "indicators_age_sec": 1.0,
            },
            {
                "symbol": "NIFTY",
                "instrument": "OPT",
                "timestamp": 2,
                "market_open": True,
                "ltp_ts_epoch": 2,
                "ltp": 25010.0,
                "quote_ok": True,
                "primary_regime": "TREND",
                "indicators_ok": False,
                "indicators_age_sec": 10.0,
            },
        ]
    )

    assert cycle_snapshots[0]["symbol"] == "NIFTY"
    # First call logs canonical snapshot.
    orch._strategy_gate_for_symbol(cycle_snapshots[0])
    # Second call with conflicting values must be ignored for this cycle.
    orch._strategy_gate_for_symbol(
        {
            "symbol": "NIFTY",
            "instrument": "OPT",
            "timestamp": 999,
            "market_open": True,
            "ltp_ts_epoch": 999,
            "ltp": 25020.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "indicators_ok": True,
            "indicators_age_sec": 0.0,
        }
    )

    rows = [row for row in emitted if row.get("symbol") == "NIFTY"]
    assert rows[0]["symbol"] == "NIFTY"
    assert rows[0]["stage"] == NODE_N3_WARMUP_DONE
    assert rows[0]["indicators_ok"] is False
    assert float(rows[0]["indicators_age_sec"]) == 10.0


def test_strategy_gate_returns_predicate_facts_from_strategy_selection(monkeypatch):
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_candidate_stream_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_decision_stream_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_decision_write_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "audit_append", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "handle_post_decision_side_effects", lambda *args, **kwargs: None)

    class _Decision:
        allowed = False
        stage = "STRATEGY_SELECT"
        blockers = ["NO_STRATEGY_QUALIFIED"]
        explain = []
        selected_strategy = None
        facts = {
            "predicate_node": "NODE_N8_STRATEGY_SELECT",
            "trade_builder_reached": True,
            "candidate_family_considered": None,
            "no_candidate_constructed": True,
            "qual_fail_codes": ["vwap"],
            "qual_fail_reasons_raw": ["price below vwap setup"],
            "picked_candidate": {"family": None},
            "all_candidates": [],
            "precondition_failures": [],
            "precondition_reasons": [],
            "strategy_reasons": [],
        }

    monkeypatch.setattr(orchestrator_module, "evaluate_decision", lambda *args, **kwargs: _Decision())

    class _Gatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            return GateResult(True, "DEFINED_RISK", [])

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _Gatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    gate = orch._strategy_gate_for_symbol(
        {
            "symbol": "NIFTY",
            "instrument": "OPT",
            "timestamp": 1,
            "market_open": True,
            "ltp_ts_epoch": 1,
            "ltp": 25000.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "indicators_ok": True,
            "indicators_age_sec": 1.0,
        }
    )

    tele = gate.facts.get("strategy_telemetry", gate.facts)
    assert gate.allowed is False
    assert gate.reasons == ["NO_STRATEGY_QUALIFIED"]
    assert str(tele["predicate_node"]).endswith("N8_STRATEGY_SELECT")
    assert tele["trade_builder_reached"] is True
    assert tele["candidate_family_considered"] is None
    assert tele["no_candidate_constructed"] is True
    assert tele["qual_fail_codes"] == ["vwap"]
    assert tele["qual_fail_reasons_raw"] == ["price below vwap setup"]


def test_strategy_gate_uses_current_cycle_indicator_truth_and_exposes_indicator_source(monkeypatch):
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_candidate_stream_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_decision_stream_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_decision_write_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "audit_append", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "handle_post_decision_side_effects", lambda *args, **kwargs: None)

    now_epoch = time.time()
    market_data_list = [
        {
            "symbol": "NIFTY",
            "instrument": "OPT",
            "timestamp": now_epoch,
            "market_open": True,
            "ltp_ts_epoch": now_epoch,
            "ltp": 25000.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "ohlc_bars_count": 60,
            "warmup_min_bars": 50,
            "indicator_last_update_epoch": now_epoch,
            "compute_indicators_error": "",
            "vwap": 25010.0,
            "rsi": 61.0,
            "ema": 25002.0,
            "atr": 110.0,
            "indicators_ok": False,
            "indicator_missing_inputs": ["rsi"],
        }
    ]
    indicator_report = build_live_indicator_readiness_report(
        market_data_list,
        now_epoch=now_epoch,
        warmup_min_bars=50,
        source="orchestrator_live_indicator_readiness_v2",
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch._cycle_market_snapshot_by_symbol = {}
    orch._apply_cycle_indicator_readiness_truth(market_data_list, indicator_report)

    class _Gatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            assert market_data["indicators_ok"] is True
            assert market_data["indicator_readiness_ready"] is True
            assert market_data["indicator_source"] == "orchestrator_live_indicator_readiness_v2"
            assert market_data["indicator_readiness_source"] == "orchestrator_live_indicator_readiness_v2"
            assert market_data["indicator_missing_inputs"] == []
            return GateResult(True, "DEFINED_RISK", ["paper_neutral_routed"])

    orch.gatekeeper = _Gatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    gate = orch._strategy_gate_for_symbol(market_data_list[0])

    tele = gate.facts.get("strategy_telemetry", gate.facts)
    assert gate.allowed is True
    assert tele["indicator_source"] == "orchestrator_live_indicator_readiness_v2"
    assert tele["indicator_readiness_source"] == "orchestrator_live_indicator_readiness_v2"
    assert tele["indicators_ok"] is True
    assert tele["indicator_missing_inputs"] == []
    assert tele["indicator_readiness_ready"] is True
    assert str(tele["predicate_node"]).endswith("N8_STRATEGY_SELECT")


def test_strategy_gate_still_rejects_when_current_cycle_indicator_truth_is_stale_or_missing(monkeypatch):
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_candidate_stream_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_decision_stream_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "append_decision_write_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "audit_append", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "handle_post_decision_side_effects", lambda *args, **kwargs: None)

    now_epoch = time.time()
    market_data_list = [
        {
            "symbol": "SENSEX",
            "instrument": "OPT",
            "timestamp": now_epoch,
            "market_open": True,
            "ltp_ts_epoch": now_epoch,
            "ltp": 72000.0,
            "quote_ok": True,
            "primary_regime": "TREND",
            "ohlc_bars_count": 60,
            "warmup_min_bars": 50,
            "indicator_last_update_epoch": now_epoch - 9999.0,
            "compute_indicators_error": "",
            "vwap": 72010.0,
            "rsi": 52.0,
            "ema": 71995.0,
            "atr": 180.0,
            "indicators_ok": False,
            "indicator_missing_inputs": [],
        }
    ]
    indicator_report = build_live_indicator_readiness_report(
        market_data_list,
        now_epoch=now_epoch,
        warmup_min_bars=50,
        source="orchestrator_live_indicator_readiness_v2",
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch._cycle_market_snapshot_by_symbol = {}
    orch._apply_cycle_indicator_readiness_truth(market_data_list, indicator_report)

    class _Gatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            assert market_data["indicators_ok"] is False
            assert market_data["indicator_readiness_ready"] is False
            assert market_data["indicator_source"] == "orchestrator_live_indicator_readiness_v2"
            return GateResult(False, None, ["NO_STRATEGY_QUALIFIED"])

    orch.gatekeeper = _Gatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    gate = orch._strategy_gate_for_symbol(market_data_list[0])

    assert gate.allowed is False
    assert "INDICATORS_MISSING" in gate.reasons
    assert gate.facts["strategy_telemetry"]["indicator_source"] == "orchestrator_live_indicator_readiness_v2"
    assert gate.facts["strategy_telemetry"]["indicator_readiness_source"] == "orchestrator_live_indicator_readiness_v2"
    assert gate.facts["strategy_telemetry"]["indicators_ok"] is False


def test_nonlive_no_strategy_gate_is_softened_for_candidate_fallback(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)

    orch = Orchestrator.__new__(Orchestrator)

    market_data = {
        "symbol": "NIFTY",
        "market_context": {"execution_mode": "SIM", "market_open": True},
        "market_open": True,
    }
    gate = GateResult(False, None, ["NO_STRATEGY_QUALIFIED"])

    assert orch._should_soften_nonlive_no_strategy_gate(market_data, gate) is True


def test_live_no_strategy_gate_is_not_softened(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)

    orch = Orchestrator.__new__(Orchestrator)

    market_data = {
        "symbol": "NIFTY",
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "market_open": True,
    }
    gate = GateResult(False, None, ["NO_STRATEGY_QUALIFIED"])

    assert orch._should_soften_nonlive_no_strategy_gate(market_data, gate) is False


def test_warmup_state_blocks_strategy_evaluation(monkeypatch):
    emitted = []
    evaluate_called = {"count": 0}

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            evaluate_called["count"] += 1
            return GateResult(True, "DEFINED_RISK", [])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted.append(record))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    snapshot = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "timestamp": 1,
        "market_open": True,
        "ltp_ts_epoch": 1,
        "ltp": 25000.0,
        "quote_ok": True,
        "primary_regime": "TREND",
        "system_state": "WARMUP",
        "warmup_reasons": ["bars_below_min:1m:10/50", "indicator_last_update_missing"],
        "indicators_ok": False,
        "indicators_age_sec": 1e9,
        "ohlc_bars_count": 10,
        "warmup_min_bars": 50,
    }
    gate = orch._strategy_gate_for_symbol(snapshot)

    assert gate.allowed is False
    assert evaluate_called["count"] == 0
    assert "WARMUP_INCOMPLETE" in gate.reasons
    warmup_rows = [row for row in emitted if row.get("stage") == NODE_N3_WARMUP_DONE and row.get("symbol") == "NIFTY"]
    assert warmup_rows[0]["symbol"] == "NIFTY"


def test_warmup_clears_when_min_bars_reached(monkeypatch):
    emitted = []
    evaluate_called = {"count": 0}

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            evaluate_called["count"] += 1
            return GateResult(True, "DEFINED_RISK", [])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted.append(record))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    warmup_snapshot = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "timestamp": 1,
        "market_open": True,
        "ltp_ts_epoch": 1,
        "ltp": 25000.0,
        "quote_ok": True,
        "primary_regime": "TREND",
        "system_state": "WARMUP",
        "warmup_reasons": ["bars_below_min:1m:20/50"],
    }
    blocked = orch._strategy_gate_for_symbol(warmup_snapshot)
    assert blocked.allowed is False
    assert evaluate_called["count"] == 0

    # Simulate next cycle after warmup contract is satisfied.
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}
    ready_snapshot = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "timestamp": 2,
        "market_open": True,
        "ltp_ts_epoch": 2,
        "ltp": 25010.0,
        "quote_ok": True,
        "primary_regime": "TREND",
        "system_state": "READY",
        "warmup_reasons": [],
        "indicators_ok": True,
        "indicators_age_sec": 0.2,
        "ohlc_bars_count": 55,
        "warmup_min_bars": 50,
    }
    allowed = orch._strategy_gate_for_symbol(ready_snapshot)
    assert allowed.allowed is True
    assert evaluate_called["count"] == 1
    warmup_rows = [row for row in emitted if row.get("stage") == NODE_N3_WARMUP_DONE and row.get("symbol") == "NIFTY"]
    strategy_rows = [row for row in emitted if row.get("stage") == NODE_N9_FINAL_DECISION and row.get("symbol") == "NIFTY"]
    assert warmup_rows[0]["symbol"] == "NIFTY"
    assert strategy_rows[0]["symbol"] == "NIFTY"


def test_blocked_candidate_emits_decision_evaluated(monkeypatch):
    emitted_gate_rows = []
    decision_stream_rows = []
    candidate_stream_rows = []

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            return GateResult(True, "DEFINED_RISK", [])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted_gate_rows.append(record))
    monkeypatch.setattr(orchestrator_module, "append_decision_stream_event", lambda payload, desk_id=None: decision_stream_rows.append(dict(payload)))
    monkeypatch.setattr(orchestrator_module, "append_candidate_stream_event", lambda payload, desk_id=None: candidate_stream_rows.append(dict(payload)))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    snapshot = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "timestamp": 1,
        "market_open": True,
        "ltp_ts_epoch": 1,
        "ltp": 25000.0,
        "quote_ok": True,
        "primary_regime": "TREND",
        "system_state": "WARMUP",
        "warmup_reasons": ["bars_below_min:1m:10/50"],
        "indicators_ok": False,
        "indicators_age_sec": 1e9,
    }
    gate = orch._strategy_gate_for_symbol(snapshot)

    assert gate.allowed is False
    evaluated = [row for row in decision_stream_rows if row.get("event_type") == "decision_evaluated"]
    blocked = [row for row in decision_stream_rows if row.get("event_type") == "decision_blocked"]
    assert candidate_stream_rows[0]["symbol"] == "NIFTY"
    assert evaluated[0]["symbol"] == "NIFTY"
    assert blocked[0]["symbol"] == "NIFTY"
    assert evaluated[0].get("candidate_id")
    assert evaluated[0].get("allowed") is False
    assert str(evaluated[0].get("decision_stage") or "") == NODE_N3_WARMUP_DONE


def test_decision_stream_write_failure_is_captured(monkeypatch, tmp_path):
    emitted_gate_rows = []

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            return GateResult(True, "DEFINED_RISK", [])

    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted_gate_rows.append(record))
    monkeypatch.setattr(orchestrator_module, "append_candidate_stream_event", lambda payload, desk_id=None: dict(payload))

    def _raise_non_serializable(*args, **kwargs):
        raise TypeError("Object of type NonSerializable is not JSON serializable")

    monkeypatch.setattr(orchestrator_module, "append_decision_stream_event", _raise_non_serializable)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    snapshot = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "timestamp": 1,
        "market_open": True,
        "ltp_ts_epoch": 1,
        "ltp": 25000.0,
        "quote_ok": True,
        "primary_regime": "TREND",
        "system_state": "READY",
        "warmup_reasons": [],
        "indicators_ok": True,
        "indicators_age_sec": 0.1,
    }

    gate = orch._strategy_gate_for_symbol(snapshot)
    assert gate.allowed is True

    err_path = decision_write_error_path("TEST")
    assert err_path.exists()
    rows = [json.loads(line) for line in err_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    last = rows[-1]
    assert last.get("stream") == "decisions_stream"
    assert last.get("exception_type") == "TypeError"
    assert "not JSON serializable" in str(last.get("exception_message") or "")
