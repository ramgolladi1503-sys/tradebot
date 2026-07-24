"""Deterministic blocker ledger and prioritization for authority matrix records."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping


PRIORITY_CLASSES = ("P1", "P2", "P3", "P4", "P5")
MAX_P1_BLOCKERS = 3
_REQUIRED_FIELDS = ("authority_target", "authority_kind", "authority_status", "blocker")
_NON_BLOCKING_STATUSES = {"PROVEN", "PASS", "READY", "CANONICAL_FAMILY_AUTHORITY_PROVEN"}


class AuthorityBlockersPriorityError(RuntimeError):
    """Base failure for blocker prioritization."""


class AuthorityMatrixInputError(AuthorityBlockersPriorityError):
    """Raised when an authority matrix record violates the input contract."""


class AuthorityBlockerInvariantError(AuthorityBlockersPriorityError):
    """Raised when generated blocker references are inconsistent."""


@dataclass(frozen=True)
class BlockerReference:
    authority_target: str
    authority_kind: str
    blocker_id: str


@dataclass(frozen=True)
class AuthorityBlockerRecord:
    blocker_id: str
    blocker_code: str
    completeness_class: str
    executable_priority: bool
    authority_targets: tuple[str, ...]
    authority_kinds: tuple[str, ...]


@dataclass(frozen=True)
class AuthorityBlockersPriorityResult:
    blockers: tuple[AuthorityBlockerRecord, ...]
    references: tuple[BlockerReference, ...]


def _required_text(record: Mapping[str, Any], field: str, index: int) -> str:
    if field not in record:
        raise AuthorityMatrixInputError(f"matrix record {index} missing required field {field!r}")
    value = record[field]
    if not isinstance(value, str) or not value.strip():
        raise AuthorityMatrixInputError(f"matrix record {index} field {field!r} must be non-empty text")
    return value.strip()


def _canonical_code(value: str) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    if not code:
        raise AuthorityMatrixInputError("blocker must contain an alphanumeric character")
    return code


def _blocker_id(blocker_code: str) -> str:
    digest = sha256(blocker_code.encode("ascii")).hexdigest()[:16]
    return f"authority-blocker-{digest}"


def _base_priority(kind: str, status: str, blocker_code: str) -> str:
    if blocker_code == "NO_TRADE_FILTER" or status == "NO_TRADE_FILTER":
        return "P5"
    if kind == "execution_readiness":
        return "P1"
    if kind == "signal_ledger":
        return "P2"
    if kind == "strategy_hypothesis":
        return "P2"
    if kind == "source_search":
        return "P3"
    if kind == "dataset_family":
        return "P4"
    return "P5"


def build_authority_blockers_priority(
    strategy_matrix_records: Iterable[Mapping[str, Any]],
) -> AuthorityBlockersPriorityResult:
    """Build a stable, deduplicated blocker ledger from strategy matrix records.

    Every blocked matrix row receives exactly one reference. Shared blocker codes
    produce one blocker record. At most three blocker classes may retain P1.
    """
    if isinstance(strategy_matrix_records, (str, bytes, Mapping)):
        raise AuthorityMatrixInputError("strategy_matrix_records must be an iterable of mappings")

    grouped: dict[str, dict[str, set[str]]] = {}
    row_refs: list[tuple[str, str, str]] = []
    seen_targets: set[tuple[str, str]] = set()
    try:
        records = list(strategy_matrix_records)
    except TypeError as exc:
        raise AuthorityMatrixInputError("strategy_matrix_records must be iterable") from exc

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise AuthorityMatrixInputError(f"matrix record {index} must be a mapping")
        target, kind, status, blocker = (_required_text(record, field, index) for field in _REQUIRED_FIELDS)
        target_key = (target, kind)
        if target_key in seen_targets:
            raise AuthorityMatrixInputError(f"duplicate authority matrix target {target!r} for kind {kind!r}")
        seen_targets.add(target_key)
        if status.upper() in _NON_BLOCKING_STATUSES:
            continue
        code = _canonical_code(blocker)
        blocker_id = _blocker_id(code)
        group = grouped.setdefault(code, {"targets": set(), "kinds": set(), "classes": set()})
        group["targets"].add(target)
        group["kinds"].add(kind)
        group["classes"].add(_base_priority(kind, status.upper(), code))
        row_refs.append((target, kind, blocker_id))

    base_class = {code: min(group["classes"], key=PRIORITY_CLASSES.index) for code, group in grouped.items()}
    p1_codes = sorted(code for code, priority in base_class.items() if priority == "P1")
    for code in p1_codes[MAX_P1_BLOCKERS:]:
        base_class[code] = "P2"

    blockers = tuple(
        AuthorityBlockerRecord(
            blocker_id=_blocker_id(code),
            blocker_code=code,
            completeness_class=base_class[code],
            executable_priority=base_class[code] in {"P1", "P2"} and code != "NO_TRADE_FILTER",
            authority_targets=tuple(sorted(grouped[code]["targets"])),
            authority_kinds=tuple(sorted(grouped[code]["kinds"])),
        )
        for code in sorted(grouped, key=lambda item: (PRIORITY_CLASSES.index(base_class[item]), item))
    )
    references = tuple(
        BlockerReference(target, kind, blocker_id)
        for target, kind, blocker_id in sorted(row_refs)
    )
    result = AuthorityBlockersPriorityResult(blockers=blockers, references=references)
    validate_no_orphan_references(result)
    return result


def validate_no_orphan_references(result: AuthorityBlockersPriorityResult) -> None:
    """Reject orphan references and unreferenced blocker records."""
    blocker_ids = [record.blocker_id for record in result.blockers]
    if len(blocker_ids) != len(set(blocker_ids)):
        raise AuthorityBlockerInvariantError("duplicate blocker_id in blocker ledger")
    referenced_ids = {reference.blocker_id for reference in result.references}
    orphan_ids = referenced_ids - set(blocker_ids)
    unreferenced_ids = set(blocker_ids) - referenced_ids
    if orphan_ids:
        raise AuthorityBlockerInvariantError(f"orphan blocker references: {sorted(orphan_ids)!r}")
    if unreferenced_ids:
        raise AuthorityBlockerInvariantError(f"unreferenced blocker records: {sorted(unreferenced_ids)!r}")
    if sum(record.completeness_class == "P1" for record in result.blockers) > MAX_P1_BLOCKERS:
        raise AuthorityBlockerInvariantError(f"P1 blocker count exceeds {MAX_P1_BLOCKERS}")
    if any(record.blocker_code == "NO_TRADE_FILTER" and record.executable_priority for record in result.blockers):
        raise AuthorityBlockerInvariantError("NO_TRADE_FILTER cannot be executable priority")


def blocker_records_as_dicts(result: AuthorityBlockersPriorityResult) -> list[dict[str, Any]]:
    """Return stable JSON-compatible records for evidence artifacts."""
    return [
        {
            "blocker_id": item.blocker_id,
            "blocker_code": item.blocker_code,
            "completeness_class": item.completeness_class,
            "executable_priority": item.executable_priority,
            "authority_targets": list(item.authority_targets),
            "authority_kinds": list(item.authority_kinds),
        }
        for item in result.blockers
    ]


def stable_result_digest(result: AuthorityBlockersPriorityResult) -> str:
    """Hash the complete semantic result, not merely its shape."""
    payload = {
        "blockers": blocker_records_as_dicts(result),
        "references": [reference.__dict__ for reference in result.references],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
