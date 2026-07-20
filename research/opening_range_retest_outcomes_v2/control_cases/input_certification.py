from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from research.opening_range_retest_outcomes_v2.contract import (
    INPUT_CANDIDATE_COUNT,
    INPUT_SOURCE_COUNT,
)
from research.opening_range_retest_outcomes_v2.control_protocol import MutationSpec, RawExecution
from research.opening_range_retest_outcomes_v2.oracle import INPUT_FILES, verify_input_bundle

ARTIFACT_DIR = Path("docs/agent_reviews")


def input_certification_mutations() -> tuple[MutationSpec, ...]:
    sidecar_specs = tuple(
        MutationSpec(
            control_id=f"INPUT_SIDECAR_{name.upper()}",
            category="input_certification",
            mutation_kind="sidecar_hash",
            mutation_payload={"input_name": name},
            target_function="oracle.verify_input_bundle",
        )
        for name in INPUT_FILES
    )
    content_specs = (
        MutationSpec(
            control_id="INPUT_SOURCE_MANIFEST_HASH",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "source_manifest",
                "field_path": ("source_manifest_semantic_hash",),
                "value": "0" * 64,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_SOURCE_MANIFEST_COUNT",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "source_manifest",
                "field_path": ("record_count",),
                "value": INPUT_SOURCE_COUNT - 1,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_CANDIDATE_LEDGER_CORE_HASH",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "candidate_ledger",
                "field_path": ("candidate_core_semantic_hash",),
                "value": "0" * 64,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "candidate_ledger",
                "field_path": ("candidate_provenance_semantic_hash",),
                "value": "0" * 64,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_CANDIDATE_LEDGER_COUNT",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "candidate_ledger",
                "field_path": ("candidate_count",),
                "value": INPUT_CANDIDATE_COUNT - 1,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_SUMMARY_VERDICT",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "phase1_summary",
                "field_path": ("decision",),
                "value": "ORB_PHASE1_V2_NOT_CERTIFIED",
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_RECONCILIATION_VERDICT",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "reconciliation",
                "field_path": ("decision",),
                "value": "NOT_RECONCILED",
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_RECONCILIATION_V1_COUNT",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "reconciliation",
                "field_path": ("v1_unaffected_candidate_count",),
                "value": 0,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_RECONCILIATION_V2_COUNT",
            category="input_certification",
            mutation_kind="json_field",
            mutation_payload={
                "input_name": "reconciliation",
                "field_path": ("v2_unaffected_candidate_count",),
                "value": 0,
            },
            target_function="oracle.verify_input_bundle",
        ),
        MutationSpec(
            control_id="INPUT_DECEPTIVE_CERTIFICATION",
            category="input_certification",
            mutation_kind="text_append",
            mutation_payload={
                "input_name": "phase1_certification",
                "text": "\n- decision: NOT_ORB_PHASE1_V2_RECERTIFIED\n",
            },
            target_function="oracle.verify_input_bundle",
        ),
    )
    return sidecar_specs + content_specs


MUTATION_SPECS = input_certification_mutations()
EXPECTATIONS = {
    "INPUT_SIDECAR_SOURCE_MANIFEST": ("INPUT_SIDECAR_MISMATCH:source_manifest",),
    "INPUT_SIDECAR_CANDIDATE_LEDGER": ("INPUT_SIDECAR_MISMATCH:candidate_ledger",),
    "INPUT_SIDECAR_PHASE1_SUMMARY": ("INPUT_SIDECAR_MISMATCH:phase1_summary",),
    "INPUT_SIDECAR_RECONCILIATION": ("INPUT_SIDECAR_MISMATCH:reconciliation",),
    "INPUT_SIDECAR_PHASE1_CERTIFICATION": ("INPUT_SIDECAR_MISMATCH:phase1_certification",),
    "INPUT_SOURCE_MANIFEST_HASH": ("INPUT_SOURCE_MANIFEST_MISMATCH",),
    "INPUT_SOURCE_MANIFEST_COUNT": ("INPUT_SOURCE_MANIFEST_MISMATCH",),
    "INPUT_CANDIDATE_LEDGER_CORE_HASH": ("INPUT_CANDIDATE_LEDGER_MISMATCH",),
    "INPUT_CANDIDATE_LEDGER_PROVENANCE_HASH": ("INPUT_CANDIDATE_LEDGER_MISMATCH",),
    "INPUT_CANDIDATE_LEDGER_COUNT": ("INPUT_CANDIDATE_LEDGER_MISMATCH",),
    "INPUT_SUMMARY_VERDICT": ("INPUT_SUMMARY_VERDICT_MISMATCH",),
    "INPUT_RECONCILIATION_VERDICT": ("INPUT_RECONCILIATION_MISMATCH",),
    "INPUT_RECONCILIATION_V1_COUNT": ("INPUT_RECONCILIATION_MISMATCH",),
    "INPUT_RECONCILIATION_V2_COUNT": ("INPUT_RECONCILIATION_MISMATCH",),
    "INPUT_DECEPTIVE_CERTIFICATION": ("INPUT_CERTIFICATION_MISMATCH",),
}
def execute_input_certification_control(spec: MutationSpec) -> RawExecution:
    result = inspect_input_certification_mutation(spec)
    return RawExecution(
        observed_failures=tuple(result["failures"]),
        target_invoked=True,
        mutation_applied=result["before_hash"] != result["after_hash"],
        fixture_hash_before=str(result["before_hash"]),
        fixture_hash_after=str(result["after_hash"]),
        target_output_hash=_hash_payload(result["failures"]),
    )


EXECUTORS = {"*": execute_input_certification_control}


def inspect_input_certification_mutation(spec: MutationSpec) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="orb-input-certification-") as tmp_dir:
        root = Path(tmp_dir)
        _copy_clean_bundle(root)
        clean_failures = _verify(root)
        if clean_failures:
            snapshot = _bundle_snapshot(root)
            snapshot_hash = _hash_payload(snapshot)
            return {
                "before": snapshot,
                "after": snapshot,
                "before_hash": snapshot_hash,
                "after_hash": snapshot_hash,
                "failures": clean_failures,
            }

        before = _bundle_snapshot(root)
        _apply_mutation(root, spec)
        after = _bundle_snapshot(root)
        failures = _verify(root)
        return {
            "before": before,
            "after": after,
            "before_hash": _hash_payload(before),
            "after_hash": _hash_payload(after),
            "failures": failures,
        }


def verify_clean_input_fixture() -> tuple[str, ...]:
    with tempfile.TemporaryDirectory(prefix="orb-input-clean-") as tmp_dir:
        root = Path(tmp_dir)
        _copy_clean_bundle(root)
        return tuple(_verify(root))


def _copy_clean_bundle(root: Path) -> None:
    for filename in INPUT_FILES.values():
        source = ARTIFACT_DIR / filename
        target = root / filename
        shutil.copy2(source, target)
        shutil.copy2(source.with_suffix(source.suffix + ".sha256"), target.with_suffix(target.suffix + ".sha256"))


def _verify(root: Path) -> list[str]:
    *_unused, failures = verify_input_bundle(root)
    return failures


def _apply_mutation(root: Path, spec: MutationSpec) -> None:
    if spec.mutation_kind == "sidecar_hash":
        input_name = _input_name(spec)
        artifact = root / INPUT_FILES[input_name]
        sidecar = artifact.with_suffix(artifact.suffix + ".sha256")
        sidecar.write_text("0" * 64 + f"  {artifact.name}\n", encoding="utf-8")
        return
    if spec.mutation_kind == "json_field":
        input_name = _input_name(spec)
        artifact = root / INPUT_FILES[input_name]
        payload = _load_json(artifact)
        _set_path(payload, tuple(spec.mutation_payload["field_path"]), spec.mutation_payload["value"])
        _write_json(artifact, payload)
        _write_sidecar(artifact)
        return
    if spec.mutation_kind == "text_append":
        input_name = _input_name(spec)
        artifact = root / INPUT_FILES[input_name]
        artifact.write_text(artifact.read_text(encoding="utf-8") + str(spec.mutation_payload["text"]), encoding="utf-8")
        _write_sidecar(artifact)
        return
    raise ValueError(f"unsupported input certification mutation kind: {spec.mutation_kind}")


def _input_name(spec: MutationSpec) -> str:
    input_name = spec.mutation_payload["input_name"]
    if not isinstance(input_name, str) or input_name not in INPUT_FILES:
        raise ValueError(f"unsupported input artifact: {input_name!r}")
    return input_name


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")


def _set_path(payload: dict[str, Any], path: tuple[object, ...], value: object) -> None:
    cursor: Any = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def _write_sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(f"{_hash_file(path)}  {path.name}\n", encoding="utf-8")


def _bundle_snapshot(root: Path) -> dict[str, dict[str, str]]:
    return {
        name: {
            "artifact": _hash_file(root / filename),
            "sidecar": (root / filename).with_suffix((root / filename).suffix + ".sha256").read_text(encoding="utf-8"),
        }
        for name, filename in INPUT_FILES.items()
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
