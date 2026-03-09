import pandas as pd

import dashboard.streamlit_app_runtime as runtime


def test_compute_decision_debug_metrics_uses_explicit_counts():
    trade_universe_df = pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])
    advisory_df = pd.DataFrame([{"id": "a"}, {"id": "b"}])
    decision_gate = {
        "evaluations_last_window": 9,
        "decisions_last_window": 4,
        "rows": {
            "NIFTY": {"gate_allowed": True},
            "BANKNIFTY": {"gate_allowed": False},
        },
    }

    metrics = runtime._compute_decision_debug_metrics(trade_universe_df, advisory_df, decision_gate)

    assert metrics["candidates_generated"] == 3
    assert metrics["decisions_generated"] == 9
    assert metrics["decisions_passed"] == 4
    assert metrics["advisory_rows"] == 2


def test_compute_decision_debug_metrics_falls_back_to_rows():
    trade_universe_df = pd.DataFrame([{"id": 1}])
    advisory_df = pd.DataFrame([])
    decision_gate = {
        "rows": {
            "NIFTY": {"gate_allowed": True},
            "BANKNIFTY": {"gate_allowed": False},
            "SENSEX": {"gate_allowed": False},
        }
    }

    metrics = runtime._compute_decision_debug_metrics(trade_universe_df, advisory_df, decision_gate)

    assert metrics["candidates_generated"] == 1
    assert metrics["decisions_generated"] == 3
    assert metrics["decisions_passed"] == 1
    assert metrics["advisory_rows"] == 0


def test_should_emit_decision_debug_log_interval():
    assert runtime._should_emit_decision_debug_log(0.0, 100.0, interval_sec=30.0) is True
    assert runtime._should_emit_decision_debug_log(90.0, 100.0, interval_sec=30.0) is False
    assert runtime._should_emit_decision_debug_log(70.0, 100.0, interval_sec=30.0) is True

