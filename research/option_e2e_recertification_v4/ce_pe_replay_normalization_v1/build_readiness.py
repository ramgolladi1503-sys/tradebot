from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.option_backtest.loader import load_option_symbol_csv
from core.option_backtest.models import OptionBacktestConfig, ResearchMode
from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
    sha256_file,
    write_json_with_sidecar,
)


NORMALIZER_VERSION = "ce_pe_replay_normalization_v1"
REQUIRED_OUTPUT_COLUMNS = (
    "timestamp",
    "symbol",
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


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_instrument_master(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    digest = sha256_file(path)
    rows = _load_json(path)
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        for key in (row.get("instrument_key"), row.get("exchange_token")):
            if key is not None:
                mapping[str(key)] = row
    return mapping, digest


def _portable_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _metadata_frame(df: pd.DataFrame, master: dict[str, dict[str, Any]]) -> pd.DataFrame:
    mapped = df["instrument_key"].astype(str).map(master)
    meta = pd.DataFrame(index=df.index)
    meta["option_type"] = mapped.map(
        lambda item: item.get("instrument_type") if isinstance(item, dict) else None
    )
    meta["strike"] = mapped.map(
        lambda item: item.get("strike_price") if isinstance(item, dict) else None
    )
    raw_expiry = mapped.map(lambda item: item.get("expiry") if isinstance(item, dict) else None)
    meta["expiry"] = pd.to_datetime(raw_expiry, unit="ms", errors="coerce").dt.date.astype("string")
    meta["trading_symbol"] = mapped.map(
        lambda item: item.get("trading_symbol") if isinstance(item, dict) else None
    )
    meta["underlying"] = mapped.map(
        lambda item: item.get("underlying_symbol") if isinstance(item, dict) else None
    )
    return meta


def _normalize_one_contract(
    *,
    group: pd.DataFrame,
    symbol: str,
    raw_hash: str,
    master_hash: str,
    output_path: Path,
) -> dict[str, Any]:
    rejection_counts: dict[str, int] = {}
    frame = group.copy()
    frame["timestamp"] = pd.to_datetime(frame["ts"], unit="s", errors="coerce").dt.floor("min") + pd.Timedelta(minutes=1)
    frame["quote_timestamp"] = pd.to_datetime(frame["ts"], unit="s", errors="coerce")
    for column in ("ltp", "bid_price", "ask_price", "volume", "oi", "strike"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    required = (
        frame["timestamp"].notna()
        & frame["quote_timestamp"].notna()
        & frame["ltp"].gt(0)
        & frame["bid_price"].gt(0)
        & frame["ask_price"].gt(0)
        & frame["ask_price"].ge(frame["bid_price"])
        & frame["option_type"].isin(["CE", "PE"])
        & frame["strike"].gt(0)
        & frame["expiry"].notna()
        & frame["underlying"].notna()
    )
    rejection_counts["missing_strict_required_fields"] = int((~required).sum())
    frame = frame.loc[required].copy()
    if frame.empty:
        return {
            "symbol": symbol,
            "output_rows": 0,
            "output_sha256": None,
            "rejection_counts": rejection_counts,
            "loader_status": "NOT_INVOKED_EMPTY_NORMALIZED_OUTPUT",
        }

    frame["provider"] = "upstox"
    frame["dataset_hash"] = raw_hash
    frame["bar_interval"] = "1m"
    frame = frame.sort_values(["timestamp", "quote_timestamp"])
    rows = []
    for timestamp, minute in frame.groupby("timestamp", sort=True):
        if minute.empty:
            continue
        last = minute.iloc[-1]
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "symbol": symbol,
                "open": float(minute["ltp"].iloc[0]),
                "high": float(minute["ltp"].max()),
                "low": float(minute["ltp"].min()),
                "close": float(minute["ltp"].iloc[-1]),
                "volume": float(minute["volume"].fillna(0).max()),
                "oi": float(minute["oi"].fillna(0).iloc[-1]),
                "bid": float(last["bid_price"]),
                "ask": float(last["ask_price"]),
                "quote_timestamp": last["quote_timestamp"].isoformat(),
                "underlying": str(last["underlying"]),
                "option_type": str(last["option_type"]),
                "strike": float(last["strike"]),
                "expiry": str(last["expiry"]),
                "provider": "upstox",
                "dataset_hash": raw_hash,
                "bar_interval": "1m",
            }
        )
    normalized = pd.DataFrame(rows, columns=REQUIRED_OUTPUT_COLUMNS)
    duplicate_minutes = int(normalized["timestamp"].duplicated().sum())
    if duplicate_minutes:
        rejection_counts["duplicate_output_minutes"] = duplicate_minutes
        normalized = normalized.drop_duplicates(subset=["timestamp"], keep="last")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False)
    output_hash = sha256_file(output_path)
    loader_status = "PASS"
    loader_error = None
    try:
        cfg = OptionBacktestConfig(
            symbol=symbol,
            data_path=output_path,
            research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
            bar_interval_minutes=1,
        )
        load_option_symbol_csv(
            data_path=output_path,
            symbol=symbol,
            date_from=None,
            date_to=None,
            timezone="Asia/Kolkata",
            config=cfg,
        )
    except Exception as exc:
        loader_status = "FAIL"
        loader_error = str(exc)
    return {
        "symbol": symbol,
        "output_rows": int(len(normalized)),
        "output_sha256": output_hash,
        "raw_source_sha256": raw_hash,
        "instrument_master_sha256": master_hash,
        "normalizer_version": NORMALIZER_VERSION,
        "parameters": {
            "bar_interval": "1m",
            "forward_fill": False,
            "midpoint_substitution": False,
            "underlying_price_substitution": False,
        },
        "rejection_counts": rejection_counts,
        "loader_status": loader_status,
        "loader_error": loader_error,
    }


def build(*, snapshot_manifest: Path, output_root: Path, evidence_dir: Path, max_contracts: int = 12) -> dict[str, Any]:
    manifest = _load_json(snapshot_manifest)
    snapshot_dir = snapshot_manifest.parent
    master_record = next(
        record for record in manifest["selected_candidates"] if record["classification"] == "INSTRUMENT_MASTER"
    )
    raw_records = [
        record for record in manifest["selected_candidates"] if record["classification"] == "REAL_OPTION_DATASET"
    ]
    master, master_hash = _load_instrument_master(snapshot_dir / master_record["snapshot_relative_path"])
    contract_results: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    valid_sessions: set[str] = set()
    for record in raw_records:
        raw_path = snapshot_dir / record["snapshot_relative_path"]
        raw_hash = sha256_file(raw_path)
        df = pd.read_parquet(raw_path)
        if "instrument_key" not in df.columns or "ts" not in df.columns:
            candidate_records.append(
                {
                    "candidate_id": record["candidate_id"],
                    "physical_sha256": raw_hash,
                    "raw_source_verdict": "RAW_OPTION_SOURCE_INVALID",
                    "reason": "missing_instrument_key_or_ts",
                }
            )
            continue
        meta = _metadata_frame(df, master)
        enriched = pd.concat([df.reset_index(drop=True), meta.reset_index(drop=True)], axis=1)
        ts = pd.to_datetime(enriched["ts"], unit="s", errors="coerce")
        option_mask = enriched["option_type"].isin(["CE", "PE"])
        valid_sessions.update(ts.loc[option_mask & ts.notna()].dt.date.astype(str).unique().tolist())
        ce_rows = int((enriched["option_type"] == "CE").sum())
        pe_rows = int((enriched["option_type"] == "PE").sum())
        bid = pd.to_numeric(enriched.get("bid_price"), errors="coerce")
        ask = pd.to_numeric(enriched.get("ask_price"), errors="coerce")
        candidate_records.append(
            {
                "candidate_id": record["candidate_id"],
                "physical_sha256": raw_hash,
                "provider": "upstox" if "upstox" in record["candidate_id"].casefold() else None,
                "provider_evidence_source": "PATH_INFERRED_LIMITATION",
                "instrument_master_sha256": master_hash,
                "date_count": int(len(set(ts.loc[option_mask & ts.notna()].dt.date.astype(str).tolist()))),
                "sessions": sorted(set(ts.loc[option_mask & ts.notna()].dt.date.astype(str).tolist())),
                "ce_rows": ce_rows,
                "pe_rows": pe_rows,
                "ce_contracts": int(enriched.loc[enriched["option_type"] == "CE", "instrument_key"].nunique()),
                "pe_contracts": int(enriched.loc[enriched["option_type"] == "PE", "instrument_key"].nunique()),
                "bid_ask_joint_coverage": float((bid.gt(0) & ask.gt(0) & ask.ge(bid)).mean()),
                "quote_timestamp_coverage": float(ts.notna().mean()),
                "contract_metadata_coverage": float((option_mask & enriched["strike"].notna() & enriched["expiry"].notna()).mean()),
                "unmapped_instrument_keys": int(enriched.loc[enriched["option_type"].isna(), "instrument_key"].nunique()),
                "duplicate_rows": int(enriched.duplicated(subset=["instrument_key", "ts"]).sum()),
                "raw_source_verdict": "RAW_CE_PE_TICK_SOURCE_VALIDATED" if ce_rows and pe_rows else "RAW_OPTION_SOURCE_INVALID",
            }
        )
        if not ce_rows or not pe_rows:
            continue
        counts = enriched.loc[option_mask].groupby("instrument_key").size().sort_values(ascending=False)
        selected_keys = list(counts.head(max_contracts).index)
        for key in selected_keys:
            group = enriched.loc[enriched["instrument_key"] == key].copy()
            symbol = str(group["trading_symbol"].dropna().iloc[0] if group["trading_symbol"].notna().any() else key)
            safe_symbol = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in symbol)
            out = output_root / record["physical_sha256"] / f"{safe_symbol}.csv"
            contract_results.append(
                _normalize_one_contract(
                    group=group,
                    symbol=symbol,
                    raw_hash=raw_hash,
                    master_hash=master_hash,
                    output_path=out,
                )
            )

    loader_passes = [result for result in contract_results if result["loader_status"] == "PASS"]
    coverage = "ONE_SESSION_SMOKE_ONLY" if len(valid_sessions) <= 1 else "MULTI_SESSION_ADAPTER_VALIDATION_ONLY"
    if loader_passes and coverage == "ONE_SESSION_SMOKE_ONLY":
        replay_verdict = "INSUFFICIENT_REPLAY_COVERAGE"
        normalization_result = "NORMALIZER_SMOKE_PASS"
    elif loader_passes:
        replay_verdict = "STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED"
        normalization_result = "NORMALIZED_CONTRACTS_STRICT_LOADER_PASS"
    else:
        replay_verdict = "STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED"
        normalization_result = "NORMALIZER_SMOKE_FAILED"
    primary = {
        "schema_version": "ce_pe_replay_readiness_v1",
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
        "candidate_count": len(candidate_records),
        "raw_option_candidate_count": len(raw_records),
        "valid_option_dates": sorted(valid_sessions),
        "valid_session_count": len(valid_sessions),
        "chronological_coverage_verdict": coverage,
        "candidate_records": candidate_records,
        "normalized_contract_count": len(contract_results),
        "strict_loader_pass_count": len(loader_passes),
        "strict_loader_fail_count": len(contract_results) - len(loader_passes),
        "strict_loader_results": contract_results,
        "normalization_result": normalization_result,
        "replay_dataset_verdict": replay_verdict,
        "strategy_development_authorized": False,
        "normalized_output_storage": "EXTERNAL_EVIDENCE_ROOT_NOT_COMMITTED",
    }
    oracle = {
        "schema_version": "ce_pe_replay_readiness_oracle_v1",
        "candidate_identity_hash": _portable_hash(
            sorted((item["candidate_id"], item["physical_sha256"]) for item in candidate_records)
        ),
        "dates": sorted(valid_sessions),
        "strict_loader_pass_symbols": sorted(result["symbol"] for result in loader_passes),
        "strict_loader_pass_count": len(loader_passes),
        "strict_loader_fail_count": len(contract_results) - len(loader_passes),
        "final_verdict": replay_verdict,
        "safety_flags": {
            "research_only": True,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "outcomes_read": False,
            "pnl_read": False,
            "holdout_outcomes_read": False,
        },
    }
    primary["oracle_agreement"] = (
        "AGREEMENT"
        if oracle["strict_loader_pass_count"] == primary["strict_loader_pass_count"]
        and oracle["dates"] == primary["valid_option_dates"]
        and oracle["final_verdict"] == primary["replay_dataset_verdict"]
        else "INVALID_DATASET_SELECTION_EVIDENCE"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    primary_sha = write_json_with_sidecar(evidence_dir / "ce_pe_replay_readiness_summary.json", primary)
    oracle_sha = write_json_with_sidecar(evidence_dir / "ce_pe_replay_readiness_oracle.json", oracle)
    external = {
        "schema_version": "ce_pe_replay_readiness_external_manifest_v1",
        "artifacts": {
            "ce_pe_replay_readiness_summary.json": primary_sha,
            "ce_pe_replay_readiness_oracle.json": oracle_sha,
        },
        "normalized_output_storage": "EXTERNAL_EVIDENCE_ROOT_NOT_COMMITTED",
        "replay_dataset_verdict": replay_verdict,
        "oracle_agreement": primary["oracle_agreement"],
        "strategy_development_authorized": False,
    }
    write_json_with_sidecar(evidence_dir / "ce_pe_replay_readiness_external_manifest.json", external)
    return primary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--max-contracts", type=int, default=12)
    args = parser.parse_args()
    result = build(
        snapshot_manifest=args.snapshot_manifest,
        output_root=args.output_root,
        evidence_dir=args.evidence_dir,
        max_contracts=args.max_contracts,
    )
    print(
        canonical_json(
            {
                "replay_dataset_verdict": result["replay_dataset_verdict"],
                "strict_loader_pass_count": result["strict_loader_pass_count"],
                "valid_session_count": result["valid_session_count"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
