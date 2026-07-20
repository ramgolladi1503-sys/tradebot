from __future__ import annotations

import math
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research.opening_range_retest_outcomes_v2.contract import (
    HORIZONS_MINUTES,
    INPUT_CANDIDATE_COUNT,
    INPUT_CANDIDATE_CORE_HASH,
    INPUT_CANDIDATE_PROVENANCE_HASH,
    INPUT_SOURCE_COUNT,
    INPUT_SOURCE_HASH,
    canonical_json_bytes,
    evidence_fields,
    safety_fields,
    sha256_bytes,
    sha256_file,
)

INPUT_FILES = {
    "source_manifest": "opening_range_retest_causal_replay_source_manifest_v2.json",
    "candidate_ledger": "opening_range_retest_causal_replay_candidate_ledger_v2.json",
    "phase1_summary": "opening_range_retest_causal_replay_summary_v2.json",
    "reconciliation": "opening_range_retest_phase1_v2_reconciliation.json",
    "phase1_certification": "opening_range_retest_phase1_v2_certification.md",
}
SOURCE_COLUMNS = [
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "source",
    "interval",
    "fetch_timestamp",
    "fetch_start_date",
    "fetch_end_date",
    "data_origin",
    "synthetic",
    "mock",
    "fallback",
    "provider",
    "source_endpoint",
]
ALLOWED_DIRECTIONS = {"BUY_CALL", "BUY_PUT"}
FAIL_CLOSED_REASONS = {
    "SOURCE_PROVENANCE_MISMATCH",
    "SOURCE_VALIDATION_FAILED",
    "CANDIDATE_TIMESTAMP_MALFORMED",
    "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION",
    "CANDIDATE_READY_OFF_GRID",
    "CANDIDATE_READY_BAR_MISSING",
    "CANDIDATE_DIRECTION_UNSUPPORTED",
    "NO_LEGAL_ENTRY_BAR",
}


def _load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def verify_sidecar_file(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    actual = sha256_file(path)
    expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None
    if actual != expected:
        raise ValueError(f"INPUT_SIDECAR_MISMATCH:{path.name}")
    return {"path": path.name, "artifact_sha256": actual, "sidecar_sha256": expected, "sidecar_match": True}


def verify_inputs(artifact_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    sidecars = {name: verify_sidecar_file(artifact_dir / filename) for name, filename in INPUT_FILES.items()}
    source = _load_json(artifact_dir / INPUT_FILES["source_manifest"])
    ledger = _load_json(artifact_dir / INPUT_FILES["candidate_ledger"])
    summary = _load_json(artifact_dir / INPUT_FILES["phase1_summary"])
    reconciliation = _load_json(artifact_dir / INPUT_FILES["reconciliation"])
    certification_text = (artifact_dir / INPUT_FILES["phase1_certification"]).read_text(encoding="utf-8")
    if summary.get("decision") != "ORB_PHASE1_V2_RECERTIFIED":
        raise ValueError("INPUT_CERTIFICATION_VERDICT_MISMATCH")
    if "- decision: ORB_PHASE1_V2_RECERTIFIED" not in certification_text or "NOT_ORB_PHASE1_V2_RECERTIFIED" in certification_text:
        raise ValueError("INPUT_PHASE1_CERTIFICATION_MISMATCH")
    expected = {
        "source": source.get("record_count") == INPUT_SOURCE_COUNT and source.get("source_manifest_semantic_hash") == INPUT_SOURCE_HASH,
        "candidate_count": ledger.get("candidate_count") == INPUT_CANDIDATE_COUNT,
        "candidate_core": ledger.get("candidate_core_semantic_hash") == INPUT_CANDIDATE_CORE_HASH,
        "candidate_provenance": ledger.get("candidate_provenance_semantic_hash") == INPUT_CANDIDATE_PROVENANCE_HASH,
        "reconciliation": reconciliation.get("decision") == "UNAFFECTED_SUBSET_RECONCILED" and reconciliation.get("v1_unaffected_candidate_count") == 2192 and reconciliation.get("v2_unaffected_candidate_count") == 2192,
    }
    if not all(expected.values()):
        raise ValueError(f"ORB_PHASE1_V2_INPUT_CERTIFICATION_MISMATCH:{expected}")
    return source, ledger, summary, sidecars


def normalize_symbol(value: Any) -> str:
    text = str(value).upper().strip()
    return text.replace("NSE_INDEX|NIFTY BANK", "BANKNIFTY").replace("NSE_INDEX|NIFTY 50", "NIFTY").replace("BSE_INDEX|SENSEX", "SENSEX")


def _ts(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Kolkata").tz_localize(None)
    return t


def _iso_ist(value: pd.Timestamp) -> str:
    return f"{value.strftime('%Y-%m-%dT%H:%M:%S')}+05:30"


def _reject_symlink_components(root: Path, relative: Path) -> None:
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("SOURCE_MISSING_OR_SYMLINK")


def resolve_source_path(record: dict[str, Any], source_project_root: Path) -> Path:
    logical = Path(str(record["logical_path"]))
    if logical.is_absolute() or ".." in logical.parts or logical.parts[:2] != ("runtime", "upstox_candidate_replay"):
        raise ValueError("SOURCE_PATH_TRAVERSAL")
    _reject_symlink_components(source_project_root, logical)
    path = (source_project_root / logical).resolve()
    allowed = (source_project_root / "runtime" / "upstox_candidate_replay").resolve()
    path.relative_to(allowed)
    if not path.is_file():
        raise ValueError("SOURCE_MISSING_OR_SYMLINK")
    if sha256_file(path) != record["actual_sha256"] or path.stat().st_size != int(record["byte_size"]):
        raise ValueError("SOURCE_BYTE_IDENTITY_MISMATCH")
    return path


def read_source(record: dict[str, Any], source_project_root: Path) -> pd.DataFrame:
    path = resolve_source_path(record, source_project_root)
    frame = pd.read_parquet(path)
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    if frame["timestamp"].dt.tz is not None:
        frame["timestamp"] = frame["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return frame


# Backward-compatible test import name.
_read_source = read_source


def validate_frame(frame: pd.DataFrame, source: dict[str, Any]) -> str | None:
    if list(frame.columns) != SOURCE_COLUMNS:
        return "SOURCE_SCHEMA_MISMATCH"
    if len(frame) != 375:
        return "SOURCE_TIMESTAMP_GAP"
    if frame["timestamp"].nunique() != len(frame) or not frame["timestamp"].is_monotonic_increasing:
        return "SOURCE_TIMESTAMP_GAP"
    if not (frame["timestamp"].diff().dropna() == pd.Timedelta(minutes=1)).all():
        return "SOURCE_TIMESTAMP_GAP"
    if frame["timestamp"].iloc[0].strftime("%H:%M") != "09:15" or frame["timestamp"].iloc[-1].strftime("%H:%M") != "15:29":
        return "SOURCE_TIMESTAMP_GAP"
    if sorted(frame["timestamp"].dt.date.astype(str).unique()) != [source["session_date"]]:
        return "SOURCE_SESSION_MISMATCH"
    symbols = sorted(normalize_symbol(v) for v in frame["symbol"].dropna().unique())
    if symbols != [source["symbol"]]:
        return "SOURCE_SYMBOL_MISMATCH"
    numeric = frame[["open", "high", "low", "close"]]
    if not numeric.map(lambda x: isinstance(x, (int, float)) and math.isfinite(float(x)) and float(x) > 0).all().all():
        return "SOURCE_OHLC_INVALID"
    if not (frame["high"] >= frame[["open", "close"]].max(axis=1)).all() or not (frame["low"] <= frame[["open", "close"]].min(axis=1)).all():
        return "SOURCE_OHLC_BOUNDS_INVALID"
    return None


def _blank_horizons(reason: str) -> dict[str, Any]:
    return {str(minutes): {"horizon_minutes": minutes, "status": reason, "reason": reason} for minutes in HORIZONS_MINUTES}


def _finalize_record(record: dict[str, Any]) -> dict[str, Any]:
    record["outcome_id"] = sha256_bytes(canonical_json_bytes({k: v for k, v in record.items() if k != "outcome_id"}))
    return record


def fail_record(candidate: dict[str, Any], source: dict[str, Any] | None, contract: dict[str, Any], reason: str, detail: str | None = None) -> dict[str, Any]:
    record = {
        "candidate_id": candidate.get("candidate_id"),
        "candidate_core": candidate.get("candidate_core", {}),
        "source_provenance": candidate.get("source_provenance", {}),
        "source_manifest_record": source,
        "outcome_contract_hash": contract["contract_hash"],
        "frozen_code_sha": contract["frozen_code_sha"],
        "implementation_tree_hash": contract["implementation_tree_hash"],
        "terminal_reason": reason,
        "terminal_detail": detail,
        "same_timestamp_bar_disposition": "UNKNOWN",
        "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR", "reason": reason},
        "horizons": _blank_horizons(reason),
        "measured_horizon_count": 0,
        **safety_fields(),
    }
    return _finalize_record(record)


def _join_failure(candidate: dict[str, Any], source: dict[str, Any] | None) -> str | None:
    core = candidate.get("candidate_core", {})
    provenance = candidate.get("source_provenance", {})
    if source is None:
        return "SOURCE_PROVENANCE_MISMATCH"
    checks = {
        "source_record_id": provenance.get("source_record_id") == source.get("source_record_id"),
        "source_logical_path": provenance.get("source_logical_path") == source.get("logical_path"),
        "source_actual_sha256": provenance.get("source_actual_sha256") == source.get("actual_sha256"),
        "source_symbol": provenance.get("source_symbol") == source.get("symbol"),
        "source_session_date": provenance.get("source_session_date") == source.get("session_date"),
        "manifest_hash": provenance.get("source_manifest_semantic_hash") == INPUT_SOURCE_HASH,
        "manifest_version": provenance.get("source_manifest_version") == "v2",
        "core_symbol": core.get("symbol") == source.get("symbol"),
        "core_session_date": core.get("session_date") == source.get("session_date"),
    }
    return None if all(checks.values()) else "SOURCE_PROVENANCE_MISMATCH"


def measure_candidate(candidate: dict[str, Any], source: dict[str, Any], frame: pd.DataFrame, contract: dict[str, Any] | str, source_failure: str | None = None) -> dict[str, Any]:
    if isinstance(contract, str):
        contract = {"contract_hash": contract, "frozen_code_sha": "UNKNOWN", "implementation_tree_hash": "UNKNOWN"}
    join_failure = _join_failure(candidate, source)
    if join_failure:
        return fail_record(candidate, source, contract, join_failure)
    if source_failure:
        return fail_record(candidate, source, contract, "SOURCE_VALIDATION_FAILED", source_failure)
    core = candidate["candidate_core"]
    if core.get("direction") not in ALLOWED_DIRECTIONS:
        return fail_record(candidate, source, contract, "CANDIDATE_DIRECTION_UNSUPPORTED")
    try:
        ready = _ts(core["proposal_ready_at_iso"])
    except Exception:
        return fail_record(candidate, source, contract, "CANDIDATE_TIMESTAMP_MALFORMED")
    if ready.date().isoformat() != source["session_date"]:
        return fail_record(candidate, source, contract, "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION")
    completed_bar_start = ready - pd.Timedelta(minutes=1)
    indexed = {row["timestamp"]: row for _, row in frame.iterrows()}
    if ready.second or ready.microsecond or ready.nanosecond:
        return fail_record(candidate, source, contract, "CANDIDATE_READY_OFF_GRID")
    if completed_bar_start not in indexed:
        return fail_record(candidate, source, contract, "CANDIDATE_READY_BAR_MISSING")
    later = frame[frame["timestamp"] > ready]
    same = frame[frame["timestamp"] == ready]
    if later.empty:
        return fail_record(candidate, source, contract, "NO_LEGAL_ENTRY_BAR")
    entry = later.iloc[0]
    entry_start = entry["timestamp"]
    entry_open = float(entry["open"])
    if entry_open <= 0:
        return fail_record(candidate, source, contract, "NO_LEGAL_ENTRY_BAR", "ENTRY_OPEN_NON_POSITIVE")
    horizons: dict[str, Any] = {}
    measured = 0
    terminal_reason = "MEASURED"
    for minutes in HORIZONS_MINUTES:
        terminal_start = entry_start + timedelta(minutes=minutes - 1)
        terminal = indexed.get(terminal_start)
        if terminal is None:
            reason = "MISSING_EXPECTED_MINUTE" if terminal_start <= frame["timestamp"].iloc[-1] else "SESSION_ENDED_BEFORE_HORIZON"
            horizons[str(minutes)] = {"horizon_minutes": minutes, "status": reason, "reason": reason}
            terminal_reason = "INSUFFICIENT_HORIZON"
            continue
        interval = frame[(frame["timestamp"] >= entry_start) & (frame["timestamp"] <= terminal_start)]
        terminal_close = float(terminal["close"])
        max_idx = interval["high"].idxmax()
        min_idx = interval["low"].idxmin()
        max_high = float(interval.loc[max_idx, "high"])
        min_low = float(interval.loc[min_idx, "low"])
        unsigned = (terminal_close - entry_open) / entry_open
        if core["direction"] == "BUY_CALL":
            directional = unsigned
            mfe = (max_high - entry_open) / entry_open
            mae = (min_low - entry_open) / entry_open
        else:
            directional = (entry_open - terminal_close) / entry_open
            mfe = (entry_open - min_low) / entry_open
            mae = (entry_open - max_high) / entry_open
        horizons[str(minutes)] = {
            "horizon_minutes": minutes,
            "status": "MEASURED",
            "reason": "MEASURED",
            "terminal_start": _iso_ist(terminal_start),
            "terminal_end": _iso_ist(terminal_start + timedelta(minutes=1)),
            "terminal_close": round(terminal_close, 8),
            "unsigned_underlying_return": round(unsigned, 12),
            "directional_underlying_return": round(directional, 12),
            "high": round(max_high, 8),
            "low": round(min_low, 8),
            "mfe": round(mfe, 12),
            "mae": round(mae, 12),
            "mfe_timestamp": _iso_ist(interval.loc[max_idx, "timestamp"]),
            "mae_timestamp": _iso_ist(interval.loc[min_idx, "timestamp"]),
            "bars_in_interval": len(interval),
            "expected_elapsed_minutes": minutes,
            "actual_elapsed_minutes": int((terminal_start - entry_start).total_seconds() // 60) + 1,
        }
        measured += 1
    record = {
        "candidate_id": candidate["candidate_id"],
        "candidate_core": core,
        "source_provenance": candidate["source_provenance"],
        "source_manifest_record": source,
        "outcome_contract_hash": contract["contract_hash"],
        "frozen_code_sha": contract["frozen_code_sha"],
        "implementation_tree_hash": contract["implementation_tree_hash"],
        "terminal_reason": terminal_reason,
        "terminal_detail": None,
        "same_timestamp_bar_disposition": "SKIPPED_FOR_PRIMARY" if not same.empty else "ABSENT",
        "legal_entry": {"status": "LEGAL_ENTRY_FOUND", "start": _iso_ist(entry_start), "end": _iso_ist(entry_start + timedelta(minutes=1)), "open": round(entry_open, 8)},
        "horizons": horizons,
        "measured_horizon_count": measured,
        **safety_fields(),
    }
    return _finalize_record(record)


def build_ledger(*, artifact_dir: Path, source_project_root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    source_manifest, candidate_ledger, _summary, input_sidecars = verify_inputs(artifact_dir)
    source_by_id = {record["source_record_id"]: record for record in source_manifest["records"]}
    frame_cache: dict[str, tuple[pd.DataFrame | None, str | None]] = {}
    records = []
    source_failures = Counter()
    join_verified = 0
    for candidate in candidate_ledger["records"]:
        source_id = candidate.get("source_provenance", {}).get("source_record_id")
        source = source_by_id.get(source_id)
        join_failure = _join_failure(candidate, source)
        if join_failure:
            source_failures[join_failure] += 1
            records.append(fail_record(candidate, source, contract, join_failure))
            continue
        assert source is not None
        if source_id not in frame_cache:
            try:
                frame = read_source(source, source_project_root)
                failure = validate_frame(frame, source)
            except Exception as exc:
                frame = None
                failure = str(exc)
            if failure:
                source_failures[failure] += 1
            frame_cache[source_id] = (frame, failure)
        frame, failure = frame_cache[source_id]
        if failure or frame is None:
            records.append(fail_record(candidate, source, contract, "SOURCE_VALIDATION_FAILED", failure))
            continue
        join_verified += 1
        records.append(measure_candidate(candidate, source, frame, contract))
    records = sorted(records, key=lambda item: item["candidate_id"])
    ids = [record["candidate_id"] for record in records]
    horizon_conservation = {str(h): sum(1 for record in records if str(h) in record.get("horizons", {})) for h in HORIZONS_MINUTES}
    ledger_hash = sha256_bytes(canonical_json_bytes(records))
    certified = (
        len(records) == INPUT_CANDIDATE_COUNT
        and len(ids) == len(set(ids))
        and not source_failures
        and all(v == INPUT_CANDIDATE_COUNT for v in horizon_conservation.values())
    )
    return {
        "schema_version": 2,
        **evidence_fields(mode="ORB_OUTCOME_LEDGER_V2", decision="ORB_OUTCOME_LEDGER_V2_CERTIFIED" if certified else "ORB_OUTCOME_LEDGER_V2_NOT_CERTIFIED", reason="measured every Phase 1 v2 candidate against certified source bars with strict fail-closed joins", source="opening_range_retest_causal_replay_candidate_ledger_v2.json"),
        "contract_hash": contract["contract_hash"],
        "frozen_code_sha": contract["frozen_code_sha"],
        "implementation_tree_hash": contract["implementation_tree_hash"],
        "input_sidecars": input_sidecars,
        "source_manifest_semantic_hash": INPUT_SOURCE_HASH,
        "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
        "candidate_provenance_semantic_hash": INPUT_CANDIDATE_PROVENANCE_HASH,
        "candidate_count": len(records),
        "duplicate_candidate_ids": len(records) - len(set(ids)),
        "missing_candidate_ids": [],
        "unexpected_candidate_ids": [],
        "join_verified_count": join_verified,
        "source_failure_counts": dict(source_failures),
        "horizon_conservation": horizon_conservation,
        "outcome_ledger_hash": ledger_hash,
        "records": records,
        **safety_fields(),
    }


def _quantile(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return round(s[lo], 12)
    return round(s[lo] * (hi - pos) + s[hi] * (pos - lo), 12)


def _stats(vals: list[float]) -> dict[str, Any]:
    return {
        "count": len(vals),
        "mean": round(sum(vals) / len(vals), 12) if vals else None,
        "median": _quantile(vals, 0.5),
        "min": round(min(vals), 12) if vals else None,
        "max": round(max(vals), 12) if vals else None,
        "p05": _quantile(vals, 0.05),
        "p25": _quantile(vals, 0.25),
        "p75": _quantile(vals, 0.75),
        "p95": _quantile(vals, 0.95),
        "positive": sum(v > 0 for v in vals),
        "zero": sum(v == 0 for v in vals),
        "negative": sum(v < 0 for v in vals),
    }


def summarize(ledger: dict[str, Any]) -> dict[str, Any]:
    records = ledger["records"]
    reason_counts = Counter(record.get("terminal_reason") for record in records)
    by_horizon: dict[str, Counter[str]] = {str(h): Counter() for h in HORIZONS_MINUTES}
    values: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    mfes: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    maes: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    breakdowns: dict[str, dict[str, Counter[str]]] = {str(h): {"symbol": Counter(), "direction": Counter(), "symbol_direction": Counter(), "calendar_year": Counter()} for h in HORIZONS_MINUTES}
    for record in records:
        core = record["candidate_core"]
        year = str(core["session_date"])[:4]
        for h in map(str, HORIZONS_MINUTES):
            payload = record.get("horizons", {}).get(h)
            if not payload:
                by_horizon[h]["MISSING_HORIZON_RECORD"] += 1
                continue
            by_horizon[h][payload["status"]] += 1
            if payload["status"] == "MEASURED":
                values[h].append(payload["directional_underlying_return"])
                mfes[h].append(payload["mfe"])
                maes[h].append(payload["mae"])
                breakdowns[h]["symbol"][core["symbol"]] += 1
                breakdowns[h]["direction"][core["direction"]] += 1
                breakdowns[h]["symbol_direction"][f"{core['symbol']}:{core['direction']}"] += 1
                breakdowns[h]["calendar_year"][year] += 1
    stats = {h: _stats(vals) | {"mfe": _stats(mfes[h]), "mae": _stats(maes[h]), "breakdowns": {k: dict(v) for k, v in breakdowns[h].items()}} for h, vals in values.items()}
    conservation = {h: sum(c.values()) for h, c in by_horizon.items()}
    decision = "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED" if ledger["decision"] == "ORB_OUTCOME_LEDGER_V2_CERTIFIED" and all(v == INPUT_CANDIDATE_COUNT for v in conservation.values()) else "ORB_OUTCOMES_V2_NOT_CERTIFIED"
    summary = {
        "schema_version": 2,
        **evidence_fields(mode="ORB_OUTCOME_SUMMARY_V2", decision=decision, reason="summarized certified outcome ledger without profitability or execution claims", source="opening_range_retest_outcome_ledger_v2.json"),
        "contract_hash": ledger["contract_hash"],
        "outcome_ledger_hash": ledger["outcome_ledger_hash"],
        "candidate_count": ledger["candidate_count"],
        "terminal_reason_counts": dict(reason_counts),
        "horizon_status_counts": {h: dict(c) for h, c in by_horizon.items()},
        "horizon_conservation": conservation,
        "descriptive_directional_return_stats": stats,
        "claim_boundary": ["DESCRIPTIVE_ONLY", "PRE_COST_UNDERLYING_ONLY", "NOT_EDGE_EVIDENCE", "NOT_OPTION_PNL", "NOT_PROFITABILITY", "NOT_PAPER_OR_LIVE_READY"],
        **safety_fields(),
    }
    summary["summary_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in summary.items() if k != "summary_hash"}))
    return summary
