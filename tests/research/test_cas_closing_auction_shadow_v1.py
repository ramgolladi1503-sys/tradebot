from pathlib import Path
import importlib.util
import sys

import pandas as pd
import pytest

MODULE = Path(__file__).parents[2] / "scripts" / "run_cas_closing_auction_shadow_v1.py"
spec = importlib.util.spec_from_file_location("cas_shadow", MODULE)
cas = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cas
assert spec.loader is not None
spec.loader.exec_module(cas)


def test_phase_boundaries_are_explicit():
    contract = cas.CasWindowContract()
    values = {
        "2026-08-04 15:14:59+05:30": "NORMAL_LATE_SESSION",
        "2026-08-04 15:15:00+05:30": "CAS_REFERENCE_TRANSITION",
        "2026-08-04 15:20:00+05:30": "CAS_ORDER_DISCOVERY",
        "2026-08-04 15:30:00+05:30": "CAS_MATCHING",
        "2026-08-04 15:35:00+05:30": "DERIVATIVE_CONVERGENCE",
    }
    for timestamp, expected in values.items():
        assert cas.classify_phase(pd.Timestamp(timestamp), contract) == expected


def test_numeric_epoch_seconds_are_not_treated_as_nanoseconds():
    frame = pd.DataFrame(
        {
            "ts": [1785749455.0],
            "instrument_key": ["NSE_INDEX|Nifty 50"],
            "ltp": [24500.0],
        }
    )
    normalized = cas.normalize_ticks(frame)
    assert normalized.timestamp.iloc[0].year == 2026
    assert normalized.timestamp.iloc[0].hour == 15


def test_exact_index_identity_rejects_option_substring():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-08-04 15:15:00+05:30"]),
            "symbol": ["NIFTY 24600 CE 04 AUG 26"],
            "price": [40.0],
        }
    )
    with pytest.raises(ValueError, match="exact_nifty_index_identity_not_found"):
        cas.build_index_timeline(frame, cas.CasWindowContract())


def test_exact_index_selected_among_option_rows():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-08-04 15:15:00+05:30",
                    "2026-08-04 15:14:00+05:30",
                    "2026-08-04 15:15:00+05:30",
                ]
            ),
            "symbol": [
                "NIFTY 24600 CE 04 AUG 26",
                "NSE_INDEX|Nifty 50",
                "NSE_INDEX|Nifty 50",
            ],
            "price": [40.0, 24400.0, 24410.0],
        }
    )
    timeline = cas.build_index_timeline(frame, cas.CasWindowContract())
    assert set(timeline.symbol) == {"NSE_INDEX|Nifty 50"}


def test_nifty_timeline_anchors_to_last_pre_1515_price():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-08-04 15:14:00+05:30",
                    "2026-08-04 15:15:00+05:30",
                    "2026-08-04 15:20:00+05:30",
                ]
            ),
            "symbol": ["NIFTY 50"] * 3,
            "price": [24400.0, 24410.0, 24500.0],
        }
    )
    timeline = cas.build_index_timeline(frame, cas.CasWindowContract())
    assert timeline.iloc[0].return_from_1515_bps == 0.0
    assert timeline.iloc[-1].return_from_1515_bps > 0.0


def test_constituent_tick_breadth_detects_concentration():
    rows = []
    for index in range(40):
        symbol = f"NSE_EQ|S{index:02d}"
        end = 120.0 if index < 3 else 100.1
        rows.extend(
            [
                {
                    "receive_wall_ts_utc": "2026-08-04T09:44:59Z",
                    "instrument_key": symbol,
                    "ltp": 100.0,
                },
                {
                    "receive_wall_ts_utc": "2026-08-04T10:00:00Z",
                    "instrument_key": symbol,
                    "ltp": end,
                },
            ]
        )
    result = cas.constituent_breadth(pd.DataFrame(rows), cas.CasWindowContract())
    assert result["available"] is True
    assert result["constituent_count"] == 40
    assert result["top3_absolute_move_share"] > 0.65
    assert result["broad_move"] is False


def test_constituent_tick_breadth_counts_direction():
    rows = []
    for index in range(40):
        symbol = f"NSE_EQ|S{index:02d}"
        end = 101.0 if index < 35 else 99.0
        rows.extend(
            [
                {
                    "receive_wall_ts_utc": "2026-08-04T09:44:59Z",
                    "instrument_key": symbol,
                    "ltp": 100.0,
                },
                {
                    "receive_wall_ts_utc": "2026-08-04T10:00:00Z",
                    "instrument_key": symbol,
                    "ltp": end,
                },
            ]
        )
    result = cas.constituent_breadth(pd.DataFrame(rows), cas.CasWindowContract())
    assert result["positive_count"] == 35
    assert result["negative_count"] == 5


def test_contract_preserves_derivative_close_boundary():
    assert cas.CasWindowContract().derivative_end == "15:40:00"
