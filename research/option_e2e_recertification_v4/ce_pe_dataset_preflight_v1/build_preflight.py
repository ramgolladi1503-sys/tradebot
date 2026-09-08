from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
    sha256_file,
    write_json_with_sidecar,
)


OUTCOME_TOKENS = (
    "outcome",
    "pnl",
    "profit",
    "loss",
    "holdout",
    "future_return",
    "forward_return",
)
OPTION_TYPE_COLUMNS = ("option_type", "instrument_type", "type")
STRIKE_COLUMNS = ("strike", "strike_price")
EXPIRY_COLUMNS = ("expiry", "expiry_date")
BID_COLUMNS = ("bid", "best_bid", "bid_price")
ASK_COLUMNS = ("ask", "best_ask", "ask_price")
QUOTE_TS_COLUMNS = (
    "quote_timestamp",
    "quote_ts",
    "exchange_timestamp",
    "local_ts",
    "ts",
)
SYMBOL_COLUMNS = ("symbol", "trading_symbol", "instrument_key", "instrument_token")

NORMALIZED_REPLAY_REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "bid",
    "ask",
    "quote_timestamp",
    "underlying",
    "option_type",
    "strike",
    "expiry",
    "provider",
    "dataset_hash",
    "bar_interval",
)


def _first(columns: list[str], names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in columns), None)


def _classify_path(path: str) -> str:
    lowered = path.casefold()
    if any(token in lowered for token in OUTCOME_TOKENS):
        return "DENIED_OUTCOME_METADATA_ONLY"
    if "instrument" in lowered and Path(path).suffix in {".json", ".jsonl"}:
        return "INSTRUMENT_MASTER"
    if Path(path).suffix in {".parquet", ".csv"} and (
        "option" in lowered or "tick" in lowered or "market_data" in lowered
    ):
        return "RAW_OPTION_TICK_DATASET"
    if Path(path).suffix in {".parquet", ".csv"} and (
        "nifty" in lowered or "underlying" in lowered
    ):
        return "UNDERLYING_DATASET"
    if "ledger" in lowered or "signal" in lowered:
        return "SIGNAL_LEDGER"
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


def _provider_evidence(df: pd.DataFrame, path: Path) -> tuple[str | None, str]:
    for column in ("provider", "source_provider", "source"):
        if column in df.columns:
            values = df[column].dropna().astype(str).str.strip()
            values = values.loc[values != ""]
            if not values.empty:
                return values.iloc[0], "IN_FILE"
    lowered = path.as_posix().casefold()
    if "upstox" in lowered:
        return "upstox", "PATH_INFERRED_LIMITATION"
    if "kite" in lowered or "zerodha" in lowered:
        return "kite", "PATH_INFERRED_LIMITATION"
    return None, "MISSING"


def _normalized_replay_blockers(
    *,
    columns: list[str],
    joint_coverage: float,
    timestamp_coverage: float,
    metadata_coverage: float,
    provider_authority: str,
) -> list[str]:
    blockers: list[str] = []
    missing_columns = [name for name in NORMALIZED_REPLAY_REQUIRED_COLUMNS if name not in columns]
    if missing_columns:
        blockers.append("missing_normalized_replay_columns:" + ",".join(missing_columns))
    if joint_coverage < 1.0:
        blockers.append("incomplete_bid_ask_coverage")
    if timestamp_coverage < 1.0:
        blockers.append("missing_quote_timestamps")
    if metadata_coverage < 1.0:
        blockers.append("incomplete_contract_metadata")
    if provider_authority != "IN_FILE":
        blockers.append("provider_provenance_not_authoritative")
    return blockers


def _inspect_dataframe(
    path: Path,
    instrument_master: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    digest = sha256_file(path)
    try:
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        elif path.suffix == ".csv":
            df = pd.read_csv(path)
        else:
            return {
                "read_status": "UNOPENED_UNSUPPORTED_SUFFIX",
                "physical_sha256": digest,
                "raw_source_acceptance": False,
                "strict_loader_acceptance": False,
                "actual_strict_loader_invoked": False,
            }
    except Exception as exc:
        return {
            "read_status": "MALFORMED",
            "physical_sha256": digest,
            "raw_source_acceptance": False,
            "strict_loader_acceptance": False,
            "actual_strict_loader_invoked": False,
            "rejection_reasons": [f"read_failed:{type(exc).__name__}"],
        }

    columns = list(map(str, df.columns))
    option_col = _first(columns, OPTION_TYPE_COLUMNS)
    strike_col = _first(columns, STRIKE_COLUMNS)
    expiry_col = _first(columns, EXPIRY_COLUMNS)
    bid_col = _first(columns, BID_COLUMNS)
    ask_col = _first(columns, ASK_COLUMNS)
    ts_col = _first(columns, QUOTE_TS_COLUMNS)
    symbol_col = _first(columns, SYMBOL_COLUMNS)

    mapped = pd.Series([None] * len(df), index=df.index, dtype=object)
    if symbol_col and instrument_master:
        mapped = df[symbol_col].astype(str).map(instrument_master)

    option_values = pd.Series(index=df.index, dtype="object")
    if option_col:
        option_values = df[option_col].astype(str).str.upper()
    elif symbol_col and instrument_master:
        option_values = mapped.map(
            lambda item: item.get("instrument_type") if isinstance(item, dict) else None
        ).astype(str).str.upper()

    strikes = pd.Series(index=df.index, dtype="float64")
    if strike_col:
        strikes = pd.to_numeric(df[strike_col], errors="coerce")
    elif symbol_col and instrument_master:
        strikes = pd.to_numeric(
            mapped.map(
                lambda item: item.get("strike_price") if isinstance(item, dict) else None
            ),
            errors="coerce",
        )

    expiries = pd.Series(index=df.index, dtype="datetime64[ns]")
    if expiry_col:
        expiries = pd.to_datetime(df[expiry_col], errors="coerce")
    elif symbol_col and instrument_master:
        raw_expiry = mapped.map(
            lambda item: item.get("expiry") if isinstance(item, dict) else None
        )
        expiries = pd.to_datetime(raw_expiry, unit="ms", errors="coerce")

    provider, provider_authority = _provider_evidence(df, path)

    ce_mask = option_values.isin(["CE", "CALL"]) if len(option_values) else pd.Series(False, index=df.index)
    pe_mask = option_values.isin(["PE", "PUT"]) if len(option_values) else pd.Series(False, index=df.index)
    ce_rows = int(ce_mask.sum())
    pe_rows = int(pe_mask.sum())

    bid_numeric = (
        pd.to_numeric(df[bid_col], errors="coerce")
        if bid_col
        else pd.Series(float("nan"), index=df.index)
    )
    ask_numeric = (
        pd.to_numeric(df[ask_col], errors="coerce")
        if ask_col
        else pd.Series(float("nan"), index=df.index)
    )
    valid_bid = bid_numeric.gt(0)
    valid_ask = ask_numeric.gt(0)
    valid_joint = valid_bid & valid_ask & ask_numeric.ge(bid_numeric)

    timestamp_coverage = float(df[ts_col].notna().mean()) if ts_col else 0.0
    bid_cov = float(valid_bid.mean()) if bid_col else 0.0
    ask_cov = float(valid_ask.mean()) if ask_col else 0.0
    joint_cov = float(valid_joint.mean()) if bid_col and ask_col else 0.0

    date_min = date_max = None
    session_count = 0
    if ts_col:
        unit = "s" if ts_col in {"ts", "local_ts"} else None
        ts = pd.to_datetime(df[ts_col], unit=unit, errors="coerce")
        if ts.notna().any():
            date_min = ts.min().isoformat()
            date_max = ts.max().isoformat()
            session_count = int(ts.dt.date.nunique())

    contract_count = int(df[symbol_col].nunique(dropna=True)) if symbol_col else 0
    contract_metadata_mask = (
        option_values.isin(["CE", "PE", "CALL", "PUT"])
        & strikes.notna()
        & expiries.notna()
    )
    contract_metadata_coverage = (
        float(contract_metadata_mask.mean()) if len(contract_metadata_mask) else 0.0
    )

    raw_blockers: list[str] = []
    if ce_rows == 0:
        raw_blockers.append("missing_ce_coverage")
    if pe_rows == 0:
        raw_blockers.append("missing_pe_coverage")
    if not bid_col or not ask_col:
        raw_blockers.append("missing_bid_ask_columns")
    elif joint_cov <= 0.0:
        raw_blockers.append("missing_executable_bid_ask_quotes")
    if timestamp_coverage <= 0.0:
        raw_blockers.append("missing_quote_timestamps")
    if contract_metadata_coverage <= 0.0:
        raw_blockers.append("missing_contract_metadata")
    if provider is None:
        raw_blockers.append("missing_provider_claim")

    strict_blockers = _normalized_replay_blockers(
        columns=columns,
        joint_coverage=joint_cov,
        timestamp_coverage=timestamp_coverage,
        metadata_coverage=contract_metadata_coverage,
        provider_authority=provider_authority,
    )

    duplicate_subset = [c for c in (symbol_col, ts_col) if c]
    duplicate_count = (
        int(df.duplicated(subset=duplicate_subset).sum())
        if len(duplicate_subset) == 2
        else 0
    )

    return {
        "read_status": "CONTENT_OPENED_SCHEMA_ONLY",
        "physical_sha256": digest,
        "row_count": int(len(df)),
        "columns": columns,
        "provider_claim": provider,
        "provider_authority": provider_authority,
        "date_range": {"min": date_min, "max": date_max},
        "session_count": session_count,
        "contract_count": contract_count,
        "ce_rows": ce_rows,
        "pe_rows": pe_rows,
        "ce_contracts": int(df.loc[ce_mask, symbol_col].nunique())
        if symbol_col and len(option_values)
        else 0,
        "pe_contracts": int(df.loc[pe_mask, symbol_col].nunique())
        if symbol_col and len(option_values)
        else 0,
        "bid_coverage": bid_cov,
        "ask_coverage": ask_cov,
        "bid_ask_joint_coverage": joint_cov,
        "quote_timestamp_coverage": timestamp_coverage,
        "contract_metadata_coverage": contract_metadata_coverage,
        "metadata_from_instrument_master": bool(instrument_master),
        "duplicate_conflict_count": duplicate_count,
        "dataset_hash_available_in_file": (
            "dataset_hash" in df.columns or "source_dataset_hash" in df.columns
        ),
        "bar_interval_available_in_file": (
            "bar_interval" in df.columns
            or "interval" in df.columns
            or "bar_size" in df.columns
        ),
        "raw_source_acceptance": not raw_blockers,
        "raw_source_rejection_reasons": raw_blockers,
        "strict_loader_acceptance": False,
        "actual_strict_loader_invoked": False,
        "strict_replay_rejection_reasons": strict_blockers
        or ["actual_strict_loader_not_invoked"],
        "replay_dataset_status": "RAW_TICK_SOURCE_ONLY",
    }


def _coverage_verdict(session_count: int) -> str:
    if session_count <= 1:
        return "ONE_SESSION_SMOKE_ONLY"
    if session_count < 20:
        return "MULTI_SESSION_ADAPTER_VALIDATION_ONLY"
    return "CHRONOLOGICAL_COVERAGE_REQUIRES_EXPLICIT_PARTITION_REVIEW"


def _assemble_outputs(
    *,
    candidates: list[dict[str, Any]],
    denied_metadata_only_candidates: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    raw_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("classification") == "RAW_OPTION_TICK_DATASET"
    ]
    valid_raw = [
        candidate
        for candidate in raw_candidates
        if candidate.get("raw_source_acceptance") is True
        and candidate.get("physical_sha256_matches_snapshot", True) is True
    ]
    valid_raw = sorted(
        valid_raw,
        key=lambda candidate: (
            -float(candidate.get("bid_ask_joint_coverage", 0.0)),
            -float(candidate.get("contract_metadata_coverage", 0.0)),
            -int(candidate.get("row_count", 0)),
            str(candidate.get("candidate_id")),
        ),
    )
    selected_raw = valid_raw[0] if valid_raw else None
    normalized = [
        candidate
        for candidate in raw_candidates
        if candidate.get("strict_loader_acceptance") is True
        and candidate.get("actual_strict_loader_invoked") is True
    ]

    if normalized:
        verdict = "NORMALIZED_OPTION_REPLAY_DATASET_ACCEPTED"
        replay_verdict = verdict
    elif selected_raw:
        verdict = "STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED"
        replay_verdict = verdict
    else:
        verdict = "RAW_CE_PE_SOURCE_INVALID"
        replay_verdict = "OPTION_REPLAY_DATASET_INVALID"

    max_sessions = max(
        (int(candidate.get("session_count", 0)) for candidate in valid_raw),
        default=0,
    )
    registry = {
        "schema_version": "ce_pe_dataset_candidate_registry_v2",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "unique_content_groups": len(
            {
                candidate.get("physical_sha256")
                for candidate in candidates
                if candidate.get("physical_sha256")
            }
        ),
        "raw_option_candidates": len(raw_candidates),
        "normalized_option_candidates": len(normalized),
        "underlying_candidates": sum(
            1
            for candidate in candidates
            if candidate.get("classification") == "UNDERLYING_DATASET"
        ),
        "signal_ledger_candidates": sum(
            1
            for candidate in candidates
            if candidate.get("classification") == "SIGNAL_LEDGER"
        ),
        "denied_metadata_only_candidates": denied_metadata_only_candidates,
        "unresolved_candidates": sum(
            1
            for candidate in candidates
            if candidate.get("classification") == "UNRESOLVED"
        ),
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    preflight = {
        "schema_version": "ce_pe_dataset_preflight_v2",
        "prior_verdict_invalidation": "INVALID_PREFLIGHT_ACCEPTANCE_WEAKENED_STRICT_CONTRACT",
        "candidate_dataset_count": len(raw_candidates),
        "accepted_dataset_id": normalized[0].get("candidate_id") if normalized else None,
        "accepted_dataset_hash": normalized[0].get("physical_sha256") if normalized else None,
        "raw_source_candidate_id": selected_raw.get("candidate_id") if selected_raw else None,
        "raw_source_candidate_hash": selected_raw.get("physical_sha256") if selected_raw else None,
        "raw_source_verdict": (
            "RAW_CE_PE_TICK_SOURCE_VALIDATED"
            if selected_raw
            else "RAW_CE_PE_SOURCE_INVALID"
        ),
        "replay_dataset_verdict": replay_verdict,
        "chronological_coverage_verdict": _coverage_verdict(max_sessions),
        "candidate_datasets": raw_candidates,
        "primary_oracle_agreement": "NOT_ESTABLISHED",
        "independent_oracle_required": True,
        "determinism": "FROZEN_SNAPSHOT_INPUT",
        "verdict": verdict,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
    }
    oracle = {
        "schema_version": "ce_pe_dataset_preflight_oracle_v2",
        "oracle_verdict": "INDEPENDENT_ORACLE_REQUIRED",
        "primary_oracle_agreement": "NOT_ESTABLISHED",
        "forbidden_outcome_metric_keys_present": False,
        "primary_summary_consumed": False,
    }
    return registry, preflight, oracle


def build_from_snapshot(*, snapshot_manifest: Path, output_dir: Path) -> dict[str, Any]:
    snapshot_dir = snapshot_manifest.parent
    manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    instrument_master: dict[str, dict[str, Any]] = {}
    for record in manifest.get("selected_candidates", []):
        if record.get("classification") != "INSTRUMENT_MASTER":
            continue
        instrument_master.update(
            _load_instrument_master(snapshot_dir / record["snapshot_relative_path"])
        )

    candidates: list[dict[str, Any]] = []
    for source_record in manifest.get("selected_candidates", []):
        classification = source_record.get("classification")
        if classification == "REAL_OPTION_DATASET":
            classification = "RAW_OPTION_TICK_DATASET"
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
        if classification == "RAW_OPTION_TICK_DATASET":
            inspected = _inspect_dataframe(path, instrument_master)
            inspected["physical_sha256_matches_snapshot"] = (
                inspected.get("physical_sha256")
                == source_record.get("physical_sha256")
            )
            record.update(inspected)
        else:
            record["physical_sha256"] = source_record.get("physical_sha256")
        candidates.append(record)

    registry, preflight, oracle = _assemble_outputs(
        candidates=candidates,
        denied_metadata_only_candidates=int(
            manifest.get("quarantined_non_input_denied_count", 0)
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_sha = write_json_with_sidecar(
        output_dir / "ce_pe_dataset_candidate_registry.json", registry
    )
    preflight_sha = write_json_with_sidecar(
        output_dir / "ce_pe_dataset_preflight.json", preflight
    )
    oracle_sha = write_json_with_sidecar(
        output_dir / "ce_pe_dataset_preflight_oracle.json", oracle
    )
    external = {
        "schema_version": "ce_pe_dataset_external_manifest_v2",
        "artifacts": {
            "ce_pe_dataset_candidate_registry.json": registry_sha,
            "ce_pe_dataset_preflight.json": preflight_sha,
            "ce_pe_dataset_preflight_oracle.json": oracle_sha,
        },
        "verdict": preflight["verdict"],
        "primary_oracle_agreement": preflight["primary_oracle_agreement"],
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(
        output_dir / "ce_pe_dataset_external_manifest.json", external
    )
    return preflight


def build(*, root_manifest: Path, output_dir: Path) -> dict[str, Any]:
    machine = json.loads(root_manifest.read_text(encoding="utf-8"))
    roots = machine.get("roots", [])
    instrument_master: dict[str, dict[str, Any]] = {}
    for root in roots:
        path = Path(root["absolute_path"])
        candidate = path / "runtime/upstox_instruments/complete.json"
        if candidate.exists():
            instrument_master.update(_load_instrument_master(candidate))

    candidates: list[dict[str, Any]] = []
    denied_count = 0
    groups: dict[str, list[str]] = defaultdict(list)
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
            record = {
                "candidate_id": f"{root_id}:{rel}",
                "current_root_id": root_id,
                "relative_path": rel,
                "classification": classification,
                "size": path.stat().st_size,
                "authority_decision": "AUTHORITY_NOT_GRANTED",
                "reason_codes": [],
            }
            if classification == "DENIED_OUTCOME_METADATA_ONLY":
                denied_count += 1
                record["content_read_status"] = "METADATA_ONLY_NOT_OPENED"
                record["reason_codes"].append("outcome_pnl_path_not_opened")
            elif classification in {
                "RAW_OPTION_TICK_DATASET",
                "UNDERLYING_DATASET",
            }:
                record.update(_inspect_dataframe(path, instrument_master))
                record["content_read_status"] = record.pop("read_status")
            else:
                record["physical_sha256"] = sha256_file(path)
            digest = record.get("physical_sha256")
            if digest:
                groups[str(digest)].append(record["candidate_id"])
            candidates.append(record)

    registry, preflight, oracle = _assemble_outputs(
        candidates=candidates,
        denied_metadata_only_candidates=denied_count,
    )
    registry["exact_duplicate_groups"] = [
        {"physical_sha256": digest, "candidate_ids": ids}
        for digest, ids in sorted(groups.items())
        if len(ids) > 1
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_sha = write_json_with_sidecar(
        output_dir / "ce_pe_dataset_candidate_registry.json", registry
    )
    preflight_sha = write_json_with_sidecar(
        output_dir / "ce_pe_dataset_preflight.json", preflight
    )
    oracle_sha = write_json_with_sidecar(
        output_dir / "ce_pe_dataset_preflight_oracle.json", oracle
    )
    external = {
        "schema_version": "ce_pe_dataset_external_manifest_v2",
        "artifacts": {
            "ce_pe_dataset_candidate_registry.json": registry_sha,
            "ce_pe_dataset_preflight.json": preflight_sha,
            "ce_pe_dataset_preflight_oracle.json": oracle_sha,
        },
        "verdict": preflight["verdict"],
        "primary_oracle_agreement": preflight["primary_oracle_agreement"],
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(
        output_dir / "ce_pe_dataset_external_manifest.json", external
    )
    return preflight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-manifest", type=Path)
    parser.add_argument("--snapshot-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.snapshot_manifest:
        result = build_from_snapshot(
            snapshot_manifest=args.snapshot_manifest,
            output_dir=args.output_dir,
        )
    elif args.root_manifest:
        result = build(
            root_manifest=args.root_manifest,
            output_dir=args.output_dir,
        )
    else:
        raise ValueError("root_manifest_or_snapshot_manifest_required")
    print(
        canonical_json(
            {
                "verdict": result["verdict"],
                "candidate_dataset_count": result["candidate_dataset_count"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
