from __future__ import annotations

import pandas as pd
import pytest

from research.liquidity_exhaustion_depth_readiness_v2.depth_readiness import (
    DepthReadinessContract,
    audit_quote_frame,
    detect_depth_capability,
    parse_quote_timestamps,
    summarize_depth_readiness,
)


def _quote_frame(*, with_sizes: bool = True, crossed: bool = False) -> pd.DataFrame:
    ts = pd.date_range("2026-07-09 03:45:00", periods=6, freq="1s", tz="UTC")
    bid = [100.0] * 6
    ask = [100.2] * 6
    if crossed:
        bid[2] = 100.3
    frame = pd.DataFrame(
        {
            "ts": (ts.astype("int64") // 1_000_000).astype("int64"),
            "token": [123] * 6,
            "symbol": ["NIFTY26JUL25000CE"] * 6,
            "ltp": [100.1] * 6,
            "bid": bid,
            "ask": ask,
        }
    )
    if with_sizes:
        frame["bid_qty"] = [100, 120, 140, 130, 110, 100]
        frame["ask_qty"] = [90, 80, 70, 75, 85, 95]
    return frame


def test_timestamp_parser_supports_epoch_milliseconds() -> None:
    frame = _quote_frame()
    parsed = parse_quote_timestamps(frame["ts"])
    assert str(parsed.dt.tz) == "UTC"
    assert parsed.iloc[0] == pd.Timestamp("2026-07-09 03:45:00", tz="UTC")


def test_depth_capability_requires_both_sides_or_structured_depth() -> None:
    with_sizes = detect_depth_capability(_quote_frame(with_sizes=True).columns)
    assert with_sizes["supports_imbalance_or_replenishment"] is True
    without_sizes = detect_depth_capability(_quote_frame(with_sizes=False).columns)
    assert without_sizes["supports_imbalance_or_replenishment"] is False


def test_quote_frame_audit_reports_gaps_spreads_and_crossed_markets() -> None:
    audit = audit_quote_frame(_quote_frame(with_sizes=True, crossed=True), source="x", date_key="20260709")
    assert audit["row_count"] == 6
    assert audit["median_gap_seconds"] == pytest.approx(1.0)
    assert audit["p95_gap_seconds"] == pytest.approx(1.0)
    assert audit["crossed_market_count"] == 1
    assert audit["depth_capability"]["supports_imbalance_or_replenishment"] is True


def test_readiness_fails_closed_for_one_session() -> None:
    audit = audit_quote_frame(_quote_frame(with_sizes=True), source="x", date_key="20260709")
    contract = DepthReadinessContract(
        minimum_development_sessions=2,
        minimum_future_holdout_sessions=1,
        minimum_session_span_minutes=0.01,
        maximum_median_gap_seconds=2.0,
        maximum_p95_gap_seconds=2.0,
    )
    summary = summarize_depth_readiness([audit], candle_dates={"20260709"}, contract=contract)
    assert summary["classification"] == "DEPTH_DATA_NOT_READY_FOR_EXHAUSTION_DISCOVERY"
    assert any(blocker.startswith("DEVELOPMENT_SESSION_COUNT_BELOW_MINIMUM") for blocker in summary["blockers"])


def test_readiness_passes_when_all_preregistered_requirements_hold() -> None:
    first = audit_quote_frame(_quote_frame(with_sizes=True), source="x", date_key="20260709")
    second = audit_quote_frame(_quote_frame(with_sizes=True), source="y", date_key="20260710")
    contract = DepthReadinessContract(
        minimum_development_sessions=2,
        minimum_future_holdout_sessions=1,
        minimum_session_span_minutes=0.01,
        maximum_median_gap_seconds=2.0,
        maximum_p95_gap_seconds=2.0,
    )
    summary = summarize_depth_readiness(
        [first, second],
        candle_dates={"20260709", "20260710"},
        future_holdout_sessions_available=1,
        contract=contract,
    )
    assert summary["classification"] == "DEPTH_DATA_READY_FOR_EXHAUSTION_DISCOVERY"
    assert summary["blockers"] == []


def test_readiness_requires_unseen_holdout_sessions() -> None:
    first = audit_quote_frame(_quote_frame(with_sizes=True), source="x", date_key="20260709")
    second = audit_quote_frame(_quote_frame(with_sizes=True), source="y", date_key="20260710")
    contract = DepthReadinessContract(
        minimum_development_sessions=2,
        minimum_future_holdout_sessions=1,
        minimum_session_span_minutes=0.01,
        maximum_median_gap_seconds=2.0,
        maximum_p95_gap_seconds=2.0,
    )
    summary = summarize_depth_readiness(
        [first, second],
        candle_dates={"20260709", "20260710"},
        future_holdout_sessions_available=0,
        contract=contract,
    )
    assert summary["classification"] == "DEPTH_DATA_NOT_READY_FOR_EXHAUSTION_DISCOVERY"
    assert any(
        blocker.startswith("FUTURE_UNSEEN_HOLDOUT_SESSION_COUNT_BELOW_MINIMUM")
        for blocker in summary["blockers"]
    )


def test_missing_required_columns_fail_closed() -> None:
    frame = _quote_frame().drop(columns=["ask"])
    with pytest.raises(ValueError, match="missing quote columns"):
        audit_quote_frame(frame, source="x", date_key="20260709")
