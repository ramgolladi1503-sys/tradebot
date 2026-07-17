from __future__ import annotations

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
        engine_identity = bundle.read_json("engine_identity.json")
        run_configuration = bundle.read_json("run_configuration.json")
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

    wfa_report_path = str(source_index.get("wfa_report") or "")
    raw_wfa: dict = {}
    if not _is_frozen_source_artifact(bundle, wfa_report_path):
        problems.append("WFA_SOURCE_REPORT_NOT_FROZEN")
    else:
        try:
            raw_wfa = bundle.read_json(wfa_report_path)
        except BundleError:
            problems.append("WFA_SOURCE_REPORT_INVALID")

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

    if raw_wfa:
        _cross_check_wfa_authority(
            raw_wfa=raw_wfa,
            engine_identity=engine_identity,
            run_configuration=run_configuration,
            bundle=bundle,
            problems=problems,
        )

    if problems:
        return GateResult(
            gate=gate,
            status=GateStatus.FAIL,
            reason_code=problems[0],
            summary=(
                "Raw WFA, generated authority fields, partition files, controls, tests, "
                "or dataset provenance are not frozen consistently."
            ),
            evidence_refs=(
                EvidenceRef("source_index.json"),
                EvidenceRef(wfa_report_path),
                EvidenceRef("engine_identity.json"),
                EvidenceRef("run_configuration.json"),
                EvidenceRef("dataset_manifest.json"),
            ),
            details={"problems": problems},
        )

    return GateResult(
        gate=gate,
        status=GateStatus.PASS,
        reason_code="SOURCE_ARTIFACTS_FROZEN",
        summary=(
            "The raw WFA authority, generated identity fields, source index, and dataset "
            "file identity are mutually consistent."
        ),
        evidence_refs=(
            EvidenceRef("source_index.json"),
            EvidenceRef(wfa_report_path),
            EvidenceRef("engine_identity.json"),
            EvidenceRef("run_configuration.json"),
            EvidenceRef("dataset_manifest.json"),
        ),
    )


def _cross_check_wfa_authority(
    *,
    raw_wfa: dict,
    engine_identity: dict,
    run_configuration: dict,
    bundle: CertificationBundle,
    problems: list[str],
) -> None:
    if str(raw_wfa.get("engine_module") or "") != str(
        engine_identity.get("engine_module") or ""
    ):
        problems.append("WFA_ENGINE_IDENTITY_MISMATCH")
    if raw_wfa.get("read_only") is not True:
        problems.append("WFA_SOURCE_NOT_READ_ONLY")
    if bool(raw_wfa.get("is_order_action")) or bool(raw_wfa.get("broker_api_called")):
        problems.append("WFA_SOURCE_ACTION_BOUNDARY_VIOLATION")
    if str(raw_wfa.get("run_id") or "") != str(bundle.manifest.get("run_id") or ""):
        problems.append("WFA_RUN_ID_MISMATCH")

    frozen = raw_wfa.get("frozen_config")
    base_config = frozen.get("base_config") if isinstance(frozen, dict) else None
    raw_mode = base_config.get("research_mode") if isinstance(base_config, dict) else None
    if str(raw_mode or "") != str(run_configuration.get("execution_mode") or ""):
        problems.append("WFA_EXECUTION_MODE_MISMATCH")
    if str(raw_wfa.get("frozen_config_hash") or "") != str(
        run_configuration.get("frozen_config_hash") or ""
    ):
        problems.append("WFA_CONFIG_HASH_MISMATCH")


def _is_frozen_source_artifact(bundle: CertificationBundle, artifact: str) -> bool:
    normalized = artifact.replace("\\", "/")
    if not normalized.startswith("source/") or artifact not in bundle.artifacts:
        return False
    try:
        return bundle.artifact_path(artifact).is_file()
    except BundleError:
        return False
