from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path, PurePath
from typing import Any, Iterable, Mapping


FULL_ARTIFACTS = {
    "input": "input_census_integrity.json",
    "families": "dataset_family_authority_reviews.json",
    "versions": "dataset_version_authority_decisions.json",
    "signal": "signal_ledger_authority_review.json",
    "unresolved": "unresolved_source_authority_review.json",
    "strategies": "all_strategy_authority_matrix.json",
    "blockers": "authority_blocker_ledger.json",
    "priorities": "strategy_authority_prioritization.json",
}

COMPACT_ARTIFACTS = (
    "schema.json",
    "authority_closure_summary.json",
    "dataset_family_authority_summary.json",
    "dataset_version_authority_summary.json",
    "signal_ledger_authority_summary.json",
    "unresolved_source_authority_summary.json",
    "strategy_authority_summary.json",
    "blocker_summary.json",
    "priority_summary.json",
    "external_evidence_manifest.json",
)

SAFETY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "append": False,
}


class CompactPublicationError(RuntimeError):
    """Base error for compact authority publication failures."""


class StaleFullArtifactError(CompactPublicationError):
    """A full artifact no longer matches its physical sidecar."""


class CompactReconciliationError(CompactPublicationError):
    """Full authority artifacts disagree on counts or statuses."""


class NonPortableSemanticContentError(CompactPublicationError):
    """Semantic content contains a host-specific absolute path."""


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_hash(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _physical_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_verified_json(path: Path) -> Any:
    if not path.is_file():
        raise CompactPublicationError(f"missing_full_artifact name={path.name}")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file():
        raise StaleFullArtifactError(f"missing_full_artifact_sidecar name={path.name}")
    fields = sidecar.read_text(encoding="utf-8").split()
    if len(fields) < 2 or fields[1] != path.name or fields[0] != _physical_hash(path):
        raise StaleFullArtifactError(f"stale_full_artifact name={path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompactPublicationError(f"invalid_full_artifact_json name={path.name}") from exc


def _as_rows(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CompactReconciliationError(f"expected_record_array artifact={name}")
    return value


def _as_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CompactReconciliationError(f"expected_object artifact={name}")
    return value


def _counts(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "UNKNOWN") for row in rows).items()))


def _sum_counts(counts: Mapping[str, Any], label: str) -> int:
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values()):
        raise CompactReconciliationError(f"invalid_count_map field={label}")
    return sum(counts.values())


def _status_index(rows: Iterable[Mapping[str, Any]], id_key: str, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        item_id = str(row.get(id_key) or "")
        if not item_id or item_id in result:
            raise CompactReconciliationError(f"non_unique_authority_target field={label}")
        result[item_id] = str(row.get("authority_status") or "UNKNOWN")
    return result


def _assert_count(actual: int, expected: Any, field: str) -> None:
    if expected is not None and (not isinstance(expected, int) or isinstance(expected, bool) or actual != expected):
        raise CompactReconciliationError(
            f"count_reconciliation_failed field={field} expected={expected} actual={actual}"
        )


def _looks_absolute(value: str) -> bool:
    return PurePath(value).is_absolute() or (len(value) > 2 and value[1] == ":" and value[2] in "\\/")


def _reject_absolute_paths(value: Any, field: str = "$") -> None:
    if isinstance(value, str) and _looks_absolute(value):
        raise NonPortableSemanticContentError(f"absolute_path_in_semantic_content field={field}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_absolute_paths(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_absolute_paths(item, f"{field}[{index}]")


def _source_link(filename: str, payload: Any) -> dict[str, str]:
    return {"artifact": filename, "semantic_sha256": semantic_hash(payload)}


def _summary(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "authority_compact_publication_v1", "summary_kind": kind, **payload}


def generate_compact_payloads(full_payloads: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Generate reconciled, portable compact payloads from full authority payloads."""
    missing = sorted(set(FULL_ARTIFACTS) - set(full_payloads))
    if missing:
        raise CompactPublicationError(f"missing_full_payload_keys keys={','.join(missing)}")

    inputs = _as_object(full_payloads["input"], FULL_ARTIFACTS["input"])
    families = _as_rows(full_payloads["families"], FULL_ARTIFACTS["families"])
    versions = _as_rows(full_payloads["versions"], FULL_ARTIFACTS["versions"])
    signal = _as_object(full_payloads["signal"], FULL_ARTIFACTS["signal"])
    unresolved = _as_object(full_payloads["unresolved"], FULL_ARTIFACTS["unresolved"])
    matrix = _as_rows(full_payloads["strategies"], FULL_ARTIFACTS["strategies"])
    blockers = _as_rows(full_payloads["blockers"], FULL_ARTIFACTS["blockers"])
    priorities = _as_rows(full_payloads["priorities"], FULL_ARTIFACTS["priorities"])

    _assert_count(len(families), inputs.get("dataset_families"), "dataset_families")
    _assert_count(len(versions), inputs.get("dataset_versions"), "dataset_versions")
    _assert_count(
        int(signal.get("canonical_signal_ledger_count", 0)),
        inputs.get("canonical_signal_ledgers"),
        "canonical_signal_ledgers",
    )
    legacy_matrix = bool(matrix and "authority_target" in matrix[0])
    if legacy_matrix:
        family_matrix = [row for row in matrix if row.get("authority_kind") == "dataset_family"]
        _assert_count(len(family_matrix), len(families), "matrix_dataset_families")
        if _status_index(families, "dataset_family_id", "dataset_families") != _status_index(
            family_matrix, "authority_target", "matrix_dataset_families"
        ):
            raise CompactReconciliationError("status_reconciliation_failed field=dataset_families")
    else:
        _assert_count(len(matrix), inputs.get("strategy_lanes"), "strategy_lanes")

    blocker_counts = {
        str(row.get("blocker_code") or row.get("blocker_class") or "UNKNOWN"):
        len(row.get("authority_targets", [])) if "authority_targets" in row else row.get("blocked_lane_count")
        for row in blockers
    }
    blocked_lane_count = len({target for row in blockers for target in row.get("authority_targets", [])})
    if not blocked_lane_count:
        blocked_lane_count = _sum_counts(blocker_counts, "blocked_lane_count_by_class")
    strategy_rows = (
        [row for row in matrix if row.get("authority_kind") == "strategy_hypothesis"]
        if legacy_matrix
        else matrix
    )
    priority_ids = [str(row.get("canonical_strategy_id") or "") for row in priorities]
    if len(priority_ids) != len(set(priority_ids)) or any(not value for value in priority_ids):
        raise CompactReconciliationError("priority_strategy_ids_not_unique")
    if strategy_rows:
        matrix_statuses = (
            _status_index(strategy_rows, "authority_target", "matrix_strategies")
            if legacy_matrix
            else {
                str(row.get("canonical_strategy_id")): str(row.get("authority_status"))
                for row in strategy_rows
            }
        )
        if _status_index(priorities, "canonical_strategy_id", "priorities") != matrix_statuses:
            raise CompactReconciliationError("status_reconciliation_failed field=strategies")

    links = {key: _source_link(FULL_ARTIFACTS[key], full_payloads[key]) for key in FULL_ARTIFACTS}
    payloads: dict[str, dict[str, Any]] = {}
    payloads["schema.json"] = {
        "schema_version": "authority_compact_publication_v1",
        "artifact_names": list(COMPACT_ARTIFACTS),
        "semantic_hash_algorithm": "sha256_canonical_json_sort_keys_ascii",
        "physical_sidecar_format": "<sha256>  <filename>",
        "required_safety_flags": SAFETY_FLAGS,
        "full_artifact_inputs": dict(FULL_ARTIFACTS),
    }
    family_statuses = _counts(families, "authority_status")
    version_decisions = _counts(versions, "authority_decision")
    strategy_statuses = _counts(priorities, "authority_status")
    payloads["dataset_family_authority_summary.json"] = _summary("dataset_family_authority", {
        "dataset_family_count": len(families), "authority_status_counts": family_statuses,
        "source": links["families"],
    })
    payloads["dataset_version_authority_summary.json"] = _summary("dataset_version_authority", {
        "dataset_version_count": len(versions), "authority_decision_counts": version_decisions,
        "source": links["versions"],
    })
    payloads["signal_ledger_authority_summary.json"] = _summary("signal_ledger_authority", {
        **{key: signal.get(key) for key in sorted(signal) if key not in {"path", "exact_path"}},
        "source": links["signal"],
    })
    payloads["unresolved_source_authority_summary.json"] = _summary("unresolved_source_authority", {
        **unresolved, "source": links["unresolved"],
    })
    payloads["strategy_authority_summary.json"] = _summary("strategy_authority", {
        "strategy_count": len(priorities), "authority_status_counts": strategy_statuses,
        "remaining_blocker_counts": _counts(priorities, "remaining_blocker"),
        "sources": [links["strategies"], links["priorities"]],
    })
    payloads["blocker_summary.json"] = _summary("authority_blockers", {
        "blocked_lane_count": blocked_lane_count, "blocked_lane_count_by_class": blocker_counts,
        "source": links["blockers"],
    })
    payloads["priority_summary.json"] = _summary("strategy_priority", {
        "prioritized_strategy_count": len(priorities), "priority_counts": _counts(priorities, "priority"),
        "ordered_strategy_ids": [row["canonical_strategy_id"] for row in sorted(
            priorities, key=lambda row: (str(row.get("priority", "")), str(row.get("canonical_strategy_id", "")))
        )], "source": links["priorities"],
    })
    payloads["authority_closure_summary.json"] = _summary("authority_closure", {
        "authority_status": "BLOCKED_WITH_DECLARED_GAPS",
        "dataset_family_count": len(families), "dataset_version_count": len(versions),
        "canonical_signal_ledger_count": int(signal.get("canonical_signal_ledger_count", 0)),
        "unresolved_candidate_count": int(unresolved.get("unresolved_candidate_count", 0)),
        "strategy_count": len(priorities), "blocked_lane_count": blocked_lane_count,
        "input_authority_status": inputs.get("authority_status") or inputs.get("status"),
        "safety": dict(SAFETY_FLAGS), "sources": list(links.values()),
    })
    compact_links = {
        name: {"artifact": name, "semantic_sha256": semantic_hash(payload)}
        for name, payload in payloads.items()
    }
    payloads["external_evidence_manifest.json"] = {
        "schema_version": "authority_compact_publication_v1",
        "authority_status": payloads["authority_closure_summary.json"]["authority_status"],
        "safety": dict(SAFETY_FLAGS), "full_artifacts": links, "compact_artifacts": compact_links,
    }

    for name, payload in payloads.items():
        _reject_absolute_paths(payload, name)
    return {name: payloads[name] for name in COMPACT_ARTIFACTS}


def build_authority_compact_publication(
    *, full_authority_dir: Path, output_dir: Path, physical_sidecars: bool = True
) -> dict[str, dict[str, Any]]:
    """Validate full artifacts and atomically publish their compact representation."""
    full_payloads = {
        key: _read_verified_json(full_authority_dir / filename) for key, filename in FULL_ARTIFACTS.items()
    }
    payloads = generate_compact_payloads(full_payloads)
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = {name: canonical_json(payload) + "\n" for name, payload in payloads.items()}
    for name, content in rendered.items():
        (output_dir / name).write_text(content, encoding="utf-8")
        sidecar = output_dir / f"{name}.sha256"
        if physical_sidecars:
            sidecar.write_text(f"{hashlib.sha256(content.encode('utf-8')).hexdigest()}  {name}\n", encoding="utf-8")
        elif sidecar.exists():
            sidecar.unlink()
    return payloads


# Explicit alias for callers that use the longer lane name.
build_all_strategy_authority_compact_publication = build_authority_compact_publication
