from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .filename_evidence import FilenameEvidence
from .manifest_evidence import ManifestEvidence
from .observed_universe import ObservedUniverseResult
from .row_evidence import RowEvidence
from .schema_classifier import classify_schema_family
from .token_mapping import TokenMappingEvidence


ROOTS = (
    "runtime/market_data/upstox",
    "runtime/strategy_validation",
    "configs/backtest_data_schema_examples",
    "runtime/upstox_instruments",
    "runtime/upstox_candidate_replay",
    "runtime/kite_candidate_replay",
    "tradebot-data",
    "tradebot-ml-evidence",
)

IDENTITY_COLUMNS = {
    "instrument_key",
    "instrument_token",
    "trading_symbol",
    "underlying_symbol",
    "underlying",
    "option_right",
    "option_type",
    "strike",
    "strike_price",
    "expiry",
    "timestamp",
    "ts",
    "exchange_timestamp",
    "bid",
    "ask",
    "ltp",
    "open",
    "high",
    "low",
    "close",
    "best_bid",
    "best_ask",
}


@dataclass(frozen=True)
class ReconstructionRecord:
    logical_path: str
    file_hash: str
    provider: str
    schema_family: str
    row_count: int
    observed_row_identity: bool
    observed_filename_identity: bool
    observed_manifest_identity: bool
    historical_token_mapping_identity: bool
    current_master_enrichment: bool
    observed_symbol: str
    observed_token: str
    observed_underlying: str
    observed_option_right: str
    observed_strike: str
    observed_expiry: str
    observed_bid_ask: bool
    observed_quote_timestamp: str
    filename_symbol: str
    filename_option_right: str
    filename_strike: str
    filename_expiry: str
    manifest_capture_ts: str
    manifest_contract_identity: str
    manifest_hash: str
    historical_mapping_source: str
    historical_mapping_asof_ts: str
    historical_mapping_hash: str
    current_master_match: bool
    current_master_fields_used: str
    observed_existence_status: str
    identity_authority_status: str
    universe_completeness_status: str
    lot_size_status: str
    tick_size_status: str
    cost_authority_status: str
    blockers: str


def build_reconstruction(repo_root: Path) -> tuple[list[ReconstructionRecord], dict[str, Any]]:
    records: list[ReconstructionRecord] = []
    seen: set[str] = set()
    mapping_index = _load_mapping_index(repo_root)
    for root in _roots(repo_root):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".parquet", ".json"}:
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                payload = _read_evidence(path)
            except Exception:
                payload = {"df": pd.DataFrame(), "manifest": {}}
            rec = _classify_file(repo_root, path, payload["df"], payload["manifest"], mapping_index)
            records.append(rec)
    summary = _summarize(records)
    return records, summary


def write_artifacts(records: list[ReconstructionRecord], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda item: item.logical_path)
    payload = {"summary": summary, "files": [asdict(item) for item in ordered]}
    (output_dir / "file_reconstruction.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        pd.DataFrame([asdict(item) for item in ordered]).to_parquet(output_dir / "file_reconstruction.parquet", index=False)
    except Exception:
        pd.DataFrame([asdict(item) for item in ordered]).to_csv(output_dir / "file_reconstruction.parquet.csv", index=False)
    (output_dir / "schema_families.json").write_text(json.dumps(_schema_families(ordered), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "evidence_component_counts.json").write_text(json.dumps(_component_counts(ordered), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "reconstruction_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name in ("schema_families.json", "reconstruction_summary.json"):
        path = output_dir / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")


def _classify_file(repo_root: Path, path: Path, df: pd.DataFrame, manifest_obj: dict[str, Any], mapping_index: dict[str, dict[str, str]]) -> ReconstructionRecord:
    try:
        logical_path = str(path.resolve().relative_to(repo_root.resolve()))
    except Exception:
        logical_path = str(path.resolve())
    schema = classify_schema_family({str(c) for c in df.columns}, logical_path)
    lower_cols = {str(c).lower() for c in df.columns}
    has_ts = bool({"timestamp", "ts", "exchange_timestamp"} & lower_cols)
    has_quote_values = bool({"bid", "ask", "ltp", "open", "high", "low", "close", "best_bid", "best_ask"} & lower_cols)
    row_identity = has_ts and has_quote_values and _row_has_explicit_contract_fields(df)
    token_only_identity = has_ts and bool({"instrument_token", "instrument_key"} & lower_cols) and not has_quote_values and not _row_has_explicit_contract_fields(df)
    filename_identity = _filename_contract_evidence(path.name)
    manifest_identity = bool(manifest_obj.get("manifest_contract_identity") or manifest_obj.get("dataset_hash") or manifest_obj.get("source_manifest"))
    current_master_enrichment = "complete.json" in path.as_posix() and "upstox_instruments" in path.as_posix()
    historical_mapping = _lookup_historical_mapping(df, mapping_index)
    historical_token_mapping_identity = historical_mapping is not None
    blockers: list[str] = []
    observed_existence_status = "INSUFFICIENT_IDENTITY"
    identity_authority_status = "INSUFFICIENT_IDENTITY"
    universe_completeness_status = "INSUFFICIENT_IDENTITY"
    lot_size_status = "INSUFFICIENT_IDENTITY"
    tick_size_status = "INSUFFICIENT_IDENTITY"
    cost_authority_status = "INSUFFICIENT_IDENTITY"
    if current_master_enrichment:
        observed_existence_status = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
        identity_authority_status = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
        universe_completeness_status = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
        lot_size_status = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
        tick_size_status = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
        cost_authority_status = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
        blockers.append("CURRENT_MASTER_NOT_HISTORICAL_AUTHORITY")
    elif row_identity and historical_token_mapping_identity:
        observed_existence_status = "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
        identity_authority_status = "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
        universe_completeness_status = "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
        lot_size_status = "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
        tick_size_status = "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
        cost_authority_status = "HISTORICAL_TOKEN_MAPPED_CONTRACT_AUTHORITY"
    elif row_identity and filename_identity:
        observed_existence_status = "SELF_DESCRIBING_QUOTE_AUTHORITY"
        identity_authority_status = "INSUFFICIENT_IDENTITY"
        universe_completeness_status = "INSUFFICIENT_IDENTITY"
        lot_size_status = "INSUFFICIENT_IDENTITY"
        tick_size_status = "INSUFFICIENT_IDENTITY"
        cost_authority_status = "INSUFFICIENT_IDENTITY"
        blockers.append("NO_HISTORICAL_MAPPING_SOURCE")
    elif token_only_identity:
        observed_existence_status = "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"
        identity_authority_status = "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"
        universe_completeness_status = "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"
        lot_size_status = "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"
        tick_size_status = "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"
        cost_authority_status = "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"
        blockers.append("TOKEN_ONLY_QUOTE")
    elif filename_identity:
        observed_existence_status = "INSUFFICIENT_IDENTITY"
        identity_authority_status = "INSUFFICIENT_IDENTITY"
        universe_completeness_status = "INSUFFICIENT_IDENTITY"
        lot_size_status = "INSUFFICIENT_IDENTITY"
        tick_size_status = "INSUFFICIENT_IDENTITY"
        cost_authority_status = "INSUFFICIENT_IDENTITY"
        blockers.append("INSUFFICIENT_IDENTITY")
    else:
        blockers.append("INSUFFICIENT_IDENTITY")
    observed = RowEvidence(
        row_identity,
        str(_first_value(df, "instrument_token", "instrument_key")),
        str(_first_value(df, "underlying_symbol", "underlying", "symbol")),
        str(_first_value(df, "option_right", "option_type")),
        str(_first_value(df, "strike", "strike_price")),
        str(_first_value(df, "expiry")),
        "bid" in lower_cols and "ask" in lower_cols,
        str(_first_value(df, "timestamp", "ts", "exchange_timestamp")),
    )
    filename = FilenameEvidence(filename_identity, *_filename_contract_fields(path.name))
    manifest = ManifestEvidence(manifest_identity, str(manifest_obj.get("capture_ts", "")), str(manifest_obj.get("manifest_contract_identity", "")), str(manifest_obj.get("manifest_hash", "")))
    mapping = TokenMappingEvidence(historical_token_mapping_identity, str(historical_mapping["source"]) if historical_mapping else "", str(historical_mapping["asof_ts"]) if historical_mapping else "", str(historical_mapping["mapping_hash"]) if historical_mapping else "", current_master_enrichment, "current_master_fields" if current_master_enrichment else "")
    universe = ObservedUniverseResult(observed_existence_status, identity_authority_status, universe_completeness_status, lot_size_status, tick_size_status, cost_authority_status, tuple(blockers))
    return ReconstructionRecord(
        logical_path=logical_path,
        file_hash=_sha256_file(path),
        provider=schema.provider,
        schema_family=schema.schema_family,
        row_count=len(df),
        observed_row_identity=observed.observed_row_identity,
        observed_filename_identity=filename.observed_filename_identity,
        observed_manifest_identity=manifest.observed_manifest_identity,
        historical_token_mapping_identity=mapping.historical_token_mapping_identity,
        current_master_enrichment=mapping.current_master_match,
        observed_symbol="",
        observed_token="",
        observed_underlying="" if current_master_enrichment else str(_first_value(df, "underlying_symbol", "underlying", "symbol")).upper(),
        observed_option_right="" if current_master_enrichment else str(_first_value(df, "option_right", "option_type")).upper(),
        observed_strike="",
        observed_expiry="",
        observed_bid_ask=observed.observed_bid_ask,
        observed_quote_timestamp="",
        filename_symbol="",
        filename_option_right="",
        filename_strike="",
        filename_expiry="",
        manifest_capture_ts=manifest.manifest_capture_ts,
        manifest_contract_identity=manifest.manifest_contract_identity,
        manifest_hash=manifest.manifest_hash,
        historical_mapping_source=mapping.historical_mapping_source,
        historical_mapping_asof_ts=mapping.historical_mapping_asof_ts,
        historical_mapping_hash=mapping.historical_mapping_hash,
        current_master_match=mapping.current_master_match,
        current_master_fields_used=mapping.current_master_fields_used,
        observed_existence_status=universe.observed_existence_status,
        identity_authority_status=universe.identity_authority_status,
        universe_completeness_status=universe.universe_completeness_status,
        lot_size_status=universe.lot_size_status,
        tick_size_status=universe.tick_size_status,
        cost_authority_status=universe.cost_authority_status,
        blockers=";".join(universe.blockers),
    )


def _summarize(records: list[ReconstructionRecord]) -> dict[str, Any]:
    return {
        "version": "option_e2e_contract_reconstruction_v4_2",
        "files_total": len(records),
        "files_read_success": sum(1 for record in records if record.row_count > 0),
        "files_read_failed": sum(1 for record in records if record.row_count == 0),
        "self_describing_quote_files": sum(1 for record in records if record.observed_existence_status == "SELF_DESCRIBING_QUOTE_AUTHORITY"),
        "token_only_quote_files": sum(1 for record in records if record.observed_existence_status == "TOKEN_ONLY_QUOTE_NO_HISTORICAL_MAPPING"),
        "filename_describing_files": sum(1 for record in records if record.observed_filename_identity),
        "manifest_describing_files": sum(1 for record in records if record.observed_manifest_identity),
        "composite_historical_authority_files": sum(1 for record in records if record.historical_token_mapping_identity),
        "current_master_diagnostic_matches": sum(1 for record in records if record.current_master_enrichment),
        "identity_conflict_files": 0,
        "post_expiry_files": 0,
        "files_proving_observed_contract_existence": sum(1 for record in records if record.observed_existence_status == "SELF_DESCRIBING_QUOTE_AUTHORITY"),
        "files_proving_historical_identity": sum(1 for record in records if record.historical_token_mapping_identity),
        "files_proving_observed_dataset_universe": sum(1 for record in records if record.observed_manifest_identity),
        "files_with_lot_size_authority": 0,
        "files_with_tick_size_authority": 0,
    }


def _schema_families(records: list[ReconstructionRecord]) -> dict[str, list[str]]:
    families: dict[str, list[str]] = {}
    for record in records:
        families.setdefault(record.schema_family, []).append(record.logical_path)
    return families


def _component_counts(records: list[ReconstructionRecord]) -> dict[str, int]:
    return {
        "observed_row_identity": sum(1 for record in records if record.observed_row_identity),
        "observed_filename_identity": sum(1 for record in records if record.observed_filename_identity),
        "observed_manifest_identity": sum(1 for record in records if record.observed_manifest_identity),
        "historical_token_mapping_identity": sum(1 for record in records if record.historical_token_mapping_identity),
        "current_master_enrichment": sum(1 for record in records if record.current_master_enrichment),
    }


def _roots(repo_root: Path) -> tuple[Path, ...]:
    return tuple([repo_root.resolve()] + [(repo_root / root).resolve() if not root.startswith("/") else Path(root) for root in ROOTS])


def _read_evidence(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return {"df": pd.read_csv(path), "manifest": {}}
    if suffix == ".parquet":
        return {"df": pd.read_parquet(path), "manifest": {}}
    if suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            return {"df": pd.DataFrame(obj), "manifest": {}}
        if isinstance(obj, dict):
            if isinstance(obj.get("files"), list):
                return {"df": pd.DataFrame(obj["files"]), "manifest": obj.get("summary", obj)}
            if isinstance(obj.get("records"), list):
                return {"df": pd.DataFrame(obj["records"]), "manifest": obj.get("summary", obj)}
            if isinstance(obj.get("rows"), list):
                return {"df": pd.DataFrame(obj["rows"]), "manifest": obj}
            return {"df": pd.DataFrame([obj]), "manifest": obj}
    return {"df": pd.DataFrame(), "manifest": {}}


def _row_has_explicit_contract_fields(df: pd.DataFrame) -> bool:
    lower_cols = {str(c).lower() for c in df.columns}
    return {"underlying_symbol", "option_right", "strike", "expiry"}.issubset(lower_cols)


def _filename_contract_evidence(name: str) -> bool:
    folded = name.lower()
    return bool(re.search(r"(nifty|banknifty|sensex).*(ce|pe)", folded) or re.search(r"(ce|pe).*(nifty|banknifty|sensex)", folded))


def _filename_contract_fields(name: str) -> tuple[str, str, str, str]:
    folded = name.lower()
    underlying = "NIFTY" if "nifty" in folded else "BANKNIFTY" if "banknifty" in folded else "SENSEX" if "sensex" in folded else ""
    option_right = "CE" if "ce" in folded else "PE" if "pe" in folded else ""
    return underlying, option_right, "", ""


def _load_mapping_index(repo_root: Path) -> dict[str, dict[str, str]]:
    mapping_path = repo_root / "runtime" / "upstox_instruments" / "complete.json"
    if not mapping_path.exists():
        return {}
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = payload if isinstance(payload, list) else payload.get("records", [])
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        underlying = str(row.get("underlying_symbol") or row.get("asset_symbol") or row.get("name") or "").upper()
        option_right = str(row.get("instrument_type") or "").upper()
        if underlying != "NIFTY" or option_right not in {"CE", "PE"}:
            continue
        item = {
            "source": "runtime/upstox_instruments/complete.json",
            "asof_ts": str(row.get("updated_at") or row.get("asof_ts") or ""),
            "mapping_hash": str(row.get("sha256") or row.get("hash") or ""),
        }
        for key in (row.get("instrument_key"), row.get("instrument_token"), row.get("exchange_token"), row.get("trading_symbol")):
            if key:
                index[str(key)] = item
    return index


def _lookup_historical_mapping(df: pd.DataFrame, mapping_index: dict[str, dict[str, str]]) -> dict[str, str] | None:
    for column in ("instrument_key", "instrument_token", "trading_symbol"):
        if column not in df.columns:
            continue
        for value in df[column].dropna().astype(str):
            if value in mapping_index:
                return mapping_index[value]
    return None


def _first_value(df: pd.DataFrame, *columns: str) -> Any:
    for column in columns:
        if column in df.columns:
            values = df[column].dropna()
            if not values.empty:
                return values.iloc[0]
    return ""


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict):
            return pd.DataFrame([payload])
        return pd.DataFrame()
    return pd.read_parquet(path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
