from __future__ import annotations

from pathlib import Path

import pandas as pd

from agentic_research.historical import HistoricalCampaignConfig, load_canonical_candles, run_historical_campaign, summarize_returns


def _write_sessions(path: Path, *, sessions: int, volume: float) -> list[str]:
    rows = []
    session_dates = []
    start = pd.Timestamp("2020-01-01 09:15")
    for offset in range(sessions):
        day = start + pd.Timedelta(days=offset)
        session_dates.append(day.date().isoformat())
        rows.append({
            "timestamp": day.isoformat(),
            "symbol": "NIFTY_F1",
            "open": 100.0 + offset,
            "high": 101.0 + offset,
            "low": 99.0 + offset,
            "close": 100.5 + offset,
            "volume": volume,
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    return session_dates


def test_loader_localizes_naive_aeron7_timestamps(tmp_path):
    path = tmp_path / "candles.csv"
    _write_sessions(path, sessions=2, volume=100)
    frame = load_canonical_candles(path)
    assert len(frame) == 2
    assert str(frame["timestamp"].dt.tz) == "Asia/Kolkata"


def test_zero_volume_is_invalid_for_vwap_strategy(tmp_path):
    path = tmp_path / "zero.csv"
    _write_sessions(path, sessions=3, volume=0)
    result = run_historical_campaign(
        path,
        tmp_path / "out",
        source_repository="fixture",
        source_commit="fixture",
        config=HistoricalCampaignConfig(minimum_sessions=1),
    )
    assert result["verdict"] == "INVALID_DUE_TO_DATA"
    assert result["blockers"] == ["zero_volume_dataset_invalid_for_vwap_strategy"]


def test_fixed_positive_trade_evidence_can_only_reach_structural_candidate(tmp_path, monkeypatch):
    path = tmp_path / "positive.csv"
    sessions = _write_sessions(path, sessions=30, volume=100)

    def fake_generate_trades(frame, config):
        trades = [
            {"session_date": session, "gross_return_bps": 12.0, "net_return_bps": 10.0}
            for session in sessions
        ]
        return trades, {"signals_total": len(trades), "trades_total": len(trades)}

    monkeypatch.setattr("agentic_research.historical.campaign.generate_trades", fake_generate_trades)
    config = HistoricalCampaignConfig(
        minimum_sessions=20,
        minimum_total_trades=10,
        minimum_holdout_trades=3,
        minimum_holdout_profit_factor=1.0,
        minimum_positive_wfa_fraction=0.5,
        maximum_top_five_session_positive_share=1.0,
        train_sessions=10,
        validation_sessions=4,
        step_sessions=4,
        boundary_purge_sessions=0,
    )
    result = run_historical_campaign(
        path,
        tmp_path / "out",
        source_repository="fixture",
        source_commit="fixture",
        config=config,
    )
    assert result["verdict"] == "STRUCTURAL_EDGE_CANDIDATE"
    assert result["options_execution_certified"] is False
    assert result["claim_scope"] == "underlying_futures_structural_research_only"


def test_return_summary_reconciles():
    summary = summarize_returns([4.0, -1.0, 2.0])
    assert summary["trades"] == 3
    assert summary["net_pnl_bps"] == 5.0
    assert summary["profit_factor"] == 6.0
