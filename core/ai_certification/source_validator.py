from __future__ import annotations

from typing import Any

from .bundle import BundleError, CertificationBundle
from .contracts import EvidenceRef, GateResult, GateStatus
from .policy import CertificationPolicy


_EXPECTED_PRODUCER = "core.ai_certification.exporter.export_option_replay_wfa_bundle"


def validate_source_index(
    bundle: CertificationBundle,
    policy: CertificationPolicy,
) -> GateResult:
    del policy
    gate = "source_artifact_provenance"
    try:
        source_index = bundle.read_json("source_index.json")
        dataset_manifest = bundle.read_json("dataset_manifest.json")
    except BundleError as exc:
        return GateResult(
            gate=gate,
            status=GateStatus.UNEVALUATED,
            reason_code="SOURCE_INDEX_UNAVAILABLE",
            summary=str(exc),
            evidence_refs=(EvidenceRef("source_index.json"),),
        )

    problems: list[str] = []
    producer = str(source_index.get("producer") or "")
    if producer != _EXPECTED_PRODUCER:
        problems.append("UNKNOWN_BUNDLE_PRODUCER")

    wfa_report = str(source_index.get("wfa_report") or "")
    if not _is_frozen_source_artifact(bundle, wfa_report):
        problems.append("WFA_SOURCE_REPORT_NOT_FROZEN")

    copied_files = source_index.get("copied_files")
    if not isinstance(copied_files, list) or not copied_files:
        problems.append("SOURCE_FILE_INDEX_EMPTY")
    else:
        for row in copied_files:
            if not isinstance(row, dict):
                problems.append("INVALID_SOURCE_FILE_INDEX_ROW")
                continue
            artifact = str(row.get("artifact") or "")
            if not _is_frozen_source_artifact(bundle, artifact):
                problems.append(f"UNFROZEN_SOURCE_ARTIFACT:{artifact}")

    dataset = source_index.get("dataset")
    if not isinstance(dataset, dict):
        problems.append("DATASET_SOURCE_IDENTITY_MISSING")
    else:
        source_hash = str(dataset.get("file_sha256") or "")
        manifest_hash = str(dataset_manifest.get("dataset_sha256") or "")
        if not source_hash or source_hash != manifest_hash:
            problems.append("DATASET_SOURCE_HASH_MISMATCH")
        if int(dataset.get("size_bytes", 0) or 0) <= 0:
            problems.append("DATASET_SOURCE_SIZE_INVALID")

    if problems:
        return GateResult(
            gate=gate,
            status=GateStatus.FAIL,
            reason_code=problems[0],
            summary="Raw WFA, partition, control, test, or dataset provenance is not frozen consistently.",
            evidence_refs=(
                EvidenceRef("source_index.json"),
                EvidenceRef("dataset_manifest.json"),
            ),
            details={"problems": problems},
        )

    return GateResult(
        gate=gate,
        status=GateStatus.PASS,
        reason_code="SOURCE_ARTIFACTS_FROZEN",
        summary="The bundle contains a frozen source report index and matching dataset file identity.",
        evidence_refs=(
            EvidenceRef("source_index.json"),
            EvidenceRef("dataset_manifest.json"),
        ),
    )


def _is_frozen_source_artifact(bundle: CertificationBundle, artifact: str) -> bool:
    normalized = artifact.replace("\\", "/")
    if not normalized.startswith("source/") or artifact not in bundle.artifacts:
        return False
    try:
        return bundle.artifact_path(artifact).is_file()
    except BundleError:
        return False
