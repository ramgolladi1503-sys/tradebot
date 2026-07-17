from __future__ import annotations

from agentic_research.historical.horizon_postprocess import summarize_risk_metrics


def test_equal_risk_summary_distinguishes_notional_and_r_expectancy():
    trades = [
        {
            "exit_reason": "STOP",
            "net_return_bps": -12.0,
            "gross_return_bps": -10.0,
            "risk_bps": 10.0,
            "gross_r_multiple": -1.0,
            "net_r_multiple": -1.2,
        },
        {
            "exit_reason": "TARGET",
            "net_return_bps": 5.5,
            "gross_return_bps": 7.5,
            "risk_bps": 5.0,
            "gross_r_multiple": 1.5,
            "net_r_multiple": 1.1,
        },
        {
            "exit_reason": "TARGET",
            "net_return_bps": 5.5,
            "gross_return_bps": 7.5,
            "risk_bps": 5.0,
            "gross_r_multiple": 1.5,
            "net_r_multiple": 1.1,
        },
    ]
    summary = summarize_risk_metrics(trades)
    assert summary["net_expectancy_bps"] < 0
    assert summary["net_expectancy_r"] > 0
    assert summary["reason_stats"]["STOP"]["average_risk_bps"] == 10.0
    assert summary["reason_stats"]["TARGET"]["average_risk_bps"] == 5.0


def test_reason_statistics_keep_timeout_separate_from_stop():
    trades = [
        {
            "exit_reason": "STOP",
            "net_return_bps": -7.0,
            "gross_return_bps": -5.0,
            "risk_bps": 5.0,
            "gross_r_multiple": -1.0,
            "net_r_multiple": -1.4,
        },
        {
            "exit_reason": "TIMEOUT",
            "net_return_bps": -1.0,
            "gross_return_bps": 1.0,
            "risk_bps": 5.0,
            "gross_r_multiple": 0.2,
            "net_r_multiple": -0.2,
        },
    ]
    summary = summarize_risk_metrics(trades)
    assert summary["stop_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["reason_stats"]["TIMEOUT"]["average_net_return_bps"] == -1.0
