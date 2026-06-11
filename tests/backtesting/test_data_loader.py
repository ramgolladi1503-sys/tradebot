from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from core.backtesting.data_loader import detect_source_format, load_historical_source
from core.backtesting.models import DataFormat, HistoricalSourceType


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_source_detection_for_csv(tmp_path: Path) -> None:
    path = tmp_path / "index.csv"
    _write(path, "timestamp,symbol,open,high,low,close,volume\n")
    assert detect_source_format(path) == DataFormat.CSV


def test_source_detection_for_sqlite_runtime_data(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE ticks(timestamp TEXT, symbol TEXT, ltp REAL)")
        conn.execute("INSERT INTO ticks VALUES('2026-01-01T09:15:00+05:30', 'NIFTY', 23000)")
        conn.commit()
    record = load_historical_source(
        db_path,
        source_type=HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA,
        provenance="repo_runtime",
    )
    assert record.data_format == DataFormat.SQLITE
    assert record.schema_valid is True
    assert record.symbols == ("NIFTY",)


def test_schema_validation_for_index_candles(tmp_path: Path) -> None:
    csv_path = tmp_path / "index.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "timestamp,symbol,open,high,low,close,volume",
                "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.UNDERLYING_INDEX_CANDLES,
        provenance="user_csv",
    )
    assert record.schema_valid is True
    assert record.coverage.start_date == "2026-01-01"


def test_schema_validation_for_option_intraday_candles(tmp_path: Path) -> None:
    csv_path = tmp_path / "option_intraday.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "timestamp,underlying,expiry,strike,option_type,open,high,low,close,volume,oi,bid,ask",
                "2026-01-01T09:15:00+05:30,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000,10.5,11.0",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY,
        provenance="user_csv",
    )
    assert record.schema_valid is True
    assert record.optional_fields_present == ("ask", "bid", "oi", "volume")


def test_schema_validation_for_option_eod_data(tmp_path: Path) -> None:
    csv_path = tmp_path / "option_eod.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "date,underlying,expiry,strike,option_type,open,high,low,close,volume,oi,settlement",
                "2026-01-01,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000,11",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.OPTION_CONTRACT_EOD,
        provenance="user_csv",
    )
    assert record.schema_valid is True
    assert record.optional_fields_present == ("oi", "settlement", "volume")


def test_missing_required_fields_produce_clear_errors(tmp_path: Path) -> None:
    csv_path = tmp_path / "broken.csv"
    _write(csv_path, "timestamp,symbol,open,high,low,close\n2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5\n")
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.UNDERLYING_INDEX_CANDLES,
        provenance="user_csv",
    )
    assert record.schema_valid is False
    assert record.missing_required_fields == ("volume",)
    assert "missing_required_fields:volume" in record.warnings[0]


def test_missing_bid_ask_reduces_realism_but_does_not_block_intraday_schema(tmp_path: Path) -> None:
    csv_path = tmp_path / "option_intraday.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "timestamp,underlying,expiry,strike,option_type,open,high,low,close,volume,oi",
                "2026-01-01T09:15:00+05:30,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY,
        provenance="user_csv",
    )
    assert record.schema_valid is True
    assert record.missing_required_fields == ()
    assert "missing_recommended_field:bid" in record.warnings
    assert "missing_recommended_field:ask" in record.warnings


def test_missing_volume_oi_creates_warnings(tmp_path: Path) -> None:
    csv_path = tmp_path / "option_intraday.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "timestamp,underlying,expiry,strike,option_type,open,high,low,close,bid,ask",
                "2026-01-01T09:15:00+05:30,NIFTY,2026-01-29,23000,CE,10,12,9,11,10.5,11.0",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY,
        provenance="user_csv",
    )
    assert record.schema_valid is True
    assert "missing_recommended_field:volume" in record.warnings
    assert "missing_recommended_field:oi" in record.warnings


def test_missing_expiry_strike_option_type_blocks_option_data_validity(tmp_path: Path) -> None:
    csv_path = tmp_path / "broken_option_intraday.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "timestamp,underlying,open,high,low,close",
                "2026-01-01T09:15:00+05:30,NIFTY,10,12,9,11",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY,
        provenance="user_csv",
    )
    assert record.schema_valid is False
    assert record.missing_required_fields == ("expiry", "option_type", "strike")
    assert "missing_required_fields:expiry,option_type,strike" in record.warnings


def test_provenance_is_preserved(tmp_path: Path) -> None:
    csv_path = tmp_path / "index.csv"
    _write(
        csv_path,
        "\n".join(
            [
                "timestamp,symbol,open,high,low,close,volume",
                "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            ]
        ),
    )
    record = load_historical_source(
        csv_path,
        source_type=HistoricalSourceType.UNDERLYING_INDEX_CANDLES,
        provenance="vendor_fixture",
    )
    assert record.provenance == "vendor_fixture"
