from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json

import pandas as pd

from research.option_e2e_recertification_v4.option_candle_backtest_v1 import (
    CandleBacktestConfig,
    CandleBacktestResult,
    run_option_candle_backtest,
)

from .signal_ledger import (
    CompressionLedgerConfig,
    CompressionSignalLedgerResult,
    build_compression_signal_ledger,
)


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CompressionCampaignConfig:
    partition: str = "development"
    slippage_grid_bps: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0)
    minimum_trades: int = 30
    quantity: int = 1
    stop_pct: float = 0.20
    target_rr: float = 1.50
    max_hold_minutes: int = 30
    fixed_cost_per_order: float = 20.0
    entry_cost_bps: float = 0.0
    exit_cost_bps: float = 0.0
    max_volume_participation: float = 0.02
    require_session_catalog: bool = True
    ledger_config: CompressionLedgerConfig = field(default_factory=CompressionLedgerConfig)

    def __post_init__(self) -> None:
        partition = str(self.partition).strip().lower()
        if partition not in {"development", "validation", "all_non_holdout", "smoke"}:
            raise ValueError("unsupported_campaign_partition")
        object.__setattr__(self, "partition", partition)
        grid = tuple(sorted({float(value) for value in self.slippage_grid_bps}))
        if not grid or any(value < 0.0 for value in grid):
            raise ValueError("invalid_slippage_grid")
        object.__setattr__(self, "slippage_grid_bps", grid)
        if self.minimum_trades <= 0:
            raise ValueError("minimum_trades_must_be_positive")


@dataclass(frozen=True)
class CompressionCampaignResult:
    ledger: CompressionSignalLedgerResult
    partition_signals: pd.DataFrame
    base_result: CandleBacktestResult | None
    sensitivity: dict[str, object]
    controls: dict[str, object]
    summary: dict[str, object]


def _date_set(values: object) -> set[str]:
    return {str(value) for value in list(values or [])}


def _allowed_dates(split_manifest: dict[str, object], partition: str) -> set[str]:
    partitions = split_manifest.get("partitions")
    if not isinstance(partitions, dict):
        raise ValueError("invalid_split_manifest")
    if partition == "all_non_holdout":
        return _date_set(partitions.get("development")) | _date_set(partitions.get("validation"))
    if partition == "smoke":
        development = _date_set(partitions.get("development"))
        return {sorted(development)[0]} if development else set()
    return _date_set(partitions.get(partition))


def _normalize_option_timestamps(frame: pd.DataFrame, timezone: str) -> pd.Series:
    timestamp_column = next(
        (candidate for candidate in ("timestamp", "date", "ts") if candidate in frame.columns),
        None,
    )
    if timestamp_column is None:
        raise ValueError("missing_option_bar_timestamp_column")
    timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("invalid_option_bar_timestamp_rows")
    if getattr(timestamps.dt, "tz", None) is None:
        return timestamps.dt.tz_localize(timezone)
    return timestamps.dt.tz_convert(timezone)


def _filter_option_inputs(
    *,
    catalog: pd.DataFrame,
    option_bars: pd.DataFrame,
    allowed_dates: set[str],
    holdout_dates: set[str],
    timezone: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars = option_bars.copy()
    bars["timestamp"] = _normalize_option_timestamps(bars, timezone)
    bars["session_date"] = bars["timestamp"].dt.date.astype(str)
    observed_dates = set(bars["session_date"].unique().tolist())
    if observed_dates & holdout_dates:
        raise ValueError("holdout_option_outcomes_supplied")
    bars = bars.loc[bars["session_date"].isin(allowed_dates)].copy()

    contracts = catalog.copy()
    if "session_date" not in contracts.columns:
        raise ValueError("session_contract_catalog_required")
    contracts["session_date"] = pd.to_datetime(
        contracts["session_date"], errors="coerce"
    ).dt.date.astype(str)
    if contracts["session_date"].isin(holdout_dates).any():
        raise ValueError("holdout_contract_catalog_supplied")
    contracts = contracts.loc[contracts["session_date"].isin(allowed_dates)].copy()
    return contracts, bars


def _backtest_config(
    campaign: CompressionCampaignConfig,
    slippage_bps: float,
) -> CandleBacktestConfig:
    return CandleBacktestConfig(
        quantity=campaign.quantity,
        stop_pct=campaign.stop_pct,
        target_rr=campaign.target_rr,
        max_hold_minutes=campaign.max_hold_minutes,
        entry_slippage_bps=float(slippage_bps),
        exit_slippage_bps=float(slippage_bps),
        fixed_cost_per_order=campaign.fixed_cost_per_order,
        entry_cost_bps=campaign.entry_cost_bps,
        exit_cost_bps=campaign.exit_cost_bps,
        max_volume_participation=campaign.max_volume_participation,
        require_session_catalog=campaign.require_session_catalog,
    )


def _scenario_row(
    *,
    slippage_bps: float,
    result: CandleBacktestResult,
) -> dict[str, object]:
    return {
        "slippage_bps_per_side": float(slippage_bps),
        "trades": int(result.summary["trades"]),
        "win_rate": result.summary["win_rate"],
        "profit_factor": result.summary["profit_factor"],
        "net_pnl": float(result.summary["net_pnl"]),
        "max_drawdown": float(result.summary["max_drawdown"]),
        "total_costs": float(result.summary["total_costs"]),
        "ce": result.summary["ce"],
        "pe": result.summary["pe"],
    }


def _run_sensitivity(
    *,
    signals: pd.DataFrame,
    catalog: pd.DataFrame,
    option_bars: pd.DataFrame,
    config: CompressionCampaignConfig,
) -> tuple[CandleBacktestResult | None, dict[str, object]]:
    base_result: CandleBacktestResult | None = None
    rows: list[dict[str, object]] = []
    for slippage in config.slippage_grid_bps:
        result = run_option_candle_backtest(
            signals=signals,
            contract_catalog=catalog,
            option_bars=option_bars,
            config=_backtest_config(config, slippage),
        )
        if float(slippage) == 50.0:
            base_result = result
        rows.append(_scenario_row(slippage_bps=slippage, result=result))
    if base_result is None and rows:
        chosen = min(config.slippage_grid_bps, key=lambda value: abs(float(value) - 50.0))
        base_result = run_option_candle_backtest(
            signals=signals,
            contract_catalog=catalog,
            option_bars=option_bars,
            config=_backtest_config(config, chosen),
        )

    stress = [row for row in rows if float(row["slippage_bps_per_side"]) >= 50.0]
    enough = bool(stress) and all(
        int(row["trades"]) >= config.minimum_trades for row in stress
    )
    positive = bool(stress) and all(
        float(row["net_pnl"]) > 0.0
        and row["profit_factor"] is not None
        and float(row["profit_factor"]) > 1.0
        for row in stress
    )
    survived = enough and positive
    payload: dict[str, object] = {
        "schema_version": "compression_breakout_sensitivity_v1",
        "result_label": (
            "CANDLE_PROXY_ECONOMICS_SURVIVED_COST_STRESS"
            if survived
            else "CANDLE_PROXY_ECONOMICS_DID_NOT_PASS_COST_STRESS"
        ),
        "minimum_trades": config.minimum_trades,
        "scenarios": rows,
        "survived_cost_stress": survived,
        "executable_option_pnl_certified": False,
        "next_gate": "FORWARD_BID_ASK_VALIDATION",
    }
    payload["semantic_hash"] = _canonical_hash(payload)
    return base_result, payload


def _control_summary(result: CandleBacktestResult) -> dict[str, object]:
    return {
        "trades": int(result.summary["trades"]),
        "win_rate": result.summary["win_rate"],
        "profit_factor": result.summary["profit_factor"],
        "net_pnl": float(result.summary["net_pnl"]),
        "max_drawdown": float(result.summary["max_drawdown"]),
    }


def _run_controls(
    *,
    signals: pd.DataFrame,
    catalog: pd.DataFrame,
    option_bars: pd.DataFrame,
    config: CompressionCampaignConfig,
) -> dict[str, object]:
    if signals.empty:
        return {
            "schema_version": "compression_breakout_controls_v1",
            "direction_flip": None,
            "one_bar_delay": None,
            "control_status": "NO_SIGNALS",
        }

    direction_flip = signals.copy()
    direction_flip["direction"] = direction_flip["direction"].map(
        {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}
    )
    delayed = signals.copy()
    delay = pd.Timedelta(minutes=config.ledger_config.bar_interval_minutes)
    delayed["signal_ts"] = pd.to_datetime(delayed["signal_ts"]) + delay
    if "feature_cutoff_ts" in delayed.columns:
        delayed["feature_cutoff_ts"] = pd.to_datetime(delayed["feature_cutoff_ts"]) + delay
    if "earliest_entry_ts" in delayed.columns:
        delayed["earliest_entry_ts"] = pd.to_datetime(delayed["earliest_entry_ts"]) + delay

    base_config = _backtest_config(config, 50.0)
    flipped_result = run_option_candle_backtest(
        signals=direction_flip,
        contract_catalog=catalog,
        option_bars=option_bars,
        config=base_config,
    )
    delayed_result = run_option_candle_backtest(
        signals=delayed,
        contract_catalog=catalog,
        option_bars=option_bars,
        config=base_config,
    )
    payload: dict[str, object] = {
        "schema_version": "compression_breakout_controls_v1",
        "direction_flip": _control_summary(flipped_result),
        "one_bar_delay": _control_summary(delayed_result),
        "control_status": "COMPLETED",
        "executable_option_pnl_certified": False,
    }
    payload["semantic_hash"] = _canonical_hash(payload)
    return payload


def run_compression_campaign(
    *,
    underlying_bars: pd.DataFrame,
    contract_catalog: pd.DataFrame | None = None,
    option_bars: pd.DataFrame | None = None,
    config: CompressionCampaignConfig | None = None,
    source_dataset_hash: str = "UNBOUND_SOURCE_HASH",
) -> CompressionCampaignResult:
    cfg = config or CompressionCampaignConfig()
    ledger = build_compression_signal_ledger(
        underlying_bars,
        config=cfg.ledger_config,
        source_dataset_hash=source_dataset_hash,
    )
    allowed = _allowed_dates(ledger.split_manifest, cfg.partition)
    holdout_dates = _date_set(ledger.split_manifest["partitions"]["holdout"])
    signals = ledger.signals.copy()
    if not signals.empty:
        signals = signals.loc[
            signals["session_date"].isin(allowed)
            & signals["selected_for_execution"].astype(bool)
        ].copy()

    base_result: CandleBacktestResult | None = None
    sensitivity: dict[str, object] = {
        "schema_version": "compression_breakout_sensitivity_v1",
        "result_label": "OPTION_INPUTS_NOT_SUPPLIED",
        "survived_cost_stress": False,
    }
    controls: dict[str, object] = {
        "schema_version": "compression_breakout_controls_v1",
        "control_status": "OPTION_INPUTS_NOT_SUPPLIED",
    }

    if (contract_catalog is None) != (option_bars is None):
        raise ValueError("catalog_and_option_bars_must_be_supplied_together")
    if contract_catalog is not None and option_bars is not None:
        catalog, bars = _filter_option_inputs(
            catalog=contract_catalog,
            option_bars=option_bars,
            allowed_dates=allowed,
            holdout_dates=holdout_dates,
            timezone=cfg.ledger_config.timezone,
        )
        base_result, sensitivity = _run_sensitivity(
            signals=signals,
            catalog=catalog,
            option_bars=bars,
            config=cfg,
        )
        controls = _run_controls(
            signals=signals,
            catalog=catalog,
            option_bars=bars,
            config=cfg,
        )

    campaign_status = "SIGNAL_LEDGER_READY_OPTION_INPUTS_REQUIRED"
    if base_result is not None:
        campaign_status = (
            "DEVELOPMENT_VALIDATION_CANDIDATE"
            if bool(sensitivity.get("survived_cost_stress"))
            else "CANDLE_PROXY_SCREEN_DID_NOT_PASS"
        )

    summary: dict[str, object] = {
        "schema_version": "compression_breakout_option_campaign_summary_v1",
        "strategy_id": "compression_breakout_v1",
        "partition": cfg.partition,
        "partition_session_count": len(allowed),
        "partition_signal_count": int(len(signals)),
        "split_manifest_hash": ledger.split_manifest["manifest_hash"],
        "ledger_semantic_hash": ledger.summary["ledger_semantic_hash"],
        "campaign_status": campaign_status,
        "cost_stress_result": sensitivity.get("result_label"),
        "control_status": controls.get("control_status"),
        "holdout_sealed": True,
        "holdout_outcomes_read": False,
        "executable_option_pnl_certified": False,
        "paper_live_allowed": False,
        "allowed_for_live_execution": False,
        "config": {
            **asdict(cfg),
            "ledger_config": asdict(cfg.ledger_config),
        },
    }
    summary["semantic_hash"] = _canonical_hash(summary)
    return CompressionCampaignResult(
        ledger=ledger,
        partition_signals=signals,
        base_result=base_result,
        sensitivity=sensitivity,
        controls=controls,
        summary=summary,
    )
