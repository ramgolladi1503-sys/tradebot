from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = 1
SCREEN_ID = "opening_range_retest_edge_screen_v1"

BASE_MAIN_SHA = "a48176fc245375f15e316493364915ec37439e29"
FROZEN_OUTCOME_CODE_SHA = "9e4798d48a39f414c88095a1d1a70d055dda98a8"
FROZEN_IMPLEMENTATION_TREE_HASH = "dfdeefa882879267ccdffff7e10454d4298d3767e8b3f687cfdbe6a0cd86bf14"

SOURCE_LEDGER_PATH = "docs/agent_reviews/opening_range_retest_outcome_ledger_v2.json"
SOURCE_LEDGER_SHA256 = "2136cf84f19aa93d4b81d3b30c3e69cc91aaaa5e849ad286b7f213ae3ec21a3a"
SOURCE_LEDGER_SEMANTIC_HASH = "2e798aa937c8d88ea164ef6c47bc295de929ee2944f03a34b1397d0ad40a10bd"
OUTCOME_CONTRACT_SHA256 = "f3778e2b3b025b88ae9101e1a4263c4ea4917b06541fc70454287901f5def4d5"
CERTIFIED_PROJECTION_HASH = "23ada7617040d2824e8e5e49742bfbb2d91e676994a3ba4f371d3e573014c581"

CERTIFIED_CANDIDATES = 2215
CERTIFIED_SOURCE_JOINS = 2215
CERTIFIED_NEGATIVE_CONTROLS = 154

PRIMARY_HORIZON = 15
SECONDARY_HORIZON = 30
DIAGNOSTIC_HORIZONS = (1, 3, 5)
HORIZONS = (1, 3, 5, 15, 30)
EXPECTED_MEASURED_COUNTS = {15: 2155, 30: 2086}

BOOTSTRAP_REPLICATIONS = 10_000
BOOTSTRAP_SEED = 20260720
BOOTSTRAP_CI = 0.95

RANDOM_DIRECTION_PERMUTATIONS = 1_000
RANDOM_DIRECTION_SEED = 20260721
MATCHED_TIME_DRAWS_PER_CANDIDATE = 100
MATCHED_TIME_SEED = 20260722
WITHIN_STRATUM_PERMUTATIONS = 1_000
WITHIN_STRATUM_SEED = 20260723

ENTRY_TIME_BUCKETS = (
    ("09:15", "10:00"),
    ("10:00", "11:00"),
    ("11:00", "12:00"),
    ("12:00", "13:00"),
    ("13:00", "14:00"),
    ("14:00", "15:00"),
    ("15:00", "15:29"),
)

SYMBOLS = ("BANKNIFTY", "NIFTY", "SENSEX")
DIRECTIONS = ("BUY_CALL", "BUY_PUT")
SYMBOL_DIRECTION_CELLS = tuple((symbol, direction) for symbol in SYMBOLS for direction in DIRECTIONS)
YEARS = (2024, 2025, 2026)

PRACTICAL_HURDLES_BPS = (0, 1, 2, 5)
STRUCTURAL_MIN_MEAN_BPS = 1.0
CONDITIONAL_MIN_CANDIDATES = 300
CONDITIONAL_MIN_SESSIONS = 150
MATCHED_TIME_MIN_COVERAGE = 0.95
HOLM_ALPHA = 0.05

CONCENTRATION_REMOVALS = (
    "best_1_session_removed",
    "best_3_sessions_removed",
    "best_5_sessions_removed",
    "best_10_sessions_removed",
    "top_1pct_candidates_removed",
    "worst_1_session_removed",
    "worst_5_sessions_removed",
)

ARTIFACT_NAMES = {
    "contract": "opening_range_retest_edge_screen_contract_v1.json",
    "metrics": "opening_range_retest_edge_screen_metrics_v1.json",
    "controls": "opening_range_retest_edge_screen_controls_v1.json",
    "concentration": "opening_range_retest_edge_screen_concentration_v1.json",
    "replication": "opening_range_retest_edge_screen_replication_v1.json",
    "overlap": "opening_range_retest_edge_screen_overlap_v1.json",
    "verdict": "opening_range_retest_edge_screen_verdict_v1.json",
    "audit": "opening_range_retest_edge_screen_audit_v1.json",
    "report": "opening_range_retest_edge_screen_report_v1.md",
}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safety_fields() -> dict[str, Any]:
    return {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "not_option_pnl": True,
        "not_profitability_proof": True,
    }


def contract_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "screen_id": SCREEN_ID,
        "base_main_sha": BASE_MAIN_SHA,
        "frozen_outcome_code_sha": FROZEN_OUTCOME_CODE_SHA,
        "frozen_implementation_tree_hash": FROZEN_IMPLEMENTATION_TREE_HASH,
        "source_ledger_path": SOURCE_LEDGER_PATH,
        "source_ledger_sha256": SOURCE_LEDGER_SHA256,
        "source_ledger_semantic_hash": SOURCE_LEDGER_SEMANTIC_HASH,
        "outcome_contract_sha256": OUTCOME_CONTRACT_SHA256,
        "certified_projection_hash": CERTIFIED_PROJECTION_HASH,
        "certified_candidates": CERTIFIED_CANDIDATES,
        "certified_source_joins": CERTIFIED_SOURCE_JOINS,
        "certified_negative_controls": CERTIFIED_NEGATIVE_CONTROLS,
        "primary_horizon_minutes": PRIMARY_HORIZON,
        "secondary_horizon_minutes": SECONDARY_HORIZON,
        "diagnostic_horizon_minutes": list(DIAGNOSTIC_HORIZONS),
        "all_horizon_minutes": list(HORIZONS),
        "expected_measured_counts": {str(k): v for k, v in EXPECTED_MEASURED_COUNTS.items()},
        "primary_estimand": "session_equal_mean",
        "bootstrap": {
            "cluster": "session_date",
            "replications": BOOTSTRAP_REPLICATIONS,
            "seed": BOOTSTRAP_SEED,
            "ci": BOOTSTRAP_CI,
            "authority": "session_cluster_bootstrap",
        },
        "random_direction_control": {
            "permutations": RANDOM_DIRECTION_PERMUTATIONS,
            "seed": RANDOM_DIRECTION_SEED,
            "preserve": ["session", "symbol", "entry_time", "horizon", "unsigned_move"],
            "direction_counts_preserved_within": ["symbol", "calendar_year"],
        },
        "opposite_direction_control": {"required_identity": "signal_return + opposite_return == 0"},
        "matched_time_control": {
            "draws_per_candidate": MATCHED_TIME_DRAWS_PER_CANDIDATE,
            "seed": MATCHED_TIME_SEED,
            "entry_time_buckets": [list(item) for item in ENTRY_TIME_BUCKETS],
            "preserve": ["session", "symbol", "direction", "horizon", "entry_time_bucket"],
            "exclude": ["actual_entry_bar", "bars_without_exact_terminal_horizon", "bars_outside_certified_session"],
            "minimum_coverage": MATCHED_TIME_MIN_COVERAGE,
        },
        "within_stratum_direction_permutation": {
            "permutations": WITHIN_STRATUM_PERMUTATIONS,
            "seed": WITHIN_STRATUM_SEED,
            "strata": ["symbol", "calendar_year", "entry_time_bucket"],
        },
        "symbols": list(SYMBOLS),
        "directions": list(DIRECTIONS),
        "symbol_direction_cells": [{"symbol": s, "direction": d} for s, d in SYMBOL_DIRECTION_CELLS],
        "years": list(YEARS),
        "practical_hurdles_bps": list(PRACTICAL_HURDLES_BPS),
        "structural_min_session_equal_mean_bps": STRUCTURAL_MIN_MEAN_BPS,
        "conditional_min_candidates": CONDITIONAL_MIN_CANDIDATES,
        "conditional_min_sessions": CONDITIONAL_MIN_SESSIONS,
        "holm_alpha": HOLM_ALPHA,
        "concentration_removals": list(CONCENTRATION_REMOVALS),
        "overlap_sensitivities": {
            "A": "earliest candidate per session x symbol x direction",
            "B": "earliest proposal_ready_at then lexicographically smallest candidate_id per overlap-connected component",
        },
        "verdicts": ["ORB_NO_STRUCTURAL_EDGE", "ORB_CONDITIONAL_EDGE_CANDIDATE", "ORB_STRUCTURAL_EDGE_CANDIDATE"],
        "forbidden": {
            "wfa": True,
            "rescue_tuning": True,
            "parameter_search": True,
            "option_replay": True,
            "option_pnl": True,
            "transaction_cost_certification": True,
            "paper_live_promotion": True,
            "production_integration": True,
        },
        **safety_fields(),
    }
    payload["contract_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in payload.items() if k != "contract_hash"}))
    return payload

