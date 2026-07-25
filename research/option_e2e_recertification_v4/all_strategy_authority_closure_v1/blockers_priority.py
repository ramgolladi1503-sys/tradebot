"""Component-traceable authority blockers and lane completeness priorities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping


PRIORITY_CLASSES = ("P1", "P2", "P3", "P4", "P5")
MAX_P1_BLOCKERS = 3
_COMPONENT_FIELDS = (
    ("implementation", "implementation_authority"),
    ("parameter", "parameter_authority"),
    ("temporal_contract", "temporal_contract_authority"),
    ("dataset", "dataset_authority"),
    ("signal", "signal_authority"),
    ("split_fold", "split_authority"),
    ("instrument_identity", "instrument_identity_authority"),
    ("multi_asset_dependency", "multi_asset_dependency_authority"),
    ("source_search", "source_search_authority"),
)
_COMPLETE = {"PROVEN", "PASS", "READY", "NOT_APPLICABLE", "CANONICAL_FAMILY_AUTHORITY_PROVEN"}
_DEFAULT_ACTION = {
    "implementation": "Bind the lane to an immutable implementation hash.",
    "parameter": "Freeze and hash the complete parameter set.",
    "temporal_contract": "Prove causal feature and entry timestamps.",
    "dataset": "Resolve the required family and version authority.",
    "signal": "Generate a causally frozen signal ledger.",
    "split_fold": "Declare and freeze development, validation, and holdout identities.",
    "instrument_identity": "Resolve exact instrument identity and roll semantics.",
    "multi_asset_dependency": "Resolve every required asset dataset and alignment contract.",
    "source_search": "Complete the declared source search and provenance record.",
}
_PROHIBITED = (
    "Do not infer missing authority from entity type.",
    "Do not use outcome, PnL, paper, or live execution to fill the evidence gap.",
)


class AuthorityBlockersPriorityError(RuntimeError):
    """Base failure for blocker prioritization."""


class AuthorityMatrixInputError(AuthorityBlockersPriorityError):
    """Raised when an authority matrix record violates the input contract."""


class AuthorityBlockerInvariantError(AuthorityBlockersPriorityError):
    """Raised when blocker references are inconsistent."""


@dataclass(frozen=True)
class BlockerReference:
    authority_target: str
    authority_kind: str
    blocker_id: str


@dataclass(frozen=True)
class AuthorityBlockerRecord:
    blocker_id: str
    blocker_code: str
    blocker_class: str
    completeness_class: str
    executable_priority: bool
    authority_targets: tuple[str, ...]
    authority_kinds: tuple[str, ...]
    affected_strategy_ids: tuple[str, ...]
    affected_family_ids: tuple[str, ...]
    affected_version_ids: tuple[str, ...]
    affected_signal_ledger_ids: tuple[str, ...]
    why_it_blocks: str
    supporting_evidence: tuple[str, ...]
    resolvable_locally: bool
    minimum_next_action: str
    prohibited_shortcuts: tuple[str, ...]


@dataclass(frozen=True)
class LanePriorityRecord:
    canonical_strategy_id: str
    priority_class: str
    component_completeness: tuple[tuple[str, bool], ...]
    priority_reason_codes: tuple[str, ...]
    remaining_blocker_ids: tuple[str, ...]
    next_minimum_action: str


@dataclass(frozen=True)
class AuthorityBlockersPriorityResult:
    blockers: tuple[AuthorityBlockerRecord, ...]
    references: tuple[BlockerReference, ...]
    priorities: tuple[LanePriorityRecord, ...] = ()


def _text(record: Mapping[str, Any], field: str, index: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AuthorityMatrixInputError(f"matrix record {index} field {field!r} must be non-empty text")
    return value.strip()


def _ids(record: Mapping[str, Any], field: str, index: int) -> tuple[str, ...]:
    value = record.get(field, ())
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item for item in value):
        raise AuthorityMatrixInputError(f"matrix record {index} field {field!r} must be a sequence of IDs")
    return tuple(sorted(set(value)))


def _code(value: str) -> str:
    result = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    if not result:
        raise AuthorityMatrixInputError("blocker must contain an alphanumeric character")
    return result


def _blocker_id(component: str, evidence: Mapping[str, Any]) -> str:
    encoded = json.dumps({"component": component, "evidence": evidence}, sort_keys=True, separators=(",", ":"))
    return f"authority-blocker-{sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _is_complete(value: Any) -> bool:
    return isinstance(value, str) and value.upper() in _COMPLETE


def _priority(completeness: Mapping[str, bool], lane_kind: str, invalidated: bool) -> tuple[str, tuple[str, ...]]:
    if lane_kind == "NO_TRADE_FILTER" or invalidated:
        return "P5", ("INVALIDATED_OR_NOT_APPLICABLE",)
    complete_count = sum(completeness.values())
    signal_complete = completeness["signal"]
    if complete_count >= 8 and signal_complete:
        return "P1", ("NEAREST_TO_AUTHORITY_READY",)
    if complete_count >= 7:
        return "P2", ("TARGETED_PROVENANCE_REPAIR_REQUIRED",)
    if complete_count >= 3:
        return "P3", ("NEW_CAUSAL_SIGNAL_GENERATION_REQUIRED",)
    return "P4", ("RESEARCH_HYPOTHESIS_ONLY",)


def _legacy_components(record: Mapping[str, Any]) -> dict[str, Any]:
    status = str(record.get("authority_status", "UNRESOLVED"))
    return {field: status if component == "source_search" else "UNRESOLVED" for component, field in _COMPONENT_FIELDS}


def build_authority_blockers_priority(
    strategy_matrix_records: Iterable[Mapping[str, Any]],
    *,
    known_family_ids: Iterable[str] | None = None,
    known_version_ids: Iterable[str] | None = None,
    known_signal_ledger_ids: Iterable[str] | None = None,
) -> AuthorityBlockersPriorityResult:
    """Build blockers for every deficient component and evaluate each lane."""
    if isinstance(strategy_matrix_records, (str, bytes, Mapping)):
        raise AuthorityMatrixInputError("strategy_matrix_records must be an iterable of mappings")
    try:
        records = list(strategy_matrix_records)
    except TypeError as exc:
        raise AuthorityMatrixInputError("strategy_matrix_records must be iterable") from exc

    universes = {
        "affected_family_ids": None if known_family_ids is None else set(known_family_ids),
        "affected_version_ids": None if known_version_ids is None else set(known_version_ids),
        "affected_signal_ledger_ids": None if known_signal_ledger_ids is None else set(known_signal_ledger_ids),
    }
    blockers: dict[str, AuthorityBlockerRecord] = {}
    references: list[BlockerReference] = []
    priorities: list[LanePriorityRecord] = []
    seen_lanes: set[str] = set()

    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise AuthorityMatrixInputError(f"matrix record {index} must be a mapping")
        legacy = "canonical_strategy_id" not in raw
        lane = _text(raw, "authority_target" if legacy else "canonical_strategy_id", index)
        if lane in seen_lanes:
            raise AuthorityMatrixInputError(f"duplicate authority matrix target {lane!r}")
        seen_lanes.add(lane)
        lane_kind = str(raw.get("lane_kind", "STRATEGY")).upper()
        components = _legacy_components(raw) if legacy else {field: raw.get(field, "UNRESOLVED") for _, field in _COMPONENT_FIELDS}
        completeness = {component: _is_complete(components[field]) for component, field in _COMPONENT_FIELDS}
        invalidated = bool(raw.get("historical_invalidation"))
        priority_class, reason_codes = _priority(completeness, lane_kind, invalidated)
        entity_refs = {
            "affected_family_ids": _ids(raw, "required_dataset_family_ids", index),
            "affected_version_ids": _ids(raw, "required_dataset_version_ids", index),
            "affected_signal_ledger_ids": _ids(raw, "signal_ledger_ids", index),
        }
        for field, values in entity_refs.items():
            universe = universes[field]
            unknown = set(values) - universe if universe is not None else set()
            if unknown:
                raise AuthorityMatrixInputError(f"unknown {field}: {sorted(unknown)!r}")

        blocker_ids: list[str] = []
        if legacy and str(raw.get("authority_status", "")).upper() in _COMPLETE:
            deficient: list[tuple[str, str]] = []
        elif legacy:
            deficient = [(str(raw.get("authority_kind", "source_search")), _text(raw, "blocker", index))]
        else:
            deficient = [(component, f"{component}_authority_incomplete") for component in completeness if not completeness[component]]
        for component, reason in deficient:
            blocker_class = _code(component)
            evidence = {
                "component": component,
                "affected_strategy_id": lane,
                "authority_value": components.get(dict(_COMPONENT_FIELDS).get(component), raw.get("authority_status")),
                **entity_refs,
            }
            blocker_id = _blocker_id(component, evidence)
            blocker_ids.append(blocker_id)
            supporting = tuple(sorted(f"{key}={value}" for key, value in evidence.items()))
            record = AuthorityBlockerRecord(
                blocker_id=blocker_id,
                blocker_code=_code(reason),
                blocker_class=blocker_class,
                completeness_class=priority_class,
                executable_priority=priority_class in {"P1", "P2"} and lane_kind != "NO_TRADE_FILTER",
                authority_targets=(lane,), authority_kinds=(component,), affected_strategy_ids=(lane,),
                affected_family_ids=entity_refs["affected_family_ids"], affected_version_ids=entity_refs["affected_version_ids"],
                affected_signal_ledger_ids=entity_refs["affected_signal_ledger_ids"],
                why_it_blocks=f"{component} authority is incomplete: {reason}", supporting_evidence=supporting,
                resolvable_locally=bool(raw.get("resolvable_locally", False)),
                minimum_next_action=str(raw.get("minimum_next_actions", {}).get(component, _DEFAULT_ACTION.get(component, "Resolve the declared authority evidence gap."))),
                prohibited_shortcuts=tuple(raw.get("prohibited_shortcuts", _PROHIBITED)),
            )
            existing = blockers.get(blocker_id)
            if existing is not None and existing != record:
                raise AuthorityBlockerInvariantError(f"conflicting blocker evidence for {blocker_id}")
            blockers[blocker_id] = record
            references.append(BlockerReference(lane, component, blocker_id))
        priorities.append(LanePriorityRecord(
            canonical_strategy_id=lane, priority_class=priority_class,
            component_completeness=tuple(completeness.items()), priority_reason_codes=reason_codes,
            remaining_blocker_ids=tuple(sorted(blocker_ids)),
            next_minimum_action="No authority action applicable." if not blocker_ids else blockers[sorted(blocker_ids)[0]].minimum_next_action,
        ))

    ordered_priorities = sorted(priorities, key=lambda item: (PRIORITY_CLASSES.index(item.priority_class), item.canonical_strategy_id))
    p1_lanes = [item for item in ordered_priorities if item.priority_class == "P1"]
    if len(p1_lanes) > MAX_P1_BLOCKERS:
        demoted = {item.canonical_strategy_id for item in p1_lanes[MAX_P1_BLOCKERS:]}
        ordered_priorities = [
            LanePriorityRecord(item.canonical_strategy_id, "P2", item.component_completeness,
                               ("P1_CAP_APPLIED",), item.remaining_blocker_ids, item.next_minimum_action)
            if item.canonical_strategy_id in demoted else item for item in ordered_priorities
        ]
    result = AuthorityBlockersPriorityResult(
        blockers=tuple(sorted(blockers.values(), key=lambda item: item.blocker_id)),
        references=tuple(sorted(references, key=lambda item: (item.authority_target, item.authority_kind, item.blocker_id))),
        priorities=tuple(ordered_priorities),
    )
    validate_no_orphan_references(result)
    return result


def validate_no_orphan_references(result: AuthorityBlockersPriorityResult) -> None:
    blocker_ids = {record.blocker_id for record in result.blockers}
    referenced_ids = {reference.blocker_id for reference in result.references}
    if referenced_ids - blocker_ids:
        raise AuthorityBlockerInvariantError(f"orphan blocker references: {sorted(referenced_ids - blocker_ids)!r}")
    if blocker_ids - referenced_ids:
        raise AuthorityBlockerInvariantError(f"unreferenced blocker records: {sorted(blocker_ids - referenced_ids)!r}")
    if sum(item.priority_class == "P1" for item in result.priorities) > MAX_P1_BLOCKERS:
        raise AuthorityBlockerInvariantError(f"P1 lane count exceeds {MAX_P1_BLOCKERS}")
    if any(item.canonical_strategy_id == "NO_TRADE_CHOP" and item.priority_class != "P5" for item in result.priorities):
        raise AuthorityBlockerInvariantError("NO_TRADE_CHOP must be P5")


def blocker_records_as_dicts(result: AuthorityBlockersPriorityResult) -> list[dict[str, Any]]:
    return [{**asdict(item), "authority_targets": list(item.authority_targets), "authority_kinds": list(item.authority_kinds),
             "affected_strategy_ids": list(item.affected_strategy_ids), "affected_family_ids": list(item.affected_family_ids),
             "affected_version_ids": list(item.affected_version_ids), "affected_signal_ledger_ids": list(item.affected_signal_ledger_ids),
             "supporting_evidence": list(item.supporting_evidence), "prohibited_shortcuts": list(item.prohibited_shortcuts)} for item in result.blockers]


def stable_result_digest(result: AuthorityBlockersPriorityResult) -> str:
    payload = {"blockers": blocker_records_as_dicts(result), "references": [asdict(item) for item in result.references],
               "priorities": [asdict(item) for item in result.priorities]}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
