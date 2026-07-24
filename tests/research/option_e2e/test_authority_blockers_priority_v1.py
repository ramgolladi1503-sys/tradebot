from dataclasses import replace

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.blockers_priority import (
    AuthorityBlockerInvariantError,
    AuthorityBlockersPriorityResult,
    AuthorityMatrixInputError,
    BlockerReference,
    build_authority_blockers_priority,
    stable_result_digest,
    validate_no_orphan_references,
)


def _row(target: str, kind: str, blocker: str, status: str = "BLOCKED") -> dict[str, str]:
    return {
        "authority_target": target,
        "authority_kind": kind,
        "authority_status": status,
        "blocker": blocker,
    }


def test_shared_blockers_are_deduplicated_with_traceable_stable_references() -> None:
    rows = [
        _row("VWAP_RECLAIM", "strategy_hypothesis", "insufficient provenance"),
        _row("ORB", "strategy_hypothesis", "INSUFFICIENT_PROVENANCE"),
    ]

    first = build_authority_blockers_priority(rows)
    second = build_authority_blockers_priority(reversed(rows))

    assert first == second
    assert stable_result_digest(first) == stable_result_digest(second)
    assert tuple(item.blocker_code for item in first.blockers) == ("INSUFFICIENT_PROVENANCE",)
    blocker = first.blockers[0]
    assert blocker.blocker_code == "INSUFFICIENT_PROVENANCE"
    assert blocker.authority_targets == ("ORB", "VWAP_RECLAIM")
    assert {reference.blocker_id for reference in first.references} == {blocker.blocker_id}


def test_priority_classes_cover_p1_to_p5_and_p1_is_capped_at_three() -> None:
    rows = [
        _row(f"execution-{index}", "execution_readiness", f"critical-{index}")
        for index in range(4)
    ] + [
        _row("ledger", "signal_ledger", "ledger-gap"),
        _row("source", "source_search", "source-gap"),
        _row("dataset", "dataset_family", "dataset-gap"),
        _row("other", "unknown_kind", "other-gap"),
    ]

    result = build_authority_blockers_priority(rows)
    classes = {item.completeness_class for item in result.blockers}

    assert classes == {"P1", "P2", "P3", "P4", "P5"}
    assert sum(item.completeness_class == "P1" for item in result.blockers) == 3
    assert next(item for item in result.blockers if item.blocker_code == "CRITICAL_3").completeness_class == "P2"


def test_no_trade_filter_is_never_an_executable_p1() -> None:
    result = build_authority_blockers_priority(
        [_row("NO_TRADE_CHOP", "execution_readiness", "NO_TRADE_FILTER", "NO_TRADE_FILTER")]
    )

    blocker = result.blockers[0]
    assert blocker.completeness_class == "P5"
    assert blocker.executable_priority is False


def test_proven_matrix_rows_do_not_create_false_blockers() -> None:
    result = build_authority_blockers_priority([_row("ledger", "signal_ledger", "historical-note", "PROVEN")])
    assert result.blockers == ()
    assert result.references == ()


@pytest.mark.parametrize(
    "mutation",
    [
        {"authority_kind": "strategy_hypothesis", "authority_status": "BLOCKED", "blocker": "gap"},
        {"authority_target": "lane", "authority_kind": "", "authority_status": "BLOCKED", "blocker": "gap"},
        {"authority_target": "lane", "authority_kind": "strategy_hypothesis", "authority_status": "BLOCKED", "blocker": "---"},
    ],
)
def test_matrix_contract_mutations_fail_typed(mutation: dict[str, str]) -> None:
    with pytest.raises(AuthorityMatrixInputError):
        build_authority_blockers_priority([mutation])


def test_duplicate_matrix_target_mutation_fails_typed() -> None:
    row = _row("VWAP_RECLAIM", "strategy_hypothesis", "gap")
    with pytest.raises(AuthorityMatrixInputError, match="duplicate authority matrix target"):
        build_authority_blockers_priority([row, dict(row)])


def test_orphan_reference_mutation_fails_typed() -> None:
    valid = build_authority_blockers_priority([_row("VWAP_RECLAIM", "strategy_hypothesis", "gap")])
    mutated = AuthorityBlockersPriorityResult(
        blockers=valid.blockers,
        references=(replace(valid.references[0], blocker_id="authority-blocker-missing"),),
    )

    with pytest.raises(AuthorityBlockerInvariantError, match="orphan blocker references"):
        validate_no_orphan_references(mutated)


def test_unreferenced_blocker_mutation_fails_typed() -> None:
    valid = build_authority_blockers_priority([_row("VWAP_RECLAIM", "strategy_hypothesis", "gap")])
    mutated = AuthorityBlockersPriorityResult(blockers=valid.blockers, references=())

    with pytest.raises(AuthorityBlockerInvariantError, match="unreferenced blocker records"):
        validate_no_orphan_references(mutated)


def test_no_trade_executable_mutation_fails_typed() -> None:
    valid = build_authority_blockers_priority(
        [_row("NO_TRADE_CHOP", "strategy_hypothesis", "NO_TRADE_FILTER", "NO_TRADE_FILTER")]
    )
    mutated = AuthorityBlockersPriorityResult(
        blockers=(replace(valid.blockers[0], completeness_class="P1", executable_priority=True),),
        references=(BlockerReference("NO_TRADE_CHOP", "strategy_hypothesis", valid.blockers[0].blocker_id),),
    )

    with pytest.raises(AuthorityBlockerInvariantError, match="NO_TRADE_FILTER cannot be executable"):
        validate_no_orphan_references(mutated)
