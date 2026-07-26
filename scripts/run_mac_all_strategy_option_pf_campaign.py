#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
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
UNDERLYINGS = ("NIFTY", "BANKNIFTY", "SENSEX")
DATE_RE = re.compile(r"(20\d{2})-?(\d{2})-?(\d{2})")
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _schema_id(columns: list[str]) -> str:
    return hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()[:16]


def _date_from_parts(parts: tuple[str, ...]) -> str | None:
    for part in parts:
        match = DATE_RE.search(part)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def _parse_option_identity(path: Path, columns: set[str]) -> dict[str, Any]:
    name = path.stem.replace("_", " ")
    text = name.upper()
    option_type = "CE" if re.search(r"\bCE\b", text) else "PE" if re.search(r"\bPE\b", text) else None
    underlying = next((item for item in UNDERLYINGS if re.search(rf"\b{item}\b", text)), None)
    strike = None
    expiry = None
    if option_type:
        match = re.search(rf"\b(\d+(?:\.\d+)?)\s+{option_type}\b", text)
        if match:
            strike = float(match.group(1))
        expiry_match = re.search(rf"{option_type}\s+(\d{{1,2}})\s+([A-Z]{{3}})\s+(\d{{2,4}})", text)
        if expiry_match and expiry_match.group(2) in MONTHS:
            year = int(expiry_match.group(3))
            year = 2000 + year if year < 100 else year
            expiry = date(year, MONTHS[expiry_match.group(2)], int(expiry_match.group(1))).isoformat()
    has_column_identity = bool({"expiry", "strike", "option_type"} <= columns and ({"symbol", "tradingsymbol", "instrument_key", "instrument_token", "token"} & columns))
    return {
        "underlying_from_name": underlying,
        "option_type_from_name": option_type,
        "strike_from_name": strike,
        "expiry_from_name": expiry,
        "has_required_option_identity": has_column_identity or all([underlying, option_type, strike, expiry]),
    }


def _valid_ohlc_sample(df: pd.DataFrame) -> bool:
    required = ["open", "high", "low", "close"]
    if not all(col in df.columns for col in required) or df.empty:
        return False
    sample = df[required].apply(pd.to_numeric, errors="coerce")
    return bool(
        (
            (sample["open"] > 0)
            & (sample["high"] > 0)
            & (sample["low"] > 0)
            & (sample["close"] > 0)
            & (sample["high"] >= sample[["open", "close"]].max(axis=1))
            & (sample["low"] <= sample[["open", "close"]].min(axis=1))
            & (sample["high"] >= sample["low"])
        ).all()
    )


def _inspect_parquet(root: Path, path: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    rel = path.relative_to(root).as_posix()
    base: dict[str, Any] = {
        "root": str(root),
        "relative_path": rel,
        "date": _date_from_parts(path.relative_to(root).parts),
        "size_bytes": path.stat().st_size,
        "physical_sha256": sha256_file(path),
    }
    try:
        parquet = pq.ParquetFile(path)
        columns = [str(name) for name in parquet.schema_arrow.names]
        schema = _schema_id(columns)
        df = parquet.read_row_group(0).to_pandas().head(200)
        colset = set(columns)
        identity = _parse_option_identity(path, colset)
        has_ohlc = {"open", "high", "low", "close"} <= colset
        has_tick = bool({"ltp", "last_price"} & colset)
        valid_ohlc = _valid_ohlc_sample(df) if has_ohlc else False
        positive_ltp = False
        if has_tick and not df.empty:
            ltp_col = "ltp" if "ltp" in df.columns else "last_price"
            positive_ltp = bool((pd.to_numeric(df[ltp_col], errors="coerce") > 0).any())
        lower = rel.casefold()
        explicit_option_name = bool(identity["option_type_from_name"] and identity["strike_from_name"] and identity["expiry_from_name"])
        is_underlying = "underlying/" in lower and has_ohlc and any(item in path.name.upper() for item in UNDERLYINGS) and not explicit_option_name
        is_mock = bool("mock" in lower or ("mock" in df.columns and df["mock"].astype(str).str.lower().eq("true").any()))
        if is_underlying and valid_ohlc:
            classification = "UNDERLYING_1M_OHLCV"
        elif has_ohlc and valid_ohlc and identity["has_required_option_identity"] and not is_mock:
            classification = "OPTION_1M_OHLCV"
        elif has_tick and positive_ltp and identity["has_required_option_identity"] and not is_mock:
            classification = "OPTION_LTP_TICKS"
        elif has_ohlc and ("options/" in lower or "opt" in lower) and (is_mock or not identity["has_required_option_identity"]):
            classification = "ZERO_PRICE_PLACEHOLDER" if is_mock else "UNKNOWN"
        elif {"strategy_id", "signal_ts"} & colset:
            classification = "STRATEGY_CANDIDATE_ROWS"
        else:
            classification = "UNKNOWN"
        return {
            **base,
            "read_status": "PARQUET_FOOTER_AND_SAMPLE_READ",
            "row_count": int(parquet.metadata.num_rows),
            "row_group_count": int(parquet.metadata.num_row_groups),
            "columns": columns,
            "schema_id": schema,
            "classification": classification,
            "valid_ohlc_sample": valid_ohlc,
            "positive_ltp_sample": positive_ltp,
            **identity,
            "timestamp_min_sample": str(df.get("timestamp", df.get("date", pd.Series(dtype=str))).min()) if not df.empty else None,
            "timestamp_max_sample": str(df.get("timestamp", df.get("date", pd.Series(dtype=str))).max()) if not df.empty else None,
        }
    except Exception as exc:
        return {**base, "read_status": "REJECTED_MALFORMED_PARQUET", "classification": "MALFORMED", "rejection_reason": type(exc).__name__}


def inspect_replay_root(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    files = sorted(path for path in root.rglob("*.parquet") if path.is_file() and not path.is_symlink())
    inventory = [_inspect_parquet(root, path) for path in files]
    schema_groups: dict[str, dict[str, Any]] = {}
    for row in inventory:
        schema = row.get("schema_id", "malformed")
        group = schema_groups.setdefault(
            schema,
            {
                "schema_id": schema,
                "columns": row.get("columns", []),
                "file_count": 0,
                "row_count": 0,
                "classifications": Counter(),
                "representative_files": [],
            },
        )
        group["file_count"] += 1
        group["row_count"] += int(row.get("row_count") or 0)
        group["classifications"][row["classification"]] += 1
        if len(group["representative_files"]) < 5:
            group["representative_files"].append(row["relative_path"])
    schema_rows = []
    for group in schema_groups.values():
        group["classifications"] = dict(group["classifications"])
        schema_rows.append(group)
    by_date: dict[str, dict[str, Any]] = defaultdict(lambda: {"date": None, "parquet_count": 0, "bytes": 0, "row_count": 0, "classifications": Counter()})
    for row in inventory:
        session = row.get("date") or "UNKNOWN"
        bucket = by_date[session]
        bucket["date"] = session
        bucket["parquet_count"] += 1
        bucket["bytes"] += int(row["size_bytes"])
        bucket["row_count"] += int(row.get("row_count") or 0)
        bucket["classifications"][row["classification"]] += 1
    coverage = []
    for bucket in by_date.values():
        bucket["classifications"] = dict(bucket["classifications"])
        coverage.append(bucket)
    rejections = [row for row in inventory if row["classification"] in {"MALFORMED", "ZERO_PRICE_PLACEHOLDER", "UNKNOWN"}]
    return inventory, sorted(schema_rows, key=lambda row: row["schema_id"]), sorted(coverage, key=lambda row: str(row["date"])), rejections


def build_session_matrix(inventory: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    sessions: dict[tuple[str, str], dict[str, Any]] = {}
    for row in inventory:
        session_date = row.get("date")
        if not session_date:
            continue
        underlyings = []
        if row["classification"] == "UNDERLYING_1M_OHLCV":
            underlyings = [next((item for item in UNDERLYINGS if item in row["relative_path"].upper()), "UNKNOWN")]
        else:
            underlyings = [row.get("underlying_from_name") or "UNKNOWN"]
        for underlying in underlyings:
            key = (session_date, underlying)
            item = sessions.setdefault(
                key,
                {
                    "date": session_date,
                    "underlying": underlying,
                    "underlying_candles_available": False,
                    "underlying_row_count": 0,
                    "candidate_rows_available": False,
                    "candidate_strategy_ids": "",
                    "option_contract_count": 0,
                    "ce_contract_count": 0,
                    "pe_contract_count": 0,
                    "positive_option_bar_count": 0,
                    "positive_option_tick_count": 0,
                    "expiry_count": 0,
                    "strike_min": None,
                    "strike_max": None,
                    "execution_window_overlap": False,
                    "session_catalogue_buildable": False,
                    "campaign_usable": False,
                    "exact_blocker": "",
                    "source_hashes": [],
                },
            )
            item["source_hashes"].append(row["physical_sha256"])
            if row["classification"] == "UNDERLYING_1M_OHLCV":
                item["underlying_candles_available"] = True
                item["underlying_row_count"] += int(row.get("row_count") or 0)
            elif row["classification"] == "STRATEGY_CANDIDATE_ROWS":
                item["candidate_rows_available"] = True
            elif row["classification"] in {"OPTION_1M_OHLCV", "OPTION_LTP_TICKS"}:
                item["option_contract_count"] += 1
                if row.get("option_type_from_name") == "CE":
                    item["ce_contract_count"] += 1
                if row.get("option_type_from_name") == "PE":
                    item["pe_contract_count"] += 1
                if row["classification"] == "OPTION_1M_OHLCV":
                    item["positive_option_bar_count"] += int(row.get("row_count") or 0)
                else:
                    item["positive_option_tick_count"] += int(row.get("row_count") or 0)
                strikes = [x for x in [row.get("strike_from_name")] if x is not None]
                if strikes:
                    item["strike_min"] = min([item["strike_min"]] + strikes) if item["strike_min"] is not None else min(strikes)
                    item["strike_max"] = max([item["strike_max"]] + strikes) if item["strike_max"] is not None else max(strikes)
    matrix = []
    for item in sessions.values():
        has_signal = item["underlying_candles_available"] or item["candidate_rows_available"]
        has_option = item["option_contract_count"] > 0 and (item["ce_contract_count"] > 0 or item["pe_contract_count"] > 0)
        item["execution_window_overlap"] = bool(has_signal and has_option)
        item["session_catalogue_buildable"] = bool(has_option and item["strike_min"] is not None and item["strike_max"] is not None)
        item["campaign_usable"] = bool(has_signal and item["session_catalogue_buildable"] and item["execution_window_overlap"])
        blockers = []
        if not has_signal:
            blockers.append("MISSING_SIGNAL_AUTHORITY")
        if item["option_contract_count"] == 0:
            blockers.append("MISSING_POSITIVE_OPTION_PRICE_AUTHORITY")
        if item["ce_contract_count"] == 0 and item["pe_contract_count"] == 0:
            blockers.append("MISSING_CE_PE_IDENTITY")
        if item["strike_min"] is None:
            blockers.append("MISSING_STRIKE_IDENTITY")
        item["exact_blocker"] = "OK" if item["campaign_usable"] else "|".join(blockers)
        item["source_hashes"] = ",".join(sorted(set(item["source_hashes"])))
        matrix.append(item)
    usable_dates = sorted({row["date"] for row in matrix if row["campaign_usable"]})
    underlying_dates = sorted({row["date"] for row in inventory if row["classification"] == "UNDERLYING_1M_OHLCV"})
    option_dates = sorted({row["date"] for row in inventory if row["classification"] in {"OPTION_1M_OHLCV", "OPTION_LTP_TICKS"}})
    underlying_summary = {"schema_version": "underlying_session_summary_v2", "usable_underlying_session_count": len(underlying_dates), "dates": underlying_dates}
    option_summary = {"schema_version": "option_session_summary_v2", "valid_option_session_count": len(option_dates), "valid_option_dates": option_dates}
    if len(usable_dates) >= 100:
        dev_end = int(len(usable_dates) * 0.6)
        val_end = int(len(usable_dates) * 0.8)
        development, validation, holdout = usable_dates[:dev_end], usable_dates[dev_end:val_end], usable_dates[val_end:]
        policy = ">=100 sessions: 60/20/20"
    elif len(usable_dates) >= 30:
        split = max(1, int(len(usable_dates) * 0.8))
        development, validation, holdout = usable_dates[:split], usable_dates[split:], []
        policy = "30-99 sessions: development + validation"
    elif len(usable_dates) >= 3:
        development, validation, holdout = usable_dates, [], []
        policy = "3-29 sessions: preliminary development only"
    else:
        development, validation, holdout = [], [], []
        policy = "<3 sessions: DATA_BLOCKED"
    partition = {
        "schema_version": "chronological_partition_manifest_v2",
        "ordered_session_universe": usable_dates,
        "development_dates": development,
        "validation_dates": validation,
        "holdout_dates": holdout,
        "coverage_policy": policy,
        "holdout_outcomes_read": False,
    }
    return sorted(matrix, key=lambda row: (row["date"], row["underlying"])), underlying_summary, option_summary, partition


def _blocked_result(entity_id: str, entity_class: str, reason: str, sessions: int, verdict: str) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "strategy_hypothesis_class": entity_class,
        "campaign_status": "DATA_BLOCKED",
        "sessions": sessions,
        "signals": 0,
        "selected_signals": 0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "profit_factor": None,
        "expectancy_per_trade": None,
        "maximum_drawdown": 0.0,
        "ce_trades": 0,
        "ce_profit_factor": None,
        "pe_trades": 0,
        "pe_profit_factor": None,
        "validation_profit_factor": None,
        "holdout_profit_factor": "SEALED",
        "pf_0bps": None,
        "pf_25bps": None,
        "pf_50bps": None,
        "pf_100bps": None,
        "negative_controls": "NOT_RUN_DATA_BLOCKED",
        "ranking_eligibility": False,
        "final_verdict": "DATA_BLOCKED",
        "exact_reason": reason,
        "source_file_hashes": "",
        "research_only": True,
        "allowed_for_live_execution": False,
        "campaign_verdict": verdict,
    }


def build_blocked_analytics(reason: str, sessions: int = 0, verdict: str = "DATA_REASSESSMENT_IN_PROGRESS") -> list[dict[str, Any]]:
    rows = [_blocked_result(entity, "CANONICAL_STRATEGY", reason, sessions, verdict) for entity in CANONICAL_STRATEGIES]
    rows.extend(_blocked_result(entity, "FROZEN_RESEARCH_HYPOTHESIS", reason, sessions, verdict) for entity in RESEARCH_HYPOTHESES)
    return rows


def _write_outputs(output_root: Path, inventory: list[dict[str, Any]], schema_groups: list[dict[str, Any]], coverage: list[dict[str, Any]], rejections: list[dict[str, Any]], matrix: list[dict[str, Any]], underlying: dict[str, Any], option: dict[str, Any], partition: dict[str, Any], analytics: list[dict[str, Any]], verdict: str, blocker: str) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    managed_names = {
        "all_strategy_option_master_analytics.csv",
        "all_strategy_option_master_analytics.json",
        "ce_pe_breakdown.csv",
        "chronological_partition_manifest.json",
        "data_blockers.csv",
        "kite_candidate_replay_date_coverage.csv",
        "kite_candidate_replay_inventory.csv",
        "kite_candidate_replay_inventory.json",
        "kite_candidate_replay_price_usability.csv",
        "kite_candidate_replay_rejections.csv",
        "kite_candidate_replay_schema_groups.json",
        "kite_candidate_replay_session_matrix.csv",
        "manifest.json",
        "monthly_strategy_metrics.csv",
        "negative_controls.csv",
        "option_session_summary.json",
        "slippage_sensitivity.csv",
        "strategy_profit_factor_leaderboard.csv",
        "strategy_verdict_matrix.csv",
        "trade_ledger_all_strategies.parquet",
        "trade_ledger_all_strategies_summary.json",
        "underlying_session_summary.json",
        "data_inventory.csv",
        "data_inventory.json",
        "rejected_source_summary.json",
        "usable_session_matrix.csv",
    }
    for name in managed_names | {f"{name}.sha256" for name in managed_names}:
        path = output_root / name
        if path.exists():
            path.unlink()
    write_json_with_sidecar(output_root / "kite_candidate_replay_inventory.json", {"schema_version": "kite_candidate_replay_inventory_v1", "rows": inventory})
    _write_csv(output_root / "kite_candidate_replay_inventory.csv", inventory)
    write_json_with_sidecar(output_root / "kite_candidate_replay_schema_groups.json", {"schema_version": "kite_candidate_replay_schema_groups_v1", "rows": schema_groups})
    _write_csv(output_root / "kite_candidate_replay_date_coverage.csv", coverage)
    _write_csv(output_root / "kite_candidate_replay_rejections.csv", rejections)
    _write_csv(output_root / "kite_candidate_replay_session_matrix.csv", matrix)
    _write_csv(output_root / "kite_candidate_replay_price_usability.csv", [{"classification": k, "file_count": v} for k, v in sorted(Counter(row["classification"] for row in inventory).items())])
    write_json_with_sidecar(output_root / "underlying_session_summary.json", underlying)
    write_json_with_sidecar(output_root / "option_session_summary.json", option)
    write_json_with_sidecar(output_root / "chronological_partition_manifest.json", partition)
    write_json_with_sidecar(output_root / "all_strategy_option_master_analytics.json", {"schema_version": "all_strategy_option_master_analytics_pf_v2", "rows": analytics})
    _write_csv(output_root / "all_strategy_option_master_analytics.csv", analytics)
    _write_csv(output_root / "strategy_profit_factor_leaderboard.csv", analytics)
    _write_csv(output_root / "strategy_verdict_matrix.csv", [{"entity_id": row["entity_id"], "final_verdict": row["final_verdict"], "exact_reason": row["exact_reason"]} for row in analytics])
    pd.DataFrame([], columns=["entity_id", "signal_ts", "underlying", "direction", "option_symbol", "net_pnl"]).to_parquet(output_root / "trade_ledger_all_strategies.parquet")
    write_json_with_sidecar(output_root / "trade_ledger_all_strategies_summary.json", {"schema_version": "trade_ledger_summary_v2", "trade_count": 0, "reason": blocker})
    _write_csv(output_root / "monthly_strategy_metrics.csv", [{"status": "DATA_BLOCKED", "reason": blocker}])
    _write_csv(output_root / "ce_pe_breakdown.csv", [{"status": "DATA_BLOCKED", "reason": blocker}])
    _write_csv(output_root / "slippage_sensitivity.csv", [{"bps_per_side": bps, "status": "DATA_BLOCKED", "reason": blocker} for bps in (0, 25, 50, 100)])
    _write_csv(output_root / "negative_controls.csv", [{"status": "NOT_RUN_DATA_BLOCKED", "reason": blocker}])
    _write_csv(output_root / "data_blockers.csv", [{"blocker": blocker, "actual_usable_session_count": len(partition["ordered_session_universe"])}])
    hashes = {path.name: sha256_file(path) for path in sorted(output_root.iterdir()) if path.is_file() and not path.name.endswith(".sha256")}
    manifest = {
        "schema_version": "all_strategy_option_pf_campaign_manifest_v2",
        "v1_invalidation": "INVALID_IMPLEMENTATION_MISSED_KITE_CANDIDATE_REPLAY_CORPUS",
        "final_verdict": verdict,
        "blocker": blocker,
        "total_parquet_files": len(inventory),
        "date_range": [coverage[0]["date"], coverage[-1]["date"]] if coverage else [],
        "actual_usable_session_count": len(partition["ordered_session_universe"]),
        "artifact_hashes": hashes,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(output_root / "manifest.json", manifest)
    return manifest


def write_outputs(output_root: Path, inventory: list[dict[str, Any]], rejected: list[dict[str, Any]], matrix: list[dict[str, Any]], underlying: dict[str, Any], option: dict[str, Any], partition: dict[str, Any], analytics: list[dict[str, Any]]) -> dict[str, Any]:
    return _write_outputs(output_root, inventory, [], [], rejected, matrix, underlying, option, partition, analytics, "DATA_REASSESSMENT_IN_PROGRESS", "TEST_BLOCKER")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--data-root", action="append", type=Path, required=True)
    parser.add_argument("--kite-replay-root", type=Path, default=Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--replace-result")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()) and not args.resume:
        raise ValueError(f"output_root_not_empty_without_resume:{output_root}")
    kite_root = args.kite_replay_root.resolve(strict=True)
    inventory, schema_groups, coverage, rejections = inspect_replay_root(kite_root)
    matrix, underlying, option, partition = build_session_matrix(inventory)
    if not any(row["classification"] in {"OPTION_1M_OHLCV", "OPTION_LTP_TICKS"} for row in inventory):
        verdict = "KITE_REPLAY_CONTAINS_NO_USABLE_OPTION_PRICE_AUTHORITY"
        blocker = "KITE_REPLAY_HAS_UNDERLYING_CANDLES_BUT_NO_OPTION_PRICE_ROWS_WITH_EXPIRY_STRIKE_CE_PE_CONTRACT_IDENTITY"
    elif len(partition["ordered_session_universe"]) < 3:
        verdict = "DATA_BLOCKED_INSUFFICIENT_OVERLAPPING_OPTION_HISTORY"
        blocker = "INSUFFICIENT_OVERLAPPING_OPTION_HISTORY_LT_3"
    else:
        verdict = "DATA_REASSESSMENT_IN_PROGRESS"
        blocker = "STRATEGY_EXECUTION_REQUIRES_SEPARATE_AUTHORIZED_REPAIR"
    analytics = build_blocked_analytics(blocker, len(partition["ordered_session_universe"]), verdict)
    manifest = _write_outputs(output_root, inventory, schema_groups, coverage, rejections, matrix, underlying, option, partition, analytics, verdict, blocker)
    print(canonical_json({k: manifest[k] for k in ("final_verdict", "blocker", "total_parquet_files", "actual_usable_session_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
