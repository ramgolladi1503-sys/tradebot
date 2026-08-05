from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "upstox_capture"
    / "generate_offline_datasets_v3.py"
)
spec = importlib.util.spec_from_file_location("generate_offline_datasets_v3", MODULE_PATH)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)


def utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def expiry_ms(value: str) -> int:
    return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)


def test_0730_utc_is_1300_ist_and_known_stale_gap():
    boundary = utc("2026-08-05 07:30:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "13:00:00"
    assert generator.classify_interval(boundary, 0.0) == "STALE_CARRY_FORWARD"


def test_0732_utc_is_continuous_market_not_startup():
    boundary = utc("2026-08-05 07:32:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "13:02:00"
    assert generator.classify_interval(boundary, 0.0) == "LIVE_FRESH"
    assert generator.get_market_phase(boundary) == "CONTINUOUS_MARKET"


def test_0915_utc_is_not_indian_market_open():
    boundary = utc("2026-08-05 09:15:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "14:45:00"
    assert generator.classify_interval(boundary, 0.0) == "LIVE_FRESH"


def test_after_1530_ist_is_excluded():
    boundary = utc("2026-08-05 10:01:00")
    assert generator.boundary_ist_time(boundary).isoformat() == "15:31:00"
    assert generator.classify_interval(boundary, 0.0) == "OUTSIDE_CONTINUOUS_MARKET"
    assert (
        generator.get_market_phase(boundary)
        == "POST_CLOSE_OR_DERIVATIVE_CONVERGENCE"
    )


def test_latest_complete_rows_preserves_single_source_row():
    frame = pd.DataFrame(
        [
            {
                "instrument_key": "A",
                "source_exchange_ts": 1000,
                "local_sequence": 1,
                "receive_monotonic_ns": 1,
                "ltp": 100.0,
                "volume": 10,
            },
            {
                "instrument_key": "A",
                "source_exchange_ts": 2000,
                "local_sequence": 2,
                "receive_monotonic_ns": 2,
                "ltp": 101.0,
                "volume": None,
            },
        ]
    )
    latest = generator._latest_complete_rows(frame, 2000).iloc[0]
    assert latest["ltp"] == 101.0
    assert pd.isna(latest["volume"])


def test_parse_expiry_accepts_milliseconds_and_iso():
    expected = pd.Timestamp("2026-08-25", tz="UTC")
    assert generator.parse_expiry_utc(expiry_ms("2026-08-25")) == expected
    assert generator.parse_expiry_utc(str(expiry_ms("2026-08-25"))) == expected
    assert generator.parse_expiry_utc("2026-08-25") == expected


def test_front_future_uses_nearest_nonexpired_expiry_not_key_order():
    frame = pd.DataFrame(
        [
            {
                "instrument_type": "FUT",
                "instrument_key": "NSE_FO|00001",
                "expiry": expiry_ms("2026-10-27"),
            },
            {
                "instrument_type": "FUT",
                "instrument_key": "NSE_FO|99999",
                "expiry": expiry_ms("2026-08-25"),
            },
            {
                "instrument_type": "FUT",
                "instrument_key": "NSE_FO|10000",
                "expiry": expiry_ms("2026-09-29"),
            },
        ]
    )
    key, expiry = generator.select_front_future(frame, "20260805")
    assert key == "NSE_FO|99999"
    assert expiry == "2026-08-25T00:00:00+00:00"


def test_front_future_rejects_expired_contracts():
    frame = pd.DataFrame(
        [
            {
                "instrument_type": "FUT",
                "instrument_key": "NSE_FO|OLD",
                "expiry": expiry_ms("2026-07-28"),
            },
            {
                "instrument_type": "FUT",
                "instrument_key": "NSE_FO|FRONT",
                "expiry": expiry_ms("2026-08-25"),
            },
        ]
    )
    key, _ = generator.select_front_future(frame, "20260805")
    assert key == "NSE_FO|FRONT"


def test_option_panel_is_nearest_expiry_balanced_and_atm_centered():
    rows = []
    weekly_expiry = expiry_ms("2026-08-11")
    monthly_expiry = expiry_ms("2026-08-25")
    for option_type in ("CE", "PE"):
        for strike in (24250, 24500, 24700, 24750, 24800, 25000, 25250):
            rows.append(
                {
                    "instrument_type": option_type,
                    "instrument_key": f"WEEKLY-{option_type}-{strike}",
                    "expiry": weekly_expiry,
                    "strike": strike,
                }
            )
        for strike in (24700, 24750, 24800):
            rows.append(
                {
                    "instrument_type": option_type,
                    "instrument_key": f"MONTHLY-{option_type}-{strike}",
                    "expiry": monthly_expiry,
                    "strike": strike,
                }
            )

    panel = generator.select_option_panel(
        pd.DataFrame(reversed(rows)),
        spot_price=24774.3,
        boundary=utc("2026-08-05 07:32:00"),
    )

    assert tuple(item["option_type"] for item in panel) == (
        "CE", "CE", "CE", "CE", "CE", "PE", "PE", "PE", "PE", "PE"
    )
    assert sum(item["option_type"] == "CE" for item in panel) == 5
    assert sum(item["option_type"] == "PE" for item in panel) == 5
    assert {item["expiry_utc"] for item in panel} == {
        "2026-08-11T00:00:00+00:00"
    }
    assert all(item["instrument_key"].startswith("WEEKLY-") for item in panel)

    for option_type in ("CE", "PE"):
        side = [item for item in panel if item["option_type"] == option_type]
        assert side[0]["strike"] == 24750.0
        assert [item["selection_rank_within_side"] for item in side] == [1, 2, 3, 4, 5]
        assert [item["absolute_moneyness"] for item in side] == sorted(
            item["absolute_moneyness"] for item in side
        )


def test_option_panel_degrades_to_available_balanced_contracts():
    expiry = expiry_ms("2026-08-11")
    frame = pd.DataFrame(
        [
            {
                "instrument_type": "CE",
                "instrument_key": "CE-24750",
                "expiry": expiry,
                "strike": 24750,
            },
            {
                "instrument_type": "PE",
                "instrument_key": "PE-24750",
                "expiry": expiry,
                "strike": 24750,
            },
        ]
    )
    panel = generator.select_option_panel(
        frame,
        spot_price=24774.3,
        boundary=utc("2026-08-05 07:32:00"),
    )
    assert [item["instrument_key"] for item in panel] == ["CE-24750", "PE-24750"]
