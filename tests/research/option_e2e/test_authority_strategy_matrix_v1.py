from __future__ import annotations

from copy import deepcopy

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.strategy_matrix import (
    AuthorityStrategyAliasError,
    AuthorityStrategyReconciliationError,
    AuthorityStrategyRegistryError,
    build_authority_strategy_matrix,
)
from research.option_e2e_recertification_v4.all_strategy_source_census_v1.census import (
    _strategy_specs,
)


def _registries(ids: tuple[str, ...] = ("ALPHA", "BETA")) -> tuple[list[dict[str, object]], ...]:
    inventory: list[dict[str, object]] = []
    aliases: list[dict[str, object]] = []
    readiness: list[dict[str, object]] = []
    for lane_id in ids:
        inventory.append(
            {
                "canonical_strategy_id": lane_id,
                "aliases": [lane_id, lane_id.lower()],
                "category": "mean_reversion",
                "implementation_path": f"strategies/{lane_id.lower()}.py",
                "implementation_commit": "commit",
                "implementation_blob_hash": f"hash-{lane_id}",
                "working_tree_file_hash": f"hash-{lane_id}",
                "parameter_owner": "owner",
                "resolved_required_parameters": ["window"],
                "temporal_contract": "CAUSAL_ONLY",
                "required_input_data": "UNDERLYING_CANDLE_DATASET",
                "valid_precomputed_signal_ledger": None,
                "invalidated_evidence": ["old"],
                "development_split_authority": "UNRESOLVED",
                "holdout_authority": "UNRESOLVED",
                "option_data_requirements": "NOT_EVALUATED",
                "current_status": "IMPLEMENTATION_BLOCKED",
            }
        )
        aliases.append(
            {"canonical_strategy_id": lane_id, "aliases": [lane_id.lower()]}
        )
        readiness.append(
            {
                "canonical_strategy_id": lane_id,
                "alias_group": [lane_id.lower()],
                "selected_canonical_dataset": f"VERSION:{lane_id}",
                "selected_canonical_signal_ledger": None,
                "implementation_authority": "commit",
                "parameter_authority": "owner",
                "split_authority": "UNRESOLVED",
                "development_session_count": 2,
                "holdout_session_count": 1,
                "option_coverage_readiness": "NOT_EVALUATED",
                "remaining_blocker": "INSUFFICIENT_SIGNAL_PROVENANCE",
                "recommended_next_action": "Freeze source set",
                "status": "READY_WITH_DATA_LIMITATIONS",
            }
        )
    return inventory, aliases, readiness


def test_builds_only_exact_canonical_strategy_lanes_with_complete_authority_fields() -> None:
    inventory, aliases, readiness = _registries()

    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
    )

    assert [row["canonical_strategy_id"] for row in matrix] == ["ALPHA", "BETA"]
    assert all(row["lane_kind"] == "SINGLE_ASSET_STRATEGY" for row in matrix)
    assert all("dataset_family_id" not in row for row in matrix)
    assert all(row["authority_status"] == "READY_WITH_DATA_LIMITATIONS" for row in matrix)
    assert matrix[0]["implementation_hash"] == "hash-ALPHA"
    assert matrix[0]["resolved_required_parameters"] == ["window"]
    assert matrix[0]["development_session_count"] == 2
    assert matrix[0]["read_only"] is True
    assert matrix[0]["is_order_action"] is False
    assert matrix[0]["broker_api_called"] is False
    assert matrix[0]["allowed_for_live_execution"] is False


def test_alias_ids_collapse_to_one_canonical_lane_and_mutation_changes_join() -> None:
    inventory, aliases, readiness = _registries(("ALPHA",))
    aliases[0]["aliases"] = ["alpha", "alpha legacy"]
    inventory[0]["canonical_strategy_id"] = "alpha legacy"
    readiness[0]["canonical_strategy_id"] = "alpha legacy"

    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
    )
    assert tuple(row["canonical_strategy_id"] for row in matrix) == ("ALPHA",)
    assert matrix[0]["canonical_strategy_id"] == "ALPHA"
    assert matrix[0]["aliases"] == ["ALPHA", "alpha", "alpha legacy"]

    mutated_aliases = deepcopy(aliases)
    mutated_aliases[0]["aliases"] = ["different"]
    with pytest.raises(AuthorityStrategyReconciliationError, match="unknown_strategy_lane"):
        build_authority_strategy_matrix(
            strategy_implementation_inventory=inventory,
            strategy_alias_registry=mutated_aliases,
            all_strategy_execution_readiness=readiness,
        )


def test_exact_lane_reconciliation_rejects_missing_and_conflicting_rows() -> None:
    inventory, aliases, readiness = _registries()
    with pytest.raises(AuthorityStrategyReconciliationError, match=r"missing=\['BETA'\]"):
        build_authority_strategy_matrix(
            strategy_implementation_inventory=inventory,
            strategy_alias_registry=aliases,
            all_strategy_execution_readiness=readiness[:-1],
        )

    duplicate = deepcopy(inventory[0])
    duplicate["canonical_strategy_id"] = "alpha"
    duplicate["implementation_blob_hash"] = "mutated"
    with pytest.raises(AuthorityStrategyRegistryError, match="conflicting_alias_rows"):
        build_authority_strategy_matrix(
            strategy_implementation_inventory=[*inventory, duplicate],
            strategy_alias_registry=aliases,
            all_strategy_execution_readiness=readiness,
        )


def test_alias_collision_is_a_typed_fail_closed_error() -> None:
    inventory, aliases, readiness = _registries()
    aliases[1]["aliases"] = ["alpha"]
    with pytest.raises(AuthorityStrategyAliasError, match="alias_collision"):
        build_authority_strategy_matrix(
            strategy_implementation_inventory=inventory,
            strategy_alias_registry=aliases,
            all_strategy_execution_readiness=readiness,
        )


def test_no_trade_filter_is_not_presented_as_an_execution_lane() -> None:
    inventory, aliases, readiness = _registries(("NO_TRADE_CHOP",))
    readiness[0]["status"] = "NO_TRADE_FILTER"
    readiness[0]["remaining_blocker"] = "NO_TRADE_FILTER"

    row = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
    )[0]

    assert row["lane_kind"] == "NO_TRADE_FILTER"
    assert row["selected_canonical_dataset"] is None
    assert row["selected_canonical_signal_ledger"] is None
    assert row["execution_eligible"] is False

    readiness[0]["status"] = "READY_FOR_CAUSAL_EXECUTION"
    with pytest.raises(AuthorityStrategyReconciliationError, match="invalid_no_trade_semantics"):
        build_authority_strategy_matrix(
            strategy_implementation_inventory=inventory,
            strategy_alias_registry=aliases,
            all_strategy_execution_readiness=readiness,
        )


def test_multi_asset_lane_rejects_generic_single_dataset_authority() -> None:
    inventory, aliases, readiness = _registries(("CONSTITUENT_BREADTH",))
    inventory[0]["category"] = "cross_asset"
    readiness[0]["status"] = "READY_FOR_CAUSAL_EXECUTION"
    readiness[0]["remaining_blocker"] = ""

    row = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
    )[0]

    assert row["lane_kind"] == "MULTI_ASSET_STRATEGY"
    assert row["selected_canonical_dataset"] is None
    assert row["selected_canonical_signal_ledger"] is None
    assert row["remaining_blocker"] == "MULTI_ASSET_DATASET_AUTHORITY_REQUIRED"
    assert row["authority_status"] == "MULTI_ASSET_AUTHORITY_REQUIRED"
    assert row["execution_eligible"] is False


def test_signal_authority_is_inherited_only_by_the_exact_linked_lane() -> None:
    inventory, aliases, readiness = _registries()
    for row in inventory:
        row["temporal_contract"] = "PRECOMPUTED_SIGNAL_LEDGER_REQUIRED"
    readiness[0]["selected_canonical_signal_ledger"] = "LEDGER:ALPHA"
    readiness[1]["selected_canonical_signal_ledger"] = "LEDGER:BETA"
    readiness[0]["status"] = "VALID_PRECOMPUTED_SIGNALS"

    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
        signal_ledger_assessments=[
            {
                "canonical_strategy_id": "ALPHA",
                "canonical_signal_ledger_id": "LEDGER:ALPHA",
                "authority_conclusion": "INSUFFICIENT_PROVENANCE",
            }
        ],
    )
    authority_by_lane = {
        row["canonical_strategy_id"]: (
            row["signal_ledger_status"],
            row["signal_authority"],
        )
        for row in matrix
    }
    assert authority_by_lane == {
        "ALPHA": ("LINKED", "INSUFFICIENT_PROVENANCE"),
        "BETA": ("NO_SIGNAL_LEDGER", "UNRESOLVED"),
    }
    assert matrix[0]["execution_eligible"] is False

    mutated = deepcopy(readiness)
    mutated[0]["selected_canonical_signal_ledger"] = "LEDGER:BETA"
    mutated_matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=mutated,
        signal_ledger_assessments=[
            {
                "canonical_strategy_id": "ALPHA",
                "canonical_signal_ledger_id": "LEDGER:ALPHA",
                "authority_conclusion": "INSUFFICIENT_PROVENANCE",
            }
        ],
    )
    assert mutated_matrix[0]["signal_authority"] != matrix[0]["signal_authority"]
    assert mutated_matrix[0]["signal_ledger_status"] == "NO_SIGNAL_LEDGER"


def test_causal_and_no_trade_lanes_have_not_applicable_signal_authority() -> None:
    inventory, aliases, readiness = _registries(("ALPHA", "NO_TRADE_CHOP"))
    readiness[0]["selected_canonical_signal_ledger"] = "UNLINKED:STALE"
    readiness[1]["status"] = "NO_TRADE_FILTER"
    readiness[1]["remaining_blocker"] = "NO_TRADE_FILTER"

    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
    )
    signal_semantics = {
        row["canonical_strategy_id"]: (
            row["signal_ledger_status"],
            row["signal_authority"],
            row["execution_eligible"],
        )
        for row in matrix
    }
    assert signal_semantics == {
        "ALPHA": ("NOT_APPLICABLE", "NOT_APPLICABLE", False),
        "NO_TRADE_CHOP": ("NOT_APPLICABLE", "NOT_APPLICABLE", False),
    }


def test_signal_assessment_cannot_cross_link_by_ledger_id_alone() -> None:
    inventory, aliases, readiness = _registries()
    for row in inventory:
        row["temporal_contract"] = "PRECOMPUTED_SIGNAL_LEDGER_REQUIRED"
    for row in readiness:
        row["selected_canonical_signal_ledger"] = "LEDGER:SHARED"

    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
        signal_ledger_assessments=[
            {
                "canonical_strategy_id": "BETA",
                "signal_ledger_id": "LEDGER:SHARED",
                "authority_conclusion": "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER",
            }
        ],
    )
    assert tuple(
        (row["canonical_strategy_id"], row["signal_authority"])
        for row in matrix
    ) == (
        ("ALPHA", "UNRESOLVED"),
        ("BETA", "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER"),
    )


def test_unknown_signal_conclusion_fails_closed() -> None:
    inventory, aliases, readiness = _registries(("ALPHA",))
    readiness[0]["selected_canonical_signal_ledger"] = "LEDGER:ALPHA"
    with pytest.raises(
        AuthorityStrategyRegistryError,
        match="invalid_signal_authority_conclusion",
    ):
        build_authority_strategy_matrix(
            strategy_implementation_inventory=inventory,
            strategy_alias_registry=aliases,
            all_strategy_execution_readiness=readiness,
            signal_ledger_assessments=[
                {
                    "canonical_strategy_id": "ALPHA",
                    "signal_ledger_id": "LEDGER:ALPHA",
                    "authority_conclusion": "APPROVED_BY_ASSERTION",
                }
            ],
        )


def test_real_census_registry_defines_exactly_sixteen_fixture_general_lanes() -> None:
    specs = _strategy_specs()
    expected_ids = (
        "VWAP_RECLAIM", "OPENING_RANGE_BREAKOUT", "OPENING_RANGE_RETEST", "TREND_PULLBACK",
        "COMPRESSION_BREAKOUT", "NO_TRADE_CHOP", "OPENING_STATE_MOMENTUM", "RSI2_MEAN_REVERSION",
        "RESIDUAL_MEAN_REVERSION", "CONSTITUENT_LEAD_LAG", "CONSTITUENT_BREADTH",
        "STRUCTURAL_PATTERN_SUITE", "STRUCTURAL_STATE_DISCOVERY", "ML_STRATEGY_DISCOVERY",
        "FIVE_MINUTE_GOVERNED_DISCOVERY", "CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY",
    )
    assert tuple(str(spec["canonical_strategy_id"]) for spec in specs) == expected_ids
    inventory, aliases, readiness = _registries(
        tuple(str(spec["canonical_strategy_id"]) for spec in specs)
    )
    for spec, row in zip(specs, inventory, strict=True):
        row["category"] = spec["category"]
    no_trade = next(row for row in readiness if row["canonical_strategy_id"] == "NO_TRADE_CHOP")
    no_trade["status"] = "NO_TRADE_FILTER"
    no_trade["remaining_blocker"] = "NO_TRADE_FILTER"

    matrix = build_authority_strategy_matrix(
        strategy_implementation_inventory=inventory,
        strategy_alias_registry=aliases,
        all_strategy_execution_readiness=readiness,
    )

    assert tuple(row["canonical_strategy_id"] for row in matrix) == tuple(sorted(expected_ids))
    assert {row["canonical_strategy_id"] for row in matrix} == {
        spec["canonical_strategy_id"] for spec in specs
    }
    assert sum(row["lane_kind"] == "NO_TRADE_FILTER" for row in matrix) == 1
    assert sum(row["lane_kind"] == "MULTI_ASSET_STRATEGY" for row in matrix) == 2
