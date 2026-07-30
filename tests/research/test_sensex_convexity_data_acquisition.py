from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.sensex_late_session_convexity_v1.data_acquisition import (
    classify_expiry_regime,
    constituent_coverage,
    derive_five_minute,
    future_dependent_strike_selection,
    normalize_candles,
    normalize_ist_timestamp,
    parse_option_symbol,
    recover_option_registry,
    sha256_file,
)


def test_timestamp_normalisation_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone-naive"):
        normalize_ist_timestamp("2026-07-01T09:15:00")
    assert str(normalize_ist_timestamp("2026-07-01T03:45:00+00:00").tz) == "Asia/Kolkata"


def test_exact_duplicate_handling_and_conflicting_duplicate_detection() -> None:
    rows = [
        {"timestamp": "2026-07-01T09:15:00+05:30", "instrument_token": 265, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
        {"timestamp": "2026-07-01T09:15:00+05:30", "instrument_token": 265, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
        {"timestamp": "2026-07-01T09:16:00+05:30", "instrument_token": 265, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
        {"timestamp": "2026-07-01T09:16:00+05:30", "instrument_token": 265, "open": 9, "high": 9, "low": 9, "close": 9, "volume": 10},
    ]
    frame, conflicts = normalize_candles(rows)
    assert len(frame) == 3
    assert conflicts and conflicts[0]["rows"] == 2


def test_one_minute_to_five_minute_aggregation_session_anchored() -> None:
    rows = []
    for idx in range(5):
        rows.append({"timestamp": f"2026-07-01T09:{15 + idx:02d}:00+05:30", "instrument_token": 265, "open": 100 + idx, "high": 105 + idx, "low": 95 - idx, "close": 101 + idx, "volume": 10 + idx, "oi": idx})
    frame, _ = normalize_candles(rows)
    five = derive_five_minute(frame)
    assert len(five) == 1
    assert five.iloc[0]["open"] == 100
    assert five.iloc[0]["high"] == 109
    assert five.iloc[0]["low"] == 91
    assert five.iloc[0]["close"] == 105
    assert five.iloc[0]["volume"] == 60
    assert five.iloc[0]["oi"] == 4
    assert five.iloc[0]["bar_label"] == "bar_open"


def test_strike_parsing_and_ce_pe_classification() -> None:
    parsed = parse_option_symbol("SENSEX26JUL80500CE")
    assert parsed == {"underlying": "SENSEX", "strike": 80500, "option_type": "CE"}
    assert parse_option_symbol("SENSEX26JUL79000PE")["option_type"] == "PE"


def test_expiry_regime_and_holiday_shifted_classification() -> None:
    assert classify_expiry_regime(pd.Timestamp("2024-07-05").date()) == "FRIDAY_EXPIRY_REGIME"
    assert classify_expiry_regime(pd.Timestamp("2025-09-02").date()) == "TUESDAY_EXPIRY_REGIME"
    assert classify_expiry_regime(pd.Timestamp("2026-07-30").date()) == "THURSDAY_EXPIRY_REGIME"
    assert classify_expiry_regime(pd.Timestamp("2026-07-29").date()) == "HOLIDAY_SHIFTED_OR_EXCEPTIONAL"


def test_constituent_coverage_calculation() -> None:
    expected = pd.DataFrame({"trading_symbol": ["A", "B", "C"], "weight": [0.5, 0.3, 0.2]})
    available = pd.DataFrame({"tradingsymbol": ["A", "C"]})
    out = constituent_coverage(expected, available)
    assert out["available_constituents"] == 2
    assert out["missing_constituents"] == ["B"]
    assert out["weight_coverage"] == pytest.approx(0.7)


def test_reject_future_dependent_strike_selection() -> None:
    assert future_dependent_strike_selection("2026-07-01T14:15:00+05:30", "2026-07-01T15:20:00+05:30")
    assert not future_dependent_strike_selection("2026-07-01T14:15:00+05:30", "2026-07-01T14:15:00+05:30")


def test_manifest_hashing(tmp_path: Path) -> None:
    path = tmp_path / "source.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert sha256_file(path) == "492d5ea496056f1a6a6592241032fab764c321596317930b4fa0e1e8bc3b7470"


def test_token_registry_parsing_from_instrument_master(tmp_path: Path) -> None:
    registry = tmp_path / "instruments.json"
    registry.write_text(
        '[{"instrument_token": 123, "exchange": "BFO", "tradingsymbol": "SENSEX26JUL80500CE", "expiry": "2026-07-31", "lot_size": 10, "tick_size": 0.05}]',
        encoding="utf-8",
    )
    records = [{"absolute_path": str(registry), "sha256": sha256_file(registry)}]
    frame = recover_option_registry(records)
    assert len(frame) == 1
    assert frame.iloc[0]["instrument_token"] == 123
    assert frame.iloc[0]["option_type"] == "CE"
    assert frame.iloc[0]["confidence"] == "HIGH"
