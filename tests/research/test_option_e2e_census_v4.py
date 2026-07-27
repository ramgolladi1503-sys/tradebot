from __future__ import annotations

import json

import pandas as pd

from research.option_e2e_recertification_v4.data_census.census import build_census


def test_census_classifies_executable_option_quote_and_authority(tmp_path) -> None:
    quote_path = tmp_path / "nifty_option_quotes.csv"
    quote_path.write_text(
        "timestamp,tradingsymbol,expiry,strike,option_type,bid,ask,ltp\n"
        "2026-07-01T09:15:00+05:30,NIFTY2670125000CE,2026-07-30,25000,CE,100.0,101.0,100.5\n",
        encoding="utf-8",
    )
    master_path = tmp_path / "historical_instrument_master_20260701.csv"
    master_path.write_text(
        "asof,tradingsymbol,instrument_token,expiry,strike,option_type,lot_size,tick_size\n"
        "2026-07-01,NIFTY2670125000CE,123,2026-07-30,25000,CE,75,0.05\n",
        encoding="utf-8",
    )

    files, summary = build_census((tmp_path,), repo_root=tmp_path)

    by_name = {item.logical_path: item for item in files}
    assert by_name["nifty_option_quotes.csv"].classification == "option_quote"
    assert by_name["nifty_option_quotes.csv"].has_bid_ask is True
    assert by_name["nifty_option_quotes.csv"].usable_for_option_e2e is True
    assert by_name["nifty_option_quotes.csv"].has_expiry is True
    assert by_name["nifty_option_quotes.csv"].has_strike is True
    assert by_name["nifty_option_quotes.csv"].has_quote_time is True
    assert by_name["nifty_option_quotes.csv"].row_count == 1
    assert by_name["historical_instrument_master_20260701.csv"].classification == "instrument_master"
    assert by_name["historical_instrument_master_20260701.csv"].point_in_time_status == "POINT_IN_TIME_AUTHORITY_CANDIDATE"
    assert by_name["historical_instrument_master_20260701.csv"].has_lot_size is True
    assert by_name["historical_instrument_master_20260701.csv"].authority_role == "expiry|strike|lot_size"
    assert summary.executable_quote_files == 1
    assert summary.point_in_time_authority_files == 1
    assert summary.files_classified == 2
    assert summary.census_sha256


def test_census_rejects_current_master_as_point_in_time_authority(tmp_path) -> None:
    current_master = tmp_path / "runtime" / "upstox_instruments" / "complete.json"
    current_master.parent.mkdir(parents=True)
    current_master.write_text(
        json.dumps(
            [
                {
                    "tradingsymbol": "NIFTY2670125000CE",
                    "instrument_token": "123",
                    "expiry": "2026-07-30",
                    "strike": 25000,
                    "option_type": "CE",
                    "lot_size": 75,
                }
            ]
        ),
        encoding="utf-8",
    )

    files, summary = build_census((tmp_path,), repo_root=tmp_path)

    assert [item.logical_path for item in files] == ["runtime/upstox_instruments/complete.json"]
    assert files[0].classification == "instrument_master"
    assert files[0].point_in_time_status == "CURRENT_MASTER_NOT_POINT_IN_TIME"
    assert files[0].usable_for_option_e2e is False
    assert files[0].blocker == "CURRENT_MASTER_NOT_POINT_IN_TIME"
    assert summary.point_in_time_authority_files == 0
    assert summary.blocked_files == 1


def test_census_skips_secret_named_files(tmp_path) -> None:
    secret_file = tmp_path / "kite_access_token_quotes.csv"
    secret_file.write_text("timestamp,bid,ask\n2026-07-01T09:15:00+05:30,1,2\n", encoding="utf-8")
    public_file = tmp_path / "quotes.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-07-01T09:15:00+05:30",
                "expiry": "2026-07-30",
                "strike": 25000,
                "option_type": "CE",
                "bid": 1,
                "ask": 2,
            }
        ]
    ).to_csv(public_file, index=False)

    files, _summary = build_census((tmp_path,), repo_root=tmp_path)

    assert [item.logical_path for item in files] == ["quotes.csv"]
    assert files[0].sha256
    assert files[0].absolute_path.endswith("quotes.csv")
