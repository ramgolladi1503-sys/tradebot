from dataclasses import replace

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.blockers_priority import (
    AuthorityBlockerInvariantError,
    AuthorityBlockersPriorityResult,
    AuthorityMatrixInputError,
    build_authority_blockers_priority,
    stable_result_digest,
    validate_no_orphan_references,
)


def _lane(lane_id: str = "VWAP_RECLAIM") -> dict[str, object]:
    return {
        "canonical_strategy_id": lane_id,
        "lane_kind": "SINGLE_ASSET_STRATEGY",
        "implementation_authority": "PROVEN",
        "parameter_authority": "PROVEN",
        "temporal_contract_authority": "PROVEN",
        "dataset_authority": "PROVEN",
        "signal_authority": "UNRESOLVED",
        "split_authority": "UNRESOLVED",
        "instrument_identity_authority": "PROVEN",
        "multi_asset_dependency_authority": "NOT_APPLICABLE",
        "source_search_authority": "PROVEN",
        "required_dataset_family_ids": ["FAMILY:NIFTY"],
        "required_dataset_version_ids": ["VERSION:NIFTY:1"],
        "signal_ledger_ids": ["LEDGER:VWAP:1"],
        "resolvable_locally": True,
    }


def _build(rows: list[dict[str, object]]):
    return build_authority_blockers_priority(
        rows,
        known_family_ids={"FAMILY:NIFTY"},
        known_version_ids={"VERSION:NIFTY:1"},
        known_signal_ledger_ids={"LEDGER:VWAP:1"},
    )


def test_emits_component_traceable_records_and_multiple_blockers_per_lane() -> None:
    result = _build([_lane()])
    blocker_classes = tuple(sorted(item.blocker_class for item in result.blockers))
    assert blocker_classes == ("SIGNAL", "SPLIT_FOLD")
    assert tuple(item.authority_kind for item in result.references) == ("signal", "split_fold")
    assert result.priorities[0].remaining_blocker_ids == tuple(sorted(item.blocker_id for item in result.blockers))
    for blocker in result.blockers:
        assert blocker.affected_strategy_ids == ("VWAP_RECLAIM",)
        assert blocker.affected_family_ids == ("FAMILY:NIFTY",)
        assert blocker.affected_version_ids == ("VERSION:NIFTY:1",)
        assert blocker.affected_signal_ledger_ids == ("LEDGER:VWAP:1",)
        assert blocker.resolvable_locally is True
        assert blocker.minimum_next_action.endswith(".")
        assert blocker.prohibited_shortcuts == (
            "Do not infer missing authority from entity type.",
            "Do not use outcome, PnL, paper, or live execution to fill the evidence gap.",
        )


def test_priority_is_component_derived_and_mutation_changes_it() -> None:
    baseline = _lane()
    first = _build([baseline])
    mutated = dict(baseline)
    mutated["implementation_authority"] = "UNRESOLVED"
    second = _build([mutated])
    assert first.priorities[0].priority_class == "P2"
    assert second.priorities[0].priority_class == "P3"
    assert first.priorities[0].component_completeness != second.priorities[0].component_completeness
    assert stable_result_digest(first) != stable_result_digest(second)


def test_same_lane_kind_with_different_evidence_has_different_priority() -> None:
    stronger = _lane("STRONGER")
    weaker = _lane("WEAKER")
    weaker["implementation_authority"] = "UNRESOLVED"
    result = _build([stronger, weaker])
    priorities = {item.canonical_strategy_id: item.priority_class for item in result.priorities}
    assert priorities == {"STRONGER": "P2", "WEAKER": "P3"}


def test_p1_is_capped_at_three_and_no_trade_is_p5() -> None:
    rows = []
    for index in range(4):
        row = _lane(f"READY_{index}")
        row["signal_authority"] = "PROVEN"
        row["split_authority"] = "PROVEN"
        rows.append(row)
    no_trade = _lane("NO_TRADE_CHOP")
    no_trade["lane_kind"] = "NO_TRADE_FILTER"
    rows.append(no_trade)
    result = _build(rows)
    p1_ids = tuple(item.canonical_strategy_id for item in result.priorities if item.priority_class == "P1")
    assert p1_ids == ("READY_0", "READY_1", "READY_2")
    no_trade_priority = next(item.priority_class for item in result.priorities if item.canonical_strategy_id == "NO_TRADE_CHOP")
    assert no_trade_priority == "P5"


def test_unknown_entity_references_fail_closed() -> None:
    lane = _lane()
    lane["required_dataset_version_ids"] = ["VERSION:UNKNOWN"]
    with pytest.raises(AuthorityMatrixInputError, match="unknown affected_version_ids"):
        _build([lane])


def test_orphan_and_unreferenced_mutations_fail_typed() -> None:
    valid = _build([_lane()])
    orphan = AuthorityBlockersPriorityResult(
        blockers=valid.blockers,
        references=(replace(valid.references[0], blocker_id="authority-blocker-missing"), *valid.references[1:]),
        priorities=valid.priorities,
    )
    with pytest.raises(AuthorityBlockerInvariantError, match="orphan blocker references"):
        validate_no_orphan_references(orphan)

    unreferenced = AuthorityBlockersPriorityResult(
        blockers=valid.blockers,
        references=valid.references[1:],
        priorities=valid.priorities,
    )
    with pytest.raises(AuthorityBlockerInvariantError, match="unreferenced blocker records"):
        validate_no_orphan_references(unreferenced)


def test_legacy_input_remains_deterministic_for_existing_integration() -> None:
    rows = [
        {"authority_target": "VWAP_RECLAIM", "authority_kind": "strategy_hypothesis", "authority_status": "BLOCKED", "blocker": "insufficient provenance"},
        {"authority_target": "ORB", "authority_kind": "strategy_hypothesis", "authority_status": "BLOCKED", "blocker": "insufficient provenance"},
    ]
    first = build_authority_blockers_priority(rows)
    second = build_authority_blockers_priority(reversed(rows))
    assert stable_result_digest(first) == stable_result_digest(second)
    affected = tuple(sorted(item.affected_strategy_ids for item in first.blockers))
    assert affected == (("ORB",), ("VWAP_RECLAIM",))
