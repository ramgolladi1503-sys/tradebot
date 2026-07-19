from __future__ import annotations

import ast
import json
import shutil
import tempfile
import traceback
import copy
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from research.opening_range_retest_outcomes_v2.contract import (
    INPUT_CANDIDATE_CORE_HASH,
    INPUT_CANDIDATE_COUNT,
    INPUT_CANDIDATE_PROVENANCE_HASH,
    INPUT_SOURCE_COUNT,
    INPUT_SOURCE_HASH,
    canonical_json_bytes,
    evidence_fields,
    safety_fields,
    sha256_bytes,
    sha256_file,
)
from research.opening_range_retest_outcomes_v2.engine import measure_candidate, validate_frame
from research.opening_range_retest_outcomes_v2.oracle import (
    cbytes,
    join_failure,
    ledger_conservation_failures,
    ledger_record_failures,
    oracle_independence_failures,
    overlap_failures,
    shab,
    source_path,
    summary_failures,
    verify_contract_payload,
    verify_input_bundle,
    verify_lineage_snapshot,
)

CATEGORY_MINIMUMS = {
    "lineage_hash": 12,
    "input_certification": 10,
    "source_join": 18,
    "temporal_horizon": 16,
    "math_identity": 10,
    "summary_overlap": 9,
}
CONTROL_TEST_FILE = "tests/test_opening_range_retest_outcome_controls_v2.py"
CONTROL_TEST_NAME = "test_orb_outcome_negative_control"
INPUT_ARTIFACT_DIR = Path("docs/agent_reviews")
INPUT_FILES = {
    "source_manifest": "opening_range_retest_causal_replay_source_manifest_v2.json",
    "candidate_ledger": "opening_range_retest_causal_replay_candidate_ledger_v2.json",
    "phase1_summary": "opening_range_retest_causal_replay_summary_v2.json",
    "reconciliation": "opening_range_retest_phase1_v2_reconciliation.json",
    "phase1_certification": "opening_range_retest_phase1_v2_certification.md",
}


@dataclass(frozen=True)
class ControlCase:
    control_id: str
    category: str
    mutation: str
    expected_failure: str
    target_function: str
    executor_function: str

    @property
    def node_id(self) -> str:
        return f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[{self.control_id}]"


@dataclass(frozen=True)
class Execution:
    observed_failure: str
    target_invoked: bool
    fixture_before: Any
    fixture_after: Any
    mutation_fingerprint: Any


@dataclass(frozen=True)
class ControlResult:
    case: ControlCase
    observed_failure: str
    target_invoked: bool
    fixture_hash_before: str
    fixture_hash_after: str
    mutation_applied: bool
    control_fingerprint: str
    status: str
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.case.control_id,
            "test_node_id": self.case.node_id,
            "pytest_node_id": self.case.node_id,
            "category": self.case.category,
            "mutation": self.case.mutation,
            "executor_function": self.case.executor_function,
            "target_function": self.case.target_function,
            "fixture_hash_before": self.fixture_hash_before,
            "fixture_hash_after": self.fixture_hash_after,
            "mutation_applied": self.mutation_applied,
            "target_invoked": self.target_invoked,
            "expected_failure": self.case.expected_failure,
            "observed_failure": self.observed_failure,
            "control_fingerprint": self.control_fingerprint,
            "status": self.status,
            "error": self.error,
        }


def _digest(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(k): normalize(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(v) for v in item]
        if isinstance(item, pd.Timestamp):
            return item.isoformat()
        if hasattr(item, "item"):
            try:
                return item.item()
            except Exception:
                pass
        if isinstance(item, float) and pd.isna(item):
            return "NaN"
        return item

    return sha256_bytes(canonical_json_bytes(normalize(value)))


def _first_failure(failures: list[str], expected: str) -> str:
    return expected if expected in failures else (failures[0] if failures else "NO_FAILURE")


def _expected(case: ControlCase) -> str:
    return case.expected_failure


def _frame() -> pd.DataFrame:
    ts = pd.date_range("2026-07-06 09:15", periods=375, freq="min")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "symbol": ["NIFTY"] * len(ts),
            "open": [100.0 + i for i in range(len(ts))],
            "high": [101.0 + i for i in range(len(ts))],
            "low": [99.0 + i for i in range(len(ts))],
            "close": [100.5 + i for i in range(len(ts))],
            "volume": [1] * len(ts),
            "oi": [0] * len(ts),
            "source": ["fixture"] * len(ts),
            "interval": ["1minute"] * len(ts),
            "fetch_timestamp": ["2026-07-06T16:00:00+05:30"] * len(ts),
            "fetch_start_date": ["2026-07-06"] * len(ts),
            "fetch_end_date": ["2026-07-06"] * len(ts),
            "data_origin": ["fixture"] * len(ts),
            "synthetic": [False] * len(ts),
            "mock": [False] * len(ts),
            "fallback": [False] * len(ts),
            "provider": ["upstox"] * len(ts),
            "source_endpoint": ["historical-candle"] * len(ts),
        }
    )


def _source(tmp: Path | None = None) -> dict[str, Any]:
    path = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    record = {
        "source_record_id": "source",
        "logical_path": path,
        "actual_sha256": "a" * 64,
        "byte_size": 1,
        "session_date": "2026-07-06",
        "symbol": "NIFTY",
    }
    if tmp is not None:
        p = tmp / path
        p.parent.mkdir(parents=True)
        _frame().to_parquet(p, index=False)
        record["actual_sha256"] = sha256_file(p)
        record["byte_size"] = p.stat().st_size
    return record


def _candidate() -> dict[str, Any]:
    return {
        "candidate_id": "candidate",
        "candidate_core": {
            "strategy_id": "opening_range_retest_v1",
            "symbol": "NIFTY",
            "direction": "BUY_CALL",
            "status": "RAW_CANDIDATE",
            "raw_score": 1.0,
            "entry_trigger": "entry",
            "invalid_if": "invalid",
            "rank_reason": "rank",
            "proposal_ready_at_iso": "2026-07-06T09:20:00+05:30",
            "setup_id": "setup",
            "history_hash": "history",
            "session_date": "2026-07-06",
        },
        "source_provenance": {
            "source_record_id": "source",
            "source_logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet",
            "source_actual_sha256": "a" * 64,
            "source_manifest_semantic_hash": INPUT_SOURCE_HASH,
            "source_manifest_version": "v2",
            "source_session_date": "2026-07-06",
            "source_symbol": "NIFTY",
        },
    }


def _contract() -> dict[str, Any]:
    payload = {
        "contract_hash": "old",
        "contract_version": "opening_range_retest_outcome_contract_v2",
        "implementation_tree_hash_algorithm": "sha256(git-ls-tree-r HEAD -- implementation-tree-paths)",
        "horizons_minutes": [1, 3, 5, 15, 30],
        "inputs": {
            "source_count": INPUT_SOURCE_COUNT,
            "source_semantic_hash": INPUT_SOURCE_HASH,
            "candidate_count": INPUT_CANDIDATE_COUNT,
            "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
            "candidate_provenance_semantic_hash": INPUT_CANDIDATE_PROVENANCE_HASH,
        },
        "frozen_code_sha": "frozen",
        "implementation_tree_hash": "tree",
    }
    payload["contract_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "contract_hash"}))
    return payload


def _exec_contract_payload(case: ControlCase) -> Execution:
    contract = _contract()
    before = copy.deepcopy(contract)
    if case.control_id == "LINEAGE_CONTRACT_SELF_HASH":
        contract["horizons_minutes"] = [1, 3, 5]
    elif "SOURCE_HASH" in case.control_id:
        contract["inputs"]["source_semantic_hash"] = "0" * 64
    elif "CANDIDATE_CORE_HASH" in case.control_id:
        contract["inputs"]["candidate_core_semantic_hash"] = "0" * 64
    elif "CANDIDATE_PROVENANCE_HASH" in case.control_id:
        contract["inputs"]["candidate_provenance_semantic_hash"] = "0" * 64
    elif "SOURCE_COUNT" in case.control_id:
        contract["inputs"]["source_count"] = INPUT_SOURCE_COUNT - 1
    elif "CANDIDATE_COUNT" in case.control_id:
        contract["inputs"]["candidate_count"] = INPUT_CANDIDATE_COUNT - 1
    elif "HORIZON_RULE" in case.control_id:
        contract["horizons_minutes"] = [1, 3, 5]
        contract["contract_hash"] = shab(cbytes({k: v for k, v in contract.items() if k != "contract_hash"}))
    elif "IMPLEMENTATION_ALGORITHM" in case.control_id:
        contract["implementation_tree_hash_algorithm"] = "sha256(other)"
        contract["contract_hash"] = shab(cbytes({k: v for k, v in contract.items() if k != "contract_hash"}))
    failures = verify_contract_payload(contract)
    return Execution(_first_failure(failures, _expected(case)), True, before, contract, {"contract": contract})


def _exec_lineage_snapshot(case: ControlCase) -> Execution:
    before = {"is_ancestor": True, "frozen_tree_hash": "tree", "head_tree_hash": "tree", "changed_paths": []}
    after = dict(before)
    if "NON_ANCESTOR" in case.control_id:
        after["is_ancestor"] = False
    elif "IMPLEMENTATION_TREE" in case.control_id:
        after["head_tree_hash"] = "other"
    elif "TEST_POST_FREEZE" in case.control_id:
        after["changed_paths"] = ["tests/test_opening_range_retest_outcome_controls_v2.py"]
    elif "POST_FREEZE" in case.control_id:
        after["changed_paths"] = ["research/opening_range_retest_outcomes_v2/engine.py"]
    elif "UNEXPECTED_PATH" in case.control_id:
        after["changed_paths"] = ["README.md"]
    failures = verify_lineage_snapshot(
        frozen_sha="frozen",
        head_sha="head",
        is_ancestor=bool(after["is_ancestor"]),
        expected_tree_hash="tree",
        frozen_tree_hash=str(after["frozen_tree_hash"]),
        head_tree_hash=str(after["head_tree_hash"]),
        changed_paths=list(after["changed_paths"]),
    )
    return Execution(_first_failure(failures, _expected(case)), True, before, after, after)


def _copy_input_bundle(tmp: Path) -> None:
    for filename in INPUT_FILES.values():
        src = INPUT_ARTIFACT_DIR / filename
        dst = tmp / filename
        shutil.copy2(src, dst)
        shutil.copy2(src.with_suffix(src.suffix + ".sha256"), dst.with_suffix(dst.suffix + ".sha256"))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")


def _exec_input_bundle(case: ControlCase) -> Execution:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _copy_input_bundle(root)
        _source, _ledger, _summary, _sidecars, clean_failures = verify_input_bundle(root)
        before = {
            name: {
                "artifact": sha256_file(root / filename),
                "sidecar": (root / filename).with_suffix((root / filename).suffix + ".sha256").read_text(encoding="utf-8"),
            }
            for name, filename in INPUT_FILES.items()
        }
        if clean_failures:
            return Execution(clean_failures[0], True, before, before, {"clean_failures": clean_failures})
        if case.control_id.startswith("INPUT_SIDECAR_"):
            key = case.control_id.removeprefix("INPUT_SIDECAR_").lower()
            if key == "phase1_certification":
                target = root / INPUT_FILES[key]
            else:
                target = root / INPUT_FILES[key]
            target.with_suffix(target.suffix + ".sha256").write_text("0" * 64 + f"  {target.name}\n", encoding="utf-8")
        elif case.control_id == "INPUT_SOURCE_MANIFEST_HASH":
            path = root / INPUT_FILES["source_manifest"]
            payload = _load(path)
            payload["source_manifest_semantic_hash"] = "0" * 64
            _write_json(path, payload)
        elif case.control_id == "INPUT_SOURCE_MANIFEST_COUNT":
            path = root / INPUT_FILES["source_manifest"]
            payload = _load(path)
            payload["record_count"] = INPUT_SOURCE_COUNT - 1
            _write_json(path, payload)
        elif case.control_id == "INPUT_CANDIDATE_LEDGER_CORE_HASH":
            path = root / INPUT_FILES["candidate_ledger"]
            payload = _load(path)
            payload["candidate_core_semantic_hash"] = "0" * 64
            _write_json(path, payload)
        elif case.control_id == "INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH":
            path = root / INPUT_FILES["candidate_ledger"]
            payload = _load(path)
            payload["candidate_provenance_semantic_hash"] = "0" * 64
            _write_json(path, payload)
        elif case.control_id == "INPUT_CANDIDATE_LEDGER_COUNT":
            path = root / INPUT_FILES["candidate_ledger"]
            payload = _load(path)
            payload["candidate_count"] = INPUT_CANDIDATE_COUNT - 1
            _write_json(path, payload)
        elif case.control_id == "INPUT_SUMMARY_VERDICT":
            path = root / INPUT_FILES["phase1_summary"]
            payload = _load(path)
            payload["decision"] = "ORB_PHASE1_V2_NOT_CERTIFIED"
            _write_json(path, payload)
        elif case.control_id == "INPUT_RECONCILIATION_VERDICT":
            path = root / INPUT_FILES["reconciliation"]
            payload = _load(path)
            payload["decision"] = "NOT_RECONCILED"
            _write_json(path, payload)
        elif case.control_id == "INPUT_RECONCILIATION_V1_COUNT":
            path = root / INPUT_FILES["reconciliation"]
            payload = _load(path)
            payload["v1_unaffected_candidate_count"] = 0
            _write_json(path, payload)
        elif case.control_id == "INPUT_RECONCILIATION_V2_COUNT":
            path = root / INPUT_FILES["reconciliation"]
            payload = _load(path)
            payload["v2_unaffected_candidate_count"] = 0
            _write_json(path, payload)
        elif case.control_id == "INPUT_DECEPTIVE_CERTIFICATION":
            path = root / INPUT_FILES["phase1_certification"]
            path.write_text(path.read_text(encoding="utf-8") + "\n- decision: NOT_ORB_PHASE1_V2_RECERTIFIED\n", encoding="utf-8")
        after = {
            name: {
                "artifact": sha256_file(root / filename),
                "sidecar": (root / filename).with_suffix((root / filename).suffix + ".sha256").read_text(encoding="utf-8"),
            }
            for name, filename in INPUT_FILES.items()
        }
        *_unused, failures = verify_input_bundle(root)
    return Execution(_first_failure(failures, _expected(case)), True, before, after, {"input_after": after, "control": case.control_id})


def _exec_source_path(case: ControlCase) -> Execution:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = _source(root)
        before = {"source": src.copy(), "path_exists": True}
        path = root / src["logical_path"]
        if case.control_id == "SOURCE_RECORD_MISSING_FROM_MANIFEST_JOIN":
            return Execution(join_failure(_candidate(), None) or "NO_FAILURE", True, before, {"source": None}, {"join": "missing"})
        if case.control_id == "SOURCE_MISSING_FILE":
            path.unlink()
        elif case.control_id == "SOURCE_SHA_MISMATCH":
            src["actual_sha256"] = "0" * 64
        elif case.control_id == "SOURCE_BYTE_SIZE_MISMATCH":
            src["byte_size"] = int(src["byte_size"]) + 1
        elif case.control_id == "SOURCE_SYMLINK_FILE":
            path.unlink()
            path.symlink_to(root / "missing.parquet")
        elif case.control_id == "SOURCE_SYMLINK_ANCESTOR":
            shutil.rmtree(root / "runtime" / "upstox_candidate_replay")
            outside = root / "outside"
            outside.mkdir()
            (root / "runtime" / "upstox_candidate_replay").symlink_to(outside)
        elif case.control_id == "SOURCE_ABSOLUTE_PATH":
            src["logical_path"] = "/tmp/orb_outcome_control_outside.parquet"
        elif case.control_id == "SOURCE_TRAVERSAL_PATH":
            src["logical_path"] = "runtime/upstox_candidate_replay/../evil.parquet"
        try:
            source_path(src, root)
            observed = "NO_FAILURE"
        except ValueError as exc:
            observed = str(exc)
        after = {"source": src, "path_exists": (root / str(src.get("logical_path", ""))).exists()}
    return Execution(observed, True, before, after, {"source": after})


def _exec_join(case: ControlCase) -> Execution:
    src = _source()
    cand = _candidate()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
    before = {"candidate": cand, "source": src}
    cand = json.loads(json.dumps(cand))
    if "record id" in case.mutation:
        cand["source_provenance"]["source_record_id"] = "other"
    elif "path" in case.mutation:
        cand["source_provenance"]["source_logical_path"] = "runtime/upstox_candidate_replay/other.parquet"
    elif "sha" in case.mutation:
        cand["source_provenance"]["source_actual_sha256"] = "0" * 64
    elif "manifest hash" in case.mutation:
        cand["source_provenance"]["source_manifest_semantic_hash"] = "0" * 64
    elif "manifest version" in case.mutation:
        cand["source_provenance"]["source_manifest_version"] = "v1"
    elif "provenance symbol" in case.mutation:
        cand["source_provenance"]["source_symbol"] = "BANKNIFTY"
    elif "provenance session" in case.mutation:
        cand["source_provenance"]["source_session_date"] = "2026-07-07"
    elif "core symbol" in case.mutation:
        cand["candidate_core"]["symbol"] = "BANKNIFTY"
    elif "core session" in case.mutation:
        cand["candidate_core"]["session_date"] = "2026-07-07"
    after = {"candidate": cand, "source": src}
    return Execution(join_failure(cand, src) or "NO_FAILURE", True, before, after, after)


def _exec_frame(case: ControlCase) -> Execution:
    frame = _frame()
    src = _source()
    before = {"columns": list(frame.columns), "rows": frame.to_dict("list")}
    if "schema order" in case.mutation:
        frame = frame[list(reversed(frame.columns))]
    elif "schema" in case.mutation:
        frame = frame.drop(columns=["provider"])
    elif "duplicate" in case.mutation:
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    elif "non-monotonic" in case.mutation:
        frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"] - pd.Timedelta(minutes=1)
    elif "missing timestamp" in case.mutation:
        frame = frame.drop(index=2).reset_index(drop=True)
    elif "irregular" in case.mutation:
        frame.loc[2, "timestamp"] = frame.loc[2, "timestamp"] + pd.Timedelta(seconds=30)
    elif "wrong first" in case.mutation:
        frame.loc[0, "timestamp"] = pd.Timestamp("2026-07-06 09:16")
    elif "wrong last" in case.mutation:
        frame.loc[374, "timestamp"] = pd.Timestamp("2026-07-06 15:30")
    elif "session date" in case.mutation or "wrong date" in case.mutation:
        frame["timestamp"] = frame["timestamp"] + pd.Timedelta(days=1)
    elif "symbol" in case.mutation:
        frame.loc[0, "symbol"] = "BANKNIFTY"
    elif "non-positive" in case.mutation:
        frame.loc[0, "open"] = 0.0
    elif "nan" in case.mutation:
        frame.loc[0, "close"] = float("nan")
    elif "inf" in case.mutation:
        frame.loc[0, "high"] = float("inf")
    elif "bounds" in case.mutation:
        frame.loc[0, "high"] = frame.loc[0, "low"] - 1
    after = {"columns": list(frame.columns), "rows": frame.to_dict("list")}
    return Execution(validate_frame(frame, src) or "NO_FAILURE", True, before, after, {"frame": case.mutation, "hash": _digest(after)})


def _exec_measure(case: ControlCase) -> Execution:
    cand = _candidate()
    src = _source()
    frame = _frame()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
    before = {"candidate": cand, "frame_hash": _digest(frame.to_dict("list"))}
    if "source validation prevents" in case.mutation:
        return Execution(measure_candidate(cand, src, frame, "contract", source_failure="SOURCE_SCHEMA_MISMATCH")["terminal_reason"], True, before, {"source_failure": True}, {"measure": case.mutation})
    if "malformed" in case.mutation:
        cand["candidate_core"]["proposal_ready_at_iso"] = "not-a-time"
    elif "outside" in case.mutation:
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-07T09:20:00+05:30"
    elif "seconds" in case.mutation:
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-06T09:20:30+05:30"
    elif "microseconds" in case.mutation:
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-06T09:20:00.000001+05:30"
    elif "completed bar" in case.mutation:
        frame = frame[frame["timestamp"] != pd.Timestamp("2026-07-06 09:19")]
    elif "no later entry" in case.mutation:
        cand["candidate_core"]["proposal_ready_at_iso"] = "2026-07-06T15:29:00+05:30"
    elif "unsupported direction" in case.mutation:
        cand["candidate_core"]["direction"] = "SELL_CALL"
    elif "missing horizon minute" in case.mutation or "ALL_HORIZONS_EXACT" in case.control_id:
        frame = frame[frame["timestamp"] != pd.Timestamp("2026-07-06 09:25")]
    outcome = measure_candidate(cand, src, frame, "contract")
    observed = outcome["horizons"]["5"]["status"] if "missing horizon minute" in case.mutation or "ALL_HORIZONS_EXACT" in case.control_id else outcome["terminal_reason"]
    after = {"candidate": cand, "frame_hash": _digest(frame.to_dict("list")), "outcome": outcome}
    return Execution(observed, True, before, after, {"measure": case.mutation, "outcome": outcome})


def _valid_outcome(direction: str = "BUY_CALL") -> dict[str, Any]:
    cand = _candidate()
    cand["candidate_core"]["direction"] = direction
    src = _source()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
    return measure_candidate(cand, src, _frame(), "contract")


def _exec_math_record(case: ControlCase) -> Execution:
    expected = _valid_outcome("BUY_CALL")
    actual = json.loads(json.dumps(expected))
    if case.control_id == "MATH_ENTRY_PRICE":
        actual["legal_entry"]["open"] += 1
    elif case.control_id == "MATH_TERMINAL_CLOSE":
        actual["horizons"]["1"]["terminal_close"] += 1
    elif case.control_id == "MATH_DIRECTIONAL_RETURN":
        actual["horizons"]["1"]["directional_underlying_return"] *= -1
    elif case.control_id == "MATH_MFE":
        actual["horizons"]["1"]["mfe"] += 1
    elif case.control_id == "MATH_MAE":
        actual["horizons"]["1"]["mae"] -= 1
    elif case.control_id == "MATH_EXTREMA_TIMESTAMP":
        actual["horizons"]["1"]["mfe_timestamp"] = "2026-07-06T09:15:00+05:30"
    elif case.control_id == "MATH_MEASURED_COUNT":
        actual["measured_horizon_count"] -= 1
    elif case.control_id == "MATH_OUTCOME_ID":
        actual["outcome_id"] = "0" * 64
    failures = ledger_record_failures(expected, actual)
    return Execution(_first_failure(failures, _expected(case)), True, expected, actual, {"record": actual})


def _exec_conservation(case: ControlCase) -> Execution:
    a = _valid_outcome("BUY_CALL")
    b = _valid_outcome("BUY_PUT")
    b["candidate_id"] = "candidate_b"
    before = [a, b]
    records = json.loads(json.dumps(before))
    expected_count = 2
    if case.control_id == "MATH_DUPLICATE_CANDIDATE_ID":
        records[1]["candidate_id"] = records[0]["candidate_id"]
        expected = "DUPLICATE_CANDIDATE_ID"
    else:
        records[0]["horizons"].pop("30")
        expected = "CANDIDATE_OR_HORIZON_CONSERVATION_FAIL"
    failures = ledger_conservation_failures(records, expected_candidate_count=expected_count)
    return Execution(_first_failure(failures, expected), True, before, records, {"records": records})


def _exec_summary(case: ControlCase) -> Execution:
    expected = {
        "summary_hash": "a",
        "terminal_reason_counts": {"MEASURED": 1},
        "horizon_status_counts": {"1": {"MEASURED": 1}},
        "descriptive_directional_return_stats": {
            "1": {
                "mean": 1,
                "median": 1,
                "p05": 1,
                "positive": 1,
                "negative": 0,
                "mfe": {"mean": 1},
                "mae": {"mean": -1},
            }
        },
    }
    actual = json.loads(json.dumps(expected))
    if "status" in case.mutation or "missing horizon" in case.mutation:
        actual["terminal_reason_counts"] = {"MEASURED": 0}
    elif "hash" in case.mutation:
        actual["summary_hash"] = "b"
    elif "MFE" in case.mutation:
        actual["descriptive_directional_return_stats"]["1"]["mfe"]["mean"] = 2
    elif "MAE" in case.mutation:
        actual["descriptive_directional_return_stats"]["1"]["mae"]["mean"] = -2
    elif "sign" in case.mutation:
        actual["descriptive_directional_return_stats"]["1"]["positive"] = 0
    else:
        actual["descriptive_directional_return_stats"]["1"]["mean"] = 2
    failures = summary_failures(expected, actual)
    return Execution(_first_failure(failures, _expected(case)), True, expected, actual, {"summary": actual, "control": case.control_id})


def _exec_overlap(case: ControlCase) -> Execution:
    expected = {"horizons": {"1": {"complete_interval_set_hash": "a", "overlapping_pair_count": 1, "max_simultaneous_candidates": 2, "direction_counts": {"BUY_CALL": 1}, "complete_session_cluster_counts": {"2026-07-06": 1}, "sample_count": 1, "sample_truncated": False, "sample": [{"candidate_id": "a"}]}}}
    actual = {"horizons": {"1": dict(expected["horizons"]["1"])}}
    if "interval" in case.mutation:
        actual["horizons"]["1"]["complete_interval_set_hash"] = "b"
    elif "pair" in case.mutation:
        actual["horizons"]["1"]["overlapping_pair_count"] = 0
    elif "concurrency" in case.mutation:
        actual["horizons"]["1"]["max_simultaneous_candidates"] = 1
    elif "direction" in case.mutation:
        actual["horizons"]["1"]["direction_counts"] = {}
    elif "session" in case.mutation:
        actual["horizons"]["1"]["complete_session_cluster_counts"] = {}
    else:
        actual["horizons"]["1"]["sample_count"] = 0
    failures = overlap_failures(expected, actual)
    return Execution(_first_failure(failures, _expected(case)), True, expected, actual, {"overlap": actual, "control": case.control_id})


def _exec_ast(case: ControlCase) -> Execution:
    sources = {
        "AST_FORBIDDEN_IMPORT_FROM": "from research.opening_range_retest_outcomes_v2.engine import measure_candidate\n",
        "AST_FORBIDDEN_MODULE_CALL": "import research.opening_range_retest_outcomes_v2.engine as engine\nengine.measure_candidate()\n",
        "AST_FORBIDDEN_ALIASED_IMPORT": "from research.opening_range_retest_outcomes_v2.overlap import build_overlap as bo\n",
    }
    source = sources.get(case.control_id, "")
    failures = oracle_independence_failures(source)
    return Execution(_first_failure(failures, _expected(case)), True, {"source": ""}, {"source": source}, {"ast": source})


EXECUTORS: dict[str, Callable[[ControlCase], Execution]] = {
    "_exec_contract_payload": _exec_contract_payload,
    "_exec_lineage_snapshot": _exec_lineage_snapshot,
    "_exec_input_bundle": _exec_input_bundle,
    "_exec_source_path": _exec_source_path,
    "_exec_join": _exec_join,
    "_exec_frame": _exec_frame,
    "_exec_measure": _exec_measure,
    "_exec_math_record": _exec_math_record,
    "_exec_conservation": _exec_conservation,
    "_exec_summary": _exec_summary,
    "_exec_overlap": _exec_overlap,
    "_exec_ast": _exec_ast,
}


def _case(control_id: str, category: str, mutation: str, expected_failure: str, target: str, executor: str) -> ControlCase:
    return ControlCase(control_id, category, mutation, expected_failure, target, executor)


CONTROL_CASES: tuple[ControlCase, ...] = (
    _case("LINEAGE_CONTRACT_SELF_HASH", "lineage_hash", "mutate portable contract horizons while retaining stale self hash", "CONTRACT_SELF_HASH_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_SOURCE_HASH", "lineage_hash", "contract source input hash mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_CANDIDATE_CORE_HASH", "lineage_hash", "contract candidate core input hash mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_CANDIDATE_PROVENANCE_HASH", "lineage_hash", "contract candidate provenance input hash mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_SOURCE_COUNT", "lineage_hash", "contract source count mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_CANDIDATE_COUNT", "lineage_hash", "contract candidate count mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_HORIZON_RULE", "lineage_hash", "horizon rule mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_IMPLEMENTATION_ALGORITHM", "lineage_hash", "implementation tree algorithm mutation", "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_payload", "_exec_contract_payload"),
    _case("LINEAGE_FROZEN_NON_ANCESTOR", "lineage_hash", "frozen SHA mutation to non ancestor", "FROZEN_CODE_SHA_NOT_ANCESTOR", "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot"),
    _case("LINEAGE_IMPLEMENTATION_TREE", "lineage_hash", "implementation-tree hash mutation", "IMPLEMENTATION_TREE_HASH_MISMATCH", "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot"),
    _case("LINEAGE_POST_FREEZE_PATH", "lineage_hash", "executable post-freeze path mutation", "POST_FREEZE_UNEXPECTED_PATH", "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot"),
    _case("LINEAGE_TEST_POST_FREEZE_PATH", "lineage_hash", "test post-freeze path mutation", "POST_FREEZE_UNEXPECTED_PATH", "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot"),
    _case("LINEAGE_UNEXPECTED_PATH", "lineage_hash", "unexpected post-freeze path mutation", "POST_FREEZE_UNEXPECTED_PATH", "oracle.verify_lineage_snapshot", "_exec_lineage_snapshot"),
    *[_case(f"INPUT_SIDECAR_{name.upper()}", "input_certification", f"{name} input sidecar mismatch", f"INPUT_SIDECAR_MISMATCH:{name}", "oracle.verify_input_bundle", "_exec_input_bundle") for name in INPUT_FILES],
    _case("INPUT_SOURCE_MANIFEST_HASH", "input_certification", "source manifest semantic hash mutation", "INPUT_SOURCE_MANIFEST_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_SOURCE_MANIFEST_COUNT", "input_certification", "source manifest count mutation", "INPUT_SOURCE_MANIFEST_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_CANDIDATE_LEDGER_CORE_HASH", "input_certification", "candidate core hash mutation", "INPUT_CANDIDATE_LEDGER_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH", "input_certification", "candidate provenance hash mutation", "INPUT_CANDIDATE_LEDGER_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_CANDIDATE_LEDGER_COUNT", "input_certification", "candidate ledger count mutation", "INPUT_CANDIDATE_LEDGER_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_SUMMARY_VERDICT", "input_certification", "Phase 1 summary verdict mutation", "INPUT_SUMMARY_VERDICT_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_RECONCILIATION_VERDICT", "input_certification", "reconciliation verdict mutation", "INPUT_RECONCILIATION_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_RECONCILIATION_V1_COUNT", "input_certification", "v1 unaffected count mutation", "INPUT_RECONCILIATION_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_RECONCILIATION_V2_COUNT", "input_certification", "v2 unaffected count mutation", "INPUT_RECONCILIATION_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("INPUT_DECEPTIVE_CERTIFICATION", "input_certification", "deceptive NOT_ORB_PHASE1_V2_RECERTIFIED certification text", "INPUT_CERTIFICATION_MISMATCH", "oracle.verify_input_bundle", "_exec_input_bundle"),
    _case("SOURCE_RECORD_MISSING_FROM_MANIFEST_JOIN", "source_join", "source record missing from manifest join", "SOURCE_PROVENANCE_MISMATCH", "oracle.join_failure", "_exec_source_path"),
    _case("SOURCE_MISSING_FILE", "source_join", "physical source file missing", "SOURCE_MISSING_OR_SYMLINK", "oracle.source_path", "_exec_source_path"),
    _case("SOURCE_SHA_MISMATCH", "source_join", "source SHA mismatch", "SOURCE_BYTE_IDENTITY_MISMATCH", "oracle.source_path", "_exec_source_path"),
    _case("SOURCE_BYTE_SIZE_MISMATCH", "source_join", "source byte-size mismatch", "SOURCE_BYTE_IDENTITY_MISMATCH", "oracle.source_path", "_exec_source_path"),
    _case("SOURCE_SYMLINK_FILE", "source_join", "symlink file rejected", "SOURCE_MISSING_OR_SYMLINK", "oracle.source_path", "_exec_source_path"),
    _case("SOURCE_SYMLINK_ANCESTOR", "source_join", "symlink ancestor rejected", "SOURCE_MISSING_OR_SYMLINK", "oracle.source_path", "_exec_source_path"),
    _case("SOURCE_ABSOLUTE_PATH", "source_join", "absolute path rejected", "SOURCE_PATH_TRAVERSAL", "oracle.source_path", "_exec_source_path"),
    _case("SOURCE_TRAVERSAL_PATH", "source_join", "traversal path rejected", "SOURCE_PATH_TRAVERSAL", "oracle.source_path", "_exec_source_path"),
    *[_case(f"JOIN_{i:02d}", "source_join", name, "SOURCE_PROVENANCE_MISMATCH", "oracle.join_failure", "_exec_join") for i, name in enumerate(["record id mismatch", "path mismatch", "sha mismatch", "manifest hash mismatch", "manifest version mismatch", "provenance symbol mismatch", "provenance session mismatch", "core symbol mismatch", "core session mismatch"], 1)],
    *[_case(f"SOURCE_FRAME_{i:02d}", "source_join", name, failure, "engine.validate_frame", "_exec_frame") for i, (name, failure) in enumerate([("schema order mismatch", "SOURCE_SCHEMA_MISMATCH"), ("schema missing column", "SOURCE_SCHEMA_MISMATCH"), ("symbol mismatch", "SOURCE_SYMBOL_MISMATCH"), ("non-positive price", "SOURCE_OHLC_INVALID"), ("nan price", "SOURCE_OHLC_INVALID"), ("inf price", "SOURCE_OHLC_INVALID"), ("bounds violation", "SOURCE_OHLC_BOUNDS_INVALID")], 1)],
    _case("SOURCE_VALIDATION_PREVENTS_MEASURED", "source_join", "source validation prevents measured outcomes", "SOURCE_VALIDATION_FAILED", "engine.measure_candidate", "_exec_measure"),
    *[_case(f"TEMPORAL_{i:02d}", "temporal_horizon", name, failure, "engine.measure_candidate", "_exec_measure") for i, (name, failure) in enumerate([("malformed readiness timestamp", "CANDIDATE_TIMESTAMP_MALFORMED"), ("outside session readiness", "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION"), ("off-grid seconds readiness", "CANDIDATE_READY_OFF_GRID"), ("off-grid microseconds readiness", "CANDIDATE_READY_OFF_GRID"), ("missing completed bar before readiness", "CANDIDATE_READY_BAR_MISSING"), ("no later entry after readiness", "NO_LEGAL_ENTRY_BAR"), ("missing horizon minute exact lookup", "MISSING_EXPECTED_MINUTE")], 1)],
    *[_case(f"TEMPORAL_FRAME_{i:02d}", "temporal_horizon", name, failure, "engine.validate_frame", "_exec_frame") for i, (name, failure) in enumerate([("duplicate timestamps", "SOURCE_TIMESTAMP_GAP"), ("non-monotonic timestamps", "SOURCE_TIMESTAMP_GAP"), ("missing timestamp row", "SOURCE_TIMESTAMP_GAP"), ("irregular timestamp cadence", "SOURCE_TIMESTAMP_GAP"), ("wrong first session bound", "SOURCE_TIMESTAMP_GAP"), ("wrong last session bound", "SOURCE_TIMESTAMP_GAP"), ("wrong date session mismatch", "SOURCE_SESSION_MISMATCH")], 1)],
    _case("TEMPORAL_HORIZON_CONSERVATION", "temporal_horizon", "remove one horizon record from valid fixture", "CANDIDATE_OR_HORIZON_CONSERVATION_FAIL", "oracle.ledger_conservation_failures", "_exec_conservation"),
    _case("TEMPORAL_ALL_HORIZONS_EXACT", "temporal_horizon", "missing horizon minute exact lookup across terminal rules", "MISSING_EXPECTED_MINUTE", "engine.measure_candidate", "_exec_measure"),
    _case("MATH_ENTRY_PRICE", "math_identity", "wrong legal entry price", "ENTRY_PRICE_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_TERMINAL_CLOSE", "math_identity", "wrong terminal close", "TERMINAL_CLOSE_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_DIRECTIONAL_RETURN", "math_identity", "wrong directional return", "DIRECTIONAL_RETURN_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_MFE", "math_identity", "wrong MFE", "MFE_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_MAE", "math_identity", "wrong MAE", "MAE_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_EXTREMA_TIMESTAMP", "math_identity", "wrong extrema timestamp", "EXTREMA_TIMESTAMP_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_MEASURED_COUNT", "math_identity", "measured horizon count mutation", "MEASURED_HORIZON_COUNT_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_OUTCOME_ID", "math_identity", "outcome ID mutation", "OUTCOME_ID_MISMATCH", "oracle.ledger_record_failures", "_exec_math_record"),
    _case("MATH_DUPLICATE_CANDIDATE_ID", "math_identity", "duplicate candidate ID aggregation", "DUPLICATE_CANDIDATE_ID", "oracle.ledger_conservation_failures", "_exec_conservation"),
    _case("MATH_UNSUPPORTED_DIRECTION", "math_identity", "unsupported direction", "CANDIDATE_DIRECTION_UNSUPPORTED", "engine.measure_candidate", "_exec_measure"),
    _case("MATH_BUY_CALL_SIGN", "math_identity", "BUY_CALL sign-count drift", "SUMMARY_SIGN_COUNT_MISMATCH", "oracle.summary_failures", "_exec_summary"),
    _case("MATH_BUY_PUT_SIGN", "math_identity", "BUY_PUT sign-count drift", "SUMMARY_SIGN_COUNT_MISMATCH", "oracle.summary_failures", "_exec_summary"),
    *[_case(f"SUMMARY_OVERLAP_{i:02d}", "summary_overlap", name, failure, "oracle.summary_failures/overlap_failures", executor) for i, (name, failure, executor) in enumerate([("status count drift", "SUMMARY_STATUS_COUNT_MISMATCH", "_exec_summary"), ("summary hash drift", "SUMMARY_HASH_MISMATCH", "_exec_summary"), ("mean drift", "SUMMARY_MEAN_MISMATCH", "_exec_summary"), ("median drift", "SUMMARY_MEDIAN_MISMATCH", "_exec_summary"), ("quantile drift", "SUMMARY_QUANTILE_MISMATCH", "_exec_summary"), ("sign-count drift", "SUMMARY_SIGN_COUNT_MISMATCH", "_exec_summary"), ("MFE drift", "SUMMARY_MFE_MISMATCH", "_exec_summary"), ("MAE drift", "SUMMARY_MAE_MISMATCH", "_exec_summary"), ("interval-set hash drift", "OVERLAP_INTERVAL_SET_HASH_MISMATCH", "_exec_overlap"), ("pair count drift", "OVERLAP_PAIR_COUNT_MISMATCH", "_exec_overlap"), ("max concurrency drift", "OVERLAP_MAX_CONCURRENCY_MISMATCH", "_exec_overlap"), ("direction count drift", "OVERLAP_DIRECTION_COUNT_MISMATCH", "_exec_overlap"), ("session count drift", "OVERLAP_SESSION_COUNT_MISMATCH", "_exec_overlap"), ("truncated sample falsely complete", "OVERLAP_SAMPLE_CONTRACT_MISMATCH", "_exec_overlap")], 1)],
    _case("AST_FORBIDDEN_IMPORT_FROM", "summary_overlap", "synthetic forbidden ImportFrom", "ORACLE_FORBIDDEN_IMPORT", "oracle.oracle_independence_failures", "_exec_ast"),
    _case("AST_FORBIDDEN_MODULE_CALL", "summary_overlap", "synthetic forbidden module-qualified call", "ORACLE_FORBIDDEN_IMPORT", "oracle.oracle_independence_failures", "_exec_ast"),
    _case("AST_FORBIDDEN_ALIASED_IMPORT", "summary_overlap", "synthetic aliased forbidden import", "ORACLE_FORBIDDEN_IMPORT", "oracle.oracle_independence_failures", "_exec_ast"),
)


def executor_expected_result_leaks(path: Path | None = None) -> list[str]:
    source = (path or Path(__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_exec_"):
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and child.attr == "expected_failure":
                    leaks.append(f"{node.name}:{child.lineno}")
    return leaks


def execute_control_case(case: ControlCase) -> ControlResult:
    try:
        execution = EXECUTORS[case.executor_function](case)
        observed = execution.observed_failure
        error = None
        before_hash = _digest(execution.fixture_before)
        after_hash = _digest(execution.fixture_after)
        mutation_applied = before_hash != after_hash
        fingerprint = _digest(
            {
                "control_id": case.control_id,
                "target": case.target_function,
                "executor": case.executor_function,
                "mutation": execution.mutation_fingerprint,
            }
        )
    except Exception:
        observed = "UNEXPECTED_EXCEPTION"
        error = traceback.format_exc()
        before_hash = "ERROR"
        after_hash = "ERROR"
        mutation_applied = False
        fingerprint = _digest({"control_id": case.control_id, "error": error})
        execution = Execution(observed, False, {}, {}, {})
    status = "PASS" if observed == case.expected_failure and execution.target_invoked and mutation_applied else "FAIL"
    return ControlResult(case, observed, execution.target_invoked, before_hash, after_hash, mutation_applied, fingerprint, status, error)


def validate_control_report(report: dict[str, Any], *, frozen_code_sha: str | None = None, implementation_tree_hash: str | None = None, test_file_hashes: dict[str, str] | None = None) -> list[str]:
    failures: list[str] = []
    controls = report.get("controls", [])
    ids = [item.get("control_id") for item in controls]
    nodes = [item.get("test_node_id") for item in controls]
    if report.get("verdict") != "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED":
        failures.append("NEGATIVE_CONTROL_VERDICT_MISMATCH")
    if report.get("collected", 0) < 75 or report.get("executed") != report.get("collected") or report.get("passed") != report.get("executed"):
        failures.append("NEGATIVE_CONTROL_EXECUTION_COUNTS_MISMATCH")
    if report.get("skipped") or report.get("xfailed") or report.get("xpassed") or report.get("failed"):
        failures.append("NEGATIVE_CONTROL_NON_PASSING_RESULT")
    if len(ids) != len(set(ids)) or len(nodes) != len(set(nodes)):
        failures.append("NEGATIVE_CONTROL_DUPLICATE_ID")
    if any(not str(node).startswith(f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[") for node in nodes):
        failures.append("NEGATIVE_CONTROL_NODE_ID_MISMATCH")
    if report.get("expected_result_leak_count") != 0:
        failures.append("CONTROL_EXECUTOR_EXPECTED_RESULT_LEAK")
    if report.get("non_invoked_target_count") != 0:
        failures.append("NEGATIVE_CONTROL_TARGET_NOT_INVOKED")
    if report.get("non_mutating_control_count") != 0:
        failures.append("NEGATIVE_CONTROL_MUTATION_NOT_APPLIED")
    if report.get("duplicate_control_fingerprint_count") != 0:
        failures.append("NEGATIVE_CONTROL_DUPLICATE_FINGERPRINT")
    if report.get("unique_control_fingerprint_count") != len(controls):
        failures.append("NEGATIVE_CONTROL_FINGERPRINT_COUNT_MISMATCH")
    if frozen_code_sha and report.get("frozen_code_sha") != frozen_code_sha:
        failures.append("NEGATIVE_CONTROL_FROZEN_SHA_MISMATCH")
    if implementation_tree_hash and report.get("implementation_tree_hash") != implementation_tree_hash:
        failures.append("NEGATIVE_CONTROL_IMPLEMENTATION_TREE_MISMATCH")
    if test_file_hashes and report.get("control_test_file_hashes") != test_file_hashes:
        failures.append("NEGATIVE_CONTROL_TEST_FILE_HASH_MISMATCH")
    return list(dict.fromkeys(failures))


def build_negative_control_report(*, frozen_code_sha: str | None = None, implementation_tree_hash: str | None = None, pytest_version: str | None = None, pytest_command: str | None = None, test_file_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    results = [execute_control_case(case) for case in CONTROL_CASES]
    controls = [result.as_dict() for result in results]
    category_counts = Counter(result.case.category for result in results)
    failed = [result for result in results if result.status != "PASS"]
    fingerprints = [result.control_fingerprint for result in results]
    leaks = executor_expected_result_leaks()
    report = {
        "schema_version": 3,
        **evidence_fields(
            mode="ORB_OUTCOME_NEGATIVE_CONTROLS_V2",
            decision="ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED",
            reason="executable negative-control results captured from concrete offline mutations",
            source=CONTROL_TEST_FILE,
        ),
        "frozen_code_sha": frozen_code_sha,
        "implementation_tree_hash": implementation_tree_hash,
        "pytest_command": pytest_command or f"python -m pytest -q {CONTROL_TEST_FILE}",
        "pytest_version": pytest_version,
        "control_test_file_hashes": test_file_hashes or {},
        "required": 75,
        "collected": len(CONTROL_CASES),
        "executed": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "control_count": len(results),
        "category_minimums": CATEGORY_MINIMUMS,
        "category_counts": dict(category_counts),
        "missing_ids": [],
        "duplicate_ids": len(results) - len({result.case.control_id for result in results}),
        "unexpected_ids": [],
        "unique_control_fingerprint_count": len(set(fingerprints)),
        "expected_result_leak_count": len(leaks),
        "expected_result_leaks": leaks,
        "non_invoked_target_count": sum(not result.target_invoked for result in results),
        "non_mutating_control_count": sum(not result.mutation_applied for result in results),
        "duplicate_control_fingerprint_count": len(fingerprints) - len(set(fingerprints)),
        "failed_controls": [result.as_dict() for result in failed],
        "controls": controls,
        **safety_fields(),
    }
    report["verdict"] = "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED"
    failures = validate_control_report(report)
    for category, minimum in CATEGORY_MINIMUMS.items():
        if category_counts[category] < minimum:
            failures.append(f"NEGATIVE_CONTROL_CATEGORY_UNDER_MINIMUM:{category}")
    report["failures"] = list(dict.fromkeys(failures))
    verdict = "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED" if not report["failures"] else "ORB_OUTCOME_NEGATIVE_CONTROLS_NOT_CERTIFIED"
    report["verdict"] = verdict
    report["decision"] = verdict
    report["report_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in report.items() if k != "report_hash"}))
    return report
