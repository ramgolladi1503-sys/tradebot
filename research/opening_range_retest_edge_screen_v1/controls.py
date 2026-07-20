from __future__ import annotations

import copy
import math
from typing import Any, Callable

from research.opening_range_retest_edge_screen_v1 import contract as C


def base_fixture() -> dict[str, Any]:
    return {
        "contract": C.contract_payload(),
        "source": {
            "ledger_sha256": C.SOURCE_LEDGER_SHA256,
            "overlap_sha256": C.SOURCE_OVERLAP_SHA256,
            "candidate_count": C.CERTIFIED_CANDIDATES,
            "source_joins": C.CERTIFIED_SOURCE_JOINS,
            "path": C.SOURCE_LEDGER_PATH,
            "timestamp_timezone": "Asia/Kolkata",
            "append": False,
        },
        "metrics": {
            "primary_horizon": 15,
            "primary": {
                "candidate_count": 2155,
                "session_count": 477,
                "session_equal_mean": 0.0002,
                "session_equal_mean_bps": 2.0,
                "session_cluster_bootstrap": {"lower_bps": 0.2, "distribution_hash": "hash"},
                "sign_test": {
                    "positive": 260,
                    "negative": 217,
                    "zero": 0,
                    "binomial_n_excluding_zero": 477,
                    "one_sided_p_positive_tendency": 0.02,
                    "two_sided_p": 0.04,
                },
            },
            "secondary": {"candidate_count": 2086},
            "symbol_direction": {f"{s}:{d}": {"holm": {"raw_p": 0.02, "holm_adjusted_p": 0.04, "reject_0_05": True}} for s, d in C.SYMBOL_DIRECTION_CELLS},
        },
        "controls": {
            "random_direction": {"permutations": 1000, "permutation_p": 0.04, "count_control_ge_observed": 39, "observed_statistic": 0.0002},
            "opposite_direction": {"records_checked": 2155, "mismatches": 0, "max_abs_error": 0.0, "verdict": "PASS"},
            "matched_time": {
                "seed": C.MATCHED_TIME_SEED,
                "draws_per_candidate": 100,
                "coverage": 0.96,
                "covered_candidates": 2155,
                "uncovered_candidates": 0,
                "draws": 215500,
                "empirical_one_sided_add_one_p": 0.04,
                "advantage_ci": {"lower_bps": 0.1},
                "leakage": False,
                "cross_session_samples": 0,
                "missing_terminal_horizons": 0,
                "future_return_selected": False,
            },
            "within_stratum_direction_permutation": {
                "seed": C.WITHIN_STRATUM_SEED,
                "permutations": 1000,
                "eligible_coverage": 0.75,
                "coverage_verdict": "ADEQUATE",
                "permutation_p": 0.04,
                "count_control_ge_observed": 39,
            },
        },
        "concentration": {"removal_means": {name: 0.0001 for name in C.CONCENTRATION_REMOVALS}},
        "replication": {"symbol_direction_cells": {f"{s}:{d}": {"holm": {"raw_p": 0.02, "holm_adjusted_p": 0.04}} for s, d in C.SYMBOL_DIRECTION_CELLS}},
        "overlap": {
            "authority": {"sha256": C.SOURCE_OVERLAP_SHA256, "validation_failures": []},
            "one_per_accepted_overlap_component": {"selection": "earliest", "candidate_count": 1000},
            "earliest_per_symbol_session": {"selection": "earliest", "candidate_count": 1000},
        },
        "verdict": {
            "verdict": "ORB_STRUCTURAL_EDGE_CANDIDATE",
            "terminal_primary_rule_applied": False,
            "structural_gates": {"primary_15m_session_equal_mean_gt_0": True, "mean_ge_1bp": True},
        },
        "execution": {
            "wfa_invoked": False,
            "production_mutation": False,
            "source_mutation": False,
            "path_leak": False,
            "ordering_hash": "stable",
            "oracle_imports_engine": False,
            "two_directory_hash_match": True,
        },
    }


def validate_fixture(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    contract = payload["contract"]
    source = payload["source"]
    metrics = payload["metrics"]
    controls = payload["controls"]
    execution = payload["execution"]
    if source["ledger_sha256"] != C.SOURCE_LEDGER_SHA256:
        failures.append("LEDGER_SHA_DRIFT")
    if source["overlap_sha256"] != C.SOURCE_OVERLAP_SHA256:
        failures.append("OVERLAP_SHA_DRIFT")
    if source["candidate_count"] != C.CERTIFIED_CANDIDATES:
        failures.append("CANDIDATE_COUNT_DRIFT")
    if source["source_joins"] != C.CERTIFIED_SOURCE_JOINS:
        failures.append("SOURCE_JOIN_COUNT_DRIFT")
    if source["path"].startswith("/") or source["path"].startswith("file://") or "\\" in source["path"] or ":" in source["path"].split("/")[0]:
        failures.append("PATH_LEAKAGE")
    if source["timestamp_timezone"] != "Asia/Kolkata":
        failures.append("TIMEZONE_DRIFT")
    if source["append"]:
        failures.append("SOURCE_APPEND_MUTATION")
    if contract["primary_horizon_minutes"] != C.PRIMARY_HORIZON:
        failures.append("PRIMARY_HORIZON_SWITCH")
    if contract["secondary_horizon_minutes"] != C.SECONDARY_HORIZON:
        failures.append("SECONDARY_HORIZON_SWITCH")
    if contract["bootstrap"]["seed"] != C.BOOTSTRAP_SEED or contract["bootstrap"]["replications"] != C.BOOTSTRAP_REPLICATIONS:
        failures.append("BOOTSTRAP_CONTRACT_DRIFT")
    if metrics["primary"]["candidate_count"] != C.EXPECTED_MEASURED_COUNTS[15]:
        failures.append("PRIMARY_CANDIDATE_COUNT_DRIFT")
    if metrics["primary"]["session_count"] >= metrics["primary"]["candidate_count"]:
        failures.append("PRIMARY_SESSION_WEIGHT_SUBSTITUTION")
    if metrics["secondary"]["candidate_count"] != C.EXPECTED_MEASURED_COUNTS[30]:
        failures.append("SECONDARY_CANDIDATE_COUNT_DRIFT")
    if not math.isfinite(metrics["primary"]["session_equal_mean"]):
        failures.append("PRIMARY_NAN_OR_INF")
    sign = metrics["primary"]["sign_test"]
    if sign["positive"] + sign["negative"] != sign["binomial_n_excluding_zero"]:
        failures.append("SIGN_TEST_ZERO_DENOMINATOR_DRIFT")
    expected_add_one = (1 + controls["random_direction"]["count_control_ge_observed"]) / (1 + controls["random_direction"]["permutations"])
    if abs(controls["random_direction"]["permutation_p"] - expected_add_one) > 1e-12:
        failures.append("RANDOM_ADD_ONE_OMISSION")
    if controls["opposite_direction"]["mismatches"] != 0 or controls["opposite_direction"]["verdict"] != "PASS":
        failures.append("OPPOSITE_RETURN_MISMATCH")
    matched = controls["matched_time"]
    if matched["seed"] != C.MATCHED_TIME_SEED or matched["draws_per_candidate"] != C.MATCHED_TIME_DRAWS_PER_CANDIDATE:
        failures.append("MATCHED_TIME_SEED_OR_COUNT_DRIFT")
    if matched["coverage"] < C.MATCHED_TIME_MIN_COVERAGE or matched["covered_candidates"] + matched["uncovered_candidates"] != metrics["primary"]["candidate_count"]:
        failures.append("MATCHED_TIME_COVERAGE_DRIFT")
    if matched["leakage"] or matched["cross_session_samples"] or matched["missing_terminal_horizons"] or matched["future_return_selected"]:
        failures.append("MATCHED_TIME_LEAKAGE")
    within = controls["within_stratum_direction_permutation"]
    if within["seed"] != C.WITHIN_STRATUM_SEED or within["permutations"] != C.WITHIN_STRATUM_PERMUTATIONS:
        failures.append("WITHIN_STRATUM_SEED_OR_COUNT_DRIFT")
    if within["eligible_coverage"] < 0.50 or within["coverage_verdict"] == "UNDERPOWERED":
        failures.append("WITHIN_STRATUM_UNDERPOWERED")
    expected_within = (1 + within["count_control_ge_observed"]) / (1 + within["permutations"])
    if abs(within["permutation_p"] - expected_within) > 1e-12:
        failures.append("WITHIN_STRATUM_ADD_ONE_OMISSION")
    for key, item in payload["replication"]["symbol_direction_cells"].items():
        if item["holm"]["holm_adjusted_p"] < item["holm"]["raw_p"]:
            failures.append(f"HOLM_MUTATION:{key}")
    if payload["overlap"]["authority"]["sha256"] != C.SOURCE_OVERLAP_SHA256 or payload["overlap"]["authority"]["validation_failures"]:
        failures.append("OVERLAP_AUTHORITY_MUTATION")
    if payload["overlap"]["one_per_accepted_overlap_component"]["selection"] != "earliest":
        failures.append("OUTCOME_SELECTED_OVERLAP_DEDUP")
    if metrics["primary"]["session_equal_mean"] <= 0 and payload["verdict"]["verdict"] != "ORB_NO_STRUCTURAL_EDGE":
        failures.append("HORIZON_RESCUE_OR_VERDICT_DRIFT")
    if payload["verdict"]["verdict"] == "ORB_STRUCTURAL_EDGE_CANDIDATE" and not all(payload["verdict"]["structural_gates"].values()):
        failures.append("VERDICT_THRESHOLD_DRIFT")
    if execution["wfa_invoked"]:
        failures.append("WFA_INVOCATION")
    if execution["production_mutation"]:
        failures.append("PRODUCTION_MUTATION")
    if execution["source_mutation"]:
        failures.append("SOURCE_MUTATION")
    if execution["path_leak"]:
        failures.append("PATH_LEAKAGE")
    if execution["ordering_hash"] != "stable":
        failures.append("ORDERING_NONDETERMINISM")
    if execution["oracle_imports_engine"]:
        failures.append("ORACLE_COUPLING")
    if not execution["two_directory_hash_match"]:
        failures.append("TWO_DIRECTORY_PATH_DEPENDENCE")
    return failures


def mutate(path: list[Any], value: Any) -> Callable[[dict[str, Any]], None]:
    def apply(payload: dict[str, Any]) -> None:
        cursor = payload
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value

    return apply


CONTROL_CASES: list[tuple[str, Callable[[dict[str, Any]], None], str, str]] = [
    ("ledger_sha_drift", mutate(["source", "ledger_sha256"], "bad"), "LEDGER_SHA_DRIFT", "hash mutation"),
    ("overlap_sha_drift", mutate(["source", "overlap_sha256"], "bad"), "OVERLAP_SHA_DRIFT", "overlap hash mutation"),
    ("candidate_count_drop", mutate(["source", "candidate_count"], 2214), "CANDIDATE_COUNT_DRIFT", "count mutation"),
    ("source_join_count_drop", mutate(["source", "source_joins"], 2214), "SOURCE_JOIN_COUNT_DRIFT", "join count mutation"),
    ("absolute_path_leak", mutate(["source", "path"], "/tmp/ledger.json"), "PATH_LEAKAGE", "absolute path leak"),
    ("windows_drive_path_leak", mutate(["source", "path"], "C:\\ledger.json"), "PATH_LEAKAGE", "Windows path leak"),
    ("file_uri_path_leak", mutate(["source", "path"], "file:///tmp/ledger.json"), "PATH_LEAKAGE", "file URI path leak"),
    ("timezone_drift", mutate(["source", "timestamp_timezone"], "UTC"), "TIMEZONE_DRIFT", "timezone mutation"),
    ("source_append_mutation", mutate(["source", "append"], True), "SOURCE_APPEND_MUTATION", "source append mutation"),
    ("primary_horizon_switch", mutate(["contract", "primary_horizon_minutes"], 30), "PRIMARY_HORIZON_SWITCH", "primary horizon mutation"),
    ("secondary_horizon_switch", mutate(["contract", "secondary_horizon_minutes"], 15), "SECONDARY_HORIZON_SWITCH", "secondary horizon mutation"),
    ("bootstrap_seed_drift", mutate(["contract", "bootstrap", "seed"], 1), "BOOTSTRAP_CONTRACT_DRIFT", "bootstrap seed mutation"),
    ("bootstrap_count_drift", mutate(["contract", "bootstrap", "replications"], 99), "BOOTSTRAP_CONTRACT_DRIFT", "bootstrap count mutation"),
    ("primary_candidate_count_drop", mutate(["metrics", "primary", "candidate_count"], 2154), "PRIMARY_CANDIDATE_COUNT_DRIFT", "primary count mutation"),
    ("primary_candidate_count_duplicate", mutate(["metrics", "primary", "candidate_count"], 2156), "PRIMARY_CANDIDATE_COUNT_DRIFT", "duplicate count mutation"),
    ("secondary_candidate_count_drop", mutate(["metrics", "secondary", "candidate_count"], 2085), "SECONDARY_CANDIDATE_COUNT_DRIFT", "secondary count mutation"),
    ("primary_nan", mutate(["metrics", "primary", "session_equal_mean"], float("nan")), "PRIMARY_NAN_OR_INF", "NaN mutation"),
    ("primary_inf", mutate(["metrics", "primary", "session_equal_mean"], float("inf")), "PRIMARY_NAN_OR_INF", "inf mutation"),
    ("sign_test_zero_denominator", mutate(["metrics", "primary", "sign_test", "binomial_n_excluding_zero"], 476), "SIGN_TEST_ZERO_DENOMINATOR_DRIFT", "sign denominator mutation"),
    ("random_add_one_omission", mutate(["controls", "random_direction", "permutation_p"], 0.039), "RANDOM_ADD_ONE_OMISSION", "random p-value mutation"),
    ("opposite_return_mismatch", mutate(["controls", "opposite_direction", "mismatches"], 1), "OPPOSITE_RETURN_MISMATCH", "opposite return mutation"),
    ("opposite_verdict_fail", mutate(["controls", "opposite_direction", "verdict"], "FAIL"), "OPPOSITE_RETURN_MISMATCH", "opposite verdict mutation"),
    ("matched_seed_drift", mutate(["controls", "matched_time", "seed"], 1), "MATCHED_TIME_SEED_OR_COUNT_DRIFT", "matched seed mutation"),
    ("matched_count_drift", mutate(["controls", "matched_time", "draws_per_candidate"], 99), "MATCHED_TIME_SEED_OR_COUNT_DRIFT", "matched draw-count mutation"),
    ("matched_coverage_low", mutate(["controls", "matched_time", "coverage"], 0.94), "MATCHED_TIME_COVERAGE_DRIFT", "matched coverage mutation"),
    ("matched_uncovered_count_drift", mutate(["controls", "matched_time", "uncovered_candidates"], 1), "MATCHED_TIME_COVERAGE_DRIFT", "matched uncovered mutation"),
    ("matched_timestamp_leakage", mutate(["controls", "matched_time", "leakage"], True), "MATCHED_TIME_LEAKAGE", "matched leakage mutation"),
    ("matched_cross_session", mutate(["controls", "matched_time", "cross_session_samples"], 1), "MATCHED_TIME_LEAKAGE", "matched cross-session mutation"),
    ("matched_missing_terminal", mutate(["controls", "matched_time", "missing_terminal_horizons"], 1), "MATCHED_TIME_LEAKAGE", "matched terminal mutation"),
    ("matched_future_selected", mutate(["controls", "matched_time", "future_return_selected"], True), "MATCHED_TIME_LEAKAGE", "future-return selection mutation"),
    ("within_seed_drift", mutate(["controls", "within_stratum_direction_permutation", "seed"], 1), "WITHIN_STRATUM_SEED_OR_COUNT_DRIFT", "within seed mutation"),
    ("within_count_drift", mutate(["controls", "within_stratum_direction_permutation", "permutations"], 99), "WITHIN_STRATUM_SEED_OR_COUNT_DRIFT", "within count mutation"),
    ("within_undercoverage", mutate(["controls", "within_stratum_direction_permutation", "eligible_coverage"], 0.49), "WITHIN_STRATUM_UNDERPOWERED", "within coverage mutation"),
    ("within_underpowered_verdict", mutate(["controls", "within_stratum_direction_permutation", "coverage_verdict"], "UNDERPOWERED"), "WITHIN_STRATUM_UNDERPOWERED", "within verdict mutation"),
    ("within_add_one_omission", mutate(["controls", "within_stratum_direction_permutation", "permutation_p"], 0.039), "WITHIN_STRATUM_ADD_ONE_OMISSION", "within p-value mutation"),
    ("holm_mutation", mutate(["replication", "symbol_direction_cells", "BANKNIFTY:BUY_CALL", "holm", "holm_adjusted_p"], 0.01), "HOLM_MUTATION:BANKNIFTY:BUY_CALL", "Holm mutation"),
    ("overlap_authority_mutation", mutate(["overlap", "authority", "sha256"], "bad"), "OVERLAP_AUTHORITY_MUTATION", "overlap authority mutation"),
    ("overlap_validation_failure", mutate(["overlap", "authority", "validation_failures"], ["bad"]), "OVERLAP_AUTHORITY_MUTATION", "overlap validation mutation"),
    ("outcome_selected_dedup", mutate(["overlap", "one_per_accepted_overlap_component", "selection"], "best_return"), "OUTCOME_SELECTED_OVERLAP_DEDUP", "outcome-selected dedup mutation"),
    ("horizon_rescue", mutate(["metrics", "primary", "session_equal_mean"], -0.0001), "HORIZON_RESCUE_OR_VERDICT_DRIFT", "horizon rescue mutation"),
    ("wfa_invocation", mutate(["execution", "wfa_invoked"], True), "WFA_INVOCATION", "WFA mutation"),
    ("production_mutation", mutate(["execution", "production_mutation"], True), "PRODUCTION_MUTATION", "production mutation"),
    ("source_mutation", mutate(["execution", "source_mutation"], True), "SOURCE_MUTATION", "source mutation"),
    ("posix_prefix_path_leak", mutate(["execution", "path_leak"], True), "PATH_LEAKAGE", "worktree prefix leak"),
    ("ordering_nondeterminism", mutate(["execution", "ordering_hash"], "unstable"), "ORDERING_NONDETERMINISM", "ordering mutation"),
    ("oracle_coupling", mutate(["execution", "oracle_imports_engine"], True), "ORACLE_COUPLING", "oracle coupling mutation"),
    ("two_directory_dependence", mutate(["execution", "two_directory_hash_match"], False), "TWO_DIRECTORY_PATH_DEPENDENCE", "two-directory mutation"),
    ("session_weight_substitution", mutate(["metrics", "primary", "session_count"], 2155), "PRIMARY_SESSION_WEIGHT_SUBSTITUTION", "session weighting mutation"),
    ("verdict_threshold_drift", mutate(["verdict", "structural_gates", "mean_ge_1bp"], False), "VERDICT_THRESHOLD_DRIFT", "threshold mutation"),
    ("unc_path_leak", mutate(["source", "path"], "\\\\server\\share\\ledger.json"), "PATH_LEAKAGE", "UNC path leak"),
]


def run_control_case(name: str) -> dict[str, Any]:
    for case_id, mutator, expected, fault in CONTROL_CASES:
        if case_id != name:
            continue
        payload = copy.deepcopy(base_fixture())
        mutator(payload)
        failures = validate_fixture(payload)
        actual = expected if expected in failures else next((failure for failure in failures if failure.startswith(expected.split(":")[0])), None)
        return {
            "control_id": name,
            "injected_fault": fault,
            "expected_detector": expected,
            "actual_detector": actual,
            "failures": failures,
            "passed": actual is not None,
        }
    raise KeyError(name)
