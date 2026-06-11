from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from core.paths import repo_root, reports_dir

from .data_loader import scan_source_path, summarize_source_coverage
from .models import (
    BacktestDataConfig,
    BacktestMode,
    DataReadinessVerdict,
    HistoricalDataSourceRecord,
    HistoricalSourceType,
    ModeFeasibility,
    PhaseOneVerdict,
)


@dataclass(frozen=True)
class DataCatalog:
    config: BacktestDataConfig
    sources: tuple[HistoricalDataSourceRecord, ...] = field(default_factory=tuple)

    def by_type(self, source_type: HistoricalSourceType) -> tuple[HistoricalDataSourceRecord, ...]:
        return tuple(record for record in self.sources if record.source_type == source_type)

    def available_sources(self) -> tuple[HistoricalDataSourceRecord, ...]:
        return tuple(record for record in self.sources if record.schema_valid)

    def invalid_sources(self) -> tuple[HistoricalDataSourceRecord, ...]:
        return tuple(record for record in self.sources if not record.schema_valid)

    def mode_feasibility(self) -> tuple[ModeFeasibility, ...]:
        valid_by_type = {
            source_type: tuple(record for record in self.by_type(source_type) if record.schema_valid)
            for source_type in HistoricalSourceType
        }
        symbols_requested = set(self.config.symbols)
        underlying_ok = _has_symbol_coverage(valid_by_type[HistoricalSourceType.UNDERLYING_INDEX_CANDLES], symbols_requested)
        futures_ok = _has_symbol_coverage(valid_by_type[HistoricalSourceType.FUTURES_CANDLES], symbols_requested)
        option_intraday_records = valid_by_type[HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY]
        option_intraday_ok = _has_symbol_coverage(
            valid_by_type[HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY],
            symbols_requested,
            span_days_required=self.config.required_span_days,
        )
        option_eod_ok = _has_symbol_coverage(valid_by_type[HistoricalSourceType.OPTION_CONTRACT_EOD], symbols_requested)
        runtime_ok = bool(valid_by_type[HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA])
        hybrid_ok = (underlying_ok or futures_ok) and (option_intraday_ok or option_eod_ok or runtime_ok)
        proxy_ok = underlying_ok or futures_ok
        option_intraday_bidask_missing = any(
            ("bid" not in record.optional_fields_present or "ask" not in record.optional_fields_present)
            for record in option_intraday_records
        ) if option_intraday_records else False

        modes = [
            ModeFeasibility(
                mode=BacktestMode.TRUE_OPTIONS_INTRADAY,
                feasible=bool(option_intraday_ok and (underlying_ok or futures_ok)),
                reasons=_true_intraday_reasons(
                    underlying_ok=underlying_ok,
                    futures_ok=futures_ok,
                    option_intraday_ok=option_intraday_ok,
                    bidask_missing=option_intraday_bidask_missing,
                ),
                supporting_sources=_supporting_sources(valid_by_type, HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY, HistoricalSourceType.UNDERLYING_INDEX_CANDLES, HistoricalSourceType.FUTURES_CANDLES),
            ),
            ModeFeasibility(
                mode=BacktestMode.OPTIONS_EOD,
                feasible=bool(option_eod_ok and (underlying_ok or futures_ok)),
                reasons=_eod_reasons(underlying_ok=underlying_ok, futures_ok=futures_ok, option_eod_ok=option_eod_ok),
                supporting_sources=_supporting_sources(valid_by_type, HistoricalSourceType.OPTION_CONTRACT_EOD, HistoricalSourceType.UNDERLYING_INDEX_CANDLES, HistoricalSourceType.FUTURES_CANDLES),
            ),
            ModeFeasibility(
                mode=BacktestMode.UNDERLYING_SIGNAL_WITH_OPTION_PROXY,
                feasible=bool(proxy_ok),
                reasons=() if proxy_ok else ("missing_underlying_or_futures_history",),
                supporting_sources=_supporting_sources(valid_by_type, HistoricalSourceType.UNDERLYING_INDEX_CANDLES, HistoricalSourceType.FUTURES_CANDLES),
            ),
            ModeFeasibility(
                mode=BacktestMode.LIVE_CAPTURE_REPLAY,
                feasible=bool(runtime_ok),
                reasons=() if runtime_ok else ("missing_runtime_replay_data",),
                supporting_sources=_supporting_sources(valid_by_type, HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA),
            ),
            ModeFeasibility(
                mode=BacktestMode.HYBRID,
                feasible=bool(hybrid_ok),
                reasons=() if hybrid_ok else ("missing_underlying_or_option_support_for_hybrid",),
                supporting_sources=_supporting_sources(
                    valid_by_type,
                    HistoricalSourceType.UNDERLYING_INDEX_CANDLES,
                    HistoricalSourceType.FUTURES_CANDLES,
                    HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY,
                    HistoricalSourceType.OPTION_CONTRACT_EOD,
                    HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA,
                ),
            ),
        ]
        return tuple(modes)

    def phase_one_verdict(self) -> PhaseOneVerdict:
        modes = {item.mode: item for item in self.mode_feasibility()}
        valid_sources = self.available_sources()
        invalid_sources = self.invalid_sources()
        if not valid_sources and invalid_sources:
            return PhaseOneVerdict.BLOCKED_BY_DATA_SCHEMA
        if not valid_sources:
            return PhaseOneVerdict.NEED_USER_HISTORICAL_DATA
        if modes[BacktestMode.TRUE_OPTIONS_INTRADAY].feasible:
            return PhaseOneVerdict.READY_FOR_PHASE_2
        if any(mode.feasible for mode in modes.values()):
            if modes[BacktestMode.UNDERLYING_SIGNAL_WITH_OPTION_PROXY].feasible or modes[BacktestMode.OPTIONS_EOD].feasible or modes[BacktestMode.HYBRID].feasible:
                return PhaseOneVerdict.INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS
            return PhaseOneVerdict.NEED_USER_HISTORICAL_DATA
        return PhaseOneVerdict.BLOCKED_BY_DATA_SCHEMA if invalid_sources else PhaseOneVerdict.NEED_USER_HISTORICAL_DATA

    def readiness_verdict(self) -> DataReadinessVerdict:
        phase = self.phase_one_verdict()
        modes = {item.mode: item for item in self.mode_feasibility()}
        if phase == PhaseOneVerdict.READY_FOR_PHASE_2 and modes[BacktestMode.TRUE_OPTIONS_INTRADAY].feasible:
            return DataReadinessVerdict.READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST
        if phase == PhaseOneVerdict.BLOCKED_BY_DATA_SCHEMA:
            return DataReadinessVerdict.BLOCKED_BY_SCHEMA
        if any(item.feasible for item in modes.values()):
            return DataReadinessVerdict.READY_FOR_EOD_OR_PROXY_ONLY
        return DataReadinessVerdict.NEED_USER_HISTORICAL_DATA

    def data_readiness_score(self) -> int:
        valid_by_type = {
            source_type: tuple(record for record in self.by_type(source_type) if record.schema_valid)
            for source_type in HistoricalSourceType
        }
        intraday_records = valid_by_type[HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY]
        underlying_records = valid_by_type[HistoricalSourceType.UNDERLYING_INDEX_CANDLES]
        futures_records = valid_by_type[HistoricalSourceType.FUTURES_CANDLES]
        eod_records = valid_by_type[HistoricalSourceType.OPTION_CONTRACT_EOD]
        runtime_records = valid_by_type[HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA]
        if intraday_records and any(record.eight_year_coverage for record in intraday_records) and (underlying_records or futures_records):
            bidask_complete = all("bid" in record.optional_fields_present and "ask" in record.optional_fields_present for record in intraday_records)
            vol_oi_complete = all("volume" in record.optional_fields_present and "oi" in record.optional_fields_present for record in intraday_records)
            if bidask_complete and vol_oi_complete:
                return 100
            if vol_oi_complete:
                return 85
            return 65
        if intraday_records and any(record.coverage.span_days >= 730 for record in intraday_records):
            return 65
        if eod_records and (underlying_records or futures_records):
            return 50
        if underlying_records or futures_records:
            return 35
        if runtime_records:
            return 20
        return 0

    def to_payload(self) -> dict[str, Any]:
        grouped = {
            source_type.value: summarize_source_coverage(list(self.by_type(source_type)))
            for source_type in HistoricalSourceType
        }
        return {
            "config": self.config.to_payload(),
            "phase_one_verdict": self.phase_one_verdict().value,
            "data_readiness_verdict": self.readiness_verdict().value,
            "data_readiness_score": self.data_readiness_score(),
            "source_count": len(self.sources),
            "sources": [record.to_payload() for record in self.sources],
            "available_sources": [record.to_payload() for record in self.available_sources()],
            "invalid_sources": [record.to_payload() for record in self.invalid_sources()],
            "sources_by_type": grouped,
            "mode_feasibility": [mode.to_payload() for mode in self.mode_feasibility()],
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "append": False,
        }


def load_backtest_config(path: str | Path) -> BacktestDataConfig:
    config_path = Path(path).expanduser()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if config_path.parent.name == "configs":
        root = config_path.resolve().parent.parent
    else:
        root = config_path.resolve().parent
    data_roots_raw = dict(raw.get("data_roots") or {})
    reports_root = _resolve_path(raw.get("reports_dir") or (reports_dir() / "backtesting"), base_dir=root)
    catalog_output_path = _resolve_path(
        raw.get("catalog_output_path") or (reports_root / "historical_data_catalog_latest.json"),
        base_dir=root,
    )
    diagnostics_output_path = _resolve_path(
        raw.get("diagnostics_output_path") or (reports_root / "backtest_data_diagnostics_latest.json"),
        base_dir=root,
    )
    readiness_output_path = _resolve_path(
        raw.get("readiness_output_path") or (reports_root / "data_readiness_latest.json"),
        base_dir=root,
    )
    data_roots = {
        source_type: tuple(_resolve_path(path_value, base_dir=root) for path_value in list(data_roots_raw.get(source_type.value, [])))
        for source_type in HistoricalSourceType
    }
    runtime_replay_roots = tuple(
        _resolve_path(path_value, base_dir=root)
        for path_value in list(raw.get("runtime_replay_roots") or [])
    )
    return BacktestDataConfig(
        config_path=config_path,
        symbols=tuple(str(symbol).strip().upper() for symbol in list(raw.get("symbols") or []) if str(symbol).strip()),
        data_roots=data_roots,
        reports_dir=reports_root,
        catalog_output_path=catalog_output_path,
        diagnostics_output_path=diagnostics_output_path,
        readiness_output_path=readiness_output_path,
        start_date=str(raw.get("start_date")).strip() if raw.get("start_date") else None,
        end_date=str(raw.get("end_date")).strip() if raw.get("end_date") else None,
        required_span_days=int(raw.get("required_span_days") or 2890),
        parquet_enabled=bool(raw.get("parquet_enabled", True)),
        runtime_replay_roots=runtime_replay_roots,
    )


def build_catalog_from_config(config: BacktestDataConfig) -> DataCatalog:
    records: list[HistoricalDataSourceRecord] = []
    for source_type, roots in config.data_roots.items():
        for root in roots:
            provenance = "repo_runtime" if source_type == HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA else "user_csv"
            if "nse_reports" in str(root):
                provenance = "nse_report"
            records.extend(
                scan_source_path(
                    root,
                    source_type=source_type,
                    provenance=provenance,
                    parquet_enabled=config.parquet_enabled,
                )
            )
    for runtime_root in config.runtime_replay_roots:
        records.extend(
            scan_source_path(
                runtime_root,
                source_type=HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA,
                provenance="repo_runtime",
                parquet_enabled=config.parquet_enabled,
            )
        )
    return DataCatalog(config=config, sources=tuple(records))


def build_diagnostics_report(config: BacktestDataConfig) -> dict[str, Any]:
    catalog = build_catalog_from_config(config)
    payload = catalog.to_payload()
    available_modes = [item["mode"] for item in payload["mode_feasibility"] if item["feasible"]]
    blocked_modes = [item["mode"] for item in payload["mode_feasibility"] if not item["feasible"]]
    payload["questions"] = {
        "what_historical_data_exists": [record["path"] for record in payload["available_sources"]],
        "what_symbols_are_covered": sorted({symbol for source in payload["available_sources"] for symbol in source["symbols"]}),
        "what_dates_are_covered": {
            "start_date": min(
                (source["coverage"]["start_date"] for source in payload["available_sources"] if source["coverage"]["start_date"]),
                default=None,
            ),
            "end_date": max(
                (source["coverage"]["end_date"] for source in payload["available_sources"] if source["coverage"]["end_date"]),
                default=None,
            ),
        },
        "do_we_have_true_intraday_option_data": payload["mode_feasibility"][0]["feasible"],
        "do_we_only_have_eod_proxy_runtime": {
            item["mode"]: item["feasible"]
            for item in payload["mode_feasibility"]
            if item["mode"] != BacktestMode.TRUE_OPTIONS_INTRADAY.value
        },
        "which_backtest_modes_are_feasible": {
            item["mode"]: item["feasible"] for item in payload["mode_feasibility"]
        },
        "what_exact_fields_are_missing": {
            source["path"]: source["missing_required_fields"]
            for source in payload["invalid_sources"]
        },
        "is_true_8y_intraday_possible_or_inconclusive": payload["phase_one_verdict"],
    }
    payload["available_modes"] = available_modes
    payload["blocked_modes"] = blocked_modes
    payload["eight_year_coverage_exists"] = any(source["eight_year_coverage"] for source in payload["available_sources"])
    payload["real_intraday_options_backtesting_possible"] = any(
        item["mode"] == BacktestMode.TRUE_OPTIONS_INTRADAY.value and item["feasible"]
        for item in payload["mode_feasibility"]
    )
    payload["recommended_next_action"] = _recommended_next_action(
        readiness_verdict=payload["data_readiness_verdict"],
        blocked_modes=blocked_modes,
    )
    return payload


def write_catalog(catalog: DataCatalog) -> Path:
    catalog.config.catalog_output_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.config.catalog_output_path.write_text(json.dumps(catalog.to_payload(), indent=2, sort_keys=True), encoding="utf-8")
    return catalog.config.catalog_output_path


def write_diagnostics_report(report: dict[str, Any], target: str | Path) -> Path:
    path = Path(target).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _resolve_path(value: str | Path, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _has_symbol_coverage(
    records: tuple[HistoricalDataSourceRecord, ...],
    symbols: set[str],
    *,
    span_days_required: int | None = None,
) -> bool:
    if not records:
        return False
    covered = {symbol for record in records for symbol in record.symbols}
    if symbols and not symbols.intersection(covered):
        return False
    if span_days_required is not None:
        return any(record.coverage.span_days >= span_days_required for record in records)
    return True


def _supporting_sources(
    valid_by_type: dict[HistoricalSourceType, tuple[HistoricalDataSourceRecord, ...]],
    *source_types: HistoricalSourceType,
) -> tuple[str, ...]:
    return tuple(
        record.path
        for source_type in source_types
        for record in valid_by_type.get(source_type, ())
    )


def _true_intraday_reasons(*, underlying_ok: bool, futures_ok: bool, option_intraday_ok: bool, bidask_missing: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if not option_intraday_ok:
        reasons.append("missing_true_intraday_option_history_or_coverage")
    if not (underlying_ok or futures_ok):
        reasons.append("missing_underlying_or_futures_signal_history")
    if option_intraday_ok and bidask_missing:
        reasons.append("missing_bid_ask_reduces_fill_realism")
    return tuple(reasons)


def _eod_reasons(*, underlying_ok: bool, futures_ok: bool, option_eod_ok: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if not option_eod_ok:
        reasons.append("missing_option_eod_history")
    if not (underlying_ok or futures_ok):
        reasons.append("missing_underlying_or_futures_signal_history")
    return tuple(reasons)


def _recommended_next_action(*, readiness_verdict: str, blocked_modes: list[str]) -> str:
    if readiness_verdict == DataReadinessVerdict.READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST.value:
        return "true_intraday_options_history_present_continue_to_phase_2"
    if readiness_verdict == DataReadinessVerdict.READY_FOR_EOD_OR_PROXY_ONLY.value:
        return "collect_expired_intraday_options_history_if_true_intraday_edge_is_required"
    if readiness_verdict == DataReadinessVerdict.BLOCKED_BY_SCHEMA.value:
        return "fix_schema_errors_in_blocked_sources"
    if BacktestMode.TRUE_OPTIONS_INTRADAY.value in blocked_modes:
        return "provide_local_intraday_options_history_with_expiry_strike_option_type_and_price_fields"
    return "provide_local_historical_data_roots_for_index_futures_options_or_runtime_replay"
