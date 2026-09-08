from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .universe import CampaignUniverse


@dataclass(frozen=True)
class StrategyAnalyticsRow:
    entity_id: str
    canonical_entity_id: str
    entity_class: str
    campaign_action: str
    campaign_status: str
    adapter_status: str
    sample_partition: str | None
    sessions: int | None
    trades: int | None
    wins: int | None
    losses: int | None
    win_rate: float | None
    gross_pnl: float | None
    total_costs: float | None
    net_pnl: float | None
    profit_factor: float | None
    expectancy: float | None
    max_drawdown: float | None
    ce_trades: int | None
    ce_profit_factor: float | None
    pe_trades: int | None
    pe_profit_factor: float | None
    pf_50bps: float | None
    pf_100bps: float | None
    direction_flip_pf: float | None
    delayed_entry_pf: float | None
    validation_profit_factor: float | None
    holdout_profit_factor: float | None
    ranking_eligible: bool
    result_reason: str
    research_only: bool = True
    allowed_for_live_execution: bool = False


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _default_status(adapter_status: str, action: str) -> tuple[str, str]:
    if action == "RUN_CE_PE_CANDLE_CAMPAIGN":
        if adapter_status == "IMPLEMENTED":
            return "READY_FOR_DATA_RUN", "Adapter exists; historical option data is required."
        return "ADAPTER_REQUIRED", "A causal strategy-to-option adapter must be implemented."
    if action == "RUN_IF_FROZEN_SIGNAL_ADAPTER_EXISTS":
        return (
            "FROZEN_SIGNAL_ADAPTER_REQUIRED",
            "The research hypothesis must expose frozen causal signals before option analytics.",
        )
    if action == "RUN_NO_TRADE_FILTER_AUDIT":
        return (
            "NO_TRADE_FILTER_AUDIT_REQUIRED",
            "Measure rejection coverage and avoided-loss behaviour; profit factor is not primary.",
        )
    if action == "DEFER_UNTIL_CHILD_CAMPAIGNS_COMPLETE":
        return (
            "DEFERRED_UNTIL_CHILDREN_COMPLETE",
            "Aggregate and ensemble analytics require completed child-strategy results.",
        )
    if action == "BLOCK_MISSING_IMPLEMENTATION":
        return "BLOCKED_MISSING_IMPLEMENTATION", "Declared implementation is absent."
    return "NOT_A_STANDALONE_ANALYTICS_ROW", "Support entity or alias."


def _analytics_entities(universe: CampaignUniverse) -> list[Any]:
    included_actions = {
        "RUN_CE_PE_CANDLE_CAMPAIGN",
        "RUN_IF_FROZEN_SIGNAL_ADAPTER_EXISTS",
        "RUN_NO_TRADE_FILTER_AUDIT",
        "DEFER_UNTIL_CHILD_CAMPAIGNS_COMPLETE",
        "BLOCK_MISSING_IMPLEMENTATION",
    }
    return [
        row
        for row in universe.entries
        if row.option_campaign_action in included_actions
    ]


def build_master_analytics(
    universe: CampaignUniverse,
    completed_results: Iterable[dict[str, Any]] = (),
) -> tuple[tuple[StrategyAnalyticsRow, ...], dict[str, object]]:
    result_by_id: dict[str, dict[str, Any]] = {}
    for result in completed_results:
        entity_id = str(result.get("entity_id") or "").strip().upper()
        if not entity_id:
            raise ValueError("completed_result_missing_entity_id")
        if entity_id in result_by_id:
            raise ValueError(f"duplicate_completed_result:{entity_id}")
        result_by_id[entity_id] = dict(result)

    entities = _analytics_entities(universe)
    known_ids = {row.entity_id for row in entities}
    unknown_results = sorted(set(result_by_id) - known_ids)
    if unknown_results:
        raise ValueError(f"unknown_completed_result_ids:{unknown_results}")

    rows: list[StrategyAnalyticsRow] = []
    for entity in entities:
        result = result_by_id.get(entity.entity_id)
        if result is None:
            status, reason = _default_status(
                entity.adapter_status,
                entity.option_campaign_action,
            )
            rows.append(
                StrategyAnalyticsRow(
                    entity_id=entity.entity_id,
                    canonical_entity_id=entity.canonical_entity_id,
                    entity_class=entity.entity_class,
                    campaign_action=entity.option_campaign_action,
                    campaign_status=status,
                    adapter_status=entity.adapter_status,
                    sample_partition=None,
                    sessions=None,
                    trades=None,
                    wins=None,
                    losses=None,
                    win_rate=None,
                    gross_pnl=None,
                    total_costs=None,
                    net_pnl=None,
                    profit_factor=None,
                    expectancy=None,
                    max_drawdown=None,
                    ce_trades=None,
                    ce_profit_factor=None,
                    pe_trades=None,
                    pe_profit_factor=None,
                    pf_50bps=None,
                    pf_100bps=None,
                    direction_flip_pf=None,
                    delayed_entry_pf=None,
                    validation_profit_factor=None,
                    holdout_profit_factor=None,
                    ranking_eligible=False,
                    result_reason=reason,
                )
            )
            continue

        trades = int(result.get("trades") or 0)
        validation_pf = result.get("validation_profit_factor")
        holdout_pf = result.get("holdout_profit_factor")
        pf_50 = result.get("pf_50bps")
        ranking_eligible = bool(
            result.get("campaign_status") == "COMPLETED"
            and trades >= int(result.get("minimum_trades") or 30)
            and validation_pf is not None
            and float(validation_pf) > 1.0
            and pf_50 is not None
            and float(pf_50) > 1.0
        )
        rows.append(
            StrategyAnalyticsRow(
                entity_id=entity.entity_id,
                canonical_entity_id=entity.canonical_entity_id,
                entity_class=entity.entity_class,
                campaign_action=entity.option_campaign_action,
                campaign_status=str(result.get("campaign_status") or "COMPLETED"),
                adapter_status=entity.adapter_status,
                sample_partition=(
                    str(result.get("sample_partition"))
                    if result.get("sample_partition") is not None
                    else None
                ),
                sessions=(int(result["sessions"]) if result.get("sessions") is not None else None),
                trades=trades,
                wins=(int(result["wins"]) if result.get("wins") is not None else None),
                losses=(int(result["losses"]) if result.get("losses") is not None else None),
                win_rate=(float(result["win_rate"]) if result.get("win_rate") is not None else None),
                gross_pnl=(float(result["gross_pnl"]) if result.get("gross_pnl") is not None else None),
                total_costs=(float(result["total_costs"]) if result.get("total_costs") is not None else None),
                net_pnl=(float(result["net_pnl"]) if result.get("net_pnl") is not None else None),
                profit_factor=(float(result["profit_factor"]) if result.get("profit_factor") is not None else None),
                expectancy=(float(result["expectancy"]) if result.get("expectancy") is not None else None),
                max_drawdown=(float(result["max_drawdown"]) if result.get("max_drawdown") is not None else None),
                ce_trades=(int(result["ce_trades"]) if result.get("ce_trades") is not None else None),
                ce_profit_factor=(float(result["ce_profit_factor"]) if result.get("ce_profit_factor") is not None else None),
                pe_trades=(int(result["pe_trades"]) if result.get("pe_trades") is not None else None),
                pe_profit_factor=(float(result["pe_profit_factor"]) if result.get("pe_profit_factor") is not None else None),
                pf_50bps=(float(result["pf_50bps"]) if result.get("pf_50bps") is not None else None),
                pf_100bps=(float(result["pf_100bps"]) if result.get("pf_100bps") is not None else None),
                direction_flip_pf=(float(result["direction_flip_pf"]) if result.get("direction_flip_pf") is not None else None),
                delayed_entry_pf=(float(result["delayed_entry_pf"]) if result.get("delayed_entry_pf") is not None else None),
                validation_profit_factor=(float(validation_pf) if validation_pf is not None else None),
                holdout_profit_factor=(float(holdout_pf) if holdout_pf is not None else None),
                ranking_eligible=ranking_eligible,
                result_reason=str(result.get("result_reason") or "Completed campaign result."),
            )
        )

    rows.sort(
        key=lambda row: (
            not row.ranking_eligible,
            -(row.validation_profit_factor or float("-inf")),
            -(row.pf_50bps or float("-inf")),
            row.entity_id,
        )
    )
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row.campaign_status] = status_counts.get(row.campaign_status, 0) + 1
    summary_without_hash: dict[str, object] = {
        "schema_version": "all_strategy_option_master_analytics_v1",
        "analytics_entity_count": len(rows),
        "completed_result_count": len(result_by_id),
        "ranking_eligible_count": sum(1 for row in rows if row.ranking_eligible),
        "status_counts": dict(sorted(status_counts.items())),
        "coverage_complete": len(rows) == len(entities),
        "ranking_policy": (
            "Rank only completed strategies with minimum sample size, validation PF > 1, "
            "and 50-bps-per-side PF > 1; never rank aliases, helpers, filters, or blocked rows."
        ),
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    summary = dict(summary_without_hash)
    summary["semantic_hash"] = _canonical_hash(
        {
            "summary": summary_without_hash,
            "rows": [asdict(row) for row in rows],
        }
    )
    return tuple(rows), summary


def write_master_analytics(
    rows: Iterable[StrategyAnalyticsRow],
    summary: dict[str, object],
    output_dir: Path,
) -> dict[str, str]:
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_list = list(rows)

    json_path = output / "all_strategy_option_master_analytics.json"
    json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "rows": [asdict(row) for row in rows_list],
            },
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    csv_path = output / "all_strategy_option_master_analytics.csv"
    fieldnames = list(asdict(rows_list[0]).keys()) if rows_list else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for row in rows_list:
                writer.writerow(asdict(row))

    hashes: dict[str, str] = {}
    for path in (json_path, csv_path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[path.name] = digest
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{digest}  {path.name}\n",
            encoding="utf-8",
        )
    return hashes


__all__ = [
    "StrategyAnalyticsRow",
    "build_master_analytics",
    "write_master_analytics",
]
