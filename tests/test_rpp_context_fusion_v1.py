from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from research.rpp_context_fusion_v1.fusion import (
    FusionConfig,
    build_constituent_context,
    enrich_events_with_context,
    evaluate_fusion,
    load_governed_panel,
    run_experiment,
)


def _prices(ts, closes):
    df = pd.DataFrame({"timestamp": ts, "close": closes})
    df["session"] = df["timestamp"].dt.date
    return df


def test_exact_five_minute_breadth_is_causal_and_eligible():
    ts = pd.date_range("2026-01-02 09:15", periods=2, freq="5min", tz="Asia/Kolkata")
    rows = []
    for i in range(40):
        symbol = f"C{i:02d}"
        rows.append({"timestamp": ts[0], "symbol": symbol, "close": 100.0 + i})
        rows.append({"timestamp": ts[1], "symbol": symbol, "close": 101.0 + i})
    rows += [
        {"timestamp": ts[0], "symbol": "NIFTY", "close": 20000.0},
        {"timestamp": ts[1], "symbol": "NIFTY", "close": 20020.0},
    ]
    panel = pd.DataFrame(rows)
    panel["session"] = panel["timestamp"].dt.date
    prices = _prices(ts, [20000.0, 20020.0])

    context = build_constituent_context(panel, prices, FusionConfig())
    c = context.loc[context["timestamp"] == ts[1]].iloc[0]
    assert c["constituent_count"] == 40
    assert c["exact_return_count"] == 40
    assert c["exact_return_coverage"] == 1.0
    assert c["breadth"] == 1.0
    assert c["nifty_context_return_bps"] > 0

    event = pd.DataFrame([{"timestamp": ts[1], "session": ts[1].date(), "signal": 1}])
    enriched = enrich_events_with_context(event, context, FusionConfig())
    assert bool(enriched.iloc[0]["fusion_eligible"])


def test_breadth_must_align_with_rpp_direction():
    ts = pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata")
    context = pd.DataFrame([
        {
            "timestamp": ts,
            "session": ts.date(),
            "constituent_count": 50,
            "exact_return_count": 50,
            "breadth": 0.8,
            "constituent_median_return_bps": 3.0,
            "constituent_dispersion_bps": 8.0,
            "exact_return_coverage": 1.0,
            "nifty_context_return_bps": 2.0,
        }
    ])
    event = pd.DataFrame([{"timestamp": ts, "session": ts.date(), "signal": -1}])
    enriched = enrich_events_with_context(event, context, FusionConfig())
    assert not bool(enriched.iloc[0]["fusion_eligible"])


def test_lagged_control_uses_context_from_thirty_minutes_earlier():
    t0 = pd.Timestamp("2026-01-02 09:30", tz="Asia/Kolkata")
    t1 = pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata")
    context = pd.DataFrame([
        {
            "timestamp": t0,
            "session": t0.date(),
            "constituent_count": 50,
            "exact_return_count": 50,
            "breadth": 0.8,
            "constituent_median_return_bps": 4.0,
            "constituent_dispersion_bps": 8.0,
            "exact_return_coverage": 1.0,
            "nifty_context_return_bps": 3.0,
        },
        {
            "timestamp": t1,
            "session": t1.date(),
            "constituent_count": 50,
            "exact_return_count": 50,
            "breadth": -0.8,
            "constituent_median_return_bps": -4.0,
            "constituent_dispersion_bps": 8.0,
            "exact_return_coverage": 1.0,
            "nifty_context_return_bps": -3.0,
        },
    ])
    event = pd.DataFrame([{"timestamp": t1, "session": t1.date(), "signal": 1}])
    enriched = enrich_events_with_context(event, context, FusionConfig())
    assert not bool(enriched.iloc[0]["fusion_eligible"])
    assert bool(enriched.iloc[0]["lagged_context_control_eligible"])
    assert enriched.iloc[0]["lagged_breadth"] == 0.8


def test_low_constituent_coverage_blocks_fusion():
    ts = pd.Timestamp("2026-01-02 10:00", tz="Asia/Kolkata")
    context = pd.DataFrame([
        {
            "timestamp": ts,
            "session": ts.date(),
            "constituent_count": 50,
            "exact_return_count": 20,
            "breadth": 1.0,
            "constituent_median_return_bps": 4.0,
            "constituent_dispersion_bps": 8.0,
            "exact_return_coverage": 0.4,
            "nifty_context_return_bps": 3.0,
        }
    ])
    event = pd.DataFrame([{"timestamp": ts, "session": ts.date(), "signal": 1}])
    enriched = enrich_events_with_context(event, context, FusionConfig())
    assert not bool(enriched.iloc[0]["fusion_eligible"])


def test_governed_special_session_is_removed(tmp_path):
    p = tmp_path / "panel.csv"
    pd.DataFrame([
        {"timestamp": "2024-01-20 10:00:00+05:30", "symbol": "NIFTY", "close": 100.0},
        {"timestamp": "2024-01-22 10:00:00+05:30", "symbol": "NIFTY", "close": 101.0},
    ]).to_csv(p, index=False)
    out = load_governed_panel(p)
    assert len(out) == 1
    assert str(out.iloc[0]["session"]) == "2024-01-22"


def _sessions(n: int):
    d0 = date(2024, 1, 1)
    return [d0 + timedelta(days=i) for i in range(n)]


def test_evaluator_does_not_fake_pass_negative_net_results():
    sessions = _sessions(315)
    rows = []
    for s in sessions:
        rows.append(
            {
                "session": s,
                "fusion_eligible": True,
                "lagged_context_control_eligible": True,
                "signed_15m_net_bps": -1.0,
                "signed_15m_gross_bps": 4.0,
                "event_type": "BULLISH_REJECTED",
                "interaction_density": 0.8,
                "breadth": 0.8,
            }
        )
    result = evaluate_fusion(pd.DataFrame(rows), sessions, FusionConfig())
    assert result["verdict"] == "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE"
    assert "MEAN_AFTER_COST_PROXY_NOT_POSITIVE" in result["blockers"]
    assert "SESSION_BOOTSTRAP_CI_NOT_POSITIVE" in result["blockers"]


def test_evaluator_can_pass_only_when_all_frozen_gates_are_satisfied():
    sessions = _sessions(315)
    rows = []
    for s in sessions:
        rows.append(
            {
                "session": s,
                "fusion_eligible": True,
                "lagged_context_control_eligible": False,
                "signed_15m_net_bps": 2.0,
                "signed_15m_gross_bps": 7.0,
                "event_type": "BULLISH_REJECTED",
                "interaction_density": 0.8,
                "breadth": 0.8,
            }
        )
        rows.append(
            {
                "session": s,
                "fusion_eligible": False,
                "lagged_context_control_eligible": True,
                "signed_15m_net_bps": -2.0,
                "signed_15m_gross_bps": 3.0,
                "event_type": "BEARISH_REJECTED",
                "interaction_density": 0.8,
                "breadth": -0.8,
            }
        )
    result = evaluate_fusion(pd.DataFrame(rows), sessions, FusionConfig())
    assert result["verdict"] == "ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY"
    assert result["blockers"] == []
    assert result["uplift_bps_vs_parent_rpp"] >= 0.5
    assert result["uplift_bps_vs_lagged_context_control"] >= 0.5


def test_input_sha_mismatch_fails_before_any_backtest(tmp_path):
    p = tmp_path / "wrong.parquet"
    p.write_bytes(b"not-the-governed-corpus")
    try:
        run_experiment(p, tmp_path / "out")
    except ValueError as exc:
        assert str(exc).startswith("input_sha256_mismatch:")
    else:
        raise AssertionError("SHA mismatch must fail closed")
