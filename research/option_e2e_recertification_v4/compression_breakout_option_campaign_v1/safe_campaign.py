from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

import pandas as pd

from .campaign import (
    CompressionCampaignConfig,
    CompressionCampaignResult,
    _allowed_dates,
    _date_set,
    _filter_option_inputs,
    run_compression_campaign as _run_campaign,
)
from .signal_ledger import build_compression_signal_ledger


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_compression_campaign_safe(
    *,
    underlying_bars: pd.DataFrame,
    contract_catalog: pd.DataFrame | None = None,
    option_bars: pd.DataFrame | None = None,
    config: CompressionCampaignConfig | None = None,
    source_dataset_hash: str = "UNBOUND_SOURCE_HASH",
) -> CompressionCampaignResult:
    cfg = config or CompressionCampaignConfig()
    if (contract_catalog is None) != (option_bars is None):
        raise ValueError("catalog_and_option_bars_must_be_supplied_together")

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

    if not signals.empty:
        return _run_campaign(
            underlying_bars=underlying_bars,
            contract_catalog=contract_catalog,
            option_bars=option_bars,
            config=cfg,
            source_dataset_hash=source_dataset_hash,
        )

    if contract_catalog is not None and option_bars is not None:
        _filter_option_inputs(
            catalog=contract_catalog,
            option_bars=option_bars,
            allowed_dates=allowed,
            holdout_dates=holdout_dates,
            timezone=cfg.ledger_config.timezone,
        )

    sensitivity: dict[str, object] = {
        "schema_version": "compression_breakout_sensitivity_v1",
        "result_label": "NO_SIGNALS_IN_PARTITION",
        "minimum_trades": cfg.minimum_trades,
        "scenarios": [],
        "survived_cost_stress": False,
        "executable_option_pnl_certified": False,
        "next_gate": "MORE_CHRONOLOGICAL_SESSIONS_REQUIRED",
    }
    sensitivity["semantic_hash"] = _canonical_hash(sensitivity)
    controls: dict[str, object] = {
        "schema_version": "compression_breakout_controls_v1",
        "direction_flip": None,
        "one_bar_delay": None,
        "control_status": "NO_SIGNALS",
        "executable_option_pnl_certified": False,
    }
    controls["semantic_hash"] = _canonical_hash(controls)

    summary: dict[str, object] = {
        "schema_version": "compression_breakout_option_campaign_summary_v1",
        "strategy_id": "compression_breakout_v1",
        "partition": cfg.partition,
        "partition_session_count": len(allowed),
        "partition_signal_count": 0,
        "split_manifest_hash": ledger.split_manifest["manifest_hash"],
        "ledger_semantic_hash": ledger.summary["ledger_semantic_hash"],
        "campaign_status": "NO_SIGNALS_IN_PARTITION",
        "cost_stress_result": sensitivity["result_label"],
        "control_status": controls["control_status"],
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
        base_result=None,
        sensitivity=sensitivity,
        controls=controls,
        summary=summary,
    )


__all__ = ["run_compression_campaign_safe"]
