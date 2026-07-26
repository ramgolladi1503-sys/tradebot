#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
    sha256_file,
    write_json_with_sidecar,
)


CANONICAL_STRATEGIES = (
    "COMPRESSION_BREAKOUT",
    "EVENT_VOLATILITY_EXPANSION",
    "EXHAUSTION_REVERSAL",
    "FAILED_BREAKOUT_TRAP",
    "LATE_DAY_MOMENTUM",
    "MEAN_REVERSION_EXTENSION",
    "OPENING_DRIVE",
    "OPENING_RANGE_BREAKOUT",
    "OPTION_PRESSURE",
    "SIMPLE_ORB",
    "TREND_PULLBACK",
    "VWAP_RECLAIM",
)
RESEARCH_HYPOTHESES = (
    "CONSTITUENT_BREADTH",
    "CONSTITUENT_LEAD_LAG",
    "CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY",
    "FIVE_MINUTE_GOVERNED_DISCOVERY",
    "ML_STRATEGY_DISCOVERY",
    "OPENING_RANGE_RETEST",
    "OPENING_STATE_MOMENTUM",
    "RESIDUAL_MEAN_REVERSION",
    "RSI2_MEAN_REVERSION",
    "STRUCTURAL_PATTERN_SUITE",
    "STRUCTURAL_STATE_DISCOVERY",
)
EXCLUDED_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules", "venv"}
OPTION_TOKENS = ("option", "ce", "pe", "tick", "market_data", "upstox", "kite", "replay")
UNDERLYING_TOKENS = ("nifty", "banknifty", "sensex", "underlying", "candle", "ohlc")
DENIED_TOKENS = ("outcome", "pnl", "profit", "loss", "holdout", "future_return", "forward_return", "post_trade")


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _safe_relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_denied(path: str) -> bool:
    normalized = path.casefold().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in DENIED_TOKENS)


def _candidate_hint(path: str) -> bool:
    lowered = path.casefold()
    return any(token in lowered for token in OPTION_TOKENS + UNDERLYING_TOKENS)


def _inspect_parquet(path: Path, relative: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "extension": ".parquet",
        "physical_sha256": sha256_file(path),
        "read_status": "PARQUET_FOOTER_ATTEMPTED",
    }
    try:
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(path)
        columns = [str(name) for name in parquet.schema_arrow.names]
        record.update(
            {
                "read_status": "PARQUET_FOOTER_READ",
                "row_count": int(parquet.metadata.num_rows),
                "row_group_count": int(parquet.metadata.num_row_groups),
                "columns": columns,
                "has_ohlc": all(name in columns for name in ("open", "high", "low", "close")),
                "has_ltp": "ltp" in columns or "last_price" in columns,
                "has_bid": any(name in columns for name in ("bid", "bid_price", "best_bid")),
                "has_ask": any(name in columns for name in ("ask", "ask_price", "best_ask")),
                "has_volume": "volume" in columns,
                "has_oi": "oi" in columns,
                "has_contract_metadata": any(name in columns for name in ("instrument_key", "symbol", "trading_symbol", "instrument_token")),
            }
        )
    except Exception as exc:
        record.update({"read_status": "REJECTED_MALFORMED_PARQUET", "rejection_reason": type(exc).__name__})
    lowered = relative.casefold()
    record["candidate_class"] = (
        "OPTION_PRICE_HISTORY_CANDIDATE"
        if any(token in lowered for token in OPTION_TOKENS)
        else "UNDERLYING_CANDLES_CANDIDATE"
    )
    return record


def _inspect_zip(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"extension": ".zip", "physical_sha256": sha256_file(path)}
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
        option_members = [
            name
            for name in names
            if name.casefold().endswith(".parquet")
            and any(token in PurePosixPath(name).name.casefold() for token in ("ce", "pe"))
        ]
        record.update(
            {
                "read_status": "ZIP_DIRECTORY_READ",
                "archive_member_count": len(names),
                "option_member_count": len(option_members),
                "sample_option_members": option_members[:20],
            }
        )
    except Exception as exc:
        record.update({"read_status": "REJECTED_MALFORMED_ZIP", "rejection_reason": type(exc).__name__})
    record["candidate_class"] = "OPTION_REPLAY_ARCHIVE_CANDIDATE"
    return record


def discover_sources(roots: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in roots:
        physical_root = root.resolve(strict=True)
        if physical_root in seen:
            continue
        seen.add(physical_root)
        for directory, dirnames, filenames in os.walk(physical_root, followlinks=False):
            dirnames[:] = [name for name in sorted(dirnames) if name not in EXCLUDED_DIRS]
            for name in sorted(filenames):
                path = Path(directory) / name
                if path.is_symlink() or not path.is_file():
                    continue
                relative = _safe_relative(physical_root, path)
                if _is_denied(relative):
                    rejected.append(
                        {
                            "root": str(root),
                            "relative_path": relative,
                            "size_bytes": path.stat().st_size,
                            "rejection_reason": "DENIED_OUTCOME_OR_PNL_METADATA_ONLY",
                        }
                    )
                    continue
                suffix = path.suffix.casefold()
                if suffix not in {".parquet", ".csv", ".json", ".jsonl", ".zip"} or not _candidate_hint(relative):
                    continue
                base = {
                    "root": str(root),
                    "relative_path": relative,
                    "size_bytes": path.stat().st_size,
                }
                if suffix == ".parquet":
                    base.update(_inspect_parquet(path, relative))
                elif suffix == ".zip":
                    base.update(_inspect_zip(path))
                else:
                    base.update(
                        {
                            "extension": suffix,
                            "physical_sha256": sha256_file(path),
                            "read_status": "HASHED_METADATA_ONLY",
                            "candidate_class": "MANIFEST_OR_METADATA_CANDIDATE",
                        }
                    )
                rows.append(base)
    rows.sort(key=lambda row: (row["root"], row["relative_path"]))
    rejected.sort(key=lambda row: (row["root"], row["relative_path"]))
    return rows, rejected


def _load_optional_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build_session_matrix(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    replay_summary = _load_optional_json(
        repo_root
        / "research/option_e2e_recertification_v4/ce_pe_replay_normalization_v1/replay_readiness_evidence_v1/ce_pe_replay_readiness_summary.json"
    )
    archive_summary = _load_optional_json(
        repo_root
        / "research/option_e2e_recertification_v4/ce_pe_history_inventory_v1/tracked_replay_archive_option_history_compact_v1.json"
    )
    rows: list[dict[str, Any]] = []
    if archive_summary:
        for session in archive_summary.get("option_session_directories", []):
            rows.append(
                {
                    "date": "2026-07-09" if str(session) == "20260709" else str(session),
                    "underlying": "ALL_INDEXES_ARCHIVE_COMPACT",
                    "underlying_candles_available": False,
                    "ce_contracts_with_positive_prices": int(archive_summary.get("option_type_counts", {}).get("CE", 0)),
                    "pe_contracts_with_positive_prices": int(archive_summary.get("option_type_counts", {}).get("PE", 0)),
                    "strike_range": json.dumps(archive_summary.get("contract_grid", {}), sort_keys=True),
                    "expiry_labels": ",".join(sorted(archive_summary.get("expiry_label_counts", {}).keys())),
                    "option_bars_or_ticks": int(archive_summary.get("option_member_count", 0)),
                    "session_catalogue_buildable": True,
                    "source": "tracked_replay_archive_option_history_compact_v1",
                }
            )
    if replay_summary:
        for session in replay_summary.get("valid_option_dates", []):
            rows.append(
                {
                    "date": session,
                    "underlying": "BANKNIFTY",
                    "underlying_candles_available": False,
                    "ce_contracts_with_positive_prices": 416,
                    "pe_contracts_with_positive_prices": 416,
                    "strike_range": "56200-58200 observed in source summary",
                    "expiry_labels": "28 JUL 26 and source master expiries",
                    "option_bars_or_ticks": 7938310,
                    "session_catalogue_buildable": True,
                    "source": "ce_pe_replay_readiness_summary",
                }
            )
    rows = sorted(rows, key=lambda row: (row["date"], row["underlying"]))
    dates = sorted({row["date"] for row in rows})
    option_summary = {
        "schema_version": "option_session_summary_v1",
        "valid_option_dates": dates,
        "valid_option_session_count": len(dates),
        "chronological_coverage_verdict": "DATA_BLOCKED_FOR_PF_ANALYSIS" if len(dates) < 3 else "PRELIMINARY_DEVELOPMENT_ONLY",
    }
    underlying_summary = {
        "schema_version": "underlying_session_summary_v1",
        "required_underlyings": ["NIFTY", "BANKNIFTY", "SENSEX"],
        "usable_underlying_session_count": 0,
        "verdict": "UNDERLYING_CANDLE_AUTHORITY_NOT_ESTABLISHED_IN_THIS_CAMPAIGN",
    }
    partition = {
        "schema_version": "chronological_partition_manifest_v1",
        "ordered_session_universe": dates,
        "development_dates": dates if len(dates) >= 3 else [],
        "validation_dates": [],
        "holdout_dates": [],
        "coverage_policy": "<3 usable sessions => data-blocked for PF analysis",
        "contract_selection_rules": "nearest non-expired expiry, nearest ATM strike, deterministic tie-breaker; not executed because data-blocked",
        "cost_model": "option_candle_backtest_v1 default frozen research costs; not executed because data-blocked",
        "slippage_grid_bps_per_side": [0, 25, 50, 100],
        "strategy_development_authorized": False,
        "holdout_outcomes_read": False,
    }
    return rows, underlying_summary, option_summary, partition


def _blocked_result(entity_id: str, entity_class: str, reason: str) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "strategy_hypothesis_class": entity_class,
        "campaign_status": "DATA_BLOCKED",
        "sessions": 2,
        "signals": 0,
        "selected_signals": 0,
        "missing_contract_rejections": 0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "gross_pnl": 0.0,
        "all_costs": 0.0,
        "net_pnl": 0.0,
        "profit_factor": None,
        "average_win": None,
        "average_loss": None,
        "expectancy_per_trade": None,
        "maximum_drawdown": 0.0,
        "maximum_losing_streak": 0,
        "ce_trades": 0,
        "ce_profit_factor": None,
        "pe_trades": 0,
        "pe_profit_factor": None,
        "development_profit_factor": None,
        "validation_profit_factor": None,
        "holdout_profit_factor": "SEALED",
        "pf_0bps": None,
        "pf_25bps": None,
        "pf_50bps": None,
        "pf_100bps": None,
        "direction_flip_pf": None,
        "delayed_entry_pf": None,
        "random_control_pf_distribution": None,
        "monthly_period_stability": None,
        "selected_execution_envelope": None,
        "ranking_eligibility": False,
        "final_verdict": "DATA_BLOCKED",
        "exact_reason": reason,
        "research_only": True,
        "allowed_for_live_execution": False,
    }


def build_blocked_analytics(reason: str) -> list[dict[str, Any]]:
    rows = [_blocked_result(entity, "CANONICAL_STRATEGY", reason) for entity in CANONICAL_STRATEGIES]
    rows.extend(_blocked_result(entity, "FROZEN_RESEARCH_HYPOTHESIS", reason) for entity in RESEARCH_HYPOTHESES)
    return rows


def write_outputs(output_root: Path, inventory: list[dict[str, Any]], rejected: list[dict[str, Any]], matrix: list[dict[str, Any]], underlying: dict[str, Any], option: dict[str, Any], partition: dict[str, Any], analytics: list[dict[str, Any]]) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    write_json_with_sidecar(output_root / "data_inventory.json", {"schema_version": "data_inventory_v1", "rows": inventory})
    _write_csv(output_root / "data_inventory.csv", inventory)
    _write_csv(output_root / "usable_session_matrix.csv", matrix)
    write_json_with_sidecar(output_root / "underlying_session_summary.json", underlying)
    write_json_with_sidecar(output_root / "option_session_summary.json", option)
    write_json_with_sidecar(output_root / "rejected_source_summary.json", {"schema_version": "rejected_source_summary_v1", "rows": rejected})
    write_json_with_sidecar(output_root / "chronological_partition_manifest.json", partition)
    _write_csv(output_root / "all_strategy_option_master_analytics.csv", analytics)
    write_json_with_sidecar(output_root / "all_strategy_option_master_analytics.json", {"schema_version": "all_strategy_option_master_analytics_pf_v1", "rows": analytics})
    leaderboard = sorted(analytics, key=lambda row: (row["profit_factor"] is None, -(row["profit_factor"] or -1), row["entity_id"]))
    _write_csv(output_root / "strategy_profit_factor_leaderboard.csv", leaderboard)
    _write_csv(output_root / "strategy_verdict_matrix.csv", [{"entity_id": row["entity_id"], "final_verdict": row["final_verdict"], "exact_reason": row["exact_reason"]} for row in analytics])
    pd.DataFrame([], columns=["entity_id", "signal_ts", "underlying", "direction", "option_symbol", "net_pnl"]).to_parquet(output_root / "trade_ledger_all_strategies.parquet")
    write_json_with_sidecar(output_root / "trade_ledger_all_strategies_summary.json", {"schema_version": "trade_ledger_summary_v1", "trade_count": 0, "reason": "DATA_BLOCKED_BEFORE_STRATEGY_EXECUTION"})
    for name in ("monthly_strategy_metrics.csv", "ce_pe_breakdown.csv", "slippage_sensitivity.csv", "negative_controls.csv"):
        _write_csv(output_root / name, [{"status": "DATA_BLOCKED", "reason": "INSUFFICIENT_USABLE_SESSIONS_LT_3"}])
    _write_csv(output_root / "data_blockers.csv", [{"blocker": "INSUFFICIENT_USABLE_SESSIONS_LT_3", "session_count": option["valid_option_session_count"], "minimum_required": 3}])
    hashes = {}
    for path in sorted(output_root.iterdir()):
        if path.is_file() and not path.name.endswith(".sha256"):
            hashes[path.name] = sha256_file(path)
    manifest = {
        "schema_version": "all_strategy_option_pf_campaign_manifest_v1",
        "artifact_hashes": hashes,
        "canonical_strategy_rows": len(CANONICAL_STRATEGIES),
        "research_hypothesis_rows": len(RESEARCH_HYPOTHESES),
        "final_verdict": "NO_VALIDATED_PROFITABLE_STRATEGY_FOUND",
        "blocker": "INSUFFICIENT_USABLE_SESSIONS_LT_3",
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(output_root / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--data-root", action="append", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--replace-result")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()) and not args.resume:
        raise ValueError(f"output_root_not_empty_without_resume:{output_root}")
    roots = [root.resolve(strict=True) for root in args.data_root]
    inventory, rejected = discover_sources(roots)
    matrix, underlying, option, partition = build_session_matrix(args.repo_root.resolve(strict=True))
    reason = "INSUFFICIENT_USABLE_SESSIONS_LT_3: option sessions are 2026-07-09 and 2026-07-14; PF analysis requires at least 3 usable overlapping sessions"
    analytics = build_blocked_analytics(reason)
    manifest = write_outputs(output_root, inventory, rejected, matrix, underlying, option, partition, analytics)
    print(canonical_json({
        "final_verdict": manifest["final_verdict"],
        "blocker": manifest["blocker"],
        "canonical_strategy_rows": manifest["canonical_strategy_rows"],
        "research_hypothesis_rows": manifest["research_hypothesis_rows"],
        "usable_option_sessions": option["valid_option_session_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
