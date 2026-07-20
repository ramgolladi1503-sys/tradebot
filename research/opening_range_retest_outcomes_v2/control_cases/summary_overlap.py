from __future__ import annotations

import ast
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from research.opening_range_retest_outcomes_v2.control_protocol import (
    ControlExpectation,
    MutationSpec,
    RawExecution,
)
from research.opening_range_retest_outcomes_v2.oracle import (
    oracle_independence_failures,
)


SUMMARY_CONTROL_CATEGORY = "summary_overlap"


@dataclass(frozen=True)
class SummaryOverlapControl:
    spec: MutationSpec
    expectation: ControlExpectation
    test_node_id: str


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def summary_fixture() -> dict[str, Any]:
    stats = {
        "count": 4,
        "mean": 0.125,
        "median": 0.075,
        "min": -0.05,
        "max": 0.4,
        "p05": -0.04,
        "p25": 0.0,
        "p75": 0.2,
        "p95": 0.37,
        "positive": 3,
        "zero": 0,
        "negative": 1,
        "mfe": {"count": 4, "mean": 0.25, "median": 0.2, "p05": 0.02, "p25": 0.1, "p75": 0.35, "p95": 0.47},
        "mae": {"count": 4, "mean": -0.08, "median": -0.06, "p05": -0.18, "p25": -0.1, "p75": -0.03, "p95": -0.01},
        "breakdowns": {
            "symbol": {"NIFTY": 3, "BANKNIFTY": 1},
            "direction": {"BUY_CALL": 3, "BUY_PUT": 1},
            "symbol_direction": {"NIFTY:BUY_CALL": 3, "BANKNIFTY:BUY_PUT": 1},
            "calendar_year": {"2026": 4},
        },
    }
    summary = {
        "summary_hash": "baseline-summary-hash",
        "terminal_reason_counts": {"MEASURED": 4},
        "horizon_status_counts": {"1": {"MEASURED": 4}},
        "descriptive_directional_return_stats": {"1": stats},
    }
    summary["summary_hash"] = canonical_hash({k: v for k, v in summary.items() if k != "summary_hash"})
    return summary


def overlap_fixture() -> dict[str, Any]:
    sample = [{"candidate_id": "a", "start": "2026-07-06T09:21:00+05:30", "end": "2026-07-06T09:22:00+05:30"}]
    return {
        "horizons": {
            "1": {
                "interval_count": 2,
                "complete_interval_count": 2,
                "complete_interval_set_hash": canonical_hash(sample),
                "overlapping_pair_count": 1,
                "max_simultaneous_candidates": 2,
                "symbol_counts": {"NIFTY": 2},
                "direction_counts": {"BUY_CALL": 1, "BUY_PUT": 1},
                "symbol_direction_counts": {"NIFTY:BUY_CALL": 1, "NIFTY:BUY_PUT": 1},
                "complete_session_cluster_counts": {"2026-07-06": 2},
                "session_cluster_counts": {"2026-07-06": 2},
                "sample_truncated": False,
                "sample_count": 1,
                "sample": sample,
                "overlap_evidence_intervals": sample,
            }
        }
    }


def _raw(observed: tuple[str, ...], target_invoked: bool, before: Any, after: Any) -> RawExecution:
    return RawExecution(
        observed_failures=observed,
        target_invoked=target_invoked,
        mutation_applied=canonical_hash(before) != canonical_hash(after),
        fixture_hash_before=canonical_hash(before),
        fixture_hash_after=canonical_hash(after),
        target_output_hash=canonical_hash(observed),
    )


def _mutate_path(payload: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor: dict[str, Any] = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def exact_summary_failures(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if expected.get("terminal_reason_counts") != actual.get("terminal_reason_counts"):
        failures.append("SUMMARY_STATUS_COUNT_MISMATCH")
    if expected.get("horizon_status_counts") != actual.get("horizon_status_counts"):
        failures.append("SUMMARY_STATUS_COUNT_MISMATCH")
    if expected.get("summary_hash") != actual.get("summary_hash"):
        failures.append("SUMMARY_HASH_MISMATCH")

    expected_stats = expected.get("descriptive_directional_return_stats", {})
    actual_stats = actual.get("descriptive_directional_return_stats", {})
    for horizon, stats in expected_stats.items():
        other = actual_stats.get(horizon, {})
        if stats.get("mean") != other.get("mean"):
            failures.append("SUMMARY_MEAN_MISMATCH")
        if stats.get("median") != other.get("median"):
            failures.append("SUMMARY_MEDIAN_MISMATCH")
        if any(stats.get(key) != other.get(key) for key in ("p05", "p25", "p75", "p95")):
            failures.append("SUMMARY_QUANTILE_MISMATCH")
        if any(stats.get(key) != other.get(key) for key in ("positive", "zero", "negative")):
            failures.append("SUMMARY_SIGN_COUNT_MISMATCH")
        if stats.get("mfe") != other.get("mfe"):
            failures.append("SUMMARY_MFE_MISMATCH")
        if stats.get("mae") != other.get("mae"):
            failures.append("SUMMARY_MAE_MISMATCH")
        if stats.get("breakdowns") != other.get("breakdowns"):
            failures.append("SUMMARY_BREAKDOWN_MISMATCH")
    if expected != actual and not failures:
        failures.append("SUMMARY_RECOMPUTE_MISMATCH")
    return list(dict.fromkeys(failures))


def exact_overlap_failures(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures: list[str] = []
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
        if item.get("sample_count") != other.get("sample_count"):
            failures.append("OVERLAP_SAMPLE_CONTRACT_MISMATCH")
        if item.get("sample_truncated") != other.get("sample_truncated"):
            failures.append("OVERLAP_SAMPLE_CONTRACT_MISMATCH")
        if item.get("sample") != other.get("sample"):
            failures.append("OVERLAP_SAMPLE_CONTRACT_MISMATCH")
    if expected != actual and not failures:
        failures.append("OVERLAP_RECOMPUTE_MISMATCH")
    return list(dict.fromkeys(failures))


def execute_summary_control(spec: MutationSpec) -> RawExecution:
    expected_summary = summary_fixture()
    actual_summary = deepcopy(expected_summary)
    payload = dict(spec.mutation_payload)
    path = tuple(str(part) for part in payload["path"])
    value = payload["value"]
    _mutate_path(actual_summary, path, value)
    return _raw(tuple(exact_summary_failures(expected_summary, actual_summary)), True, expected_summary, actual_summary)


def execute_overlap_control(spec: MutationSpec) -> RawExecution:
    expected_overlap = overlap_fixture()
    actual_overlap = deepcopy(expected_overlap)
    payload = dict(spec.mutation_payload)
    path = tuple(str(part) for part in payload["path"])
    value = payload["value"]
    _mutate_path(actual_overlap, path, value)
    return _raw(tuple(exact_overlap_failures(expected_overlap, actual_overlap)), True, expected_overlap, actual_overlap)


def execute_static_control(spec: MutationSpec) -> RawExecution:
    payload = dict(spec.mutation_payload)
    source = str(payload["source"])
    before = {"source": ""}
    after = {"source": source}
    return _raw(tuple(oracle_independence_failures(source)), True, before, after)


EXECUTORS: dict[str, Callable[[MutationSpec], RawExecution]] = {
    "control_cases.summary_overlap.exact_summary_failures": execute_summary_control,
    "control_cases.summary_overlap.exact_overlap_failures": execute_overlap_control,
    "oracle.oracle_independence_failures": execute_static_control,
}


def _control(
    control_id: str,
    *,
    mutation_kind: str,
    mutation_payload: dict[str, Any],
    target_function: str,
    expected_failures: tuple[str, ...],
) -> SummaryOverlapControl:
    spec = MutationSpec(
        control_id=control_id,
        category=SUMMARY_CONTROL_CATEGORY,
        mutation_kind=mutation_kind,
        mutation_payload=mutation_payload,
        target_function=target_function,
    )
    expectation = ControlExpectation(control_id=control_id, expected_failures=expected_failures)
    return SummaryOverlapControl(
        spec=spec,
        expectation=expectation,
        test_node_id=f"tests/orb_outcome_controls/test_summary_overlap_controls_v2.py::test_summary_overlap_control[{control_id}]",
    )


SUMMARY_CONTROLS: tuple[SummaryOverlapControl, ...] = (
    _control(
        "SUMMARY_STATUS_TERMINAL_REASON_COUNTS",
        mutation_kind="summary_field",
        mutation_payload={"path": ("terminal_reason_counts", "MEASURED"), "value": 3},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_STATUS_COUNT_MISMATCH",),
    ),
    _control(
        "SUMMARY_STATUS_HORIZON_COUNTS",
        mutation_kind="summary_field",
        mutation_payload={"path": ("horizon_status_counts", "1", "MEASURED"), "value": 3},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_STATUS_COUNT_MISMATCH",),
    ),
    _control(
        "SUMMARY_HASH",
        mutation_kind="summary_field",
        mutation_payload={"path": ("summary_hash",), "value": "mutated-summary-hash"},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_HASH_MISMATCH",),
    ),
    _control(
        "SUMMARY_MEAN",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "mean"), "value": 0.5},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_MEAN_MISMATCH",),
    ),
    _control(
        "SUMMARY_MEDIAN",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "median"), "value": 0.5},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_MEDIAN_MISMATCH",),
    ),
    _control(
        "SUMMARY_P05",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "p05"), "value": -0.5},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_QUANTILE_MISMATCH",),
    ),
    _control(
        "SUMMARY_P25",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "p25"), "value": -0.25},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_QUANTILE_MISMATCH",),
    ),
    _control(
        "SUMMARY_P75",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "p75"), "value": 0.75},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_QUANTILE_MISMATCH",),
    ),
    _control(
        "SUMMARY_P95",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "p95"), "value": 0.95},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_QUANTILE_MISMATCH",),
    ),
    _control(
        "SUMMARY_SIGN_POSITIVE",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "positive"), "value": 2},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_SIGN_COUNT_MISMATCH",),
    ),
    _control(
        "SUMMARY_SIGN_NEGATIVE",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "negative"), "value": 2},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_SIGN_COUNT_MISMATCH",),
    ),
    _control(
        "SUMMARY_MFE_MEAN",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "mfe", "mean"), "value": 0.9},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_MFE_MISMATCH",),
    ),
    _control(
        "SUMMARY_MAE_MEAN",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "mae", "mean"), "value": -0.9},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_MAE_MISMATCH",),
    ),
    _control(
        "SUMMARY_BREAKDOWN_DIRECTION",
        mutation_kind="summary_field",
        mutation_payload={"path": ("descriptive_directional_return_stats", "1", "breakdowns", "direction", "BUY_CALL"), "value": 2},
        target_function="control_cases.summary_overlap.exact_summary_failures",
        expected_failures=("SUMMARY_BREAKDOWN_MISMATCH",),
    ),
)

OVERLAP_CONTROLS: tuple[SummaryOverlapControl, ...] = (
    _control(
        "OVERLAP_INTERVAL_SET_HASH",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "complete_interval_set_hash"), "value": "mutated"},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_INTERVAL_SET_HASH_MISMATCH",),
    ),
    _control(
        "OVERLAP_PAIR_COUNT",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "overlapping_pair_count"), "value": 9},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_PAIR_COUNT_MISMATCH",),
    ),
    _control(
        "OVERLAP_MAX_CONCURRENCY",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "max_simultaneous_candidates"), "value": 9},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_MAX_CONCURRENCY_MISMATCH",),
    ),
    _control(
        "OVERLAP_DIRECTION_COUNTS",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "direction_counts", "BUY_CALL"), "value": 2},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_DIRECTION_COUNT_MISMATCH",),
    ),
    _control(
        "OVERLAP_SESSION_CLUSTER_COUNTS",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "complete_session_cluster_counts", "2026-07-06"), "value": 1},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_SESSION_COUNT_MISMATCH",),
    ),
    _control(
        "OVERLAP_SAMPLE_COUNT",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "sample_count"), "value": 0},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_SAMPLE_CONTRACT_MISMATCH",),
    ),
    _control(
        "OVERLAP_SAMPLE_TRUNCATED",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "sample_truncated"), "value": True},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_SAMPLE_CONTRACT_MISMATCH",),
    ),
    _control(
        "OVERLAP_SAMPLE_PAYLOAD",
        mutation_kind="overlap_field",
        mutation_payload={"path": ("horizons", "1", "sample"), "value": []},
        target_function="control_cases.summary_overlap.exact_overlap_failures",
        expected_failures=("OVERLAP_SAMPLE_CONTRACT_MISMATCH",),
    ),
)

STATIC_CONTROLS: tuple[SummaryOverlapControl, ...] = (
    _control(
        "STATIC_FORBIDDEN_ENGINE_IMPORT_FROM",
        mutation_kind="static_source",
        mutation_payload={"source": "from research.opening_range_retest_outcomes_v2.engine import measure_candidate\n"},
        target_function="oracle.oracle_independence_failures",
        expected_failures=("ORACLE_FORBIDDEN_IMPORT",),
    ),
    _control(
        "STATIC_FORBIDDEN_OVERLAP_IMPORT_FROM",
        mutation_kind="static_source",
        mutation_payload={"source": "from research.opening_range_retest_outcomes_v2.overlap import build_overlap\n"},
        target_function="oracle.oracle_independence_failures",
        expected_failures=("ORACLE_FORBIDDEN_IMPORT",),
    ),
    _control(
        "STATIC_FORBIDDEN_ENGINE_IMPORT_ALIAS_CALL",
        mutation_kind="static_source",
        mutation_payload={"source": "import research.opening_range_retest_outcomes_v2.engine as engine\nengine.measure_candidate()\n"},
        target_function="oracle.oracle_independence_failures",
        expected_failures=("ORACLE_FORBIDDEN_IMPORT",),
    ),
    _control(
        "STATIC_FORBIDDEN_OVERLAP_IMPORT_ALIAS_CALL",
        mutation_kind="static_source",
        mutation_payload={"source": "import research.opening_range_retest_outcomes_v2.overlap as overlap\noverlap.build_overlap()\n"},
        target_function="oracle.oracle_independence_failures",
        expected_failures=("ORACLE_FORBIDDEN_IMPORT",),
    ),
)

CONTROL_CASES: tuple[SummaryOverlapControl, ...] = SUMMARY_CONTROLS + OVERLAP_CONTROLS + STATIC_CONTROLS


def execute_control(control: SummaryOverlapControl) -> RawExecution:
    return EXECUTORS[control.spec.target_function](control.spec)


def control_fingerprint(control: SummaryOverlapControl, raw: RawExecution) -> str:
    return canonical_hash(
        {
            "control_id": control.spec.control_id,
            "category": control.spec.category,
            "mutation_kind": control.spec.mutation_kind,
            "mutation_payload": control.spec.mutation_payload,
            "target_function": control.spec.target_function,
            "target_output_hash": raw.target_output_hash,
        }
    )


def executor_expected_access_findings() -> list[str]:
    source = __import__(__name__, fromlist=[""]).__loader__.get_source(__name__)  # type: ignore[union-attr]
    if source is None:
        return ["MODULE_SOURCE_UNAVAILABLE"]
    tree = ast.parse(source)
    findings: list[str] = []
    forbidden_names = {"expected", "expectation", "expected_failure", "expected_failures", "ControlExpectation"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("execute_"):
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id in forbidden_names:
                    findings.append(f"{node.name}:{child.lineno}:{child.id}")
                if isinstance(child, ast.Attribute) and child.attr in forbidden_names:
                    findings.append(f"{node.name}:{child.lineno}:{child.attr}")
    return findings
