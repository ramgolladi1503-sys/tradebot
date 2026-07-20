from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.opening_range_retest_outcomes_v2.control_protocol import (
    ControlExpectation,
    MutationSpec,
)


LINEAGE_CATEGORY = "lineage_hash"


@dataclass(frozen=True)
class LineageControlCase:
    mutation: MutationSpec
    expectation: ControlExpectation


def _contract(control_id: str, path: str, value: Any, failure: str) -> LineageControlCase:
    return LineageControlCase(
        mutation=MutationSpec(
            control_id=control_id,
            category=LINEAGE_CATEGORY,
            mutation_kind="contract_field_replace",
            mutation_payload={"path": path, "replacement": value},
            target_function="verify_contract_payload",
        ),
        expectation=ControlExpectation(control_id=control_id, expected_failures=(failure,)),
    )


def _lineage(control_id: str, key: str, value: Any, failure: str) -> LineageControlCase:
    return LineageControlCase(
        mutation=MutationSpec(
            control_id=control_id,
            category=LINEAGE_CATEGORY,
            mutation_kind="lineage_snapshot_replace",
            mutation_payload={"snapshot_key": key, "replacement": value},
            target_function="verify_lineage_snapshot",
        ),
        expectation=ControlExpectation(control_id=control_id, expected_failures=(failure,)),
    )


CONTRACT_SEMANTIC_FIELD_CASES: tuple[LineageControlCase, ...] = (
    _contract("LINEAGE_CONTRACT_SCHEMA_VERSION", "schema_version", 3, "CONTRACT_FIELD_MISMATCH:schema_version"),
    _contract("LINEAGE_CONTRACT_VERSION", "contract_version", "wrong", "CONTRACT_FIELD_MISMATCH:contract_version"),
    _contract("LINEAGE_CONTRACT_MODE", "mode", "WRONG_MODE", "CONTRACT_FIELD_MISMATCH:mode"),
    _contract("LINEAGE_CONTRACT_DECISION", "decision", "WRONG_DECISION", "CONTRACT_FIELD_MISMATCH:decision"),
    _contract("LINEAGE_CONTRACT_REASON", "reason", "wrong reason", "CONTRACT_FIELD_MISMATCH:reason"),
    _contract("LINEAGE_CONTRACT_SOURCE", "source", "wrong.json", "CONTRACT_FIELD_MISMATCH:source"),
    _contract("LINEAGE_CONTRACT_BASE_MAIN_SHA", "base_main_sha", "0" * 40, "CONTRACT_FIELD_MISMATCH:base_main_sha"),
    _contract("LINEAGE_CONTRACT_FROZEN_CODE_SHA", "frozen_code_sha", "1" * 40, "CONTRACT_FIELD_MISMATCH:frozen_code_sha"),
    _contract("LINEAGE_CONTRACT_TREE_HASH", "implementation_tree_hash", "2" * 64, "CONTRACT_FIELD_MISMATCH:implementation_tree_hash"),
    _contract(
        "LINEAGE_CONTRACT_TREE_ALGORITHM",
        "implementation_tree_hash_algorithm",
        "sha256(wrong)",
        "CONTRACT_FIELD_MISMATCH:implementation_tree_hash_algorithm",
    ),
    _contract(
        "LINEAGE_CONTRACT_TREE_PATHS",
        "implementation_tree_paths",
        ["research/opening_range_retest_outcomes_v2"],
        "CONTRACT_FIELD_MISMATCH:implementation_tree_paths",
    ),
    _contract("LINEAGE_CONTRACT_INPUT_SOURCE_COUNT", "inputs.source_count", 1511, "CONTRACT_FIELD_MISMATCH:inputs.source_count"),
    _contract(
        "LINEAGE_CONTRACT_INPUT_SOURCE_HASH",
        "inputs.source_semantic_hash",
        "3" * 64,
        "CONTRACT_FIELD_MISMATCH:inputs.source_semantic_hash",
    ),
    _contract(
        "LINEAGE_CONTRACT_INPUT_CANDIDATE_COUNT",
        "inputs.candidate_count",
        2214,
        "CONTRACT_FIELD_MISMATCH:inputs.candidate_count",
    ),
    _contract(
        "LINEAGE_CONTRACT_INPUT_CANDIDATE_CORE_HASH",
        "inputs.candidate_core_semantic_hash",
        "4" * 64,
        "CONTRACT_FIELD_MISMATCH:inputs.candidate_core_semantic_hash",
    ),
    _contract(
        "LINEAGE_CONTRACT_INPUT_CANDIDATE_PROVENANCE_HASH",
        "inputs.candidate_provenance_semantic_hash",
        "5" * 64,
        "CONTRACT_FIELD_MISMATCH:inputs.candidate_provenance_semantic_hash",
    ),
    _contract("LINEAGE_CONTRACT_SOURCE_PREFIX", "source_authority.logical_prefix", "runtime/other", "CONTRACT_FIELD_MISMATCH:source_authority.logical_prefix"),
    _contract("LINEAGE_CONTRACT_SOURCE_MUTATE", "source_authority.mutate", True, "CONTRACT_FIELD_MISMATCH:source_authority.mutate"),
    _contract("LINEAGE_CONTRACT_SOURCE_COPY", "source_authority.copy", True, "CONTRACT_FIELD_MISMATCH:source_authority.copy"),
    _contract("LINEAGE_CONTRACT_SOURCE_SYMLINK", "source_authority.symlink", True, "CONTRACT_FIELD_MISMATCH:source_authority.symlink"),
    _contract("LINEAGE_CONTRACT_BAR_LABEL", "bars.label", "end-labelled 1-minute bars", "CONTRACT_FIELD_MISMATCH:bars.label"),
    _contract("LINEAGE_CONTRACT_BAR_TIMEZONE", "bars.session_timezone", "UTC", "CONTRACT_FIELD_MISMATCH:bars.session_timezone"),
    _contract("LINEAGE_CONTRACT_SESSION_START", "bars.session_start", "09:16", "CONTRACT_FIELD_MISMATCH:bars.session_start"),
    _contract("LINEAGE_CONTRACT_SESSION_LAST_START", "bars.session_last_start", "15:28", "CONTRACT_FIELD_MISMATCH:bars.session_last_start"),
    _contract("LINEAGE_CONTRACT_CADENCE", "bars.cadence_seconds", 120, "CONTRACT_FIELD_MISMATCH:bars.cadence_seconds"),
    _contract("LINEAGE_CONTRACT_ENTRY_RULE", "entry.primary_rule", "first bar at or after ready", "CONTRACT_FIELD_MISMATCH:entry.primary_rule"),
    _contract("LINEAGE_CONTRACT_ENTRY_PRICE", "entry.price", "close", "CONTRACT_FIELD_MISMATCH:entry.price"),
    _contract(
        "LINEAGE_CONTRACT_SAME_TIME_DISPOSITION",
        "entry.same_timestamp_bar_disposition",
        "INCLUDED",
        "CONTRACT_FIELD_MISMATCH:entry.same_timestamp_bar_disposition",
    ),
    _contract("LINEAGE_CONTRACT_HORIZONS", "horizons_minutes", [1, 5, 30], "CONTRACT_FIELD_MISMATCH:horizons_minutes"),
    _contract("LINEAGE_CONTRACT_HORIZON_1", "horizon_terminal_rule.1", "next close", "CONTRACT_FIELD_MISMATCH:horizon_terminal_rule.1"),
    _contract("LINEAGE_CONTRACT_HORIZON_3", "horizon_terminal_rule.3", "entry+3m close", "CONTRACT_FIELD_MISMATCH:horizon_terminal_rule.3"),
    _contract("LINEAGE_CONTRACT_HORIZON_5", "horizon_terminal_rule.5", "entry+5m close", "CONTRACT_FIELD_MISMATCH:horizon_terminal_rule.5"),
    _contract("LINEAGE_CONTRACT_HORIZON_15", "horizon_terminal_rule.15", "entry+15m close", "CONTRACT_FIELD_MISMATCH:horizon_terminal_rule.15"),
    _contract("LINEAGE_CONTRACT_HORIZON_30", "horizon_terminal_rule.30", "entry+30m close", "CONTRACT_FIELD_MISMATCH:horizon_terminal_rule.30"),
    _contract("LINEAGE_CONTRACT_HORIZON_SELECTION", "horizon_terminal_rule.selection", "fall forward", "CONTRACT_FIELD_MISMATCH:horizon_terminal_rule.selection"),
    _contract("LINEAGE_CONTRACT_RETURN_BUY_CALL", "returns.BUY_CALL", "terminal_close / entry_open", "CONTRACT_FIELD_MISMATCH:returns.BUY_CALL"),
    _contract("LINEAGE_CONTRACT_RETURN_BUY_PUT", "returns.BUY_PUT", "terminal_close / entry_open", "CONTRACT_FIELD_MISMATCH:returns.BUY_PUT"),
    _contract("LINEAGE_CONTRACT_RETURN_UNSIGNED", "returns.unsigned", "abs(close-open)", "CONTRACT_FIELD_MISMATCH:returns.unsigned"),
    _contract("LINEAGE_CONTRACT_MFE_MAE_INTERVAL", "mfe_mae.interval", "entry only", "CONTRACT_FIELD_MISMATCH:mfe_mae.interval"),
    _contract("LINEAGE_CONTRACT_BUY_CALL_MFE", "mfe_mae.BUY_CALL_MFE", "wrong", "CONTRACT_FIELD_MISMATCH:mfe_mae.BUY_CALL_MFE"),
    _contract("LINEAGE_CONTRACT_BUY_CALL_MAE", "mfe_mae.BUY_CALL_MAE", "wrong", "CONTRACT_FIELD_MISMATCH:mfe_mae.BUY_CALL_MAE"),
    _contract("LINEAGE_CONTRACT_BUY_PUT_MFE", "mfe_mae.BUY_PUT_MFE", "wrong", "CONTRACT_FIELD_MISMATCH:mfe_mae.BUY_PUT_MFE"),
    _contract("LINEAGE_CONTRACT_BUY_PUT_MAE", "mfe_mae.BUY_PUT_MAE", "wrong", "CONTRACT_FIELD_MISMATCH:mfe_mae.BUY_PUT_MAE"),
    _contract("LINEAGE_CONTRACT_MAE_SIGNED", "mfe_mae.mae_signed", False, "CONTRACT_FIELD_MISMATCH:mfe_mae.mae_signed"),
    _contract("LINEAGE_CONTRACT_OVERLAP_INTERVAL", "overlap.interval", "(entry, terminal)", "CONTRACT_FIELD_MISMATCH:overlap.interval"),
    _contract("LINEAGE_CONTRACT_OVERLAP_CANONICAL", "overlap.canonical", "removed", "CONTRACT_FIELD_MISMATCH:overlap.canonical"),
    _contract("LINEAGE_CONTRACT_CLAIM_BOUNDARY", "claim_boundary", ["DESCRIPTIVE_ONLY"], "CONTRACT_FIELD_MISMATCH:claim_boundary"),
    _contract("LINEAGE_CONTRACT_READ_ONLY", "read_only", False, "CONTRACT_FIELD_MISMATCH:read_only"),
    _contract("LINEAGE_CONTRACT_APPEND", "append", True, "CONTRACT_FIELD_MISMATCH:append"),
    _contract("LINEAGE_CONTRACT_ORDER_ACTION", "is_order_action", True, "CONTRACT_FIELD_MISMATCH:is_order_action"),
    _contract("LINEAGE_CONTRACT_BROKER_CALLED", "broker_api_called", True, "CONTRACT_FIELD_MISMATCH:broker_api_called"),
    _contract("LINEAGE_CONTRACT_LIVE_ALLOWED", "allowed_for_live_execution", True, "CONTRACT_FIELD_MISMATCH:allowed_for_live_execution"),
)

LINEAGE_SNAPSHOT_CASES: tuple[LineageControlCase, ...] = (
    _lineage("LINEAGE_FROZEN_SHA_MISSING", "frozen_sha", "", "FROZEN_CODE_SHA_NOT_ANCESTOR"),
    _lineage("LINEAGE_HEAD_SHA_MISSING", "head_sha", "", "FROZEN_CODE_SHA_NOT_ANCESTOR"),
    _lineage("LINEAGE_FROZEN_NOT_ANCESTOR", "is_ancestor", False, "FROZEN_CODE_SHA_NOT_ANCESTOR"),
    _lineage("LINEAGE_FROZEN_TREE_HASH", "frozen_tree_hash", "6" * 64, "IMPLEMENTATION_TREE_HASH_MISMATCH"),
    _lineage("LINEAGE_HEAD_TREE_HASH", "head_tree_hash", "7" * 64, "IMPLEMENTATION_TREE_HASH_MISMATCH"),
    _lineage("LINEAGE_POST_FREEZE_PATH", "changed_paths", ["research/opening_range_retest_outcomes_v2/oracle.py"], "POST_FREEZE_UNEXPECTED_PATH"),
)

LINEAGE_CONTROL_CASES: tuple[LineageControlCase, ...] = CONTRACT_SEMANTIC_FIELD_CASES + LINEAGE_SNAPSHOT_CASES
LINEAGE_MUTATION_SPECS: tuple[MutationSpec, ...] = tuple(case.mutation for case in LINEAGE_CONTROL_CASES)
LINEAGE_EXPECTATIONS: tuple[ControlExpectation, ...] = tuple(case.expectation for case in LINEAGE_CONTROL_CASES)

