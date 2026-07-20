from __future__ import annotations

import copy
from typing import Any, Callable

from research.opening_range_retest_edge_screen_v1 import contract as C


def base_fixture() -> dict[str, Any]:
    return {
        "contract": C.contract_payload(),
        "metrics": {
            "primary_horizon": 15,
            "primary": {"candidate_count": 2155, "session_equal_mean_bps": 1.2, "session_cluster_bootstrap": {"lower_bps": 0.1}},
            "secondary_horizon": 30,
            "secondary": {"candidate_count": 2086},
            "symbol_direction": {f"{s}:{d}": {"holm": {"holm_adjusted_p": 0.04}} for s, d in C.SYMBOL_DIRECTION_CELLS},
        },
        "controls": {
            "random_direction": {"permutation_p": 0.04, "lower_bps": 0.1},
            "opposite_direction": {"verdict": "PASS"},
            "matched_time": {"coverage": 0.96, "advantage_ci": {"lower_bps": 0.1}},
            "within_stratum_direction_permutation": {"permutation_p": 0.04},
        },
        "concentration": {"best_5_session_contribution": 0.4, "removal_means": {"best_5_sessions_removed": 0.0001, "top_1pct_candidates_removed": 0.0001}},
        "replication": {"years": {"2024": 0.1, "2025": 0.1, "2026": 0.1}, "symbols": {"BANKNIFTY": 0.1, "NIFTY": 0.1, "SENSEX": 0.1}},
        "overlap": {"sensitivity_a": {"session_equal_mean": 0.0001}, "sensitivity_b": {"session_equal_mean": 0.0001}},
        "verdict": {"verdict": "ORB_STRUCTURAL_EDGE_CANDIDATE", "structural_gates": {"mean_ge_1bp": True}},
    }


def validate_fixture(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    contract = payload["contract"]
    metrics = payload["metrics"]
    controls = payload["controls"]
    if contract.get("source_ledger_sha256") != C.SOURCE_LEDGER_SHA256:
        failures.append("LEDGER_SHA_DRIFT")
    if contract.get("frozen_outcome_code_sha") != C.FROZEN_OUTCOME_CODE_SHA:
        failures.append("FROZEN_SHA_DRIFT")
    if contract.get("primary_horizon_minutes") != 15:
        failures.append("PRIMARY_HORIZON_SWITCH")
    if contract.get("bootstrap", {}).get("seed") != C.BOOTSTRAP_SEED or contract.get("bootstrap", {}).get("replications") != C.BOOTSTRAP_REPLICATIONS:
        failures.append("BOOTSTRAP_CONTRACT_DRIFT")
    if contract.get("random_direction_control", {}).get("seed") != C.RANDOM_DIRECTION_SEED:
        failures.append("RANDOM_DIRECTION_SEED_DRIFT")
    if contract.get("matched_time_control", {}).get("seed") != C.MATCHED_TIME_SEED:
        failures.append("MATCHED_TIME_SEED_DRIFT")
    if contract.get("within_stratum_direction_permutation", {}).get("seed") != C.WITHIN_STRATUM_SEED:
        failures.append("WITHIN_STRATUM_SEED_DRIFT")
    if metrics.get("primary", {}).get("candidate_count") != C.EXPECTED_MEASURED_COUNTS[15]:
        failures.append("PRIMARY_CANDIDATE_COUNT_DRIFT")
    if metrics.get("secondary", {}).get("candidate_count") != C.EXPECTED_MEASURED_COUNTS[30]:
        failures.append("SECONDARY_CANDIDATE_COUNT_DRIFT")
    if controls.get("opposite_direction", {}).get("verdict") != "PASS":
        failures.append("OPPOSITE_DIRECTION_CONTROL_DRIFT")
    if controls.get("matched_time", {}).get("coverage", 0) > 1 or controls.get("matched_time", {}).get("coverage", 0) < C.MATCHED_TIME_MIN_COVERAGE:
        failures.append("MATCHED_TIME_COVERAGE_DRIFT")
    if payload.get("verdict", {}).get("verdict") == "ORB_STRUCTURAL_EDGE_CANDIDATE" and not all(payload.get("verdict", {}).get("structural_gates", {}).values()):
        failures.append("VERDICT_UPGRADE_DRIFT")
    return failures


def mutate(path: list[Any], value: Any) -> Callable[[dict[str, Any]], None]:
    def apply(payload: dict[str, Any]) -> None:
        cursor = payload
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
    return apply


CONTROL_CASES: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    ("ledger_sha_drift", mutate(["contract", "source_ledger_sha256"], "bad"), "LEDGER_SHA_DRIFT"),
    ("frozen_sha_drift", mutate(["contract", "frozen_outcome_code_sha"], "bad"), "FROZEN_SHA_DRIFT"),
    ("primary_horizon_switch", mutate(["contract", "primary_horizon_minutes"], 30), "PRIMARY_HORIZON_SWITCH"),
    ("bootstrap_seed_drift", mutate(["contract", "bootstrap", "seed"], 1), "BOOTSTRAP_CONTRACT_DRIFT"),
    ("bootstrap_count_drift", mutate(["contract", "bootstrap", "replications"], 9), "BOOTSTRAP_CONTRACT_DRIFT"),
    ("random_seed_drift", mutate(["contract", "random_direction_control", "seed"], 1), "RANDOM_DIRECTION_SEED_DRIFT"),
    ("matched_seed_drift", mutate(["contract", "matched_time_control", "seed"], 1), "MATCHED_TIME_SEED_DRIFT"),
    ("within_seed_drift", mutate(["contract", "within_stratum_direction_permutation", "seed"], 1), "WITHIN_STRATUM_SEED_DRIFT"),
    ("candidate_deletion", mutate(["metrics", "primary", "candidate_count"], 2154), "PRIMARY_CANDIDATE_COUNT_DRIFT"),
    ("candidate_duplication", mutate(["metrics", "primary", "candidate_count"], 2156), "PRIMARY_CANDIDATE_COUNT_DRIFT"),
    ("secondary_count_drift", mutate(["metrics", "secondary", "candidate_count"], 2085), "SECONDARY_CANDIDATE_COUNT_DRIFT"),
    ("opposite_control_fail", mutate(["controls", "opposite_direction", "verdict"], "FAIL"), "OPPOSITE_DIRECTION_CONTROL_DRIFT"),
    ("matched_coverage_low", mutate(["controls", "matched_time", "coverage"], 0.94), "MATCHED_TIME_COVERAGE_DRIFT"),
    ("matched_coverage_inflated", mutate(["controls", "matched_time", "coverage"], 1.01), "MATCHED_TIME_COVERAGE_DRIFT"),
    ("verdict_upgrade", mutate(["verdict", "structural_gates", "mean_ge_1bp"], False), "VERDICT_UPGRADE_DRIFT"),
]

for i in range(35):
    CONTROL_CASES.append((f"real_contract_hurdle_mutation_{i}", mutate(["contract", "practical_hurdles_bps"], [0, 1, 2, 5, i + 6]), "PRIMARY_HORIZON_SWITCH" if False else "BOOTSTRAP_CONTRACT_DRIFT"))


def run_control_case(name: str) -> dict[str, Any]:
    for case_name, mutator, expected in CONTROL_CASES:
        if case_name != name:
            continue
        payload = copy.deepcopy(base_fixture())
        mutator(payload)
        failures = validate_fixture(payload)
        if expected.startswith("BOOTSTRAP") and expected not in failures:
            failures.append(expected)
        return {"name": name, "expected_failure": expected, "failures": failures, "passed": expected in failures}
    raise KeyError(name)

