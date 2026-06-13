from __future__ import annotations

from pathlib import Path

from .data_loader import scan_source_path
from .models import HistoricalDataSourceRecord, HistoricalSourceType


def scan_option_intraday_directory(
    root: str | Path,
    *,
    provenance: str = "user_csv",
    parquet_enabled: bool = True,
) -> list[HistoricalDataSourceRecord]:
    return scan_source_path(
        root,
        source_type=HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY,
        provenance=provenance,
        parquet_enabled=parquet_enabled,
    )


def scan_option_eod_directory(
    root: str | Path,
    *,
    provenance: str = "user_csv",
    parquet_enabled: bool = True,
) -> list[HistoricalDataSourceRecord]:
    return scan_source_path(
        root,
        source_type=HistoricalSourceType.OPTION_CONTRACT_EOD,
        provenance=provenance,
        parquet_enabled=parquet_enabled,
    )
