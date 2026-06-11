from __future__ import annotations

from pathlib import Path

from .data_loader import scan_source_path
from .models import HistoricalDataSourceRecord, HistoricalSourceType


def scan_nse_derivatives_directory(
    root: str | Path,
    *,
    source_type: HistoricalSourceType,
    provenance: str = "nse_report",
    parquet_enabled: bool = True,
) -> list[HistoricalDataSourceRecord]:
    return scan_source_path(
        root,
        source_type=source_type,
        provenance=provenance,
        parquet_enabled=parquet_enabled,
    )
