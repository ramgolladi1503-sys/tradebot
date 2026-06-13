from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class HistoricalSourceType(str, Enum):
    UNDERLYING_INDEX_CANDLES = "UNDERLYING_INDEX_CANDLES"
    FUTURES_CANDLES = "FUTURES_CANDLES"
    OPTION_CONTRACT_CANDLES_INTRADAY = "OPTION_CONTRACT_CANDLES_INTRADAY"
    OPTION_CONTRACT_EOD = "OPTION_CONTRACT_EOD"
    OPTION_CHAIN_SNAPSHOT = "OPTION_CHAIN_SNAPSHOT"
    RUNTIME_CAPTURED_LIVE_DATA = "RUNTIME_CAPTURED_LIVE_DATA"


class BacktestMode(str, Enum):
    TRUE_OPTIONS_INTRADAY = "TRUE_OPTIONS_INTRADAY"
    OPTIONS_EOD = "OPTIONS_EOD"
    UNDERLYING_SIGNAL_WITH_OPTION_PROXY = "UNDERLYING_SIGNAL_WITH_OPTION_PROXY"
    LIVE_CAPTURE_REPLAY = "LIVE_CAPTURE_REPLAY"
    HYBRID = "HYBRID"


class DataFormat(str, Enum):
    CSV = "csv"
    SQLITE = "sqlite"
    PARQUET = "parquet"
    UNKNOWN = "unknown"


class PhaseOneVerdict(str, Enum):
    READY_FOR_PHASE_2 = "READY_FOR_PHASE_2"
    BLOCKED_BY_DATA_SCHEMA = "BLOCKED_BY_DATA_SCHEMA"
    INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS = "INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS"
    NEED_USER_HISTORICAL_DATA = "NEED_USER_HISTORICAL_DATA"


class DataReadinessVerdict(str, Enum):
    READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST = "READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST"
    READY_FOR_EOD_OR_PROXY_ONLY = "READY_FOR_EOD_OR_PROXY_ONLY"
    READY_FOR_RUNTIME_REPLAY_ONLY = "READY_FOR_RUNTIME_REPLAY_ONLY"
    NEED_USER_HISTORICAL_DATA = "NEED_USER_HISTORICAL_DATA"
    BLOCKED_BY_SCHEMA = "BLOCKED_BY_SCHEMA"


@dataclass(frozen=True)
class CoverageWindow:
    start_date: str | None
    end_date: str | None
    span_days: int
    row_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "span_days": int(self.span_days),
            "row_count": int(self.row_count),
        }


@dataclass(frozen=True)
class HistoricalDataSourceRecord:
    source_type: HistoricalSourceType
    path: str
    data_format: DataFormat
    provenance: str
    schema_valid: bool
    coverage: CoverageWindow
    symbols: tuple[str, ...] = ()
    expiries: tuple[str, ...] = ()
    strikes: tuple[str, ...] = ()
    intervals: tuple[str, ...] = ()
    missing_required_fields: tuple[str, ...] = ()
    optional_fields_present: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    eight_year_coverage: bool = False
    replay_ready: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type.value,
            "path": self.path,
            "data_format": self.data_format.value,
            "provenance": self.provenance,
            "schema_valid": bool(self.schema_valid),
            "coverage": self.coverage.to_payload(),
            "symbols": list(self.symbols),
            "expiries": list(self.expiries),
            "strikes": list(self.strikes),
            "intervals": list(self.intervals),
            "missing_required_fields": list(self.missing_required_fields),
            "optional_fields_present": list(self.optional_fields_present),
            "warnings": list(self.warnings),
            "eight_year_coverage": bool(self.eight_year_coverage),
            "replay_ready": bool(self.replay_ready),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ModeFeasibility:
    mode: BacktestMode
    feasible: bool
    reasons: tuple[str, ...]
    supporting_sources: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "feasible": bool(self.feasible),
            "reasons": list(self.reasons),
            "supporting_sources": list(self.supporting_sources),
        }


@dataclass(frozen=True)
class BacktestDataConfig:
    config_path: Path
    symbols: tuple[str, ...]
    data_roots: dict[HistoricalSourceType, tuple[Path, ...]]
    reports_dir: Path
    catalog_output_path: Path
    diagnostics_output_path: Path
    readiness_output_path: Path
    start_date: str | None = None
    end_date: str | None = None
    required_span_days: int = 2890
    parquet_enabled: bool = True
    runtime_replay_roots: tuple[Path, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "config_path": str(self.config_path),
            "symbols": list(self.symbols),
            "data_roots": {
                source_type.value: [str(path) for path in paths]
                for source_type, paths in self.data_roots.items()
            },
            "reports_dir": str(self.reports_dir),
            "catalog_output_path": str(self.catalog_output_path),
            "diagnostics_output_path": str(self.diagnostics_output_path),
            "readiness_output_path": str(self.readiness_output_path),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "required_span_days": int(self.required_span_days),
            "parquet_enabled": bool(self.parquet_enabled),
            "runtime_replay_roots": [str(path) for path in self.runtime_replay_roots],
        }
