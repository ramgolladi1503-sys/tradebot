from config import config as cfg
import core.orchestrator as orchestrator_module
from core.decision_dag import (
    NODE_N3_WARMUP_DONE,
    NODE_N9_FINAL_DECISION,
)
from core.orchestrator import Orchestrator
from core.strategy_gatekeeper import GateResult


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

    assert len(emitted) == 3
    rows_by_symbol = {row.get("symbol"): row for row in emitted}
    assert rows_by_symbol["NIFTY"]["stage"] == NODE_N3_WARMUP_DONE
    assert rows_by_symbol["BANKNIFTY"]["stage"] == NODE_N9_FINAL_DECISION
    assert rows_by_symbol["SENSEX"]["stage"] == NODE_N9_FINAL_DECISION
    assert len(evaluate_calls) == 2
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

    assert len(cycle_snapshots) == 1
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
    assert len(rows) == 1
    assert rows[0]["stage"] == NODE_N3_WARMUP_DONE
    assert rows[0]["indicators_ok"] is False
    assert float(rows[0]["indicators_age_sec"]) == 10.0


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
    assert len(warmup_rows) == 1


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
    assert len(warmup_rows) == 1
    assert len(strategy_rows) == 1
