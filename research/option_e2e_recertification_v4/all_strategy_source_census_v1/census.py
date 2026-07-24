from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REQUIRED_BUNDLE_FILES = (
    "run_status.json",
    "source_search_summary.json",
    "source_search_manifest.json",
    "candidate_inventory.jsonl",
    "root_inventory.json",
    "git_search_manifest.json",
    "source_search_manifest.json.sha256",
)

@dataclass(frozen=True)
class BundleIntegrity:
    status: str
    errors: list[str]
    path: str
    candidate_count: int
    accepted_candidate_count: int
    unresolved_candidate_count: int
    candidate_inventory_sha256: str
    manifest_semantic_sha256: str


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _semantic_hash(payload: object) -> str:
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _portable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _portable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def verify_input_bundle(bundle_dir: Path) -> BundleIntegrity:
    bundle_dir = bundle_dir.resolve()
    errors: list[str] = []
    for name in REQUIRED_BUNDLE_FILES:
        if not (bundle_dir / name).exists():
            errors.append(f"MISSING:{name}")
    run_status = _read_json(bundle_dir / "run_status.json") if (bundle_dir / "run_status.json").exists() else {}
    summary = _read_json(bundle_dir / "source_search_summary.json") if (bundle_dir / "source_search_summary.json").exists() else {}
    manifest = _read_json(bundle_dir / "source_search_manifest.json") if (bundle_dir / "source_search_manifest.json").exists() else {}
    candidate_path = bundle_dir / "candidate_inventory.jsonl"
    candidates = _read_jsonl(candidate_path) if candidate_path.exists() else []
    candidate_count = len(candidates)
    accepted_candidate_count = sum(1 for row in candidates if row.get("accepted") is True)
    unresolved_candidate_count = sum(1 for row in candidates if row.get("unresolved") is True)
    candidate_sha256 = _sha256_file(candidate_path) if candidate_path.exists() else ""
    sidecar = (bundle_dir / "source_search_manifest.json.sha256").read_text(encoding="utf-8").split()[0] if (bundle_dir / "source_search_manifest.json.sha256").exists() else ""
    manifest_semantic_sha256 = str(manifest.get("semantic_sha256", ""))
    if sidecar and manifest_semantic_sha256 and sidecar != manifest_semantic_sha256:
        errors.append("SIDECAR_MISMATCH")
    if run_status.get("status") != "COMPLETE":
        errors.append("RUN_STATUS_NOT_COMPLETE")
    if summary.get("candidate_count") != candidate_count:
        errors.append("CANDIDATE_COUNT_MISMATCH")
    if summary.get("accepted_candidate_count") != accepted_candidate_count:
        errors.append("ACCEPTED_COUNT_MISMATCH")
    if summary.get("unresolved_candidate_count") != unresolved_candidate_count:
        errors.append("UNRESOLVED_COUNT_MISMATCH")
    if manifest.get("candidate_count") != candidate_count:
        errors.append("MANIFEST_COUNT_MISMATCH")
    if manifest.get("accepted_candidate_count") != accepted_candidate_count:
        errors.append("MANIFEST_ACCEPTED_MISMATCH")
    if manifest.get("unresolved_candidate_count") != unresolved_candidate_count:
        errors.append("MANIFEST_UNRESOLVED_MISMATCH")
    if manifest.get("semantic_sha256") and sidecar and manifest.get("semantic_sha256") != sidecar:
        errors.append("MANIFEST_SHA256_MISMATCH")
    return BundleIntegrity(
        status="INPUT_BUNDLE_INTEGRITY_PASSED" if not errors else "INPUT_BUNDLE_INTEGRITY_FAILED",
        errors=errors,
        path=str(bundle_dir),
        candidate_count=candidate_count,
        accepted_candidate_count=accepted_candidate_count,
        unresolved_candidate_count=unresolved_candidate_count,
        candidate_inventory_sha256=candidate_sha256,
        manifest_semantic_sha256=manifest_semantic_sha256,
    )


def _exact_duplicate_groups(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        sha = str(row.get("sha256", ""))
        classification = str(row.get("classification", ""))
        size = int(row.get("size", 0) or 0)
        if sha:
            groups[(sha, classification, size)].append(row)
    output = []
    for (sha, classification, size), rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(rows) <= 1:
            continue
        selected = min(rows, key=lambda row: (str(row.get("root_id", "")), str(row.get("relative_path", ""))))
        output.append(
            {
                "canonical_candidate_id": f"{sha}:{classification}:{size}",
                "sha256": sha,
                "classification": classification,
                "copy_count": len(rows),
                "root_ids": sorted({str(row.get("root_id", "")) for row in rows}),
                "relative_paths": sorted({str(row.get("relative_path", "")) for row in rows}),
                "selected_canonical_copy": {"root_id": selected.get("root_id"), "relative_path": selected.get("relative_path")},
                "selection_reason": "PREFERRED_PATH_STABILITY",
            }
        )
    return output


def _semantic_key_for_row(row: dict[str, Any]) -> tuple[str, ...]:
    classification = str(row.get("classification", ""))
    rel = str(row.get("relative_path", ""))
    if classification == "UNDERLYING_CANDLE_DATASET":
        return (
            classification,
            rel.lower().replace("\\", "/").split("/")[-1],
            str(row.get("row_count", "")),
            str(row.get("nifty_identity", "")),
        )
    if classification == "PRE_OUTCOME_SIGNAL_LEDGER":
        cols = tuple(sorted(row.get("columns", [])))
        return (
            classification,
            str(row.get("root_id", "")),
            str(row.get("row_count", "")),
            hashlib.sha256(("|".join(cols)).encode("utf-8")).hexdigest(),
        )
    return (classification, str(row.get("sha256", "")), rel)


def _semantic_duplicate_groups(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        groups[_semantic_key_for_row(row)].append(row)
    output = []
    for key, rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(rows) <= 1:
            continue
        selected = min(rows, key=lambda row: (str(row.get("root_id", "")), str(row.get("relative_path", ""))))
        output.append(
            {
                "semantic_key": list(key),
                "copy_count": len(rows),
                "root_ids": sorted({str(row.get("root_id", "")) for row in rows}),
                "relative_paths": sorted({str(row.get("relative_path", "")) for row in rows}),
                "selected_canonical_copy": {"root_id": selected.get("root_id"), "relative_path": selected.get("relative_path")},
            }
        )
    return output


def _status_for_dataset(row: dict[str, Any]) -> str:
    if row.get("accepted") and row.get("classification") == "UNDERLYING_CANDLE_DATASET":
        return "CANONICAL_UNDERLYING_DATASET" if not row.get("rejection_code") else "USABLE_WITH_LIMITATIONS"
    if row.get("classification") == "UNDERLYING_CANDLE_DATASET" and not row.get("accepted"):
        return "EXPLORATORY_ONLY"
    return "UNRESOLVED_DATASET"


def _canonical_dataset_registry(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    datasets = [row for row in candidates if row.get("classification") == "UNDERLYING_CANDLE_DATASET"]
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in datasets:
        by_key[(str(row.get("sha256", "")), str(row.get("row_count", "")))].append(row)
    out = []
    for (sha, row_count), rows in sorted(by_key.items(), key=lambda item: (-len(item[1]), item[0])):
        selected = min(rows, key=lambda row: (str(row.get("root_id", "")), str(row.get("relative_path", ""))))
        out.append(
            {
                "canonical_dataset_id": f"{sha}:{row_count}",
                "sha256": sha,
                "row_count": int(row_count or 0),
                "copy_count": len(rows),
                "root_ids": sorted({str(row.get("root_id", "")) for row in rows}),
                "relative_paths": sorted({str(row.get("relative_path", "")) for row in rows}),
                "status": _status_for_dataset(selected),
                "selected_canonical_copy": {"root_id": selected.get("root_id"), "relative_path": selected.get("relative_path")},
                "selection_reason": "CANONICAL_DATASET_SELECTED_BY_STABILITY",
            }
        )
    return out


def _canonical_signal_registry(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledgers = [row for row in candidates if row.get("classification") == "PRE_OUTCOME_SIGNAL_LEDGER"]
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ledgers:
        by_key[(str(row.get("sha256", "")), str(row.get("row_count", "")))].append(row)
    out = []
    for (sha, row_count), rows in sorted(by_key.items(), key=lambda item: (-len(item[1]), item[0])):
        selected = min(rows, key=lambda row: (str(row.get("root_id", "")), str(row.get("relative_path", ""))))
        approved = bool(selected.get("accepted")) and bool(selected.get("sha256")) and bool(selected.get("row_count"))
        status = "INVALID_SIGNAL_LEDGER"
        if approved:
            status = "INSUFFICIENT_PROVENANCE"
        out.append(
            {
                "canonical_signal_ledger_id": f"{sha}:{row_count}",
                "sha256": sha,
                "row_count": int(row_count or 0),
                "copy_count": len(rows),
                "root_ids": sorted({str(row.get("root_id", "")) for row in rows}),
                "relative_paths": sorted({str(row.get("relative_path", "")) for row in rows}),
                "status": status,
                "selected_canonical_copy": {"root_id": selected.get("root_id"), "relative_path": selected.get("relative_path")},
                "selection_reason": "CANONICAL_SIGNAL_LEDGER_SELECTED_BY_STABILITY",
            }
        )
    return out


def _dataset_family_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    rel = str(row.get("relative_path", "")).lower()
    instrument_type = "unknown"
    market = "unknown"
    bar_interval = "unknown"
    if "nifty_f1" in rel or "aeron7" in rel:
        return ("NIFTY_F1", "futures", "NSE", "1m")
    if "banknifty" in rel:
        return ("BANKNIFTY", "spot", "NSE", "unknown")
    if "sensex" in rel:
        return ("SENSEX", "spot", "BSE", "unknown")
    if "continuous_futures" in rel:
        return ("NIFTY_CONTINUOUS_FUTURES", "futures", "NSE", "unknown")
    if "futures" in rel:
        return ("NIFTY_FUTURES", "futures", "NSE", "unknown")
    if "nifty 50" in rel or "nifty_50" in rel or rel.endswith("nifty.csv") or "nifty" in rel:
        instrument_type = "spot"
        market = "NSE"
        bar_interval = "5m" if "5minute" in rel or "5m" in rel else "unknown"
        return ("NIFTY_SPOT", instrument_type, market, bar_interval)
    if "options_intraday" in rel or "option" in rel:
        return ("OPTIONS_INTRADAY", "proxy", "NSE", "unknown")
    if "combined" in rel:
        return ("COMBINED_SOURCE", "synthetic", "NSE", "unknown")
    return ("UNRESOLVED_FAMILY", "unknown", "unknown", "unknown")


def _partition_role(relative_path: str) -> str:
    rel = relative_path.lower()
    if "daily" in rel:
        return "DAILY_PARTITION"
    if "monthly" in rel:
        return "MONTHLY_PARTITION"
    if "session" in rel:
        return "SESSION_PARTITION"
    if "slice" in rel or "derived" in rel or "feature" in rel:
        return "DERIVED_SLICE"
    if "parquet" in rel or "csv" in rel or "jsonl" in rel:
        return "MONOLITHIC_FILE"
    return "UNKNOWN_PARTITION"


def _physical_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in candidates:
        out.append(
            {
                "candidate_id": str(row.get("candidate_id", "")) or f"{row.get('root_id', '')}:{row.get('relative_path', '')}",
                "root_id": row.get("root_id"),
                "relative_path": row.get("relative_path"),
                "physical_sha256": row.get("sha256"),
                "size": row.get("size"),
                "classification": row.get("classification"),
                "accepted": bool(row.get("accepted")),
                "unresolved": bool(row.get("unresolved")),
            }
        )
    return out


def _exact_content_blobs(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        sha = str(row.get("sha256", ""))
        classification = str(row.get("classification", ""))
        size = int(row.get("size", 0) or 0)
        if sha:
            grouped[(sha, classification, size)].append(row)
    out = []
    for (sha, classification, size), rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        selected = min(rows, key=lambda row: (str(row.get("root_id", "")), str(row.get("relative_path", ""))))
        out.append(
            {
                "blob_id": f"{sha}:{classification}:{size}",
                "physical_sha256": sha,
                "classification": classification,
                "size": size,
                "copy_count": len(rows),
                "candidate_ids": [str(row.get("candidate_id", "")) or f"{row.get('root_id', '')}:{row.get('relative_path', '')}" for row in rows],
                "all_paths": sorted({str(row.get("relative_path", "")) for row in rows}),
                "canonical_copy": {"root_id": selected.get("root_id"), "relative_path": selected.get("relative_path")},
                "canonical_selection_reason": "PREFERRED_PATH_STABILITY",
            }
        )
    return out


def _logical_dataset_families(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted = [row for row in candidates if row.get("classification") == "UNDERLYING_CANDLE_DATASET" and row.get("accepted")]
    families: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        families[_dataset_family_key(row)].append(row)
    out: list[dict[str, Any]] = []
    for key, rows in sorted(families.items(), key=lambda item: item[0]):
        family_id = "FAMILY:" + ":".join(key)
        exact_copy_count = max(0, len(rows) - len({str(r.get("sha256", "")) for r in rows}))
        first_row = min(rows, key=lambda row: (str(row.get("root_id", "")), str(row.get("relative_path", ""))))
        family_status = "IDENTITY_INCOMPLETE" if "unknown" in key or key[0] == "UNRESOLVED_FAMILY" else "PROVISIONAL"
        out.append({
            "dataset_family_id": family_id,
            "instrument": key[0],
            "instrument_type": key[1],
            "market": key[2],
            "bar_interval": key[3],
            "timezone": "IST" if key[0] != "UNRESOLVED_FAMILY" else "UNKNOWN",
            "source_owner": "tradebot" if any("runtime/" in str(r.get("relative_path", "")).lower() for r in rows) else "unresolved",
            "generation_method": "derived" if any("derived" in str(r.get("relative_path", "")).lower() or "aeron7" in str(r.get("relative_path", "")).lower() for r in rows) else "source",
            "partition_count": len({str(r.get("relative_path")) for r in rows}),
            "physical_file_count": len(rows),
            "exact_copy_count": exact_copy_count,
            "first_timestamp": first_row.get("first_timestamp"),
            "last_timestamp": first_row.get("last_timestamp"),
            "session_count": first_row.get("session_count"),
            "session_set_hash": first_row.get("session_set_hash"),
            "versions": [],
            "identity_status": family_status,
        })
    return out


def _dataset_versions(candidates: list[dict[str, Any]], families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted = [row for row in candidates if row.get("classification") == "UNDERLYING_CANDLE_DATASET" and row.get("accepted")]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in accepted:
        family_key = _dataset_family_key(row)
        family_id = "FAMILY:" + ":".join(family_key)
        version_key = (family_id, str(row.get("sha256", "")))
        if version_key in seen:
            continue
        seen.add(version_key)
        rel = str(row.get("relative_path", "")).lower()
        status = "UNRESOLVED_DATASET_VERSION"
        limitations: list[str] = []
        if "unknown" not in family_key and family_key[0] != "UNRESOLVED_FAMILY":
            status = "CANONICAL_DATASET_VERSION" if row.get("accepted") and row.get("sha256") else "USABLE_WITH_LIMITATIONS"
        if "derived" in rel or "aeron7" in rel:
            status = "USABLE_WITH_LIMITATIONS"
            limitations.append("derived_or_cached_source")
        if not row.get("timezone"):
            status = "USABLE_WITH_LIMITATIONS" if status == "CANONICAL_DATASET_VERSION" else status
            limitations.append("timezone_incomplete")
        if not row.get("root_id"):
            limitations.append("source_provenance_incomplete")
        out.append({
            "dataset_version_id": "VERSION:" + family_id + ":" + str(row.get("sha256", ""))[:16],
            "dataset_family_id": family_id,
            "schema_hash": hashlib.sha256(",".join(sorted(row.get("columns", []))).encode("utf-8")).hexdigest() if row.get("columns") else "",
            "partition_manifest_hash": str(row.get("sha256", "")),
            "session_set_hash": str(row.get("sha256", ""))[:16],
            "source_provenance": str(row.get("root_id", "")),
            "creation_method": "physical_file",
            "partition_ids": [str(row.get("relative_path", ""))],
            "quality_metrics": {
                "row_count": row.get("row_count"),
                "copy_count": 1,
            },
            "status": status,
            "limitations": limitations if limitations else ([] if status == "CANONICAL_DATASET_VERSION" else ["identity_or_provenance_incomplete"]),
        })
    return out


def _current_986_breakdown(candidates: list[dict[str, Any]], exact: list[dict[str, Any]], families: list[dict[str, Any]], versions: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in candidates if row.get("classification") == "UNDERLYING_CANDLE_DATASET" and row.get("accepted")]
    return {
        "superseded_file_level_dataset_count": 986,
        "supersession_reason": "PHYSICAL_FILES_AND_PARTITIONS_WERE_MISLABELLED_AS_DATASETS",
        "raw_candidate_file_count": len(candidates),
        "accepted_physical_file_count": len(accepted),
        "exact_content_blob_count": len(exact),
        "duplicate_physical_copy_count": max(0, len(accepted) - len(exact)),
        "dataset_partition_count": len(accepted),
        "logical_dataset_family_count": len(families),
        "dataset_version_count": len(versions),
    }


def _signal_ledger_audit(ledgers: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in candidates if row.get("classification") == "PRE_OUTCOME_SIGNAL_LEDGER"]
    out: list[dict[str, Any]] = []
    for ledger in ledgers:
        candidate = rows[0] if rows else {}
        status = "INVALID_SIGNAL_LEDGER"
        if candidate and candidate.get("accepted") and candidate.get("sha256") and candidate.get("row_count"):
            status = "INSUFFICIENT_PROVENANCE"
        out.append(
            {
                "canonical_signal_ledger_id": ledger["canonical_signal_ledger_id"],
                "exact_path": candidate.get("relative_path"),
                "physical_sha256": candidate.get("sha256"),
                "strategy_or_hypothesis_id": candidate.get("strategy_or_hypothesis_id"),
                "alias_group": candidate.get("alias_group"),
                "row_count": candidate.get("row_count"),
                "session_count": candidate.get("session_count"),
                "signal_id_unique": bool(candidate.get("signal_id_unique", True)),
                "feature_cutoff_ts": candidate.get("feature_cutoff_ts"),
                "signal_ts": candidate.get("signal_ts"),
                "earliest_entry_ts": candidate.get("earliest_entry_ts"),
                "implementation_commit": candidate.get("implementation_commit"),
                "parameter_hash": candidate.get("parameter_hash"),
                "dataset_source_hash": candidate.get("dataset_source_hash"),
                "fold_identity": candidate.get("fold_identity"),
                "is_holdout": candidate.get("is_holdout"),
                "pre_outcome_freeze_provenance": candidate.get("pre_outcome_freeze_provenance"),
                "status": status,
            }
        )
    return out


def _unresolved_candidate_resolution(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved = [row for row in candidates if row.get("unresolved")]
    resolved_duplicate = [row for row in unresolved if row.get("classification") == "UNDERLYING_CANDLE_DATASET"]
    unresolved_out = []
    for row in unresolved:
        unresolved_out.append(
            {
                "candidate_id": str(row.get("candidate_id", "")) or f"{row.get('root_id', '')}:{row.get('relative_path', '')}",
                "root_id": row.get("root_id"),
                "relative_path": row.get("relative_path"),
                "original_reason": row.get("reason") or row.get("classification"),
                "targeted_inspection_performed": bool(row.get("targeted_inspection_performed", False)),
                "final_status": "still_unresolved" if not row.get("resolved") else row.get("resolved_status", "resolved"),
                "final_reason": row.get("final_reason") or "targeted inspection not performed",
            }
        )
    return [{
        "input_unresolved_count": len(unresolved),
        "resolved_as_duplicate": len(resolved_duplicate),
        "resolved_as_invalid": sum(1 for row in unresolved if row.get("resolved_status") == "invalid"),
        "resolved_as_usable": sum(1 for row in unresolved if row.get("resolved_status") == "usable"),
        "still_unresolved": sum(1 for row in unresolved if not row.get("resolved")),
        "items": unresolved_out,
    }]


def _strategy_specs() -> list[dict[str, Any]]:
    return [
        {"canonical_strategy_id": "VWAP_RECLAIM", "aliases": ["vwap reclaim", "VWAP_RECLAIM"], "patterns": ["strategies/movement/vwap_reclaim.py"], "category": "mean_reversion", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "strategies/movement/vwap_reclaim.py"},
        {"canonical_strategy_id": "OPENING_RANGE_BREAKOUT", "aliases": ["ORB", "OPENING_RANGE_BREAKOUT"], "patterns": ["opening_range_breakout", "orb"], "category": "opening_momentum", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "OPENING_RANGE_RETEST", "aliases": ["OPENING_RANGE_RETEST", "Opening Range Retest"], "patterns": ["opening_range_retest"], "category": "opening_momentum", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "TREND_PULLBACK", "aliases": ["TREND_PULLBACK"], "patterns": ["trend_pullback"], "category": "trend", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "COMPRESSION_BREAKOUT", "aliases": ["COMPRESSION_BREAKOUT"], "patterns": ["compression_breakout"], "category": "breakout", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "NO_TRADE_CHOP", "aliases": ["NO_TRADE_CHOP"], "patterns": ["no_trade_chop"], "category": "filter", "dataset_hint": "NOT_APPLICABLE", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "OPENING_STATE_MOMENTUM", "aliases": ["OPENING_STATE_MOMENTUM"], "patterns": ["opening state momentum", "opening_state"], "category": "opening_momentum", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "RSI2_MEAN_REVERSION", "aliases": ["RSI2", "RSI2_MEAN_REVERSION"], "patterns": ["rsi2"], "category": "mean_reversion", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "RESIDUAL_MEAN_REVERSION", "aliases": ["RESIDUAL_MEAN_REVERSION"], "patterns": ["residual_mean_reversion", "residual mean"], "category": "mean_reversion", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "CONSTITUENT_LEAD_LAG", "aliases": ["CONSTITUENT_LEAD_LAG"], "patterns": ["lead_lag", "lead-lag"], "category": "cross_asset", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "CONSTITUENT_BREADTH", "aliases": ["CONSTITUENT_BREADTH"], "patterns": ["breadth"], "category": "cross_asset", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "STRUCTURAL_PATTERN_SUITE", "aliases": ["STRUCTURAL_PATTERN_SUITE"], "patterns": ["structural_pattern"], "category": "research_suite", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "STRUCTURAL_STATE_DISCOVERY", "aliases": ["STRUCTURAL_STATE_DISCOVERY"], "patterns": ["structural_state"], "category": "research_suite", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "ML_STRATEGY_DISCOVERY", "aliases": ["ML_STRATEGY_DISCOVERY"], "patterns": ["ml_strategy_discovery"], "category": "research_suite", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "FIVE_MINUTE_GOVERNED_DISCOVERY", "aliases": ["FIVE_MINUTE_GOVERNED_DISCOVERY"], "patterns": ["five-minute governed", "governed five-minute"], "category": "research_suite", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
        {"canonical_strategy_id": "CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY", "aliases": ["CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY"], "patterns": ["continuous structural", "continuous-edge"], "category": "research_suite", "dataset_hint": "UNDERLYING_CANDLE_DATASET", "parameter_owner": "UNRESOLVED"},
    ]


def _locate_strategy(spec: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    matches = []
    for pattern in spec["patterns"]:
        for path in repo_root.rglob("*"):
            if path.is_file() and pattern.lower() in path.as_posix().lower():
                matches.append(str(path.relative_to(repo_root)))
    matches = sorted(dict.fromkeys(matches))
    implementation_path = matches[0] if matches else None
    blob_hash = _sha256_file(repo_root / implementation_path) if implementation_path else ""
    return {
        "canonical_strategy_id": spec["canonical_strategy_id"],
        "aliases": spec["aliases"],
        "category": spec["category"],
        "implementation_path": implementation_path,
        "implementation_commit": "UNRESOLVED",
        "implementation_blob_hash": blob_hash,
        "working_tree_file_hash": blob_hash,
        "parameter_owner": spec.get("parameter_owner", "UNRESOLVED"),
        "resolved_required_parameters": [],
        "temporal_contract": "CAUSAL_ONLY",
        "required_input_data": spec["dataset_hint"],
        "valid_precomputed_signal_ledger": None,
        "invalidated_evidence": [],
        "development_split_authority": "UNRESOLVED",
        "holdout_authority": "UNRESOLVED",
        "option_data_requirements": "NOT_EVALUATED",
        "current_status": "SOURCE_SEARCH_INCOMPLETE" if not implementation_path else "IMPLEMENTATION_BLOCKED",
    }


def _readiness_matrix(strategy_inventory: list[dict[str, Any]], datasets: list[dict[str, Any]], ledgers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_dataset = datasets[0] if datasets else None
    approved_ledgers = [row for row in ledgers if row.get("status") in {"CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER", "VALID_WITH_LIMITATIONS"}]
    selected_ledger = approved_ledgers[0] if approved_ledgers else None
    out = []
    for strategy in strategy_inventory:
        status = "SOURCE_SEARCH_INCOMPLETE"
        blocker = "SOURCE_SEARCH_INCOMPLETE"
        if strategy["implementation_path"] and selected_dataset and selected_ledger:
            status = "VALID_PRECOMPUTED_SIGNALS"
            blocker = ""
        elif strategy["implementation_path"] and selected_dataset:
            status = "READY_WITH_DATA_LIMITATIONS"
            blocker = "INSUFFICIENT_SIGNAL_PROVENANCE"
        elif strategy["implementation_path"]:
            status = "IMPLEMENTATION_BLOCKED"
            blocker = "DATASET_BLOCKED"
        if strategy["canonical_strategy_id"] == "NO_TRADE_CHOP":
            status = "NO_TRADE_FILTER"
            blocker = "NO_TRADE_FILTER"
        out.append(
            {
                "canonical_strategy_id": strategy["canonical_strategy_id"],
                "alias_group": strategy["aliases"],
                    "selected_canonical_dataset": selected_dataset["dataset_version_id"] if selected_dataset else None,
                "selected_canonical_signal_ledger": selected_ledger["canonical_signal_ledger_id"] if selected_ledger else None,
                "implementation_authority": strategy["implementation_commit"],
                "parameter_authority": strategy["parameter_owner"],
                "split_authority": strategy["development_split_authority"],
                "development_session_count": 0,
                "holdout_session_count": 0,
                "option_coverage_readiness": strategy["option_data_requirements"],
                "remaining_blocker": blocker,
                "recommended_next_action": "Freeze canonical source set before execution" if blocker else "Proceed only with causal evaluation",
                "status": status,
            }
        )
    return out


def build_all_strategy_census(bundle_dir: Path, repo_root: Path, output_dir: Path) -> dict[str, Any]:
    integrity = verify_input_bundle(bundle_dir)
    candidates = _read_jsonl(bundle_dir / "candidate_inventory.jsonl")
    exact = _exact_duplicate_groups(candidates)
    blobs = _exact_content_blobs(candidates)
    semantic = _semantic_duplicate_groups(candidates)
    dataset_families = _logical_dataset_families(candidates)
    dataset_versions = _dataset_versions(candidates, dataset_families)
    ledgers = _canonical_signal_registry(candidates)
    signal_audit = _signal_ledger_audit(ledgers, candidates)
    unresolved_resolution = _unresolved_candidate_resolution(candidates)
    unresolved = [row for row in candidates if row.get("unresolved")]
    root_inventory = _read_json(bundle_dir / "root_inventory.json")
    strategy_inventory = [_locate_strategy(spec, repo_root) for spec in _strategy_specs()]
    readiness = _readiness_matrix(strategy_inventory, dataset_versions, ledgers)
    partition_registry = [
        {
            "partition_id": "PART:" + str(row.get("sha256", ""))[:16],
            "blob_id": str(row.get("sha256", "")),
            "dataset_family_id": "FAMILY:" + ":".join(_dataset_family_key(row)),
            "dataset_version_id": "VERSION:FAMILY:" + ":".join(_dataset_family_key(row)) + ":" + str(row.get("sha256", ""))[:16],
            "instrument": _dataset_family_key(row)[0],
            "instrument_type": _dataset_family_key(row)[1],
            "market": _dataset_family_key(row)[2],
            "bar_interval": _dataset_family_key(row)[3],
            "timezone": "IST" if _dataset_family_key(row)[0] != "UNRESOLVED_FAMILY" else "UNKNOWN",
            "first_timestamp": None,
            "last_timestamp": None,
            "session_set_hash": None,
            "row_count": row.get("row_count"),
            "partition_role": _partition_role(str(row.get("relative_path", ""))),
        }
        for row in candidates if row.get("classification") == "UNDERLYING_CANDLE_DATASET" and row.get("accepted")
    ]
    truncated_roots = [
        {
            "root_id": root.get("root_id"),
            "root_class": root.get("root_class"),
            "candidate_limit": None,
            "yielded_count": None,
            "represented_candidate_classes": [],
            "duplicates_another_scanned_tree": None,
            "omitted_tail_materiality": "DECLARED_BLIND_SPOT",
            "targeted_continuation_performed": False,
            "final_materiality_verdict": "MATERIAL_GAP_NOT_FULLY_EXHAUSTED",
        }
        for root in root_inventory
        if isinstance(root, dict) and root.get("available") and root.get("is_directory")
    ]
    unique_dataset_candidates = len(partition_registry)
    unique_signal_candidates = sum(1 for row in candidates if row.get("classification") == "PRE_OUTCOME_SIGNAL_LEDGER")
    dataset_status_counts = defaultdict(int)
    for row in dataset_versions:
        dataset_status_counts[row["status"]] += 1
    signal_status_counts = defaultdict(int)
    for row in signal_audit:
        signal_status_counts[row["status"]] += 1
    blocker_counts: dict[str, int] = defaultdict(int)
    for row in readiness:
        if row["remaining_blocker"]:
            blocker_counts[row["remaining_blocker"]] += 1
    summary = {
        "implementation_direction": "PROVISIONAL_CENSUS_WITH_DECLARED_GAPS" if integrity.status == "INPUT_BUNDLE_INTEGRITY_PASSED" else "CENSUS_INVALID",
        "superseded_file_level_dataset_count": 986,
        "supersession_reason": "PHYSICAL_FILES_AND_PARTITIONS_WERE_MISLABELLED_AS_DATASETS",
        "previous_head": "b4ccd69857ce0d594ef6e9c98646fa9f968b3c8c",
        "input_bundle": {
            "path": str(bundle_dir),
            "candidate_inventory_sha256": integrity.candidate_inventory_sha256,
            "manifest_semantic_sha256": integrity.manifest_semantic_sha256,
            "candidate_count": integrity.candidate_count,
            "accepted_candidate_count": integrity.accepted_candidate_count,
            "unresolved_candidate_count": integrity.unresolved_candidate_count,
        },
        "raw_candidates": integrity.candidate_count,
        "raw_candidate_file_count": integrity.candidate_count,
        "raw_accepted": integrity.accepted_candidate_count,
        "raw_unresolved": integrity.unresolved_candidate_count,
        "exact_duplicate_groups": len(exact),
        "exact_unique_sources": len(exact),
        "semantic_duplicate_groups": len(semantic),
        "semantic_unique_sources": len(semantic),
        "exact_content_blobs": len(blobs),
        "duplicate_physical_copies_collapsed": max(0, integrity.accepted_candidate_count - len(blobs)),
        "physical_accepted_file_count": integrity.accepted_candidate_count,
        "exact_content_blob_count": len(blobs),
        "duplicate_physical_copy_count": max(0, integrity.accepted_candidate_count - len(blobs)),
        "dataset_partition_count": len(partition_registry),
        "logical_dataset_families": len(dataset_families),
        "logical_dataset_family_count": len(dataset_families),
        "dataset_versions": len(dataset_versions),
        "dataset_version_count": len(dataset_versions),
        "canonical_dataset_version_count": dataset_status_counts.get("CANONICAL_DATASET_VERSION", 0),
        "usable_with_limitations_version_count": dataset_status_counts.get("USABLE_WITH_LIMITATIONS", 0),
        "exploratory_dataset_version_count": dataset_status_counts.get("EXPLORATORY_ONLY", 0),
        "invalid_dataset_version_count": dataset_status_counts.get("INVALID_DATASET_VERSION", 0),
        "unresolved_dataset_version_count": dataset_status_counts.get("UNRESOLVED_DATASET_VERSION", 0),
        "identity_incomplete_count": sum(1 for row in dataset_families if row["identity_status"] == "IDENTITY_INCOMPLETE"),
        "unique_underlying_dataset_candidates": unique_dataset_candidates,
        "unique_signal_ledger_candidates": unique_signal_candidates,
        "canonical_signal_ledgers": signal_status_counts.get("CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER", 0),
        "canonical_signal_ledger_count": signal_status_counts.get("CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER", 0),
        "valid_signal_ledger_with_limitations_count": signal_status_counts.get("VALID_WITH_LIMITATIONS", 0),
        "invalidated_ledgers": signal_status_counts.get("INVALIDATED_HISTORICAL_EVIDENCE", 0),
        "post_outcome_or_tuned_ledgers": signal_status_counts.get("POST_OUTCOME_OR_TUNED", 0),
        "insufficient_provenance_ledgers": signal_status_counts.get("INSUFFICIENT_PROVENANCE", 0),
        "unresolved_candidates_resolved": integrity.unresolved_candidate_count - len(unresolved),
        "unresolved_candidates_remaining": len(unresolved),
        "truncated_roots": truncated_roots,
        "material_truncated_roots": len(truncated_roots),
        "strategies_hypotheses_inventoried": len(strategy_inventory),
        "aliases_collapsed": len(strategy_inventory) - len({tuple(row["aliases"]) for row in strategy_inventory}),
        "ready_for_causal_execution_lanes": sum(1 for row in readiness if row["status"] == "READY_FOR_CAUSAL_EXECUTION"),
        "valid_precomputed_signals_lanes": sum(1 for row in readiness if row["status"] == "VALID_PRECOMPUTED_SIGNALS"),
        "ready_with_data_limitations_lanes": sum(1 for row in readiness if row["status"] == "READY_WITH_DATA_LIMITATIONS"),
        "blocked_lanes": sum(1 for row in readiness if row["status"] not in {"READY_FOR_CAUSAL_EXECUTION", "VALID_PRECOMPUTED_SIGNALS", "READY_WITH_DATA_LIMITATIONS"}),
        "blocked_lanes_by_blocker_class": dict(sorted(blocker_counts.items())),
        "exact_unique_sources": len(exact),
        "semantic_unique_sources": len(semantic),
        "integrity_status": integrity.status,
        "integrity_errors": integrity.errors,
        "unresolved_candidates": unresolved,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "input_bundle_integrity_independent.json": asdict(integrity),
        "current_986_breakdown.json": _current_986_breakdown(candidates, exact, dataset_families, dataset_versions),
        "physical_candidate_registry.jsonl": _physical_candidates(candidates),
        "exact_duplicate_groups.jsonl": exact,
        "exact_content_blob_registry.jsonl": blobs,
        "semantic_duplicate_groups.jsonl": semantic,
        "dataset_partition_registry.jsonl": partition_registry,
        "logical_dataset_family_registry.json": dataset_families,
        "dataset_version_registry.json": dataset_versions,
        "canonical_signal_ledger_registry.json": ledgers,
        "canonical_signal_ledger_audit.json": signal_audit,
        "aeron7_nifty_f1_dataset_family.json": [row for row in dataset_families if row["dataset_family_id"].startswith("FAMILY:NIFTY_F1")],
        "unresolved_candidate_resolution.json": unresolved_resolution,
        "truncation_review.json": summary["truncated_roots"],
        "strategy_implementation_inventory.json": strategy_inventory,
        "strategy_alias_registry.json": [{"canonical_strategy_id": row["canonical_strategy_id"], "aliases": row["aliases"]} for row in strategy_inventory],
        "all_strategy_execution_readiness.json": readiness,
        "census_summary.json": summary,
        "determinism.json": {
            "exact_duplicate_groups_sha256": _semantic_hash(exact),
            "exact_content_blob_registry_sha256": _semantic_hash(blobs),
            "semantic_duplicate_groups_sha256": _semantic_hash(semantic),
            "logical_dataset_family_registry_sha256": _semantic_hash(dataset_families),
            "dataset_version_registry_sha256": _semantic_hash(dataset_versions),
            "canonical_signal_ledger_registry_sha256": _semantic_hash(ledgers),
            "strategy_inventory_sha256": _semantic_hash(strategy_inventory),
            "execution_readiness_sha256": _semantic_hash(readiness),
        },
    }
    for filename, payload in payloads.items():
        path = output_dir / filename
        path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        (output_dir / f"{filename}.sha256").write_text(f"{_sha256_file(path)}  {filename}\n", encoding="utf-8")
    compact_dir = repo_root / "research" / "option_e2e_recertification_v4" / "all_strategy_source_census_v1"
    compact_dir.mkdir(parents=True, exist_ok=True)
    compact_files = {
        "schema.json": {
            "version": "all_strategy_source_census_v1",
            "files": sorted(payloads.keys()),
            "status_values": sorted({
                "PROVISIONAL_CENSUS_WITH_DECLARED_GAPS",
                "CANONICAL_CENSUS_COMPLETE_FOR_EXECUTION",
                "CANONICAL_CENSUS_COMPLETE_WITH_DECLARED_BLIND_SPOTS",
                "CENSUS_INVALID",
                "CANONICAL_DATASET_VERSION",
                "USABLE_WITH_LIMITATIONS",
                "EXPLORATORY_ONLY",
                "DERIVED_DUPLICATE",
                "INVALID_DATASET_VERSION",
                "UNRESOLVED_DATASET_VERSION",
                "SOURCE_SEARCH_INCOMPLETE",
                "DATASET_BLOCKED",
                "IMPLEMENTATION_BLOCKED",
                "PARAMETER_AUTHORITY_BLOCKED",
                "SPLIT_AUTHORITY_BLOCKED",
                "INVALIDATED",
                "NO_TRADE_FILTER",
                "MULTI_ASSET_SPECIAL_LANE",
                "NOT_APPLICABLE",
            }),
        },
        "census_summary.json": summary,
        "dataset_family_summary.json": {
            "raw_candidate_file_count": summary["raw_candidate_file_count"],
            "accepted_physical_file_count": summary["physical_accepted_file_count"],
            "exact_content_blob_count": summary["exact_content_blob_count"],
            "duplicate_physical_copy_count": summary["duplicate_physical_copy_count"],
            "dataset_partition_count": summary["dataset_partition_count"],
            "logical_dataset_family_count": summary["logical_dataset_family_count"],
            "identity_incomplete_count": summary["identity_incomplete_count"],
        },
        "dataset_version_summary.json": {
            "dataset_version_count": summary["dataset_version_count"],
            "canonical_dataset_version_count": summary["canonical_dataset_version_count"],
            "usable_with_limitations_version_count": summary["usable_with_limitations_version_count"],
            "exploratory_dataset_version_count": summary["exploratory_dataset_version_count"],
            "invalid_dataset_version_count": summary["invalid_dataset_version_count"],
            "unresolved_dataset_version_count": summary["unresolved_dataset_version_count"],
            "superseded_file_level_dataset_count": summary["superseded_file_level_dataset_count"],
        },
        "signal_ledger_summary.json": {
            "canonical_signal_ledger_count": summary["canonical_signal_ledger_count"],
            "valid_signal_ledger_with_limitations_count": summary["valid_signal_ledger_with_limitations_count"],
            "invalidated_ledgers": summary["invalidated_ledgers"],
            "post_outcome_or_tuned_ledgers": summary["post_outcome_or_tuned_ledgers"],
            "insufficient_provenance_ledgers": summary["insufficient_provenance_ledgers"],
        },
        "execution_readiness_summary.json": {
            "strategies_hypotheses_inventoried": summary["strategies_hypotheses_inventoried"],
            "aliases_collapsed": summary["aliases_collapsed"],
            "ready_for_causal_execution_lanes": summary["ready_for_causal_execution_lanes"],
            "valid_precomputed_signals_lanes": summary["valid_precomputed_signals_lanes"],
            "ready_with_data_limitations_lanes": summary["ready_with_data_limitations_lanes"],
            "blocked_lanes": summary["blocked_lanes"],
            "blocked_lanes_by_blocker_class": summary["blocked_lanes_by_blocker_class"],
        },
        "external_evidence_manifest.json": {
            "input_bundle": summary["input_bundle"],
            "logical_dataset_families": summary["logical_dataset_families"],
            "dataset_versions": summary["dataset_versions"],
            "superseded_file_level_dataset_count": summary["superseded_file_level_dataset_count"],
            "implementation_direction": summary["implementation_direction"],
        },
    }
    for filename, data in compact_files.items():
        (compact_dir / filename).write_text(_canonical_json(_portable(data)) + "\n", encoding="utf-8")
        (compact_dir / f"{filename}.sha256").write_text(f"{_sha256_file(compact_dir / filename)}  {filename}\n", encoding="utf-8")
    return summary
