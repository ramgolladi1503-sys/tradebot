import json

import pandas as pd

from core.reports.daily_audit import build_daily_audit
from strategies.trade_builder import TradeBuilder


def test_build_with_trace_blocked_has_reason_code():
    builder = TradeBuilder()
    trade, trace = builder.build_with_trace(
        {
            "run_id": "RUN-TRACE-1",
            "symbol": "NIFTY",
            "valid": False,
            "invalid_reason": "invalid_ltp",
        }
    )
    assert trade is None
    assert trace.final_decision == "BLOCKED"
    assert trace.run_id == "RUN-TRACE-1"
    assert "INVALID_LTP" in trace.reasons


def test_daily_audit_contains_decision_traces_and_config_snapshot(tmp_path):
    out_path = tmp_path / "daily_audit.json"
    day = "2026-02-10"
    df = pd.DataFrame(
        [
            {
                "ts": "2026-02-10T10:00:00+05:30",
                "gatekeeper_allowed": 1,
                "risk_allowed": 1,
                "filled_bool": 0,
                "strategy_id": "ENSEMBLE_OPT",
                "primary_regime": "TREND",
                "pnl_15m": 0.0,
            }
        ]
    )
    traces = [
        {
            "run_id": "RUN-TRACE-1",
            "symbol": "NIFTY",
            "final_decision": "BLOCKED",
            "reasons": ["INVALID_LTP"],
        }
    ]
    config_snapshot = {"MAX_OPTION_QUOTE_AGE_SEC": 8, "REQUIRE_LIVE_QUOTES": True}
    build_daily_audit(
        df,
        day,
        out_path,
        decision_traces=traces,
        config_snapshot=config_snapshot,
    )
    payload = json.loads(out_path.read_text())
    assert payload.get("decision_traces") == traces
    assert payload.get("config_snapshot") == config_snapshot
