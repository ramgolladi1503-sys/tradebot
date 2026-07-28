#!/usr/bin/env python3
"""Stage-gated reverse-causal option expansion discovery.

Research-only. No broker calls, order actions, runtime wiring, live config, or
strategy registration. The runner separates structural/gross evidence from
execution certification so missing bid/ask/depth blocks only the stages that
need observed execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_HORIZONS = (3, 5, 10, 15, 20, 30)
EVENT_POINT_THRESHOLD = 25.0
EVENT_ADVERSE_LIMIT = 15.0
CONTROL_SAMPLE_PER_EVENT = 3
NON_ACTION_FLAGS = {
    "research_only": True,
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "append": False,
}
QUOTE_FIELDS = {"bid", "ask", "best_bid", "best_ask", "spread", "bid_ask_spread", "ltp_bid", "ltp_ask"}
DEPTH_FIELDS = {"depth", "bid_depth", "ask_depth", "order_book", "bid_qty", "ask_qty"}
REQUIRED_OPTION_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "expiry",
    "strike",
    "option_type",
    "trading_symbol",
    "expired_instrument_key",
}


@dataclass(frozen=True)
class FileAudit:
    path: str
    exists: bool
    size_bytes: int | None
    sha256: str | None
    first_bytes_hex: str | None
    is_lfs_pointer: bool
    file_kind: str
    row_count: int | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    schema_fingerprint: str | None = None
    columns: list[str] | None = None


@dataclass(frozen=True)
class DataInventory:
    source_root: str
    source_root_exists: bool
    contract_inventory: FileAudit
    atm_selection_ledger: FileAudit
    underlying_source: FileAudit | None
    lfs_candidate_files: list[FileAudit]
    contract_inventory_rows: int
    valid_contract_rows: int
    expiries: int
    option_types: list[str]
    one_minute_rows: int
    first_candle: str | None
    last_candle: str | None
    has_real_instrument_identity: bool
    has_option_premium_ohlcv: bool
    has_underlying_observations: bool
    has_underlying_provenance_hash: bool
    has_observed_quote_or_spread: bool
    has_depth: bool
    option_schema_fingerprint: str | None
    source_hash: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def schema_fingerprint(df: pd.DataFrame) -> str:
    return stable_json_sha256({name: str(dtype) for name, dtype in df.dtypes.items()})


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    head = path.read_bytes()[:256]
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def audit_file(path: Path, file_kind: str, timestamp_column: str = "timestamp") -> FileAudit:
    if not path.exists():
        return FileAudit(str(path), False, None, None, None, False, file_kind)
    head = path.read_bytes()[:16]
    row_count = None
    first_ts = None
    last_ts = None
    fingerprint = None
    columns = None
    if path.suffix == ".parquet" and not is_lfs_pointer(path):
        df = pd.read_parquet(path)
        row_count = int(len(df))
        columns = list(df.columns)
        fingerprint = schema_fingerprint(df)
        if timestamp_column in df.columns:
            ts = pd.to_datetime(df[timestamp_column], errors="coerce")
            if ts.notna().any():
                first_ts = str(ts.min())
                last_ts = str(ts.max())
    return FileAudit(
        path=str(path),
        exists=True,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        first_bytes_hex=head.hex(),
        is_lfs_pointer=is_lfs_pointer(path),
        file_kind=file_kind,
        row_count=row_count,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        schema_fingerprint=fingerprint,
        columns=columns,
    )


def load_contract_inventory(source_root: Path) -> pd.DataFrame:
    path = source_root / "manifests" / "contract_inventory.parquet"
    if not path.exists():
        raise FileNotFoundError(f"missing contract inventory: {path}")
    return pd.read_parquet(path)


def first_existing_option_file(source_root: Path, contracts: pd.DataFrame) -> Path | None:
    for rel in contracts.get("normalized_1m_path", pd.Series(dtype=str)).dropna():
        path = source_root / str(rel)
        if path.exists() and not is_lfs_pointer(path):
            return path
    return None


def build_inventory(source_root: Path, contracts: pd.DataFrame, repo_root: Path) -> DataInventory:
    valid = contracts[contracts.get("final_status").eq("VALID_COMPLETE")].copy()
    contract_audit = audit_file(source_root / "manifests" / "contract_inventory.parquet", "contract_inventory")
    atm_path = source_root / "manifests" / "atm_selection_ledger.parquet"
    atm_audit = audit_file(atm_path, "atm_selection_ledger", "selection_timestamp")
    atm = pd.read_parquet(atm_path) if atm_path.exists() else pd.DataFrame()

    underlying_audit = None
    has_underlying_hash = False
    if not atm.empty and "underlying_source_path" in atm.columns:
        source_paths = sorted({str(p) for p in atm["underlying_source_path"].dropna()})
        if len(source_paths) == 1:
            underlying_path = Path(source_paths[0])
            underlying_audit = audit_file(underlying_path, "underlying_source")
            if underlying_audit.exists and underlying_audit.sha256:
                observed = atm.get("underlying_source_hash", pd.Series(dtype=str)).fillna("").astype(str)
                has_underlying_hash = bool((observed == underlying_audit.sha256).all())

    lfs_candidates = [
        audit_file(repo_root / "runtime/strategy_validation/resolved_option_ticks_20260702.parquet", "lfs_candidate")
    ]
    option_sample = first_existing_option_file(source_root, valid)
    option_audit = audit_file(option_sample, "option_sample") if option_sample else None

    first_candle = pd.to_datetime(valid.get("first_candle", pd.Series(dtype=str)), errors="coerce").min()
    last_candle = pd.to_datetime(valid.get("last_candle", pd.Series(dtype=str)), errors="coerce").max()
    option_cols = set(option_audit.columns or []) if option_audit else set()
    matrix_inputs = {
        "contract_inventory_sha256": contract_audit.sha256,
        "atm_selection_ledger_sha256": atm_audit.sha256,
        "underlying_sha256": underlying_audit.sha256 if underlying_audit else None,
        "lfs_candidate_sha256": [item.sha256 for item in lfs_candidates],
        "option_sample_schema": option_audit.schema_fingerprint if option_audit else None,
        "valid_contract_rows": int(len(valid)),
    }
    return DataInventory(
        source_root=str(source_root),
        source_root_exists=source_root.exists(),
        contract_inventory=contract_audit,
        atm_selection_ledger=atm_audit,
        underlying_source=underlying_audit,
        lfs_candidate_files=lfs_candidates,
        contract_inventory_rows=int(len(contracts)),
        valid_contract_rows=int(len(valid)),
        expiries=int(valid.get("expiry", pd.Series(dtype=str)).nunique()),
        option_types=sorted(str(v) for v in valid.get("option_type", pd.Series(dtype=str)).dropna().unique()),
        one_minute_rows=int(pd.to_numeric(valid.get("one_minute_row_count"), errors="coerce").fillna(0).sum()),
        first_candle=None if pd.isna(first_candle) else str(first_candle),
        last_candle=None if pd.isna(last_candle) else str(last_candle),
        has_real_instrument_identity=has_identity(valid),
        has_option_premium_ohlcv=bool(option_cols >= REQUIRED_OPTION_COLUMNS),
        has_underlying_observations=bool(underlying_audit and underlying_audit.exists and not underlying_audit.is_lfs_pointer),
        has_underlying_provenance_hash=has_underlying_hash,
        has_observed_quote_or_spread=bool(option_cols & QUOTE_FIELDS),
        has_depth=bool(option_cols & DEPTH_FIELDS),
        option_schema_fingerprint=option_audit.schema_fingerprint if option_audit else None,
        source_hash=stable_json_sha256(matrix_inputs),
    )


def has_identity(df: pd.DataFrame) -> bool:
    required = ["expired_instrument_key", "expiry", "strike", "option_type", "trading_symbol"]
    return bool(len(df)) and all(col in df.columns and df[col].notna().all() for col in required)


def source_integrity_blockers(inventory: DataInventory) -> list[str]:
    blockers = []
    if not inventory.source_root_exists:
        blockers.append("SOURCE_ROOT_MISSING")
    if inventory.contract_inventory.is_lfs_pointer:
        blockers.append("CONTRACT_INVENTORY_IS_LFS_POINTER")
    if not inventory.has_real_instrument_identity:
        blockers.append("OPTION_INSTRUMENT_IDENTITY_INVALID")
    if not inventory.has_option_premium_ohlcv:
        blockers.append("OPTION_OHLCV_SCHEMA_INVALID")
    if any(item.is_lfs_pointer for item in inventory.lfs_candidate_files):
        blockers.append("LFS_POINTER_SOURCE_PRESENT")
    return blockers


def capability_matrix(inventory: DataInventory) -> dict[str, dict[str, Any]]:
    stage_a_blockers = source_integrity_blockers(inventory)
    stage_b_blockers = list(stage_a_blockers)
    if not inventory.has_underlying_observations:
        stage_b_blockers.append("UNDERLYING_OBSERVATIONS_MISSING_OPTION_ONLY_REQUIRED")
    stage_c_blockers = list(stage_b_blockers)
    stage_d_blockers = list(stage_c_blockers)
    stage_e_blockers = list(stage_c_blockers)
    if not inventory.has_observed_quote_or_spread:
        stage_e_blockers.append("AUTHORITATIVE_QUOTE_OR_SPREAD_MISSING")
    stage_f_blockers = list(stage_e_blockers)
    stage_f_blockers.extend(
        [
            "FROZEN_MECHANISM_MISSING",
            "UNTOUCHED_HOLDOUT_NOT_EXECUTED",
            "INDEPENDENT_FINAL_AUDIT_NOT_EXECUTED",
        ]
    )
    return {
        "A_SOURCE_INTEGRITY": {"can_run": not stage_a_blockers, "classification": "SOURCE_INTEGRITY_REPAIRED", "blockers": stage_a_blockers},
        "B_CAUSAL_STRUCTURAL_DISCOVERY": {"can_run": not stage_b_blockers, "classification": "STRUCTURAL_DISCOVERY_ONLY", "blockers": stage_b_blockers},
        "C_GROSS_OUTCOME_EVALUATION": {"can_run": not stage_c_blockers, "classification": "GROSS_OUTCOME_ONLY", "blockers": stage_c_blockers},
        "D_ASSUMPTION_COST_STRESS": {"can_run": not stage_d_blockers, "classification": "ASSUMPTION_BASED_COST_STRESS_ONLY", "blockers": stage_d_blockers},
        "E_EXECUTION_CERTIFICATION": {"can_run": not stage_e_blockers, "classification": "EXECUTION_CERTIFICATION", "blockers": stage_e_blockers},
        "F_FINAL_VALIDATED_EDGE": {"can_run": False, "classification": "VALIDATED_OPTION_EXPANSION_EDGE", "blockers": stage_f_blockers},
    }


def verdict_from_matrix(matrix: dict[str, dict[str, Any]], precursor_rows: int) -> str:
    if not matrix["A_SOURCE_INTEGRITY"]["can_run"]:
        return "INVALID_EVIDENCE_PIPELINE"
    if precursor_rows == 0 and matrix["C_GROSS_OUTCOME_EVALUATION"]["can_run"]:
        return "NO_DISCRIMINATIVE_PRECURSOR"
    if matrix["D_ASSUMPTION_COST_STRESS"]["can_run"]:
        return "ASSUMPTION_BASED_COST_STRESS_ONLY"
    if matrix["C_GROSS_OUTCOME_EVALUATION"]["can_run"]:
        return "GROSS_OUTCOME_ONLY"
    if matrix["B_CAUSAL_STRUCTURAL_DISCOVERY"]["can_run"]:
        return "STRUCTURAL_DISCOVERY_ONLY"
    return "SOURCE_INTEGRITY_REPAIRED"


def load_option_population(source_root: Path, contracts: pd.DataFrame) -> pd.DataFrame:
    frames = []
    valid = contracts[contracts.get("final_status").eq("VALID_COMPLETE")]
    for rel in valid["normalized_1m_path"].dropna():
        path = source_root / str(rel)
        if not path.exists() or is_lfs_pointer(path):
            continue
        frame = pd.read_parquet(path)
        missing = REQUIRED_OPTION_COLUMNS - set(frame.columns)
        if missing:
            continue
        selected_columns = sorted((REQUIRED_OPTION_COLUMNS | {"open_interest"}) & set(frame.columns))
        frames.append(frame[selected_columns])
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "expiry", "strike", "option_type"])
    df["session"] = df["timestamp"].dt.date.astype(str)
    df["minute_of_day"] = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date.astype(str)
    df["days_to_expiry"] = (pd.to_datetime(df["expiry"]) - pd.to_datetime(df["session"])).dt.days
    df["premium_band"] = pd.cut(
        df["close"], bins=[0, 25, 50, 100, 200, 400, 800, float("inf")], labels=False, include_lowest=True
    ).astype("Int64")
    return df.sort_values(["expired_instrument_key", "timestamp"]).reset_index(drop=True)


def add_forward_labels(df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    rows = []
    for _, group in df.groupby("expired_instrument_key", sort=False):
        group = group.sort_values("timestamp").copy()
        next_open = group["open"].shift(-1)
        future_high = group["high"].shift(-1).iloc[::-1].rolling(horizon, min_periods=1).max().iloc[::-1]
        future_low = group["low"].shift(-1).iloc[::-1].rolling(horizon, min_periods=1).min().iloc[::-1]
        forward_close = group["close"].shift(-horizon)
        out = group.copy()
        out["entry_price_next_open"] = next_open
        out["forward_mfe_points"] = future_high - next_open
        out["forward_mae_points"] = next_open - future_low
        out["forward_close_change_points"] = forward_close - next_open
        out["forward_expansion_pct"] = out["forward_mfe_points"] / next_open.replace(0, pd.NA) * 100
        out["label_horizon_minutes"] = horizon
        out["is_expansion_event"] = (
            (out["forward_mfe_points"] >= EVENT_POINT_THRESHOLD)
            & (out["forward_mae_points"] <= EVENT_ADVERSE_LIMIT)
            & next_open.notna()
        )
        rows.append(out)
    labeled = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return labeled.dropna(subset=["entry_price_next_open", "forward_mfe_points", "forward_mae_points"])


def suppress_overlaps(labeled: pd.DataFrame, cooldown_minutes: int = 30) -> pd.DataFrame:
    labeled = labeled.copy()
    labeled["move_cluster_id"] = pd.NA
    cluster_counter = 0
    for key, group in labeled[labeled["is_expansion_event"]].groupby("expired_instrument_key", sort=False):
        last_ts = None
        for idx, row in group.sort_values("timestamp").iterrows():
            ts = row["timestamp"]
            if last_ts is None or (ts - last_ts).total_seconds() >= cooldown_minutes * 60:
                cluster_counter += 1
                last_ts = ts
            labeled.at[idx, "move_cluster_id"] = f"{key}:{cluster_counter}"
    return labeled


def add_precursor_features(labeled: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, group in labeled.groupby("expired_instrument_key", sort=False):
        group = group.sort_values("timestamp").copy()
        group["prior_5m_return_pct"] = group["close"].pct_change(5) * 100
        group["prior_10m_range_pct"] = (
            (group["high"].rolling(10, min_periods=10).max() - group["low"].rolling(10, min_periods=10).min())
            / group["close"].replace(0, pd.NA)
            * 100
        )
        group["prior_5m_volume_ratio"] = group["volume"] / group["volume"].rolling(20, min_periods=10).median()
        group["transition_compression_to_lift"] = (group["prior_10m_range_pct"] <= 8.0) & (group["prior_5m_return_pct"] >= 2.0)
        group["transition_put_call_selloff_or_lift"] = (
            ((group["option_type"] == "CE") & (group["prior_5m_return_pct"] >= 5.0))
            | ((group["option_type"] == "PE") & (group["prior_5m_return_pct"] >= 5.0))
        )
        group["transition_volume_participation"] = group["prior_5m_volume_ratio"] >= 1.5
        frames.append(group)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_controls(labeled: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    labeled = labeled.copy()
    if "session" not in labeled.columns:
        labeled["session"] = pd.to_datetime(labeled["timestamp"]).dt.date.astype(str)
    if "minute_of_day" not in labeled.columns:
        ts = pd.to_datetime(labeled["timestamp"])
        labeled["minute_of_day"] = ts.dt.hour * 60 + ts.dt.minute
    events = labeled[labeled["is_expansion_event"]].copy()
    non_events = labeled[~labeled["is_expansion_event"]].copy()
    events["control_bucket"] = list(
        zip(
            events["option_type"],
            events["premium_band"].astype(str),
            events["days_to_expiry"].astype(str),
            (events["minute_of_day"] // 15).astype(str),
        )
    )
    non_events["control_bucket"] = list(
        zip(
            non_events["option_type"],
            non_events["premium_band"].astype(str),
            non_events["days_to_expiry"].astype(str),
            (non_events["minute_of_day"] // 15).astype(str),
        )
    )
    non_event_buckets = {bucket: group for bucket, group in non_events.groupby("control_bucket", sort=False)}
    controls = []
    for event_idx, event in events.iterrows():
        pool = non_event_buckets.get(event["control_bucket"], pd.DataFrame())
        if len(pool):
            pool = pool[pool["session"] != event["session"]].head(CONTROL_SAMPLE_PER_EVENT)
        pool = pool.assign(matched_event_index=int(event_idx), control_type="matched_ordinary")
        controls.append(pool)
    matched = pd.concat(controls, ignore_index=True) if controls else pd.DataFrame()
    near_miss = non_events[
        (non_events["forward_mfe_points"] >= EVENT_POINT_THRESHOLD * 0.6)
        & (non_events["forward_mfe_points"] < EVENT_POINT_THRESHOLD)
    ].copy()
    near_miss["control_type"] = "near_miss"
    quality = {
        "event_rows": int(len(events)),
        "independent_event_clusters": int(events["move_cluster_id"].dropna().nunique()),
        "matched_control_rows": int(len(matched)),
        "near_miss_rows": int(len(near_miss)),
        "events_with_at_least_one_control": int(matched["matched_event_index"].nunique()) if len(matched) else 0,
    }
    return matched, near_miss, quality


def precursor_analysis(labeled: pd.DataFrame, matched: pd.DataFrame, near_miss: pd.DataFrame) -> pd.DataFrame:
    event_rows = labeled[labeled["is_expansion_event"]]
    features = ["transition_compression_to_lift", "transition_put_call_selloff_or_lift", "transition_volume_participation"]
    records = []
    for feature in features:
        event_rate = float(event_rows[feature].fillna(False).mean()) if len(event_rows) else 0.0
        control_rate = float(matched[feature].fillna(False).mean()) if len(matched) else 0.0
        near_rate = float(near_miss[feature].fillna(False).mean()) if len(near_miss) else 0.0
        lift = event_rate / control_rate if control_rate > 0 else None
        records.append(
            {
                "precursor": feature,
                "event_occurrence_rate": event_rate,
                "matched_control_occurrence_rate": control_rate,
                "near_miss_occurrence_rate": near_rate,
                "lift": lift,
                "independent_event_clusters": int(event_rows.loc[event_rows[feature].fillna(False), "move_cluster_id"].dropna().nunique()),
                "event_count": int(len(event_rows)),
                "matched_control_count": int(len(matched)),
                "accepted_for_freeze": bool(lift and lift >= 2.0 and event_rate >= 0.05 and len(event_rows) >= 30),
            }
        )
    return pd.DataFrame(records)


def run_discovery(source_root: Path, contracts: pd.DataFrame, output_dir: Path) -> dict[str, Any]:
    population = load_option_population(source_root, contracts)
    labeled = add_forward_labels(population, horizon=5)
    labeled = suppress_overlaps(labeled)
    labeled = add_precursor_features(labeled)
    matched, near_miss, quality = build_controls(labeled)
    analysis = precursor_analysis(labeled, matched, near_miss)
    output_dir.mkdir(parents=True, exist_ok=True)
    labeled.to_parquet(output_dir / "event_universe_5m.parquet", index=False)
    matched.to_parquet(output_dir / "matched_controls.parquet", index=False)
    near_miss.to_parquet(output_dir / "near_miss_controls.parquet", index=False)
    analysis.to_csv(output_dir / "precursor_discrimination.csv", index=False)
    return {
        "event_universe_rows": int(len(labeled)),
        "raw_event_rows": quality["event_rows"],
        "independent_event_clusters": quality["independent_event_clusters"],
        "matched_control_rows": quality["matched_control_rows"],
        "near_miss_rows": quality["near_miss_rows"],
        "events_with_at_least_one_control": quality["events_with_at_least_one_control"],
        "accepted_precursors": int(analysis["accepted_for_freeze"].sum()) if len(analysis) else 0,
    }


def write_outputs(output_dir: Path, inventory: DataInventory, matrix: dict[str, Any], repo_head: str, discovery: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    verdict = verdict_from_matrix(matrix, discovery.get("accepted_precursors", 0))
    package = {
        "mission": "reverse_causal_option_expansion_discovery_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_head": repo_head,
        "principal_verdict": verdict,
        "non_action_flags": NON_ACTION_FLAGS,
        "data_inventory": asdict(inventory),
        "capability_matrix": matrix,
        "discovery_summary": discovery,
        "holdout_status": "NOT_OPENED_NO_FROZEN_MECHANISM",
        "frozen_mechanisms": [],
        "execution_certification": "BLOCKED_AUTHORITATIVE_QUOTE_OR_SPREAD_MISSING",
    }
    (output_dir / "research_package.json").write_text(json.dumps(package, indent=2, sort_keys=True) + "\n")
    (output_dir / "data_inventory.json").write_text(json.dumps(asdict(inventory), indent=2, sort_keys=True) + "\n")
    (output_dir / "capability_matrix.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    (output_dir / "final_decision_report.md").write_text(render_markdown(package))
    return package


def render_markdown(package: dict[str, Any]) -> str:
    inv = package["data_inventory"]
    summary = package["discovery_summary"]
    lines = [
        "# Reverse-Causal Option Expansion Discovery V1",
        "",
        f"Principal verdict: `{package['principal_verdict']}`",
        "",
        "## Safety Flags",
        "",
    ]
    for key, value in package["non_action_flags"].items():
        lines.append(f"- `{key}={str(value).lower()}`")
    lines.extend(
        [
            "",
            "## Source Coverage",
            "",
            f"- Source root: `{inv['source_root']}`",
            f"- Contract inventory rows: `{inv['contract_inventory_rows']}`",
            f"- Valid contracts: `{inv['valid_contract_rows']}`",
            f"- Expiries: `{inv['expiries']}`",
            f"- One-minute option rows declared: `{inv['one_minute_rows']}`",
            f"- First candle: `{inv['first_candle']}`",
            f"- Last candle: `{inv['last_candle']}`",
            f"- Source hash: `{inv['source_hash']}`",
            "",
            "## LFS Findings",
            "",
        ]
    )
    for item in inv["lfs_candidate_files"]:
        lines.append(
            f"- `{item['path']}`: pointer=`{str(item['is_lfs_pointer']).lower()}`, size=`{item['size_bytes']}`, sha256=`{item['sha256']}`"
        )
    lines.extend(["", "## Capability Matrix", ""])
    for stage, result in package["capability_matrix"].items():
        lines.append(f"- `{stage}`: can_run=`{str(result['can_run']).lower()}`, blockers=`{result['blockers']}`")
    lines.extend(
        [
            "",
            "## Discovery Counts",
            "",
            f"- Eligible labelled observations: `{summary.get('event_universe_rows', 0)}`",
            f"- Raw expansion events: `{summary.get('raw_event_rows', 0)}`",
            f"- Independent move clusters: `{summary.get('independent_event_clusters', 0)}`",
            f"- Matched ordinary controls: `{summary.get('matched_control_rows', 0)}`",
            f"- Near-miss controls: `{summary.get('near_miss_rows', 0)}`",
            f"- Accepted precursors for freeze: `{summary.get('accepted_precursors', 0)}`",
            "",
            "## Decision",
            "",
            "Stage B/C structural and gross outcome artifacts may be produced from valid causal option OHLCV. Execution certification and final validated-edge claims remain blocked without authoritative timestamp-aligned quote or spread evidence. No mechanism was frozen and the holdout was not opened.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("/Users/madhuram/tradebot/runtime/upstox-expired-options-v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/research/reverse_causal_option_expansion_v1"))
    parser.add_argument("--skip-discovery", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    source_root = args.source_root if args.source_root.is_absolute() else repo_root / args.source_root
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir
    contracts = load_contract_inventory(source_root)
    inventory = build_inventory(source_root, contracts, repo_root)
    matrix = capability_matrix(inventory)
    discovery = {}
    if matrix["C_GROSS_OUTCOME_EVALUATION"]["can_run"] and not args.skip_discovery:
        discovery = run_discovery(source_root, contracts, output_dir)
    package = write_outputs(output_dir, inventory, matrix, git_head(repo_root), discovery)
    print(json.dumps({"principal_verdict": package["principal_verdict"], "discovery_summary": discovery}, sort_keys=True))
    return 0


def git_head(repo_root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
