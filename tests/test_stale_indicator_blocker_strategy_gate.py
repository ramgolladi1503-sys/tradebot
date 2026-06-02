from __future__ import annotations

import time

from config import config as cfg
import core.orchestrator as orchestrator_module
from core.decision_dag import NODE_N3_WARMUP_DONE
from core.orchestrator import Orchestrator
from core.strategy_gatekeeper import GateResult


def test_live_ready_indicator_values_do_not_get_reblocked_as_indicators_missing(monkeypatch):
    emitted: list[dict] = []
    evaluate_calls = {"count": 0}

    class _StubGatekeeper:
        def evaluate(self, market_data, mode="MAIN"):
            evaluate_calls["count"] += 1
            return GateResult(False, "DEFINED_RISK", ["cross_asset_required_stale"])

    monkeypatch.setattr(orchestrator_module, "append_gate_status", lambda record, desk_id=None: emitted.append(record))
    monkeypatch.setattr(cfg, "DESK_ID", "TEST", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.gatekeeper = _StubGatekeeper()
    orch._gate_status_cycle_seen = set()
    orch._gatekeeper_cycle_cache = {}

    current_ts = time.time()
    snapshot = {
        "symbol": "SENSEX",
        "instrument": "OPT",
        "timestamp": current_ts,
        "market_open": True,
        "ltp_ts_epoch": current_ts,
        "ltp": 72000.0,
        "bid": 71995.0,
        "ask": 72005.0,
        "quote_ok": True,
        "primary_regime": "TREND",
        "regime_probs": {"TREND": 0.8},
        "regime_entropy": 0.1,
        "indicators_ok": False,
        "indicators_age_sec": 0.1,
        "indicator_last_update_epoch": current_ts,
        "ohlc_bars_count": 60,
        "warmup_min_bars": 30,
        "vwap": 71990.0,
        "rsi": 55.0,
        "ema": 71980.0,
        "atr": 120.0,
        "unstable_reasons": [],
        "market_context": {"execution_mode": "LIVE", "market_open": True},
    }

    gate = orch._strategy_gate_for_symbol(snapshot)

    assert evaluate_calls["count"] == 1
    assert gate.allowed is False
    assert "INDICATORS_MISSING" not in list(gate.reasons or [])
    assert any(
        row.get("symbol") == "SENSEX" and row.get("stage") != NODE_N3_WARMUP_DONE
        for row in emitted
    )
