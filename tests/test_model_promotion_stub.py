import pandas as pd

from core.reports.promotion_report import evaluate_promotion
from scripts.run_model_promotion import decide_promotion


def test_promotion_decision_passes():
    df = pd.DataFrame({
        "ts": ["2026-01-01T10:00:00", "2026-01-02T10:00:00"],
        "filled_bool": [1, 0],
        "champion_proba": [0.6, 0.6],
        "challenger_proba": [0.55, 0.45],
        "primary_regime": ["RANGE", "RANGE"],
        "pnl_15m": [10.0, -5.0],
        "trade_id": ["T1", "T2"],
        "gatekeeper_allowed": [1, 1],
        "risk_allowed": [1, 1],
        "exec_guard_allowed": [1, 1],
    })
    report = evaluate_promotion(df, "2026-01-01", gates={"ece_bins": 5, "tail_k": 1})
    promote, reasons = decide_promotion(
        report,
        gates={"ece_max_delta": 0.05, "seg_max": 0.05, "event_seg_max": 0.01},
    )
    assert promote is True
    assert reasons == []


def test_evaluate_promotion_emits_profitability_metrics():
    df = pd.DataFrame({
        "ts": ["2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"],
        "filled_bool": [1, 0, 1],
        "champion_proba": [0.6, 0.6, 0.6],
        "challenger_proba": [0.7, 0.4, 0.65],
        "primary_regime": ["RANGE", "RANGE", "TREND"],
        "pnl_15m": [10.0, -5.0, 3.0],
        "trade_id": ["T1", "T2", "T3"],
        "gatekeeper_allowed": [1, 1, 1],
        "risk_allowed": [1, 1, 1],
        "exec_guard_allowed": [1, 1, 1],
    })

    report = evaluate_promotion(df, "2026-01-01", gates={"ece_bins": 5, "tail_k": 1})

    assert report["profitability"]["expectancy"] == 8.0 / 3.0
    assert report["profitability"]["profit_factor"] == 13.0 / 5.0
    assert "max_drawdown" in report["profitability"]
