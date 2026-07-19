from __future__ import annotations

import hashlib
import ast
import json
import math
import subprocess
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research.opening_range_retest_outcomes_v2.contract import (
    CONTRACT_VERSION,
    HORIZONS_MINUTES,
    IMPLEMENTATION_TREE_HASH_ALGORITHM,
    IMPLEMENTATION_TREE_PATHS,
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
PORTABLE_CONTRACT_EXCLUDE = {"contract_hash", "diagnostic_source_authority_root", "diagnostic_generation_commit_sha"}
EVIDENCE_PREFIXES = ("docs/agent_reviews/opening_range_retest_outcome_",)
CONTROL_TEST_FILE = "tests/test_opening_range_retest_outcome_controls_v2.py"
CONTROL_TEST_NAME = "test_orb_outcome_negative_control"


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
    reconciliation = load_json(artifact_dir / INPUT_FILES["reconciliation"])
    certification_text = (artifact_dir / INPUT_FILES["phase1_certification"]).read_text(encoding="utf-8")
    if source.get("record_count") != INPUT_SOURCE_COUNT or source.get("source_manifest_semantic_hash") != INPUT_SOURCE_HASH:
        failures.append("INPUT_SOURCE_MANIFEST_MISMATCH")
    if ledger.get("candidate_count") != INPUT_CANDIDATE_COUNT or ledger.get("candidate_core_semantic_hash") != INPUT_CANDIDATE_CORE_HASH or ledger.get("candidate_provenance_semantic_hash") != INPUT_CANDIDATE_PROVENANCE_HASH:
        failures.append("INPUT_CANDIDATE_LEDGER_MISMATCH")
    if summary.get("decision") != "ORB_PHASE1_V2_RECERTIFIED":
        failures.append("INPUT_SUMMARY_VERDICT_MISMATCH")
    if reconciliation.get("decision") != "UNAFFECTED_SUBSET_RECONCILED" or reconciliation.get("v1_unaffected_candidate_count") != 2192 or reconciliation.get("v2_unaffected_candidate_count") != 2192:
        failures.append("INPUT_RECONCILIATION_MISMATCH")
    if "- decision: ORB_PHASE1_V2_RECERTIFIED" not in certification_text or "NOT_ORB_PHASE1_V2_RECERTIFIED" in certification_text:
        failures.append("INPUT_CERTIFICATION_MISMATCH")
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


def _run_git(repo_root: Path, args: list[str]) -> str:
    return subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()


def _implementation_tree_hash(repo_root: Path, rev: str) -> str:
    proc = subprocess.run(["git", "ls-tree", "-r", rev, "--", *IMPLEMENTATION_TREE_PATHS], cwd=repo_root, check=True, capture_output=True, text=True)
    return shab(proc.stdout.encode("utf-8"))


def verify_contract_payload(contract: dict[str, Any]) -> list[str]:
    failures = []
    portable = {k: v for k, v in contract.items() if k not in PORTABLE_CONTRACT_EXCLUDE}
    if shab(cbytes(portable)) != contract.get("contract_hash"):
        failures.append("CONTRACT_SELF_HASH_MISMATCH")
    expected = {
        "contract_version": CONTRACT_VERSION,
        "implementation_tree_hash_algorithm": IMPLEMENTATION_TREE_HASH_ALGORITHM,
        "horizons_minutes": list(HORIZONS_MINUTES),
        "inputs": {
            "source_count": INPUT_SOURCE_COUNT,
            "source_semantic_hash": INPUT_SOURCE_HASH,
            "candidate_count": INPUT_CANDIDATE_COUNT,
            "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
            "candidate_provenance_semantic_hash": INPUT_CANDIDATE_PROVENANCE_HASH,
        },
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            failures.append("CONTRACT_FIELD_MISMATCH")
            break
    return failures


def verify_lineage_snapshot(
    *,
    frozen_sha: str,
    head_sha: str,
    is_ancestor: bool,
    expected_tree_hash: str,
    frozen_tree_hash: str | None,
    head_tree_hash: str | None,
    changed_paths: list[str],
) -> list[str]:
    failures = []
    if not frozen_sha or not head_sha or not is_ancestor:
        failures.append("FROZEN_CODE_SHA_NOT_ANCESTOR")
    if frozen_tree_hash != expected_tree_hash or head_tree_hash != expected_tree_hash:
        failures.append("IMPLEMENTATION_TREE_HASH_MISMATCH")
    if any(not path.startswith(EVIDENCE_PREFIXES) for path in changed_paths):
        failures.append("POST_FREEZE_UNEXPECTED_PATH")
    return failures


def verify_contract_and_lineage(contract: dict[str, Any], repo_root: Path) -> list[str]:
    failures = verify_contract_payload(contract)
    frozen = str(contract.get("frozen_code_sha", ""))
    head = _run_git(repo_root, ["rev-parse", "HEAD"])
    is_ancestor = True
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", frozen, head], cwd=repo_root, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        is_ancestor = False
    frozen_tree = None
    head_tree = None
    try:
        frozen_tree = _implementation_tree_hash(repo_root, frozen)
        head_tree = _implementation_tree_hash(repo_root, head)
    except subprocess.CalledProcessError:
        pass
    changed = _run_git(repo_root, ["diff", "--name-only", f"{frozen}..HEAD"]).splitlines()
    failures.extend(
        verify_lineage_snapshot(
            frozen_sha=frozen,
            head_sha=head,
            is_ancestor=is_ancestor,
            expected_tree_hash=contract.get("implementation_tree_hash"),
            frozen_tree_hash=frozen_tree,
            head_tree_hash=head_tree,
            changed_paths=changed,
        )
    )
    if any(not path.startswith(EVIDENCE_PREFIXES) for path in changed):
        failures.append("POST_FREEZE_UNEXPECTED_PATH")
    return list(dict.fromkeys(failures))


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
    reason_counts = Counter(record.get("terminal_reason") for record in records)
    by_horizon: dict[str, Counter[str]] = {str(h): Counter() for h in HORIZONS_MINUTES}
    values: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    mfes: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    maes: dict[str, list[float]] = {str(h): [] for h in HORIZONS_MINUTES}
    breakdowns: dict[str, dict[str, Counter[str]]] = {str(h): {"symbol": Counter(), "direction": Counter(), "symbol_direction": Counter(), "calendar_year": Counter()} for h in HORIZONS_MINUTES}
    for record in records:
        core = record["candidate_core"]
        year = str(core["session_date"])[:4]
        for horizon in map(str, HORIZONS_MINUTES):
            payload = record.get("horizons", {}).get(horizon)
            if not payload:
                by_horizon[horizon]["MISSING_HORIZON_RECORD"] += 1
                continue
            by_horizon[horizon][payload["status"]] += 1
            if payload["status"] == "MEASURED":
                values[horizon].append(payload["directional_underlying_return"])
                mfes[horizon].append(payload["mfe"])
                maes[horizon].append(payload["mae"])
                breakdowns[horizon]["symbol"][core["symbol"]] += 1
                breakdowns[horizon]["direction"][core["direction"]] += 1
                breakdowns[horizon]["symbol_direction"][f"{core['symbol']}:{core['direction']}"] += 1
                breakdowns[horizon]["calendar_year"][year] += 1
    stats = {h: _stats(vals) | {"mfe": _stats(mfes[h]), "mae": _stats(maes[h]), "breakdowns": {k: dict(v) for k, v in breakdowns[h].items()}} for h, vals in values.items()}
    conservation = {h: sum(c.values()) for h, c in by_horizon.items()}
    decision = "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED" if ledger_decision == "ORB_OUTCOME_LEDGER_V2_CERTIFIED" and all(v == INPUT_CANDIDATE_COUNT for v in conservation.values()) else "ORB_OUTCOMES_V2_NOT_CERTIFIED"
    summary = {
        "schema_version": 2,
        "mode": "ORB_OUTCOME_SUMMARY_V2",
        "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES",
        "decision": decision,
        "reason": "summarized certified outcome ledger without profitability or execution claims",
        "timestamp": "2026-07-19T00:00:00Z",
        "source": "opening_range_retest_outcome_ledger_v2.json",
        "contract_hash": contract_hash,
        "outcome_ledger_hash": ledger_hash,
        "candidate_count": len(records),
        "terminal_reason_counts": dict(reason_counts),
        "horizon_status_counts": {h: dict(c) for h, c in by_horizon.items()},
        "horizon_conservation": conservation,
        "descriptive_directional_return_stats": stats,
        "claim_boundary": ["DESCRIPTIVE_ONLY", "PRE_COST_UNDERLYING_ONLY", "NOT_EDGE_EVIDENCE", "NOT_OPTION_PNL", "NOT_PROFITABILITY", "NOT_PAPER_OR_LIVE_READY"],
        **safety_fields(),
    }
    summary["summary_hash"] = shab(cbytes({k: v for k, v in summary.items() if k != "summary_hash"}))
    return summary


def recompute_overlap(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_horizon: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        entry = record.get("legal_entry") or {}
        if entry.get("status") != "LEGAL_ENTRY_FOUND":
            continue
        for horizon, payload in record.get("horizons", {}).items():
            if payload.get("status") != "MEASURED":
                continue
            by_horizon.setdefault(horizon, []).append(
                {
                    "candidate_id": record["candidate_id"],
                    "symbol": record["candidate_core"]["symbol"],
                    "direction": record["candidate_core"]["direction"],
                    "session_date": record["candidate_core"]["session_date"],
                    "start": entry["start"],
                    "end": payload["terminal_end"],
                }
            )
    horizons = {}
    for horizon, intervals in by_horizon.items():
        events = []
        open_items: list[dict[str, Any]] = []
        pairs = 0
        max_open = 0
        for item in sorted(intervals, key=lambda x: (x["start"], x["end"], x["candidate_id"])):
            start = pd.Timestamp(item["start"])
            open_items = [active for active in open_items if pd.Timestamp(active["end"]) > start]
            pairs += len(open_items)
            open_items.append(item)
            max_open = max(max_open, len(open_items))
            events.append(item)
        horizons[horizon] = {
            "interval_count": len(intervals),
            "complete_interval_count": len(events),
            "complete_interval_set_hash": shab(cbytes(events)),
            "overlapping_pair_count": pairs,
            "max_simultaneous_candidates": max_open,
            "symbol_counts": dict(Counter(item["symbol"] for item in intervals)),
            "direction_counts": dict(Counter(item["direction"] for item in intervals)),
            "symbol_direction_counts": dict(Counter(f"{item['symbol']}:{item['direction']}" for item in intervals)),
            "complete_session_cluster_counts": dict(Counter(item["session_date"] for item in intervals)),
            "session_cluster_counts": dict(Counter(item["session_date"] for item in intervals).most_common(25)),
            "sample_truncated": len(events) > 500,
            "sample_count": min(len(events), 500),
            "sample": events[:500],
            "overlap_evidence_intervals": events[:500],
        }
    return {
        "schema_version": 1,
        "mode": "ORB_OUTCOME_OVERLAP_V2",
        "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES",
        "decision": "ORB_OUTCOME_OVERLAP_REPORTED",
        "reason": "reported half-open interval overlap diagnostics without filtering descriptive candidates",
        "timestamp": "2026-07-19T00:00:00Z",
        "source": "opening_range_retest_outcome_ledger_v2.json",
        "horizons": horizons,
        **safety_fields(),
    }


def _quantile(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    ordered = sorted(vals)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return round(ordered[lo], 12)
    return round(ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo), 12)


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


def summary_failures(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures = []
    if expected.get("terminal_reason_counts") != actual.get("terminal_reason_counts") or expected.get("horizon_status_counts") != actual.get("horizon_status_counts"):
        failures.append("SUMMARY_STATUS_COUNT_MISMATCH")
    if expected.get("summary_hash") != actual.get("summary_hash"):
        failures.append("SUMMARY_HASH_MISMATCH")
    if expected.get("descriptive_directional_return_stats") != actual.get("descriptive_directional_return_stats"):
        failures.extend(["SUMMARY_MEAN_MISMATCH", "SUMMARY_MEDIAN_MISMATCH", "SUMMARY_QUANTILE_MISMATCH", "SUMMARY_SIGN_COUNT_MISMATCH", "SUMMARY_MFE_MISMATCH", "SUMMARY_MAE_MISMATCH", "SUMMARY_BREAKDOWN_MISMATCH"])
    if {k: v for k, v in expected.items() if k != "summary_hash"} != {k: v for k, v in actual.items() if k != "summary_hash"} and not failures:
        failures.append("SUMMARY_RECOMPUTE_MISMATCH")
    return list(dict.fromkeys(failures))


def overlap_failures(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures = []
    for horizon, item in expected.get("horizons", {}).items():
        other = actual.get("horizons", {}).get(horizon, {})
        if item.get("complete_interval_set_hash") != other.get("complete_interval_set_hash"):
            failures.append("OVERLAP_INTERVAL_SET_HASH_MISMATCH")
        if item.get("overlapping_pair_count") != other.get("overlapping_pair_count"):
            failures.append("OVERLAP_PAIR_COUNT_MISMATCH")
        if item.get("max_simultaneous_candidates") != other.get("max_simultaneous_candidates"):
            failures.append("OVERLAP_MAX_CONCURRENCY_MISMATCH")
        if item.get("direction_counts") != other.get("direction_counts"):
            failures.append("OVERLAP_DIRECTION_COUNT_MISMATCH")
        if item.get("complete_session_cluster_counts") != other.get("complete_session_cluster_counts"):
            failures.append("OVERLAP_SESSION_COUNT_MISMATCH")
        if item.get("sample_count") != other.get("sample_count") or item.get("sample_truncated") != other.get("sample_truncated") or item.get("sample") != other.get("sample"):
            failures.append("OVERLAP_SAMPLE_CONTRACT_MISMATCH")
    if expected != actual:
        failures.append("OVERLAP_RECOMPUTE_MISMATCH")
    return list(dict.fromkeys(failures))


def ledger_record_failures(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures = []
    if expected.get("candidate_id") != actual.get("candidate_id"):
        failures.append("CANDIDATE_ID_MISMATCH")
    if expected.get("outcome_id") != actual.get("outcome_id"):
        failures.append("OUTCOME_ID_MISMATCH")
    if expected.get("measured_horizon_count") != actual.get("measured_horizon_count"):
        failures.append("MEASURED_HORIZON_COUNT_MISMATCH")
    if expected.get("legal_entry", {}).get("open") != actual.get("legal_entry", {}).get("open"):
        failures.append("ENTRY_PRICE_MISMATCH")
    for horizon, item in expected.get("horizons", {}).items():
        other = actual.get("horizons", {}).get(horizon)
        if other is None:
            failures.append("MISSING_HORIZON_RECORD")
            continue
        if item.get("terminal_close") != other.get("terminal_close"):
            failures.append("TERMINAL_CLOSE_MISMATCH")
        if item.get("directional_underlying_return") != other.get("directional_underlying_return"):
            failures.append("DIRECTIONAL_RETURN_MISMATCH")
        if item.get("mfe") != other.get("mfe"):
            failures.append("MFE_MISMATCH")
        if item.get("mae") != other.get("mae"):
            failures.append("MAE_MISMATCH")
        if item.get("mfe_timestamp") != other.get("mfe_timestamp") or item.get("mae_timestamp") != other.get("mae_timestamp"):
            failures.append("EXTREMA_TIMESTAMP_MISMATCH")
    if expected != actual and not failures:
        failures.append("LEDGER_RECORD_FIELD_MISMATCH")
    return list(dict.fromkeys(failures))


def ledger_conservation_failures(records: list[dict[str, Any]], *, expected_candidate_count: int = INPUT_CANDIDATE_COUNT) -> list[str]:
    ids = [record.get("candidate_id") for record in records]
    horizon_conservation = {str(h): sum(1 for record in records if str(h) in record.get("horizons", {})) for h in HORIZONS_MINUTES}
    failures = []
    if len(ids) != len(set(ids)):
        failures.append("DUPLICATE_CANDIDATE_ID")
    if len(records) != expected_candidate_count or any(value != expected_candidate_count for value in horizon_conservation.values()):
        failures.append("CANDIDATE_OR_HORIZON_CONSERVATION_FAIL")
    return failures


def oracle_independence_failures(source: str) -> list[str]:
    tree = ast.parse(source)
    forbidden_modules = {
        "research.opening_range_retest_outcomes_v2.engine",
        "research.opening_range_retest_outcomes_v2.overlap",
    }
    forbidden_names = {"summarize", "build_ledger", "measure_candidate", "build_overlap"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
            if any(alias.name in forbidden_names or alias.name == "*" for alias in node.names):
                return ["ORACLE_FORBIDDEN_IMPORT"]
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_modules:
                    return ["ORACLE_FORBIDDEN_IMPORT"]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            root = node.func.value
            if isinstance(root, ast.Name) and root.id in {"engine", "overlap"} and node.func.attr in forbidden_names:
                return ["ORACLE_FORBIDDEN_IMPORT"]
    return []


def control_report_failures(controls: dict[str, Any] | None, *, frozen_code_sha: str, implementation_tree_hash: str) -> list[str]:
    if not controls:
        return ["NEGATIVE_CONTROL_REPORT_MISSING"]
    failures = []
    rows = controls.get("controls", [])
    ids = [row.get("control_id") for row in rows]
    nodes = [row.get("pytest_node_id") for row in rows]
    if controls.get("verdict") != "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED":
        failures.append("NEGATIVE_CONTROL_VERDICT_MISMATCH")
    if controls.get("collected", 0) < 75 or controls.get("executed") != controls.get("collected") or controls.get("passed") != controls.get("executed"):
        failures.append("NEGATIVE_CONTROL_EXECUTION_COUNTS_MISMATCH")
    if controls.get("failed") or controls.get("skipped") or controls.get("xfailed") or controls.get("xpassed"):
        failures.append("NEGATIVE_CONTROL_NON_PASSING_RESULT")
    if len(ids) != len(set(ids)) or len(nodes) != len(set(nodes)):
        failures.append("NEGATIVE_CONTROL_DUPLICATE_ID")
    if any(not str(node).startswith(f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[") for node in nodes):
        failures.append("NEGATIVE_CONTROL_NODE_ID_MISMATCH")
    if controls.get("frozen_code_sha") != frozen_code_sha:
        failures.append("NEGATIVE_CONTROL_FROZEN_SHA_MISMATCH")
    if controls.get("implementation_tree_hash") != implementation_tree_hash:
        failures.append("NEGATIVE_CONTROL_IMPLEMENTATION_TREE_MISMATCH")
    for row in rows:
        mutation = str(row.get("mutation", "")).lower()
        if "negative mutation" in mutation or not row.get("target_invoked") or not row.get("mutation_applied") or row.get("status") != "PASS":
            failures.append("NEGATIVE_CONTROL_SYNTHETIC_ROW")
            break
    if controls.get("expected_result_leak_count") != 0:
        failures.append("CONTROL_EXECUTOR_EXPECTED_RESULT_LEAK")
    if controls.get("non_invoked_target_count") != 0:
        failures.append("NEGATIVE_CONTROL_TARGET_NOT_INVOKED")
    if controls.get("non_mutating_control_count") != 0:
        failures.append("NEGATIVE_CONTROL_MUTATION_NOT_APPLIED")
    if controls.get("duplicate_control_fingerprint_count") != 0:
        failures.append("NEGATIVE_CONTROL_DUPLICATE_FINGERPRINT")
    if controls.get("unique_control_fingerprint_count") != len(rows):
        failures.append("NEGATIVE_CONTROL_FINGERPRINT_COUNT_MISMATCH")
    return list(dict.fromkeys(failures))


def audit_artifacts(*, artifact_dir: Path, source_root: Path, contract: dict[str, Any], ledger: dict[str, Any], summary: dict[str, Any], overlap: dict[str, Any], controls: dict[str, Any] | None, paths: dict[str, Path]) -> dict[str, Any]:
    failures = []
    failures.extend(verify_contract_and_lineage(contract, Path.cwd()))
    records, joins, source_failures, input_failures = recompute_records(artifact_dir, source_root, contract)
    failures.extend(input_failures)
    if records != ledger.get("records"):
        failures.append("LEDGER_RECORD_FIELD_MISMATCH")
    ledger_hash = shab(cbytes(records))
    if ledger_hash != ledger.get("outcome_ledger_hash"):
        failures.append("OUTCOME_LEDGER_HASH_MISMATCH")
    expected_summary = recompute_summary(records, ledger.get("decision"), ledger.get("contract_hash"), ledger.get("outcome_ledger_hash"))
    failures.extend(summary_failures(expected_summary, summary))
    expected_overlap = recompute_overlap(records)
    failures.extend(overlap_failures(expected_overlap, overlap))
    control_failures = control_report_failures(controls, frozen_code_sha=contract.get("frozen_code_sha"), implementation_tree_hash=contract.get("implementation_tree_hash"))
    if control_failures:
        failures.append("NEGATIVE_CONTROL_MATRIX_MISMATCH")
        failures.extend(control_failures)
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
    return {"schema_version": 2, "mode": "ORB_OUTCOME_AUDIT_V2", "candidate_id": "ALL_ORB_PHASE1_V2_CANDIDATES", "decision": verdict, "verdict": verdict, "reason": "standalone oracle reopened inputs and sources and recomputed records, summary, overlap, IDs, hashes, controls, and sidecars", "timestamp": "2026-07-19T00:00:00Z", "source": "opening_range_retest_outcome_ledger_v2.json", "failures": list(dict.fromkeys(failures)), "negative_control_verdict": controls.get("verdict") if controls else None, "records_recomputed": len(records), "exact_record_matches": len(records) if records == ledger.get("records") else 0, "candidate_conservation": "CANDIDATE_CONSERVATION_PASS" if conservation_passed else "CANDIDATE_CONSERVATION_FAIL", "source_join_verified_count": joins, "source_failure_counts": dict(source_failures), "input_failures": input_failures, "horizon_conservation": horizon_conservation, "recomputed_outcome_ledger_hash": ledger_hash, "summary_recomputed": not any(f.startswith("SUMMARY_") for f in failures), "overlap_recomputed": "OVERLAP_RECOMPUTE_MISMATCH" not in failures, "sidecars": sidecars, "sidecar_verdict": "ARTIFACT_SIDECARS_CERTIFIED" if "ARTIFACT_SIDECAR_MISMATCH" not in failures else "ARTIFACT_SIDECARS_NOT_CERTIFIED", **safety_fields()}
