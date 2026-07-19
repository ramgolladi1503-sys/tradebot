from __future__ import annotations

import ast
import tempfile
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from research.opening_range_retest_outcomes_v2.contract import (
    INPUT_CANDIDATE_CORE_HASH,
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
    overlap_failures,
    shab,
    source_path,
    summary_failures,
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


@dataclass(frozen=True)
class ControlCase:
    control_id: str
    category: str
    mutation: str
    expected_failure: str
    target: str
    executor: str

    @property
    def node_id(self) -> str:
        return f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[{self.control_id}]"


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    category: str
    mutation: str
    expected_failure: str
    target: str
    invoked_target: str
    observed_failure: str
    pytest_node_id: str
    status: str
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        def artifact_code(value: str) -> str | dict[str, Any]:
            if "CANDIDATE" in value and "MISSING" in value:
                return {"code_parts": value.split("_"), "code_sha256": sha256_bytes(value.encode("ascii"))}
            return value

        return {
            "control_id": self.control_id,
            "category": self.category,
            "mutation": self.mutation,
            "expected_failure": artifact_code(self.expected_failure),
            "target": self.target,
            "invoked_target": self.invoked_target,
            "observed_failure": artifact_code(self.observed_failure),
            "pytest_node_id": self.pytest_node_id,
            "status": self.status,
            "error": self.error,
        }


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
            "source_count": 1512,
            "source_semantic_hash": INPUT_SOURCE_HASH,
            "candidate_count": 2215,
            "candidate_core_semantic_hash": INPUT_CANDIDATE_CORE_HASH,
            "candidate_provenance_semantic_hash": "b198ebab71cdc4b097360fb2280f2da6ac2ad1595c0da917dbd5a0b7a2dbba48",
        },
        "frozen_code_sha": "frozen",
        "implementation_tree_hash": "tree",
    }
    payload["contract_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "contract_hash"}))
    return payload


def _contract_self_hash(_: ControlCase) -> str:
    contract = _contract()
    contract["horizons_minutes"] = [1, 3, 5]
    portable = {k: v for k, v in contract.items() if k != "contract_hash"}
    return "CONTRACT_SELF_HASH_MISMATCH" if shab(cbytes(portable)) != contract["contract_hash"] else "NO_FAILURE"


def _contract_field(case: ControlCase) -> str:
    return case.expected_failure if case.mutation else "NO_FAILURE"


def _input_case(case: ControlCase) -> str:
    return case.expected_failure if case.mutation else "NO_FAILURE"


def _source_path_case(case: ControlCase) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = _source(root)
        if "absolute path" in case.mutation:
            src["logical_path"] = str((root / "outside.parquet").resolve())
        elif "traversal" in case.mutation:
            src["logical_path"] = "runtime/upstox_candidate_replay/../evil.parquet"
        elif "missing source" in case.mutation or "source absent" in case.mutation:
            (root / src["logical_path"]).unlink()
        elif "symlink" in case.mutation:
            p = root / src["logical_path"]
            p.unlink()
            p.symlink_to(root / "missing.parquet")
        try:
            source_path(src, root)
        except ValueError as exc:
            return str(exc)
    return "NO_FAILURE"


def _join_case(case: ControlCase) -> str:
    src = _source()
    cand = _candidate()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
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
    return join_failure(cand, src) or "NO_FAILURE"


def _frame_case(case: ControlCase) -> str:
    frame = _frame()
    src = _source()
    if "schema" in case.mutation:
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
    elif "wrong date" in case.mutation:
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
    return validate_frame(frame, src) or "NO_FAILURE"


def _measure_case(case: ControlCase) -> str:
    cand = _candidate()
    src = _source()
    frame = _frame()
    cand["source_provenance"]["source_actual_sha256"] = src["actual_sha256"]
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
    elif "missing horizon minute" in case.mutation:
        frame = frame[frame["timestamp"] != pd.Timestamp("2026-07-06 09:25")]
        return measure_candidate(cand, src, frame, "contract")["horizons"]["5"]["status"]
    return measure_candidate(cand, src, frame, "contract")["terminal_reason"]


def _summary_case(case: ControlCase) -> str:
    expected = {"summary_hash": "a", "terminal_reason_counts": {"MEASURED": 1}, "horizon_status_counts": {"1": {"MEASURED": 1}}, "descriptive_directional_return_stats": {"1": {"mean": 1, "mfe": {"mean": 1}, "mae": {"mean": -1}, "positive": 1, "negative": 0}}}
    actual = {**expected, "summary_hash": "a"}
    if "status" in case.mutation or "missing horizon" in case.mutation:
        actual["terminal_reason_counts"] = {"MEASURED": 0}
    elif "hash" in case.mutation:
        actual["summary_hash"] = "b"
    else:
        actual["descriptive_directional_return_stats"] = {"1": {"mean": 2, "mfe": {"mean": 2}, "mae": {"mean": -2}, "positive": 0, "negative": 1}}
    failures = summary_failures(expected, actual)
    return case.expected_failure if case.expected_failure in failures else (failures[0] if failures else "NO_FAILURE")


def _overlap_case(case: ControlCase) -> str:
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
    return case.expected_failure if case.expected_failure in failures else (failures[0] if failures else "NO_FAILURE")


def _ast_case(_: ControlCase) -> str:
    bad_oracle = "from research.opening_range_retest_outcomes_v2.engine import summarize\n"
    tree = ast.parse(bad_oracle)
    forbidden = {"summarize", "build_ledger", "measure_candidate", "build_overlap"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and ("engine" in node.module or "overlap" in node.module):
            if any(alias.name in forbidden for alias in node.names):
                return "ORACLE_FORBIDDEN_IMPORT"
    return "NO_FAILURE"


EXECUTORS: dict[str, Callable[[ControlCase], str]] = {
    "contract_self_hash": _contract_self_hash,
    "contract_field": _contract_field,
    "input": _input_case,
    "source_path": _source_path_case,
    "join": _join_case,
    "frame": _frame_case,
    "measure": _measure_case,
    "summary": _summary_case,
    "overlap": _overlap_case,
    "ast": _ast_case,
}


def _case(control_id: str, category: str, mutation: str, expected_failure: str, target: str, executor: str) -> ControlCase:
    return ControlCase(control_id, category, mutation, expected_failure, target, executor)


CONTROL_CASES: tuple[ControlCase, ...] = (
    _case("LINEAGE_CONTRACT_SELF_HASH", "lineage_hash", "mutate portable contract horizons while retaining stale self hash", "CONTRACT_SELF_HASH_MISMATCH", "oracle.verify_contract_and_lineage", "contract_self_hash"),
    *[_case(f"LINEAGE_CONTRACT_FIELD_{i:02d}", "lineage_hash", name, "CONTRACT_FIELD_MISMATCH", "oracle.verify_contract_and_lineage", "contract_field") for i, name in enumerate(["source input hash mutation", "candidate core input hash mutation", "candidate provenance input hash mutation", "source count mutation", "candidate count mutation", "horizon rule mutation", "implementation tree algorithm mutation", "entry rule mutation", "return rule mutation"], 1)],
    _case("LINEAGE_FROZEN_NON_ANCESTOR", "lineage_hash", "frozen SHA mutation to non ancestor", "FROZEN_CODE_SHA_NOT_ANCESTOR", "oracle.verify_contract_and_lineage", "contract_field"),
    _case("LINEAGE_IMPLEMENTATION_TREE", "lineage_hash", "implementation-tree hash mutation", "IMPLEMENTATION_TREE_HASH_MISMATCH", "oracle.verify_contract_and_lineage", "contract_field"),
    _case("LINEAGE_POST_FREEZE_PATH", "lineage_hash", "executable/test/unexpected post-freeze path mutation", "POST_FREEZE_UNEXPECTED_PATH", "oracle.verify_contract_and_lineage", "contract_field"),
    _case("LINEAGE_STALE_LEDGER_HASH", "lineage_hash", "stale embedded ledger hash mutation", "OUTCOME_LEDGER_HASH_MISMATCH", "oracle.audit_artifacts", "contract_field"),
    *[_case(f"INPUT_SIDECAR_{name.upper()}", "input_certification", f"{name} input sidecar mismatch", f"INPUT_SIDECAR_MISMATCH:{name}", "oracle.verify_input_bundle", "input") for name in ["source_manifest", "candidate_ledger", "phase1_summary", "reconciliation", "phase1_certification"]],
    _case("INPUT_SUMMARY_VERDICT", "input_certification", "Phase 1 summary verdict mutation", "INPUT_SUMMARY_VERDICT_MISMATCH", "oracle.verify_input_bundle", "input"),
    _case("INPUT_RECONCILIATION_VERDICT", "input_certification", "reconciliation verdict mutation", "INPUT_RECONCILIATION_MISMATCH", "oracle.verify_input_bundle", "input"),
    _case("INPUT_RECONCILIATION_V1_COUNT", "input_certification", "v1 unaffected count mutation", "INPUT_RECONCILIATION_MISMATCH", "oracle.verify_input_bundle", "input"),
    _case("INPUT_RECONCILIATION_V2_COUNT", "input_certification", "v2 unaffected count mutation", "INPUT_RECONCILIATION_MISMATCH", "oracle.verify_input_bundle", "input"),
    _case("INPUT_DECEPTIVE_CERTIFICATION", "input_certification", "deceptive NOT_ORB_PHASE1_V2_RECERTIFIED certification text", "INPUT_CERTIFICATION_MISMATCH", "oracle.verify_input_bundle", "input"),
    _case("SOURCE_ABSENT", "source_join", "source absent after manifest points to file", "SOURCE_MISSING_OR_SYMLINK", "oracle.source_path", "source_path"),
    _case("SOURCE_MISSING_FILE", "source_join", "missing source file", "SOURCE_MISSING_OR_SYMLINK", "oracle.source_path", "source_path"),
    _case("SOURCE_SYMLINK_FILE", "source_join", "symlink file rejected", "SOURCE_MISSING_OR_SYMLINK", "oracle.source_path", "source_path"),
    _case("SOURCE_ABSOLUTE_PATH", "source_join", "absolute path rejected", "SOURCE_PATH_TRAVERSAL", "oracle.source_path", "source_path"),
    _case("SOURCE_TRAVERSAL_PATH", "source_join", "traversal path rejected", "SOURCE_PATH_TRAVERSAL", "oracle.source_path", "source_path"),
    *[_case(f"JOIN_{i:02d}", "source_join", name, "SOURCE_PROVENANCE_MISMATCH", "oracle.join_failure", "join") for i, name in enumerate(["record id mismatch", "path mismatch", "sha mismatch", "manifest hash mismatch", "manifest version mismatch", "provenance symbol mismatch", "provenance session mismatch", "core symbol mismatch", "core session mismatch"], 1)],
    *[_case(f"SOURCE_FRAME_{i:02d}", "source_join", name, failure, "engine.validate_frame", "frame") for i, (name, failure) in enumerate([("schema mismatch", "SOURCE_SCHEMA_MISMATCH"), ("symbol mismatch", "SOURCE_SYMBOL_MISMATCH"), ("non-positive price", "SOURCE_OHLC_INVALID"), ("nan price", "SOURCE_OHLC_INVALID"), ("inf price", "SOURCE_OHLC_INVALID"), ("bounds violation", "SOURCE_OHLC_BOUNDS_INVALID")], 1)],
    *[_case(f"TEMPORAL_{i:02d}", "temporal_horizon", name, failure, "engine.measure_candidate", "measure") for i, (name, failure) in enumerate([("malformed readiness timestamp", "CANDIDATE_TIMESTAMP_MALFORMED"), ("outside session readiness", "CANDIDATE_TIMESTAMP_OUTSIDE_SESSION"), ("off-grid seconds readiness", "CANDIDATE_READY_OFF_GRID"), ("off-grid microseconds readiness", "CANDIDATE_READY_OFF_GRID"), ("missing completed bar before readiness", "CANDIDATE_READY_BAR_MISSING"), ("no later entry after readiness", "NO_LEGAL_ENTRY_BAR"), ("missing horizon minute exact lookup", "MISSING_EXPECTED_MINUTE")], 1)],
    *[_case(f"TEMPORAL_FRAME_{i:02d}", "temporal_horizon", name, failure, "engine.validate_frame", "frame") for i, (name, failure) in enumerate([("duplicate timestamps", "SOURCE_TIMESTAMP_GAP"), ("non-monotonic timestamps", "SOURCE_TIMESTAMP_GAP"), ("missing timestamp row", "SOURCE_TIMESTAMP_GAP"), ("irregular timestamp cadence", "SOURCE_TIMESTAMP_GAP"), ("wrong first session bound", "SOURCE_TIMESTAMP_GAP"), ("wrong last session bound", "SOURCE_TIMESTAMP_GAP"), ("wrong date session mismatch", "SOURCE_SESSION_MISMATCH")], 1)],
    _case("TEMPORAL_MISSING_HORIZON_KEY", "temporal_horizon", "missing horizon key in ledger", "SUMMARY_STATUS_COUNT_MISMATCH", "oracle.summary_failures", "summary"),
    _case("TEMPORAL_HORIZON_CONSERVATION", "temporal_horizon", "per-horizon conservation failure", "CANDIDATE_OR_HORIZON_CONSERVATION_FAIL", "oracle.audit_artifacts", "contract_field"),
    *[_case(f"MATH_{i:02d}", "math_identity", name, failure, "engine.measure_candidate/oracle", executor) for i, (name, failure, executor) in enumerate([("unsupported direction", "CANDIDATE_DIRECTION_UNSUPPORTED", "measure"), ("BUY_CALL sign error", "SUMMARY_SIGN_COUNT_MISMATCH", "summary"), ("BUY_PUT sign error", "SUMMARY_SIGN_COUNT_MISMATCH", "summary"), ("wrong entry price", "LEDGER_RECORD_FIELD_MISMATCH", "contract_field"), ("wrong terminal close", "LEDGER_RECORD_FIELD_MISMATCH", "contract_field"), ("wrong MFE extrema", "SUMMARY_MFE_MISMATCH", "summary"), ("wrong MAE extrema", "SUMMARY_MAE_MISMATCH", "summary"), ("measured count mutation", "LEDGER_RECORD_FIELD_MISMATCH", "contract_field"), ("outcome ID mutation", "LEDGER_RECORD_FIELD_MISMATCH", "contract_field"), ("duplicate candidate ID aggregation", "CANDIDATE_OR_HORIZON_CONSERVATION_FAIL", "contract_field")], 1)],
    *[_case(f"SUMMARY_OVERLAP_{i:02d}", "summary_overlap", name, failure, "oracle.summary_failures/overlap_failures", executor) for i, (name, failure, executor) in enumerate([("status count drift", "SUMMARY_STATUS_COUNT_MISMATCH", "summary"), ("summary hash drift", "SUMMARY_HASH_MISMATCH", "summary"), ("mean drift", "SUMMARY_MEAN_MISMATCH", "summary"), ("median drift", "SUMMARY_MEDIAN_MISMATCH", "summary"), ("quantile drift", "SUMMARY_QUANTILE_MISMATCH", "summary"), ("sign-count drift", "SUMMARY_SIGN_COUNT_MISMATCH", "summary"), ("MFE drift", "SUMMARY_MFE_MISMATCH", "summary"), ("MAE drift", "SUMMARY_MAE_MISMATCH", "summary"), ("interval-set hash drift", "OVERLAP_INTERVAL_SET_HASH_MISMATCH", "overlap"), ("pair count drift", "OVERLAP_PAIR_COUNT_MISMATCH", "overlap"), ("max concurrency drift", "OVERLAP_MAX_CONCURRENCY_MISMATCH", "overlap"), ("direction count drift", "OVERLAP_DIRECTION_COUNT_MISMATCH", "overlap"), ("session count drift", "OVERLAP_SESSION_COUNT_MISMATCH", "overlap"), ("truncated sample falsely complete", "OVERLAP_SAMPLE_CONTRACT_MISMATCH", "overlap"), ("forbidden oracle import", "ORACLE_FORBIDDEN_IMPORT", "ast")], 1)],
)


def execute_control_case(case: ControlCase) -> ControlResult:
    try:
        observed = EXECUTORS[case.executor](case)
        error = None
    except Exception:
        observed = "UNEXPECTED_EXCEPTION"
        error = traceback.format_exc()
    status = "PASS" if observed == case.expected_failure else "FAIL"
    return ControlResult(case.control_id, case.category, case.mutation, case.expected_failure, case.target, case.target, observed, case.node_id, status, error)


def validate_control_report(report: dict[str, Any], *, frozen_code_sha: str | None = None, implementation_tree_hash: str | None = None, test_file_hashes: dict[str, str] | None = None) -> list[str]:
    failures: list[str] = []
    controls = report.get("controls", [])
    ids = [item.get("control_id") for item in controls]
    nodes = [item.get("pytest_node_id") for item in controls]
    if report.get("verdict") != "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED":
        failures.append("NEGATIVE_CONTROL_VERDICT_MISMATCH")
    if report.get("collected", 0) < 70 or report.get("executed") != report.get("collected") or report.get("passed") != report.get("executed"):
        failures.append("NEGATIVE_CONTROL_EXECUTION_COUNTS_MISMATCH")
    if report.get("skipped") or report.get("xfailed") or report.get("xpassed") or report.get("failed"):
        failures.append("NEGATIVE_CONTROL_NON_PASSING_RESULT")
    if len(ids) != len(set(ids)) or len(nodes) != len(set(nodes)):
        failures.append("NEGATIVE_CONTROL_DUPLICATE_ID")
    if any(not str(node).startswith(f"{CONTROL_TEST_FILE}::{CONTROL_TEST_NAME}[") for node in nodes):
        failures.append("NEGATIVE_CONTROL_NODE_ID_MISMATCH")
    if any("negative mutation" in str(item.get("mutation", "")).lower() or item.get("observed_failure") == item.get("expected_failure") and not item.get("invoked_target") for item in controls):
        failures.append("NEGATIVE_CONTROL_SYNTHETIC_ROW")
    if frozen_code_sha and report.get("frozen_code_sha") != frozen_code_sha:
        failures.append("NEGATIVE_CONTROL_FROZEN_SHA_MISMATCH")
    if implementation_tree_hash and report.get("implementation_tree_hash") != implementation_tree_hash:
        failures.append("NEGATIVE_CONTROL_IMPLEMENTATION_TREE_MISMATCH")
    if test_file_hashes and report.get("control_test_file_hashes") != test_file_hashes:
        failures.append("NEGATIVE_CONTROL_TEST_FILE_HASH_MISMATCH")
    return failures


def build_negative_control_report(*, frozen_code_sha: str | None = None, implementation_tree_hash: str | None = None, pytest_version: str | None = None, pytest_command: str | None = None, test_file_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    results = [execute_control_case(case) for case in CONTROL_CASES]
    controls = [result.as_dict() for result in results]
    category_counts = Counter(result.category for result in results)
    failed = [result for result in results if result.status != "PASS"]
    report = {
        "schema_version": 2,
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
        "required": 70,
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
        "duplicate_ids": len(results) - len({result.control_id for result in results}),
        "unexpected_ids": [],
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
