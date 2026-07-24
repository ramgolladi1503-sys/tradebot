from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class UnresolvedSourceError(ValueError):
    """Base class for unresolved-source authority failures."""


class InvalidUnresolvedCandidateError(UnresolvedSourceError):
    """Raised when an unresolved candidate lacks a stable identity."""


class CandidateMembershipError(UnresolvedSourceError):
    """Base class for failures in exact candidate membership reconciliation."""


class DuplicateCandidateMembershipError(CandidateMembershipError):
    """Raised when a candidate is present more than once in source groups."""


class MissingCandidateMembershipError(CandidateMembershipError):
    """Raised when a candidate is absent from source groups."""


class UnexpectedCandidateMembershipError(CandidateMembershipError):
    """Raised when a source group contains a candidate outside the input set."""


class UniqueSourceDisposition(str, Enum):
    UNIQUE_UNHASHED_SOURCE = "UNIQUE_UNHASHED_SOURCE"
    UNIQUE_HASHED_SOURCE = "UNIQUE_HASHED_SOURCE"
    EXACT_CONTENT_DUPLICATE_SOURCE = "EXACT_CONTENT_DUPLICATE_SOURCE"


@dataclass(frozen=True, order=True)
class UnresolvedCandidate:
    candidate_id: str
    root_id: str
    relative_path: str
    sha256: str | None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> UnresolvedCandidate:
        root_id = _required_text(row, "root_id")
        relative_path = _required_text(row, "relative_path")
        expected_id = f"{root_id}:{relative_path}"
        candidate_id = row.get("candidate_id", expected_id)
        if not isinstance(candidate_id, str) or not candidate_id:
            raise InvalidUnresolvedCandidateError("candidate_id must be a non-empty string")
        if candidate_id != expected_id:
            raise InvalidUnresolvedCandidateError(
                f"candidate_id {candidate_id!r} does not match root/path identity {expected_id!r}"
            )
        sha256 = row.get("sha256")
        if sha256 is not None:
            if not isinstance(sha256, str) or len(sha256) != 64:
                raise InvalidUnresolvedCandidateError(
                    f"candidate {candidate_id!r} has an invalid sha256"
                )
            try:
                int(sha256, 16)
            except ValueError as exc:
                raise InvalidUnresolvedCandidateError(
                    f"candidate {candidate_id!r} has a non-hex sha256"
                ) from exc
            sha256 = sha256.lower()
        return cls(candidate_id, root_id, relative_path, sha256)


@dataclass(frozen=True)
class UnresolvedSourceGroup:
    source_id: str
    disposition: UniqueSourceDisposition
    sha256: str | None
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateMembershipReconciliation:
    input_candidate_ids: tuple[str, ...]
    grouped_candidate_ids: tuple[str, ...]
    source_count: int


def group_unresolved_candidates(
    rows: Iterable[Mapping[str, Any] | UnresolvedCandidate],
) -> tuple[UnresolvedSourceGroup, ...]:
    """Group candidates by exact content where proven, otherwise by identity."""

    candidates = tuple(_coerce_candidate(row) for row in rows)
    input_ids = [candidate.candidate_id for candidate in candidates]
    duplicate_inputs = _duplicates(input_ids)
    if duplicate_inputs:
        raise DuplicateCandidateMembershipError(
            f"duplicate input candidate membership: {', '.join(duplicate_inputs)}"
        )

    members_by_source: dict[str, list[UnresolvedCandidate]] = {}
    for candidate in candidates:
        source_id = (
            f"sha256:{candidate.sha256}"
            if candidate.sha256 is not None
            else f"candidate:{candidate.candidate_id}"
        )
        members_by_source.setdefault(source_id, []).append(candidate)

    groups: list[UnresolvedSourceGroup] = []
    for source_id, members in members_by_source.items():
        ordered_ids = tuple(sorted(member.candidate_id for member in members))
        sha256 = members[0].sha256
        if sha256 is None:
            disposition = UniqueSourceDisposition.UNIQUE_UNHASHED_SOURCE
        elif len(members) == 1:
            disposition = UniqueSourceDisposition.UNIQUE_HASHED_SOURCE
        else:
            disposition = UniqueSourceDisposition.EXACT_CONTENT_DUPLICATE_SOURCE
        groups.append(UnresolvedSourceGroup(source_id, disposition, sha256, ordered_ids))

    result = tuple(sorted(groups, key=lambda group: group.source_id))
    reconcile_candidate_membership(candidates, result)
    return result


def reconcile_candidate_membership(
    candidates: Iterable[Mapping[str, Any] | UnresolvedCandidate],
    groups: Sequence[UnresolvedSourceGroup],
) -> CandidateMembershipReconciliation:
    """Prove that groups contain every input candidate exactly once and no others."""

    expected_ids = tuple(sorted(_coerce_candidate(row).candidate_id for row in candidates))
    duplicate_inputs = _duplicates(expected_ids)
    if duplicate_inputs:
        raise DuplicateCandidateMembershipError(
            f"duplicate input candidate membership: {', '.join(duplicate_inputs)}"
        )

    grouped_ids = tuple(sorted(candidate_id for group in groups for candidate_id in group.candidate_ids))
    duplicate_grouped = _duplicates(grouped_ids)
    if duplicate_grouped:
        raise DuplicateCandidateMembershipError(
            f"candidates assigned to multiple source groups: {', '.join(duplicate_grouped)}"
        )

    expected_set = set(expected_ids)
    grouped_set = set(grouped_ids)
    missing = sorted(expected_set - grouped_set)
    if missing:
        raise MissingCandidateMembershipError(
            f"candidates missing from source groups: {', '.join(missing)}"
        )
    unexpected = sorted(grouped_set - expected_set)
    if unexpected:
        raise UnexpectedCandidateMembershipError(
            f"unexpected candidates in source groups: {', '.join(unexpected)}"
        )
    return CandidateMembershipReconciliation(expected_ids, grouped_ids, len(groups))


def _coerce_candidate(row: Mapping[str, Any] | UnresolvedCandidate) -> UnresolvedCandidate:
    if isinstance(row, UnresolvedCandidate):
        return row
    return UnresolvedCandidate.from_mapping(row)


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidUnresolvedCandidateError(f"{key} must be a non-empty string")
    return value


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)
