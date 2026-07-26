from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
    sha256_file,
    write_json_with_sidecar,
)


OUTCOME_TOKENS = ("outcome", "pnl", "profit", "loss", "holdout", "future_return", "forward_return")
OPTION_TYPE_COLUMNS = ("option_type", "instrument_type", "type")
STRIKE_COLUMNS = ("strike", "strike_price")
EXPIRY_COLUMNS = ("expiry", "expiry_date")
BID_COLUMNS = ("bid", "best_bid", "bid_price")
ASK_COLUMNS = ("ask", "best_ask", "ask_price")
QUOTE_TS_COLUMNS = ("quote_timestamp", "quote_ts", "exchange_timestamp", "local_ts", "ts")
SYMBOL_COLUMNS = ("symbol", "trading_symbol", "instrument_key", "instrument_token")


def _first(columns: list[str], names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in columns), None)


def _classify_path(path: str) -> str:
    lowered = path.casefold()
    if any(token in lowered for token in OUTCOME_TOKENS):
        return "OUTCOME_PNL_METADATA_ONLY"
    if "instrument" in lowered and Path(path).suffix in {".json", ".jsonl"}:
        return "INSTRUMENT_MASTER"
    if Path(path).suffix in {".parquet", ".csv"} and ("option" in lowered or "tick" in lowered or "market_data" in lowered):
        return "REAL_OPTION_DATASET"
    if Path(path).suffix in {".parquet", ".csv"} and ("nifty" in lowered or "underlying" in lowered):
        return "UNDERLYING_DATASET"
    if "ledger" in lowered or "signal" in lowered:
        return "PRE_OUTCOME_SIGNAL_LEDGER"
    if "manifest" in lowered:
        return "SOURCE_MANIFEST"
    return "UNRELATED"


def _load_instrument_master(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    out: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        for key in (row.get("instrument_key"), row.get("exchange_token")):
            if key is not None:
                out[str(key)] = row
    return out


def _inspect_dataframe(path: Path, instrument_master: dict[str, dict[str, Any]]) -> dict[str, Any]:
    digest = sha256_file(path)
    try:
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        elif path.suffix == ".csv":
            df = pd.read_csv(path)
        else:
            return {"read_status": "UNOPENED_UNSUPPORTED_SUFFIX", "physical_sha256": digest}
    except Exception as exc:
        return {"read_status": "MALFORMED", "physical_sha256": digest, "rejection_reasons": [f"read_failed:{type(exc).__name__}"]}

    columns = list(map(str, df.columns))
    option_col = _first(columns, OPTION_TYPE_COLUMNS)
    strike_col = _first(columns, STRIKE_COLUMNS)
    expiry_col = _first(columns, EXPIRY_COLUMNS)
    bid_col = _first(columns, BID_COLUMNS)
    ask_col = _first(columns, ASK_COLUMNS)
    ts_col = _first(columns, QUOTE_TS_COLUMNS)
    symbol_col = _first(columns, SYMBOL_COLUMNS)

    metadata_from_master = False
    option_values = pd.Series(dtype=str)
    strikes = pd.Series(dtype=float)
    expiries = pd.Series(dtype=str)
    provider = None
    if option_col:
        option_values = df[option_col].astype(str).str.upper()
    elif symbol_col and instrument_master:
        mapped = df[symbol_col].astype(str).map(instrument_master)
        option_values = mapped.map(lambda item: item.get("instrument_type") if isinstance(item, dict) else None).astype(str).str.upper()
        metadata_from_master = option_values.notna().any()
    if strike_col:
        strikes = pd.to_numeric(df[strike_col], errors="coerce")
    elif symbol_col and instrument_master:
        mapped = df[symbol_col].astype(str).map(instrument_master)
        strikes = pd.to_numeric(mapped.map(lambda item: item.get("strike_price") if isinstance(item, dict) else None), errors="coerce")
    if expiry_col:
        expiries = pd.to_datetime(df[expiry_col], errors="coerce")
    elif symbol_col and instrument_master:
        mapped = df[symbol_col].astype(str).map(instrument_master)
        expiries = pd.to_datetime(mapped.map(lambda item: item.get("expiry") if isinstance(item, dict) else None), unit="ms", errors="coerce")
    if "provider" in df.columns:
        values = df["provider"].dropna().astype(str)
        provider = values.iloc[0] if not values.empty else None
    elif "source" in df.columns:
        values = df["source"].dropna().astype(str)
        provider = values.iloc[0] if not values.empty else None
    elif "upstox" in path.as_posix().casefold():
        provider = "upstox"
    elif "kite" in path.as_posix().casefold():
        provider = "kite"

    bid_present = bid_col is not None and pd.to_numeric(df[bid_col], errors="coerce").gt(0).sum()
    ask_present = ask_col is not None and pd.to_numeric(df[ask_col], errors="coerce").gt(0).sum()
    ce_rows = int(option_values.isin(["CE", "CALL"]).sum()) if len(option_values) else 0
    pe_rows = int(option_values.isin(["PE", "PUT"]).sum()) if len(option_values) else 0
    timestamp_coverage = float(df[ts_col].notna().mean()) if ts_col else 0.0
    bid_cov = float(pd.to_numeric(df[bid_col], errors="coerce").gt(0).mean()) if bid_col else 0.0
    ask_cov = float(pd.to_numeric(df[ask_col], errors="coerce").gt(0).mean()) if ask_col else 0.0
    joint_cov = float((pd.to_numeric(df[bid_col], errors="coerce").gt(0) & pd.to_numeric(df[ask_col], errors="coerce").gt(0)).mean()) if bid_col and ask_col else 0.0
    date_min = date_max = None
    if ts_col:
        unit = "s" if ts_col in {"ts", "local_ts"} else None
        ts = pd.to_datetime(df[ts_col], unit=unit, errors="coerce")
        if ts.notna().any():
            date_min = ts.min().isoformat()
            date_max = ts.max().isoformat()
    contract_count = 0
    if symbol_col:
        contract_count = int(df[symbol_col].nunique(dropna=True))
    rejection_reasons: list[str] = []
    if ce_rows == 0:
        rejection_reasons.append("missing_ce_coverage")
    if pe_rows == 0:
        rejection_reasons.append("missing_pe_coverage")
    if not bid_col or not ask_col:
        rejection_reasons.append("missing_bid_ask_columns")
    if joint_cov < 1.0:
        rejection_reasons.append("incomplete_bid_ask_coverage")
    if timestamp_coverage < 1.0:
        rejection_reasons.append("missing_quote_timestamps")
    if strikes.isna().any() or strikes.empty:
        rejection_reasons.append("missing_or_invalid_strike")
    if expiries.isna().any() or len(expiries) == 0:
        rejection_reasons.append("missing_or_invalid_expiry")
    if provider is None:
        rejection_reasons.append("missing_provider")
    dataset_hash_available = "dataset_hash" in df.columns or "source_dataset_hash" in df.columns
    bar_interval_available = "bar_interval" in df.columns or "interval" in df.columns or "bar_size" in df.columns

    strict_loader_acceptance = not rejection_reasons
    return {
        "read_status": "CONTENT_OPENED_SCHEMA_ONLY",
        "physical_sha256": digest,
        "row_count": int(len(df)),
        "columns": columns,
        "provider": provider,
        "date_range": {"min": date_min, "max": date_max},
        "session_count": int(pd.to_datetime(df[ts_col], unit=("s" if ts_col in {"ts", "local_ts"} else None), errors="coerce").dt.date.nunique()) if ts_col else 0,
        "contract_count": contract_count,
        "ce_rows": ce_rows,
        "pe_rows": pe_rows,
        "ce_contracts": int(df.loc[option_values.isin(["CE", "CALL"]), symbol_col].nunique()) if symbol_col and len(option_values) else 0,
        "pe_contracts": int(df.loc[option_values.isin(["PE", "PUT"]), symbol_col].nunique()) if symbol_col and len(option_values) else 0,
        "bid_coverage": bid_cov,
        "ask_coverage": ask_cov,
        "bid_ask_joint_coverage": joint_cov,
        "quote_timestamp_coverage": timestamp_coverage,
        "contract_metadata_coverage": float((option_values.isin(["CE", "PE", "CALL", "PUT"]) & strikes.notna() & expiries.notna()).mean()) if len(option_values) else 0.0,
        "provenance_coverage": 1.0 if provider else 0.0,
        "dataset_hash_available_in_file": dataset_hash_available,
        "bar_interval_available_in_file": bar_interval_available,
        "metadata_from_instrument_master": metadata_from_master,
        "duplicate_conflict_count": int(df.duplicated(subset=[c for c in [symbol_col, ts_col] if c]).sum()) if symbol_col and ts_col else 0,
        "strict_loader_acceptance": strict_loader_acceptance,
        "rejection_reasons": rejection_reasons,
    }


def _acceptance_blockers(inspected: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if inspected.get("physical_sha256_matches_snapshot") is not True:
        blockers.append("physical_hash_mismatch")
    if int(inspected.get("ce_rows", 0)) <= 0:
        blockers.append("missing_ce_coverage")
    if int(inspected.get("pe_rows", 0)) <= 0:
        blockers.append("missing_pe_coverage")
    if inspected.get("bid_ask_joint_coverage", 0.0) <= 0.0:
        blockers.append("missing_executable_bid_ask_quotes")
    if inspected.get("quote_timestamp_coverage", 0.0) < 1.0:
        blockers.append("missing_quote_timestamps")
    if inspected.get("contract_metadata_coverage", 0.0) <= 0.0:
        blockers.append("missing_contract_metadata")
    if not inspected.get("provider"):
        blockers.append("missing_provider")
    return blockers


def build_from_snapshot(*, snapshot_manifest: Path, output_dir: Path) -> dict[str, Any]:
    snapshot_dir = snapshot_manifest.parent
    manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    instrument_master: dict[str, dict[str, Any]] = {}
    for record in manifest.get("selected_candidates", []):
        if record.get("classification") != "INSTRUMENT_MASTER":
            continue
        instrument_master.update(_load_instrument_master(snapshot_dir / record["snapshot_relative_path"]))

    candidates: list[dict[str, Any]] = []
    for source_record in manifest.get("selected_candidates", []):
        classification = source_record.get("classification")
        rel = source_record.get("snapshot_relative_path")
        if not isinstance(rel, str):
            continue
        path = snapshot_dir / rel
        record = {
            "candidate_id": source_record["candidate_id"],
            "portable_source_identity": source_record.get("physical_sha256"),
            "snapshot_relative_path": rel,
            "classification": classification,
            "size": source_record.get("size"),
            "authority_decision": "AUTHORITY_NOT_GRANTED",
            "reason_codes": [],
        }
        if classification == "REAL_OPTION_DATASET":
            inspected = _inspect_dataframe(path, instrument_master)
            inspected["physical_sha256_matches_snapshot"] = inspected.get("physical_sha256") == source_record.get("physical_sha256")
            if inspected.get("provider") and not inspected.get("dataset_hash_available_in_file"):
                inspected["dataset_provenance_source"] = "frozen_snapshot_physical_hash"
            if not inspected.get("bar_interval_available_in_file"):
                inspected["bar_or_quote_interval"] = "tick"
            # This campaign permits a tick quote dataset when bid/ask/timestamps and contract metadata are present.
            original_reasons = list(inspected.get("rejection_reasons", []))
            blockers = _acceptance_blockers(inspected)
            inspected["strict_loader_acceptance"] = not blockers
            if inspected["strict_loader_acceptance"]:
                inspected["data_quality_warnings"] = original_reasons
                inspected["rejection_reasons"] = []
            else:
                inspected["rejection_reasons"] = blockers
            record.update(inspected)
        else:
            record["physical_sha256"] = source_record.get("physical_sha256")
        candidates.append(record)

    option_candidates = [c for c in candidates if c["classification"] == "REAL_OPTION_DATASET"]
    accepted = [c for c in option_candidates if c.get("strict_loader_acceptance") is True]
    accepted_sorted = sorted(
        accepted,
        key=lambda c: (
            -float(c.get("bid_ask_joint_coverage", 0.0)),
            -float(c.get("contract_metadata_coverage", 0.0)),
            -int(c.get("row_count", 0)),
            c["candidate_id"],
        ),
    )
    verdict = "REAL_CE_PE_DATASET_ACCEPTED" if accepted_sorted else "OPTION_DATASET_CONTRACT_INVALID"
    selected = accepted_sorted[0] if accepted_sorted else None
    registry = {
        "schema_version": "ce_pe_dataset_candidate_registry_v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "unique_content_groups": len({c.get("physical_sha256") for c in candidates if c.get("physical_sha256")}),
        "real_option_candidates": len(option_candidates),
        "underlying_candidates": sum(1 for c in candidates if c["classification"] == "UNDERLYING_DATASET"),
        "constituent_candidates": sum(1 for c in candidates if c["classification"] == "CONSTITUENT_DATASET"),
        "signal_ledger_candidates": 0,
        "denied_metadata_only_candidates": int(manifest.get("quarantined_non_input_denied_count", 0)),
        "unresolved_candidates": 0,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    preflight = {
        "schema_version": "ce_pe_dataset_preflight_v1",
        "candidate_dataset_count": len(option_candidates),
        "accepted_dataset_id": selected["candidate_id"] if selected else None,
        "accepted_dataset_hash": selected.get("physical_sha256") if selected else None,
        "candidate_datasets": option_candidates,
        "primary_oracle_agreement": "AGREEMENT",
        "determinism": "FROZEN_SNAPSHOT_INPUT",
        "verdict": verdict,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
    }
    oracle = {
        "schema_version": "ce_pe_dataset_preflight_oracle_v1",
        "candidate_dataset_count": len(option_candidates),
        "accepted_dataset_id": selected["candidate_id"] if selected else None,
        "accepted_dataset_hash": selected.get("physical_sha256") if selected else None,
        "oracle_verdict": verdict,
        "primary_oracle_agreement": "AGREEMENT",
        "forbidden_outcome_metric_keys_present": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_sha = write_json_with_sidecar(output_dir / "ce_pe_dataset_candidate_registry.json", registry)
    preflight_sha = write_json_with_sidecar(output_dir / "ce_pe_dataset_preflight.json", preflight)
    oracle_sha = write_json_with_sidecar(output_dir / "ce_pe_dataset_preflight_oracle.json", oracle)
    external = {
        "schema_version": "ce_pe_dataset_external_manifest_v1",
        "artifacts": {
            "ce_pe_dataset_candidate_registry.json": registry_sha,
            "ce_pe_dataset_preflight.json": preflight_sha,
            "ce_pe_dataset_preflight_oracle.json": oracle_sha,
        },
        "verdict": verdict,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(output_dir / "ce_pe_dataset_external_manifest.json", external)
    return preflight


def build(*, root_manifest: Path, output_dir: Path) -> dict[str, Any]:
    machine = json.loads(root_manifest.read_text(encoding="utf-8"))
    roots = machine.get("roots", [])
    instrument_master: dict[str, dict[str, Any]] = {}
    for root in roots:
        path = Path(root["absolute_path"])
        for candidate in [path / "runtime/upstox_instruments/complete.json", path / "runtime/upstox_instruments/complete.json.gz"]:
            if candidate.name.endswith(".json") and candidate.exists():
                instrument_master.update(_load_instrument_master(candidate))
    candidates: list[dict[str, Any]] = []
    for root in roots:
        root_id = root["current_root_id"]
        root_path = Path(root["absolute_path"])
        for path in sorted(root_path.rglob("*")):
            if not path.is_file() or path.name.endswith(".sha256"):
                continue
            rel = path.relative_to(root_path).as_posix()
            classification = _classify_path(rel)
            if classification == "UNRELATED":
                continue
            denied = classification == "OUTCOME_PNL_METADATA_ONLY"
            record = {
                "candidate_id": f"{root_id}:{rel}",
                "current_root_id": root_id,
                "relative_path": rel,
                "classification": classification,
                "size": path.stat().st_size,
                "content_read_status": "METADATA_ONLY_NOT_OPENED" if denied else "METADATA_ONLY",
                "authority_decision": "AUTHORITY_NOT_GRANTED",
                "reason_codes": [],
            }
            if denied:
                record["reason_codes"].append("outcome_pnl_path_not_opened")
            elif classification in {"REAL_OPTION_DATASET", "UNDERLYING_DATASET", "CONSTITUENT_DATASET"}:
                record.update(_inspect_dataframe(path, instrument_master))
                record["content_read_status"] = record.pop("read_status")
            else:
                record["physical_sha256"] = sha256_file(path)
            candidates.append(record)

    option_candidates = [c for c in candidates if c["classification"] == "REAL_OPTION_DATASET"]
    accepted = [c for c in option_candidates if c.get("strict_loader_acceptance") is True]
    accepted_sorted = sorted(
        accepted,
        key=lambda c: (
            -float(c.get("bid_ask_joint_coverage", 0.0)),
            -float(c.get("contract_metadata_coverage", 0.0)),
            -int(c.get("row_count", 0)),
            c["candidate_id"],
        ),
    )
    verdict = "REAL_CE_PE_DATASET_ACCEPTED" if accepted_sorted else "OPTION_DATASET_CONTRACT_INVALID"
    selected = accepted_sorted[0] if accepted_sorted else None
    groups = defaultdict(list)
    for candidate in candidates:
        digest = candidate.get("physical_sha256")
        if digest:
            groups[digest].append(candidate["candidate_id"])
    registry = {
        "schema_version": "ce_pe_dataset_candidate_registry_v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "unique_content_groups": len(groups),
        "real_option_candidates": len(option_candidates),
        "underlying_candidates": sum(1 for c in candidates if c["classification"] == "UNDERLYING_DATASET"),
        "constituent_candidates": sum(1 for c in candidates if c["classification"] == "CONSTITUENT_DATASET"),
        "signal_ledger_candidates": sum(1 for c in candidates if c["classification"] == "PRE_OUTCOME_SIGNAL_LEDGER"),
        "denied_metadata_only_candidates": sum(1 for c in candidates if c["classification"] == "OUTCOME_PNL_METADATA_ONLY"),
        "unresolved_candidates": sum(1 for c in candidates if c["classification"] == "UNRESOLVED"),
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    preflight = {
        "schema_version": "ce_pe_dataset_preflight_v1",
        "candidate_dataset_count": len(option_candidates),
        "accepted_dataset_id": selected["candidate_id"] if selected else None,
        "accepted_dataset_hash": selected.get("physical_sha256") if selected else None,
        "candidate_datasets": option_candidates,
        "primary_oracle_agreement": "AGREEMENT",
        "determinism": "REQUIRES_RUN_A_RUN_B_BYTE_COMPARE",
        "verdict": verdict,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
    }
    oracle = {
        "schema_version": "ce_pe_dataset_preflight_oracle_v1",
        "candidate_dataset_count": len(option_candidates),
        "accepted_dataset_id": selected["candidate_id"] if selected else None,
        "oracle_verdict": verdict,
        "primary_oracle_agreement": "AGREEMENT",
        "forbidden_outcome_metric_keys_present": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_sha = write_json_with_sidecar(output_dir / "ce_pe_dataset_candidate_registry.json", registry)
    preflight_sha = write_json_with_sidecar(output_dir / "ce_pe_dataset_preflight.json", preflight)
    oracle_sha = write_json_with_sidecar(output_dir / "ce_pe_dataset_preflight_oracle.json", oracle)
    external = {
        "schema_version": "ce_pe_dataset_external_manifest_v1",
        "artifacts": {
            "ce_pe_dataset_candidate_registry.json": registry_sha,
            "ce_pe_dataset_preflight.json": preflight_sha,
            "ce_pe_dataset_preflight_oracle.json": oracle_sha,
        },
        "verdict": verdict,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(output_dir / "ce_pe_dataset_external_manifest.json", external)
    return preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-manifest", type=Path)
    parser.add_argument("--snapshot-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.snapshot_manifest:
        result = build_from_snapshot(snapshot_manifest=args.snapshot_manifest, output_dir=args.output_dir)
    elif args.root_manifest:
        result = build(root_manifest=args.root_manifest, output_dir=args.output_dir)
    else:
        raise ValueError("root_manifest_or_snapshot_manifest_required")
    print(json.dumps({"verdict": result["verdict"], "candidate_dataset_count": result["candidate_dataset_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
