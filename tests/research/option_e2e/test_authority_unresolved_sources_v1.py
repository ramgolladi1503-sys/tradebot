from __future__ import annotations

from dataclasses import replace

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.unresolved_sources import (
    DuplicateCandidateMembershipError,
    MissingCandidateMembershipError,
    UniqueSourceDisposition,
    UnexpectedCandidateMembershipError,
    group_unresolved_candidates,
    reconcile_candidate_membership,
)


ZIP_HASH = "4" * 64


def _candidate(root_id: str, path: str, sha256: str | None) -> dict[str, object]:
    return {
        "candidate_id": f"{root_id}:{path}",
        "root_id": root_id,
        "relative_path": path,
        "sha256": sha256,
    }


def _evidence_rows() -> list[dict[str, object]]:
    return [
        _candidate("REGISTERED_WORKTREE_002", "runtime/replay.zip", ZIP_HASH),
        _candidate("MAIN_TRADEBOT", ".runtime/logs/trace.jsonl", None),
        _candidate("CURRENT_WORKTREE", "runtime/replay.zip", ZIP_HASH),
    ]


def test_grouping_is_deterministic_and_reconciles_exact_membership() -> None:
    rows = _evidence_rows()

    forward = group_unresolved_candidates(rows)
    reverse = group_unresolved_candidates(reversed(rows))

    assert forward == reverse
    assert [group.source_id for group in forward] == [
        "candidate:MAIN_TRADEBOT:.runtime/logs/trace.jsonl",
        f"sha256:{ZIP_HASH}",
    ]
    assert forward[0].disposition is UniqueSourceDisposition.UNIQUE_UNHASHED_SOURCE
    assert forward[0].candidate_ids == ("MAIN_TRADEBOT:.runtime/logs/trace.jsonl",)
    assert forward[1].disposition is UniqueSourceDisposition.EXACT_CONTENT_DUPLICATE_SOURCE
    assert forward[1].candidate_ids == (
        "CURRENT_WORKTREE:runtime/replay.zip",
        "REGISTERED_WORKTREE_002:runtime/replay.zip",
    )

    reconciliation = reconcile_candidate_membership(rows, forward)
    assert reconciliation.input_candidate_ids == reconciliation.grouped_candidate_ids
    assert reconciliation.source_count == 2


def test_hash_mutation_changes_source_identity_and_disposition() -> None:
    rows = _evidence_rows()
    rows[2] = {**rows[2], "sha256": "5" * 64}

    groups = group_unresolved_candidates(rows)

    assert tuple(group.source_id for group in groups) == (
        "candidate:MAIN_TRADEBOT:.runtime/logs/trace.jsonl",
        f"sha256:{ZIP_HASH}",
        f"sha256:{'5' * 64}",
    )
    assert {group.disposition for group in groups} == {
        UniqueSourceDisposition.UNIQUE_HASHED_SOURCE,
        UniqueSourceDisposition.UNIQUE_UNHASHED_SOURCE,
    }
    assert {group.source_id for group in groups} >= {f"sha256:{ZIP_HASH}", f"sha256:{'5' * 64}"}


def test_duplicate_group_membership_fails_with_typed_error() -> None:
    rows = _evidence_rows()
    groups = group_unresolved_candidates(rows)
    duplicated = (
        groups[0],
        replace(groups[1], candidate_ids=groups[1].candidate_ids + groups[0].candidate_ids),
    )

    with pytest.raises(DuplicateCandidateMembershipError, match="multiple source groups"):
        reconcile_candidate_membership(rows, duplicated)


def test_missing_group_membership_fails_with_typed_error() -> None:
    rows = _evidence_rows()
    groups = group_unresolved_candidates(rows)
    missing = (replace(groups[0], candidate_ids=()), groups[1])

    with pytest.raises(MissingCandidateMembershipError, match="MAIN_TRADEBOT"):
        reconcile_candidate_membership(rows, missing)


def test_unexpected_group_membership_is_not_allowed() -> None:
    rows = _evidence_rows()
    groups = group_unresolved_candidates(rows)
    unexpected = (
        replace(groups[0], candidate_ids=("UNSEEN:path",)),
        groups[1],
    )

    with pytest.raises(MissingCandidateMembershipError):
        reconcile_candidate_membership(rows, unexpected)

    no_missing = [rows[0], rows[2]]
    with pytest.raises(UnexpectedCandidateMembershipError, match="MAIN_TRADEBOT"):
        reconcile_candidate_membership(no_missing, groups)


def test_duplicate_input_candidate_fails_before_grouping() -> None:
    row = _evidence_rows()[0]

    with pytest.raises(DuplicateCandidateMembershipError, match="duplicate input"):
        group_unresolved_candidates([row, dict(row)])
