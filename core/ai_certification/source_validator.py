from __future__ import annotations

from typing import Any

from .bundle import BundleError, CertificationBundle
from .contracts import EvidenceRef, GateResult, GateStatus
from .policy import CertificationPolicy


_EXPECTED_PRODUCER = "core.ai_certification.exporter.export_option_replay_wfa_bundle"
_REQUIRED_BASE_ROLES = ("wfa_report", "controls_input", "tests_input")
_PARTITION_FILES = ("summary.json", "trade_journal.json", "decision_samples.json")


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
        normalized_controls = bundle.read_json("negative_controls.json")
        normalized_tests = bundle.read_json("test_results.json")
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
    raw_wfa: dict[str, Any] = {}
    if not _is_frozen_source_artifact(bundle, wfa_report_path):
        problems.append("WFA_SOURCE_REPORT_NOT_FROZEN")
    else:
        try:
            raw_wfa = bundle.read_json(wfa_report_path)
        except BundleError:
            problems.append("WFA_SOURCE_REPORT_INVALID")

    roles = _validate_source_roles(
        bundle=bundle,
        source_index=source_index,
        raw_wfa=raw_wfa,
        problems=problems,
    )
    raw_controls = _read_role_object(
        bundle=bundle,
        roles=roles,
        role="controls_input",
        problems=problems,
    )
    raw_tests = _read_role_object(
        bundle=bundle,
        roles=roles,
        role="tests_input",
        problems=problems,
    )

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
    if raw_controls:
        _cross_check_controls(
            raw_controls=raw_controls,
            normalized_controls=normalized_controls,
            roles=roles,
            problems=problems,
        )
    if raw_tests:
        _cross_check_tests(
            raw_tests=raw_tests,
            normalized_tests=normalized_tests,
            bundle=bundle,
            roles=roles,
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
                EvidenceRef("negative_controls.json"),
                EvidenceRef("test_results.json"),
                EvidenceRef("dataset_manifest.json"),
            ),
            details={"problems": problems, "roles": roles},
        )

    return GateResult(
        gate=gate,
        status=GateStatus.PASS,
        reason_code="SOURCE_ARTIFACTS_FROZEN",
        summary=(
            "The raw WFA authority, required source roles, normalized controls and tests, "
            "and dataset file identity are mutually consistent."
        ),
        evidence_refs=(
            EvidenceRef("source_index.json"),
            EvidenceRef(wfa_report_path),
            EvidenceRef(roles["controls_input"]),
            EvidenceRef(roles["tests_input"]),
            EvidenceRef("engine_identity.json"),
            EvidenceRef("run_configuration.json"),
            EvidenceRef("dataset_manifest.json"),
        ),
    )


def _validate_source_roles(
    *,
    bundle: CertificationBundle,
    source_index: dict[str, Any],
    raw_wfa: dict[str, Any],
    problems: list[str],
) -> dict[str, str]:
    copied_files = source_index.get("copied_files")
    roles: dict[str, str] = {}
    if not isinstance(copied_files, list) or not copied_files:
        problems.append("SOURCE_FILE_INDEX_EMPTY")
        return roles
    for row in copied_files:
        if not isinstance(row, dict):
            problems.append("INVALID_SOURCE_FILE_INDEX_ROW")
            continue
        artifact = str(row.get("artifact") or "")
        role = str(row.get("role") or "")
        if not role:
            problems.append("SOURCE_FILE_ROLE_MISSING")
            continue
        if role in roles:
            problems.append(f"DUPLICATE_SOURCE_ROLE:{role}")
            continue
        roles[role] = artifact
        if not _is_frozen_source_artifact(bundle, artifact):
            problems.append(f"UNFROZEN_SOURCE_ARTIFACT:{artifact}")

    for role in _REQUIRED_BASE_ROLES:
        if role not in roles:
            problems.append(f"SOURCE_ROLE_MISSING:{role}")

    partitions = raw_wfa.get("partitions") if isinstance(raw_wfa, dict) else None
    if not isinstance(partitions, dict) or not partitions:
        problems.append("WFA_PARTITION_INDEX_MISSING")
        return roles
    for partition, result in partitions.items():
        if not isinstance(result, dict) or result.get("status") != "completed":
            continue
        for filename in _PARTITION_FILES:
            role = f"{partition}_{filename}"
            if role not in roles:
                problems.append(f"SOURCE_ROLE_MISSING:{role}")
    return roles


def _read_role_object(
    *,
    bundle: CertificationBundle,
    roles: dict[str, str],
    role: str,
    problems: list[str],
) -> dict[str, Any]:
    artifact = roles.get(role)
    if not artifact:
        return {}
    try:
        return bundle.read_json(artifact)
    except BundleError:
        problems.append(f"SOURCE_ROLE_INVALID_JSON:{role}")
        return {}


def _cross_check_wfa_authority(
    *,
    raw_wfa: dict[str, Any],
    engine_identity: dict[str, Any],
    run_configuration: dict[str, Any],
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
    raw_hash = str(raw_wfa.get("frozen_config_hash") or "")
    generated_hash = str(run_configuration.get("frozen_config_hash") or "")
    if not raw_hash or not generated_hash or raw_hash != generated_hash:
        problems.append("WFA_CONFIG_HASH_MISMATCH")


def _cross_check_controls(
    *,
    raw_controls: dict[str, Any],
    normalized_controls: dict[str, Any],
    roles: dict[str, str],
    problems: list[str],
) -> None:
    if raw_controls.get("controls") != normalized_controls.get("controls"):
        problems.append("SOURCE_CONTROLS_MISMATCH")
    if normalized_controls.get("source") not in (None, roles.get("controls_input")):
        problems.append("SOURCE_CONTROLS_POINTER_MISMATCH")


def _cross_check_tests(
    *,
    raw_tests: dict[str, Any],
    normalized_tests: dict[str, Any],
    bundle: CertificationBundle,
    roles: dict[str, str],
    problems: list[str],
) -> None:
    for field in ("collected", "passed", "failed", "errors"):
        if int(raw_tests.get(field, 0) or 0) != int(
            normalized_tests.get(field, 0) or 0
        ):
            problems.append(f"SOURCE_TEST_RESULTS_MISMATCH:{field}")
    raw_commit = str(
        raw_tests.get("repository_commit") or raw_tests.get("commit_sha") or ""
    )
    if raw_commit != str(normalized_tests.get("repository_commit") or ""):
        problems.append("SOURCE_TEST_COMMIT_MISMATCH")
    expected_match = bool(
        raw_commit and raw_commit == str(bundle.manifest.get("repository_commit") or "")
    )
    if normalized_tests.get("commit_matches_bundle") is not expected_match:
        problems.append("SOURCE_TEST_COMMIT_FLAG_MISMATCH")
    if normalized_tests.get("source") not in (None, roles.get("tests_input")):
        problems.append("SOURCE_TEST_POINTER_MISMATCH")


def _is_frozen_source_artifact(bundle: CertificationBundle, artifact: str) -> bool:
    normalized = artifact.replace("\\", "/")
    if not normalized.startswith("source/") or artifact not in bundle.artifacts:
        return False
    try:
        return bundle.artifact_path(artifact).is_file()
    except BundleError:
        return False
