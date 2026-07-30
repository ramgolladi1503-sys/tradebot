from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_upstox_option_tick_replay import REQUIRED_COLUMNS, audit_file, run_audit


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": [1_754_992_200_000, 1_754_992_201_000],
            "instrument_key": ["NSE_FO|1", "NSE_FO|1"],
            "ltp": [100.0, 101.0],
            "bid_price": [99.5, 100.5],
            "ask_price": [100.5, 101.5],
            "delta": [0.5, 0.51],
            "theta": [-1.0, -1.1],
            "gamma": [0.01, 0.01],
            "vega": [2.0, 2.1],
            "iv": [12.0, 12.1],
            "volume": [100, 110],
            "oi": [1000, 1010],
        }
    )


def test_valid_market_tick_file_is_replay_usable(tmp_path: Path) -> None:
    path = tmp_path / "ticks.parquet"
    _valid_frame().to_parquet(path, index=False)

    audit = audit_file(path)

    assert audit.usable is True
    assert audit.blockers == ()
    assert audit.rows == 2
    assert audit.instrument_count == 1
    assert set(audit.columns) == REQUIRED_COLUMNS
    assert audit.first_ts is not None
    assert audit.last_ts is not None


def test_missing_column_blocks_replay(tmp_path: Path) -> None:
    path = tmp_path / "ticks.parquet"
    _valid_frame().drop(columns=["ask_price"]).to_parquet(path, index=False)

    audit = audit_file(path)

    assert audit.usable is False
    assert "missing_required_columns" in audit.blockers
    assert audit.missing_columns == ("ask_price",)


def test_crossed_quote_blocks_replay(tmp_path: Path) -> None:
    frame = _valid_frame()
    frame.loc[0, "bid_price"] = 101.0
    frame.loc[0, "ask_price"] = 100.0
    path = tmp_path / "ticks.parquet"
    frame.to_parquet(path, index=False)

    audit = audit_file(path)

    assert audit.usable is False
    assert audit.crossed_quote_rows == 1
    assert "crossed_quotes" in audit.blockers


def test_directory_summary_is_deterministic_and_bounded(tmp_path: Path) -> None:
    _valid_frame().to_parquet(tmp_path / "a.parquet", index=False)
    _valid_frame().to_parquet(tmp_path / "b.parquet", index=False)

    first = run_audit(tmp_path)
    second = run_audit(tmp_path)

    assert first == second
    assert first["file_count"] == 2
    assert first["usable_file_count"] == 2
    assert first["total_rows"] == 4
    assert first["distinct_schema_count"] == 1
    assert first["verdict"] == {
        "market_input_replay_usable": True,
        "candidate_lifecycle_present": False,
        "execution_authority_present": False,
        "scope": "market_input_reconstruction_only",
    }
