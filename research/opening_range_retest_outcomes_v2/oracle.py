from __future__ import annotations

import hashlib
import json
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
    safety_fields,
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
CLAIM_BOUNDARY = {"DESCRIPTIVE_ONLY", "PRE_COST_UNDERLYING_ONLY", "NOT_EDGE_EVIDENCE", "NOT_OPTION_PNL", "NOT_PROFITABILITY", "NOT_PAPER_OR_LIVE_READY"}


def cbytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def shab(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shafile(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    actual = shafile(path)
    expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None
    return {"path": path.name, "artifact_sha256": actual, "sidecar_sha256": expected, "sidecar_match": actual == expected}


def verify_input_bundle(artifact_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    failures = []
    sidecars = {name: verify_sidecar(artifact_dir / filename) for name, filename in INPUT_FILES.items()}
    for name, item in sidecars.items():
        if not item["sidecar_match"]:
            failures.append(f"INPUT_SIDECAR_MISMATCH:{name}")
    source = load_json(artifact_dir / INPUT_FILES["source_manifest"])
    ledger = load_json(artifact_dir / INPUT_FILES["candidate_ledger"])
    summary = load_json(artifact_dir / INPUT_FILES["phase1_summary"])
    if source.get("record_count") != INPUT_SOURCE_COUNT or source.get("source_manifest_semantic_hash") != INPUT_SOURCE_HASH:
        failures.append("INPUT_SOURCE_MANIFEST_MISMATCH")
    if ledger.get("candidate_count") != INPUT_CANDIDATE_COUNT or ledger.get("candidate_core_semantic_hash") != INPUT_CANDIDATE_CORE_HASH or ledger.get("candidate_provenance_semantic_hash") != INPUT_CANDIDATE_PROVENANCE_HASH:
        failures.append("INPUT_CANDIDATE_LEDGER_MISMATCH")
    if summary.get("decision") != "ORB_PHASE1_V2_RECERTIFIED":
        failures.append("INPUT_SUMMARY_VERDICT_MISMATCH")
    return source, ledger, summary, sidecars, failures


def norm_symbol(value: Any) -> str:
    return str(value).upper().strip().replace("NSE_INDEX|NIFTY BANK", "BANKNIFTY").replace("NSE_INDEX|NIFTY 50", "NIFTY").replace("BSE_INDEX|SENSEX", "SENSEX")


def ts(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Kolkata").tz_localize(None)
    return t


def iso(value: pd.Timestamp) -> str:
    return f"{value.strftime('%Y-%m-%dT%H:%M:%S')}+05:30"


def reject_symlink_components(root: Path, logical: Path) -> None:
    cur = root
    for part in logical.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError("SOURCE_MISSING_OR_SYMLINK")


def source_path(record: dict[str, Any], root: Path) -> Path:
    logical = Path(str(record["logical_path"]))
    if logical.is_absolute() or ".." in logical.parts or logical.parts[:2] != ("runtime", "upstox_candidate_replay"):
        raise ValueError("SOURCE_PATH_TRAVERSAL")
    reject_symlink_components(root, logical)
    path = (root / logical).resolve()
    path.relative_to((root / "runtime" / "upstox_candidate_replay").resolve())
    if not path.is_file():
        raise ValueError("SOURCE_MISSING_OR_SYMLINK")
    if shafile(path) != record["actual_sha256"] or path.stat().st_size != int(record["byte_size"]):
        raise ValueError("SOURCE_BYTE_IDENTITY_MISMATCH")
    return path


def read_frame(record: dict[str, Any], root: Path) -> pd.DataFrame:
    frame = pd.read_parquet(source_path(record, root)).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    if frame["timestamp"].dt.tz is not None:
        frame["timestamp"] = frame["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return frame


def validate_frame(frame: pd.DataFrame, source: dict[str, Any]) -> str | None:
    if list(frame.columns) != SOURCE_COLUMNS:
        return "SOURCE_SCHEMA_MISMATCH"
    if len(frame) != 375 or frame["timestamp"].nunique() != len(frame) or not frame["timestamp"].is_monotonic_increasing:
        return "SOURCE_TIMESTAMP_GAP"
    if not (frame["timestamp"].diff().dropna() == pd.Timedelta(minutes=1)).all():
        return "SOURCE_TIMESTAMP_GAP"
    if frame["timestamp"].iloc[0].strftime("%H:%M") != "09:15" or frame["timestamp"].iloc[-1].strftime("%H:%M") != "15:29":
        return "SOURCE_TIMESTAMP_GAP"
    if sorted(frame["timestamp"].dt.date.astype(str).unique()) != [source["session_date"]]:
        return "SOURCE_SESSION_MISMATCH"
    if sorted(norm_symbol(v) for v in frame["symbol"].dropna().unique()) != [source["symbol"]]:
        return "SOURCE_SYMBOL_MISMATCH"
    numeric = frame[["open", "high", "low", "close"]]
    if not numeric.map(lambda x: isinstance(x, (int, float)) and math.isfinite(float(x)) and float(x) > 0).all().all():
        return "SOURCE_OHLC_INVALID"
    if not (frame["high"] >= frame[["open", "close"]].max(axis=1)).all() or not (frame["low"] <= frame[["open", "close"]].min(axis=1)).all():
        return "SOURCE_OHLC_BOUNDS_INVALID"
    return None


def blank_horizons(reason: str) -> dict[str, Any]:
    return {str(m): {"horizon_minutes": m, "status": reason, "reason": reason} for m in HORIZONS_MINUTES}


def finalize(record: dict[str, Any]) -> dict[str, Any]:
    record["outcome_id"] = shab(cbytes({k: v for k, v in record.items() if k != "outcome_id"}))
    return record


def fail_record(candidate: dict[str, Any], source: dict[str, Any] | None, contract: dict[str, Any], reason: str, detail: str | None = None) -> dict[str, Any]:
    return finalize({"candidate_id": candidate.get("candidate_id"), "candidate_core": candidate.get("candidate_core", {}), "source_provenance": candidate.get("source_provenance", {}), "source_manifest_record": source, "outcome_contract_hash": contract["contract_hash"], "frozen_code_sha": contract["frozen_code_sha"], "implementation_tree_hash": contract["implementation_tree_hash"], "terminal_reason": reason, "terminal_detail": detail, "same_timestamp_bar_disposition": "UNKNOWN", "legal_entry": {"status": "NO_LEGAL_ENTRY_BAR", "reason": reason}, "horizons": blank_horizons(reason), "measured_horizon_count": 0, **safety_fields()})


def join_failure(candidate: dict[str, Any], source: dict[str, Any] | None) -> str | None:
    core = candidate.get("candidate_core", {})
    prov = candidate.get("source_provenance", {})
    if source is None:
        return "SOURCE_PROVENANCE_MISMATCH"
    checks = [prov.get("source_record_id") == source.get("source_record_id"), prov.get("source_logical_path") == source.get("logical_path"), prov.get("source_actual_sha256") == source.get("actual_sha256"), prov.get("source_symbol") == source.get("symbol"), prov.get("source_session_date") == source.get("session_date"), prov.get("source_manifest_semantic_hash") == INPUT_SOURCE_HASH, prov.get("source_manifest_version") == "v2", core.get("symbol") == source.get("symbol"), core.get("session_date") == source.get("session_date")]
    return None if all(checks) else "SOURCE_PROVENANCE_MISMATCH"


def measure(candidate: dict[str, Any], source: dict[str, Any], frame: pd.DataFrame, contract: dict[str, Any], source_failure: str | None = None) -> dict[str, Any]:
    jf = join_failure(candidate, source)
    if jf:
        return fail_record(candidate, source, contract, jf)
    if source_failure:
        return fail_record(candidate, source, contract, "SOURCE_VALIDATION_FAILED", source_failure)
    core = candidate["candidate_core"]
    if core.get("direction") not in {"BUY_CALL", "BUY_PUT"}:
        return fail_record(candidate, source, contract, "CANDIDATE_DIRECTION_UNSUPPORTED")
    try:
        ready = ts(core["proposal_ready_at_iso"])
    except Exception:
        return fail_record(candidate, source, contract, "CANDIDATE_TIMESTAMP_MALFORMED")
    if ready.date().isoformat() != source["session_date"]:
        return fail_record(candidate, source, contract, "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION")
    indexed = {row["timestamp"]: row for _, row in frame.iterrows()}
    if ready.second or ready.microsecond or ready.nanosecond:
        return fail_record(candidate, source, contract, "CANDIDATE_READY_OFF_GRID")
    if ready - pd.Timedelta(minutes=1) not in indexed:
        return fail_record(candidate, source, contract, "CANDIDATE_READY_BAR_MISSING")
    later = frame[frame["timestamp"] > ready]
    same = frame[frame["timestamp"] == ready]
    if later.empty:
        return fail_record(candidate, source, contract, "NO_LEGAL_ENTRY_BAR")
    entry = later.iloc[0]
    entry_start = entry["timestamp"]
    entry_open = float(entry["open"])
    horizons = {}
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
        horizons[str(minutes)] = {"horizon_minutes": minutes, "status": "MEASURED", "reason": "MEASURED", "terminal_start": iso(terminal_start), "terminal_end": iso(terminal_start + timedelta(minutes=1)), "terminal_close": round(terminal_close, 8), "unsigned_underlying_return": round(unsigned, 12), "directional_underlying_return": round(directional, 12), "high": round(max_high, 8), "low": round(min_low, 8), "mfe": round(mfe, 12), "mae": round(mae, 12), "mfe_timestamp": iso(interval.loc[max_idx, "timestamp"]), "mae_timestamp": iso(interval.loc[min_idx, "timestamp"]), "bars_in_interval": len(interval), "expected_elapsed_minutes": minutes, "actual_elapsed_minutes": int((terminal_start - entry_start).total_seconds() // 60) + 1}
        measured += 1
    return finalize({"candidate_id": candidate["candidate_id"], "candidate_core": core, "source_provenance": candidate["source_provenance"], "source_manifest_record": source, "outcome_contract_hash": contract["contract_hash"], "frozen_code_sha": contract["frozen_code_sha"], "implementation_tree_hash": contract["implementation_tree_hash"], "terminal_reason": terminal_reason, "terminal_detail": None, "same_timestamp_bar_disposition": "SKIPPED_FOR_PRIMARY" if not same.empty else "ABSENT", "legal_entry": {"status": "LEGAL_ENTRY_FOUND", "start": iso(entry_start), "end": iso(entry_start + timedelta(minutes=1)), "open": round(entry_open, 8)}, "horizons": horizons, "measured_horizon_count": measured, **safety_fields()})


def recompute_records(artifact_dir: Path, source_root: Path, contract: dict[str, Any]) -> tuple[list[dict[str, Any]], int, Counter[str], list[str]]:
    source_manifest, candidate_ledger, _summary, _sidecars, failures = verify_input_bundle(artifact_dir)
    by_id = {r["source_record_id"]: r for r in source_manifest["records"]}
    cache: dict[str, tuple[pd.DataFrame | None, str | None]] = {}
    out = []
    joins = 0
    source_failures: Counter[str] = Counter()
    for cand in candidate_ledger["records"]:
        src = by_id.get(cand.get("source_provenance", {}).get("source_record_id"))
        jf = join_failure(cand, src)
        if jf:
            source_failures[jf] += 1
            out.append(fail_record(cand, src, contract, jf))
            continue
        assert src is not None
        sid = src["source_record_id"]
        if sid not in cache:
            try:
                frame = read_frame(src, source_root)
                failure = validate_frame(frame, src)
            except Exception as exc:
                frame = None
                failure = str(exc)
            if failure:
                source_failures[failure] += 1
            cache[sid] = (frame, failure)
        frame, failure = cache[sid]
        if failure or frame is None:
            out.append(fail_record(cand, src, contract, "SOURCE_VALIDATION_FAILED", failure))
        else:
            joins += 1
            out.append(measure(cand, src, frame, contract))
    return sorted(out, key=lambda r: r["candidate_id"]), joins, source_failures, failures


def recompute_summary(records: list[dict[str, Any]], ledger_decision: str, contract_hash: str, ledger_hash: str) -> dict[str, Any]:
    from research.opening_range_retest_outcomes_v2.engine import summarize  # summary formatting is compared after record recomputation

    return summarize({"records": records, "decision": ledger_decision, "contract_hash": contract_hash, "outcome_ledger_hash": ledger_hash, "candidate_count": len(records)})


def recompute_overlap(records: list[dict[str, Any]]) -> dict[str, Any]:
    from research.opening_range_retest_outcomes_v2.overlap import build_overlap

    return build_overlap({"records": records})


def audit_artifacts(*, artifact_dir: Path, source_root: Path, contract: dict[str, Any], ledger: dict[str, Any], summary: dict[str, Any], overlap: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    failures = []
    records, joins, source_failures, input_failures = recompute_records(artifact_dir, source_root, contract)
    failures.extend(input_failures)
    if records != ledger.get("records"):
        failures.append("LEDGER_RECORD_FIELD_MISMATCH")
    ledger_hash = shab(cbytes(records))
    if ledger_hash != ledger.get("outcome_ledger_hash"):
        failures.append("OUTCOME_LEDGER_HASH_MISMATCH")
    expected_summary = recompute_summary(records, ledger.get("decision"), ledger.get("contract_hash"), ledger.get("outcome_ledger_hash"))
    if {k: v for k, v in expected_summary.items() if k != "summary_hash"} != {k: v for k, v in summary.items() if k != "summary_hash"}:
        failures.append("SUMMARY_RECOMPUTE_MISMATCH")
    expected_overlap = recompute_overlap(records)
    if expected_overlap != overlap:
        failures.append("OVERLAP_RECOMPUTE_MISMATCH")
    sidecars = {name: verify_sidecar(path) for name, path in paths.items()}
    if not all(v["sidecar_match"] for v in sidecars.values()):
        failures.append("ARTIFACT_SIDECAR_MISMATCH")
    ids = [r["candidate_id"] for r in records]
    horizon_conservation = {str(h): sum(1 for r in records if str(h) in r.get("horizons", {})) for h in HORIZONS_MINUTES}
    conservation_passed = len(records) == INPUT_CANDIDATE_COUNT and len(ids) == len(set(ids)) and all(v == INPUT_CANDIDATE_COUNT for v in horizon_conservation.values())
    if not conservation_passed:
        failures.append("CANDIDATE_OR_HORIZON_CONSERVATION_FAIL")
    if not CLAIM_BOUNDARY.issubset(set(contract.get("claim_boundary", []))) or not CLAIM_BOUNDARY.issubset(set(summary.get("claim_boundary", []))):
        failures.append("CLAIM_BOUNDARY_MISSING")
    forbidden = {"profitability_claim\":true", "option_pnl\":true", "live_ready\":true", "paper_ready\":true", "edge_claim\":true"}
    if any(key in cbytes(obj).decode("utf-8").lower() for obj in (contract, summary, ledger, overlap) for key in forbidden):
        failures.append("FORBIDDEN_CLAIM_FOUND")
    verdict = "ORB_OUTCOMES_V2_AUDIT_CERTIFIED" if not failures and not source_failures else "ORB_OUTCOMES_V2_AUDIT_NOT_CERTIFIED"
    return {"schema_version": 2, "mode": "ORB_OUTCOME_AUDIT_V2", "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES", "decision": verdict, "verdict": verdict, "reason": "standalone oracle reopened inputs and sources and recomputed records, summary, overlap, IDs, hashes, and sidecars", "timestamp": "2026-07-19T00:00:00Z", "source": "opening_range_retest_outcome_ledger_v2.json", "failures": failures, "records_recomputed": len(records), "exact_record_matches": len(records) if records == ledger.get("records") else 0, "candidate_conservation": "CANDIDATE_CONSERVATION_PASS" if conservation_passed else "CANDIDATE_CONSERVATION_FAIL", "source_join_verified_count": joins, "source_failure_counts": dict(source_failures), "input_failures": input_failures, "horizon_conservation": horizon_conservation, "recomputed_outcome_ledger_hash": ledger_hash, "summary_recomputed": "SUMMARY_RECOMPUTE_MISMATCH" not in failures, "overlap_recomputed": "OVERLAP_RECOMPUTE_MISMATCH" not in failures, "sidecars": sidecars, "sidecar_verdict": "ARTIFACT_SIDECARS_CERTIFIED" if "ARTIFACT_SIDECAR_MISMATCH" not in failures else "ARTIFACT_SIDECARS_NOT_CERTIFIED", **safety_fields()}
