from config import config as cfg
import core.orchestrator as orchestrator_module
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

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    raw_market_data = [
        {"symbol": "NIFTY", "instrument": "OPT", "timestamp": 1, "indicators_ok": True, "indicators_age_sec": 1.0},
        {"symbol": "NIFTY", "instrument": "OPT", "timestamp": 2, "indicators_ok": False, "indicators_age_sec": 999.0},
        {"symbol": "BANKNIFTY", "instrument": "OPT", "timestamp": 1, "indicators_ok": True, "indicators_age_sec": 1.0},
        {"symbol": "SENSEX", "instrument": "OPT", "timestamp": 1, "indicators_ok": True, "indicators_age_sec": 1.0},
    ]
    cycle_snapshots = orch._build_cycle_market_data(raw_market_data)

    # Simulate multiple call sites in the same cycle.
    for snap in cycle_snapshots:
        orch._strategy_gate_for_symbol(snap)
        conflict_view = dict(snap)
        conflict_view["indicators_ok"] = not bool(snap.get("indicators_ok"))
        orch._strategy_gate_for_symbol(conflict_view)

    strategy_rows = [row for row in emitted if row.get("stage") == "strategy_gate"]
    assert sorted(row.get("symbol") for row in strategy_rows) == ["BANKNIFTY", "NIFTY", "SENSEX"]
    assert len(strategy_rows) == 3
    assert len(evaluate_calls) == 3
    assert immutable_seen == [True, True, True]


def test_strategy_gate_logs_no_conflicting_indicator_values_within_cycle(monkeypatch):
    emitted = []

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            return GateResult(True, "DEFINED_RISK", [])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted.append(record))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    # Newer timestamp has indicators_ok=False and must be the canonical snapshot.
    cycle_snapshots = orch._build_cycle_market_data(
        [
            {"symbol": "NIFTY", "instrument": "OPT", "timestamp": 1, "indicators_ok": True, "indicators_age_sec": 1.0},
            {"symbol": "NIFTY", "instrument": "OPT", "timestamp": 2, "indicators_ok": False, "indicators_age_sec": 10.0},
        ]
    )

    assert len(cycle_snapshots) == 1
    # First call logs canonical snapshot.
    orch._strategy_gate_for_symbol(cycle_snapshots[0])
    # Second call with conflicting values must be ignored for this cycle.
    orch._strategy_gate_for_symbol(
        {"symbol": "NIFTY", "instrument": "OPT", "timestamp": 999, "indicators_ok": True, "indicators_age_sec": 0.0}
    )

    strategy_rows = [row for row in emitted if row.get("stage") == "strategy_gate" and row.get("symbol") == "NIFTY"]
    assert len(strategy_rows) == 1
    assert strategy_rows[0]["indicators_ok"] is False
    assert float(strategy_rows[0]["indicators_age_sec"]) == 10.0
