from __future__ import annotations

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


def _load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _ts(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Kolkata").tz_localize(None)
    return t


def _iso_ist(value: pd.Timestamp) -> str:
    return f"{value.strftime('%Y-%m-%dT%H:%M:%S')}+05:30"


def verify_inputs(artifact_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = _load_json(artifact_dir / "opening_range_retest_causal_replay_source_manifest_v2.json")
    ledger = _load_json(artifact_dir / "opening_range_retest_causal_replay_candidate_ledger_v2.json")
    summary = _load_json(artifact_dir / "opening_range_retest_causal_replay_summary_v2.json")
    if summary.get("decision") != "ORB_PHASE1_V2_RECERTIFIED":
        raise ValueError("INPUT_CERTIFICATION_VERDICT_MISMATCH")
    expected = {
        "source": source.get("record_count") == INPUT_SOURCE_COUNT and source.get("source_manifest_semantic_hash") == INPUT_SOURCE_HASH,
        "candidate_count": ledger.get("candidate_count") == INPUT_CANDIDATE_COUNT,
        "candidate_core": ledger.get("candidate_core_semantic_hash") == INPUT_CANDIDATE_CORE_HASH,
        "candidate_provenance": ledger.get("candidate_provenance_semantic_hash") == INPUT_CANDIDATE_PROVENANCE_HASH,
    }
    if not all(expected.values()):
        raise ValueError(f"ORB_PHASE1_V2_INPUT_CERTIFICATION_MISMATCH:{expected}")
    return source, ledger, summary


def _read_source(record: dict[str, Any], source_project_root: Path) -> pd.DataFrame:
    logical = Path(str(record["logical_path"]))
    if logical.is_absolute() or ".." in logical.parts or logical.parts[:2] != ("runtime", "upstox_candidate_replay"):
        raise ValueError("SOURCE_PATH_TRAVERSAL")
    path = (source_project_root / logical).resolve()
    allowed = (source_project_root / "runtime" / "upstox_candidate_replay").resolve()
    path.relative_to(allowed)
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_MISSING_OR_SYMLINK")
    if sha256_file(path) != record["actual_sha256"] or path.stat().st_size != int(record["byte_size"]):
        raise ValueError("SOURCE_BYTE_IDENTITY_MISMATCH")
    frame = pd.read_parquet(path)
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    if frame["timestamp"].dt.tz is not None:
        frame["timestamp"] = frame["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return frame


def _validate_frame(frame: pd.DataFrame, source: dict[str, Any]) -> str | None:
    if len(frame) != 375:
        return "SOURCE_TIMESTAMP_GAP"
    if frame["timestamp"].nunique() != len(frame) or not frame["timestamp"].is_monotonic_increasing:
        return "SOURCE_TIMESTAMP_GAP"
    if not (frame["timestamp"].diff().dropna() == pd.Timedelta(minutes=1)).all():
        return "SOURCE_TIMESTAMP_GAP"
    if sorted(frame["timestamp"].dt.date.astype(str).unique()) != [source["session_date"]]:
        return "SOURCE_SESSION_MISMATCH"
    symbols = sorted(str(v).upper().replace("NSE_INDEX|NIFTY BANK", "BANKNIFTY").replace("NSE_INDEX|NIFTY 50", "NIFTY").replace("BSE_INDEX|SENSEX", "SENSEX") for v in frame["symbol"].dropna().unique())
    if symbols != [source["symbol"]]:
        return "SOURCE_SYMBOL_MISMATCH"
    if not (frame["high"] >= frame[["open", "close"]].max(axis=1)).all() or not (frame["low"] <= frame[["open", "close"]].min(axis=1)).all():
        return "SOURCE_TIMESTAMP_GAP"
    return None


def measure_candidate(candidate: dict[str, Any], source: dict[str, Any], frame: pd.DataFrame, contract_hash: str) -> dict[str, Any]:
    core = candidate["candidate_core"]
    provenance = candidate["source_provenance"]
    base = {
        "candidate_id": candidate["candidate_id"],
        "candidate_core": core,
        "source_provenance": provenance,
        "outcome_contract_hash": contract_hash,
        **safety_fields(),
    }
    if provenance.get("source_record_id") != source.get("source_record_id") or provenance.get("source_actual_sha256") != source.get("actual_sha256"):
        return {**base, "terminal_reason": "SOURCE_PROVENANCE_MISMATCH", "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR"}, "horizons": {}}
    try:
        ready = _ts(core["proposal_ready_at_iso"])
    except Exception:
        return {**base, "terminal_reason": "CANDIDATE_TIMESTAMP_MALFORMED", "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR"}, "horizons": {}}
    if ready.date().isoformat() != source["session_date"]:
        return {**base, "terminal_reason": "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION", "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR"}, "horizons": {}}
    later = frame[frame["timestamp"] > ready]
    same = frame[frame["timestamp"] == ready]
    if later.empty:
        return {**base, "terminal_reason": "NO_LEGAL_ENTRY_BAR", "same_timestamp_bar_disposition": "SKIPPED_FOR_PRIMARY" if not same.empty else "ABSENT", "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR"}, "horizons": {}}
    entry = later.iloc[0]
    entry_start = entry["timestamp"]
    entry_open = float(entry["open"])
    if entry_open <= 0:
        return {**base, "terminal_reason": "NO_LEGAL_ENTRY_BAR", "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR"}, "horizons": {}}
    indexed = {row["timestamp"]: row for _, row in frame.iterrows()}
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
        **base,
        "terminal_reason": terminal_reason,
        "same_timestamp_bar_disposition": "SKIPPED_FOR_PRIMARY" if not same.empty else "ABSENT",
        "legal_entry": {
            "status": "LEGAL_ENTRY_FOUND",
            "start": _iso_ist(entry_start),
            "end": _iso_ist(entry_start + timedelta(minutes=1)),
            "open": round(entry_open, 8),
        },
        "horizons": horizons,
    }
    record["outcome_id"] = sha256_bytes(canonical_json_bytes({k: v for k, v in record.items() if k != "outcome_id"}))
    record["measured_horizon_count"] = measured
    return record


def build_ledger(*, artifact_dir: Path, source_project_root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    source_manifest, candidate_ledger, _summary = verify_inputs(artifact_dir)
    source_by_id = {record["source_record_id"]: record for record in source_manifest["records"]}
    frames: dict[str, pd.DataFrame] = {}
    records = []
    source_failures = Counter()
    join_verified = 0
    for candidate in candidate_ledger["records"]:
        source_id = candidate["source_provenance"].get("source_record_id")
        source = source_by_id.get(source_id)
        if source is None:
            source_failures["SOURCE_PROVENANCE_MISMATCH"] += 1
            records.append({**candidate, "terminal_reason": "SOURCE_PROVENANCE_MISMATCH", "horizons": {}})
            continue
        if source_id not in frames:
            frame = _read_source(source, source_project_root)
            failure = _validate_frame(frame, source)
            if failure:
                source_failures[failure] += 1
            frames[source_id] = frame
        join_verified += 1
        records.append(measure_candidate(candidate, source, frames[source_id], contract["contract_hash"]))
    records = sorted(records, key=lambda item: item["candidate_id"])
    ledger_hash = sha256_bytes(canonical_json_bytes(records))
    decision = "ORB_OUTCOME_LEDGER_V2_CERTIFIED" if len(records) == INPUT_CANDIDATE_COUNT and not source_failures else "ORB_OUTCOME_LEDGER_V2_NOT_CERTIFIED"
    return {
        "schema_version": 1,
        **evidence_fields(
            mode="ORB_OUTCOME_LEDGER_V2",
            decision=decision,
            reason="measured every Phase 1 v2 candidate against certified source bars with strict fail-closed joins",
            source="opening_range_retest_causal_replay_candidate_ledger_v2.json",
        ),
        "contract_hash": contract["contract_hash"],
        "source_manifest_semantic_hash": INPUT_SOURCE_HASH,
        "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
        "candidate_provenance_semantic_hash": INPUT_CANDIDATE_PROVENANCE_HASH,
        "candidate_count": len(records),
        "duplicate_candidate_ids": len(records) - len({record["candidate_id"] for record in records}),
        "join_verified_count": join_verified,
        "source_failure_counts": dict(source_failures),
        "outcome_ledger_hash": ledger_hash,
        "records": records,
        **safety_fields(),
    }


def summarize(ledger: dict[str, Any]) -> dict[str, Any]:
    reason_counts = Counter(record.get("terminal_reason") for record in ledger["records"])
    by_horizon: dict[str, Counter[str]] = {str(h): Counter() for h in HORIZONS_MINUTES}
    values: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    for record in ledger["records"]:
        for h, payload in record.get("horizons", {}).items():
            by_horizon[h][payload["status"]] += 1
            if payload["status"] == "MEASURED":
                values[h].append(payload["directional_underlying_return"])
    stats = {}
    for h, vals in values.items():
        stats[h] = {"count": len(vals), "mean": round(sum(vals) / len(vals), 12) if vals else None, "positive": sum(v > 0 for v in vals), "zero": sum(v == 0 for v in vals), "negative": sum(v < 0 for v in vals)}
    decision = "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED" if ledger["decision"] == "ORB_OUTCOME_LEDGER_V2_CERTIFIED" else "ORB_OUTCOMES_V2_NOT_CERTIFIED"
    return {
        "schema_version": 1,
        **evidence_fields(
            mode="ORB_OUTCOME_SUMMARY_V2",
            decision=decision,
            reason="summarized certified outcome ledger without profitability or execution claims",
            source="opening_range_retest_outcome_ledger_v2.json",
        ),
        "candidate_count": ledger["candidate_count"],
        "terminal_reason_counts": dict(reason_counts),
        "horizon_status_counts": {h: dict(c) for h, c in by_horizon.items()},
        "descriptive_directional_return_stats": stats,
        "claim_labels": ["DESCRIPTIVE_ONLY", "PRE_COST_UNDERLYING_ONLY", "NOT_EDGE_EVIDENCE", "NOT_OPTION_PNL"],
        **safety_fields(),
    }
