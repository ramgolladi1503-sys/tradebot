from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


EXPECTED_LEDGER_SHA256 = "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed"
EXPECTED_ROW_COUNT = 24
EXPECTED_ARTIFACT_KIND = "MULTI_OWNER_BLOCKED_PLACEHOLDER_INVENTORY"
EXPECTED_VERDICT = "SIGNAL_LEDGER_INVALIDATED"
EXPECTED_DERIVED_REASON = "DERIVED_THROUGH_PROVEN_INVALIDATED_GENERATOR_BINDING"

REQUIRED_EVIDENCE_FILES = (
    "signal_ledger_provenance_summary.json",
    "signal_ledger_implementation_review.json",
    "signal_ledger_freeze_contamination_review.json",
    "signal_ledger_ownership_review.json",
    "external_evidence_manifest.json",
)

_SAFETY_FLAGS = {
    "research_only": True,
    "read_only": True,
    "allowed_for_live_execution": False,
    "broker_api_called": False,
    "is_order_action": False,
}


class ProvenanceEvidenceFailureCode(str, Enum):
    MISSING_FILE = "MISSING_FILE"
    SIDECAR_MISMATCH = "SIDECAR_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
    ARTIFACT_KIND_MISMATCH = "ARTIFACT_KIND_MISMATCH"
    VERDICT_MISMATCH = "VERDICT_MISMATCH"
    PRIMARY_ORACLE_DISAGREEMENT = "PRIMARY_ORACLE_DISAGREEMENT"
    MISSING_GENERATOR_BINDING = "MISSING_GENERATOR_BINDING"
    INVALIDATION_CONTRADICTION = "INVALIDATION_CONTRADICTION"
    WRONG_REASON_CODE = "WRONG_REASON_CODE"
    UNSAFE_SAFETY_FLAG = "UNSAFE_SAFETY_FLAG"
    MALFORMED_JSON = "MALFORMED_JSON"
    UNKNOWN_ENUM = "UNKNOWN_ENUM"
    SEMANTIC_MANIFEST_MISMATCH = "SEMANTIC_MANIFEST_MISMATCH"
    OWNERSHIP_CONTRADICTION = "OWNERSHIP_CONTRADICTION"


class ProvenanceEvidenceError(RuntimeError):
    def __init__(self, code: ProvenanceEvidenceFailureCode, detail: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {detail}")


@dataclass(frozen=True)
class SignalLedgerProvenanceEvidence:
    evidence_dir: Path
    physical_hash: str
    row_count: int
    artifact_kind: str
    verdict: str
    direct_ledger_invalidation_authority: str
    implementation_invalidation_authority: str
    derived_ledger_invalidation_authority: str
    derived_invalidation_reason_code: str
    generator_output_binding_status: str
    primary_oracle_agreement: str
    canonical_strategy_id: None
    introduction_commit: str
    introduction_status: str
    source_physical_sha256: Mapping[str, str]
    source_semantic_sha256: Mapping[str, str]

    def assessment_fields(self) -> dict[str, Any]:
        return {
            "provenance_ledger_hash": self.physical_hash,
            "provenance_row_count": self.row_count,
            "artifact_kind": self.artifact_kind,
            "artifact_verdict": self.verdict,
            "direct_ledger_invalidation_authority": self.direct_ledger_invalidation_authority,
            "implementation_invalidation_authority": self.implementation_invalidation_authority,
            "derived_ledger_invalidation_authority": self.derived_ledger_invalidation_authority,
            "derived_invalidation_reason_code": self.derived_invalidation_reason_code,
            "generator_output_binding_status": self.generator_output_binding_status,
            "primary_oracle_agreement": self.primary_oracle_agreement,
            "aggregate_canonical_strategy_id": self.canonical_strategy_id,
            **_SAFETY_FLAGS,
        }


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _fail(code: ProvenanceEvidenceFailureCode, detail: str) -> None:
    raise ProvenanceEvidenceError(code, detail)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(ProvenanceEvidenceFailureCode.MALFORMED_JSON, f"object_required field={field}")
    return value


def _known(value: Any, allowed: set[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(ProvenanceEvidenceFailureCode.UNKNOWN_ENUM, f"field={field} value={value!r}")
    return value


def _verify_sidecar(path: Path) -> str:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        missing = path if not path.is_file() else sidecar
        _fail(ProvenanceEvidenceFailureCode.MISSING_FILE, f"path={missing}")
    fields = sidecar.read_text(encoding="utf-8").split()
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(fields) != 2 or fields[1] != path.name or fields[0] != actual:
        _fail(ProvenanceEvidenceFailureCode.SIDECAR_MISMATCH, f"artifact={path.name}")
    return actual


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceEvidenceError(
            ProvenanceEvidenceFailureCode.MALFORMED_JSON,
            f"artifact={path.name}",
        ) from exc
    if not isinstance(payload, dict):
        _fail(ProvenanceEvidenceFailureCode.MALFORMED_JSON, f"root_object_required artifact={path.name}")
    return payload


def _verify_safety(payloads: Mapping[str, Mapping[str, Any]]) -> None:
    for name, payload in payloads.items():
        for field, expected in _SAFETY_FLAGS.items():
            if payload.get(field) is not expected:
                _fail(
                    ProvenanceEvidenceFailureCode.UNSAFE_SAFETY_FLAG,
                    f"artifact={name} field={field} expected={expected!r} actual={payload.get(field)!r}",
                )
        for field in ("outcomes_read", "pnl_read", "holdout_outcomes_read"):
            if field in payload and payload[field] is not False:
                _fail(
                    ProvenanceEvidenceFailureCode.UNSAFE_SAFETY_FLAG,
                    f"artifact={name} field={field} actual={payload[field]!r}",
                )


def load_signal_ledger_provenance_evidence(evidence_dir: Path) -> SignalLedgerProvenanceEvidence:
    evidence_dir = evidence_dir.resolve()
    payloads: dict[str, dict[str, Any]] = {}
    physical_hashes: dict[str, str] = {}
    for name in REQUIRED_EVIDENCE_FILES:
        path = evidence_dir / name
        physical_hashes[name] = _verify_sidecar(path)
        payloads[name] = _read_object(path)

    _verify_safety(payloads)
    manifest = payloads["external_evidence_manifest.json"]
    manifest_hashes = _mapping(manifest.get("artifact_semantic_sha256"), "artifact_semantic_sha256")
    semantic_hashes: dict[str, str] = {}
    for name in REQUIRED_EVIDENCE_FILES[:-1]:
        expected = manifest_hashes.get(name)
        actual = semantic_sha256(payloads[name])
        if expected != actual:
            _fail(
                ProvenanceEvidenceFailureCode.SEMANTIC_MANIFEST_MISMATCH,
                f"artifact={name} expected={expected!r} actual={actual}",
            )
        semantic_hashes[name] = actual
    semantic_hashes["external_evidence_manifest.json"] = semantic_sha256(manifest)

    summary = payloads["signal_ledger_provenance_summary.json"]
    ledger = _mapping(summary.get("ledger"), "ledger")
    if ledger.get("physical_sha256") != EXPECTED_LEDGER_SHA256:
        _fail(ProvenanceEvidenceFailureCode.HASH_MISMATCH, f"actual={ledger.get('physical_sha256')!r}")
    if ledger.get("row_count") != EXPECTED_ROW_COUNT:
        _fail(ProvenanceEvidenceFailureCode.ROW_COUNT_MISMATCH, f"actual={ledger.get('row_count')!r}")
    if ledger.get("artifact_kind") != EXPECTED_ARTIFACT_KIND:
        _fail(ProvenanceEvidenceFailureCode.ARTIFACT_KIND_MISMATCH, f"actual={ledger.get('artifact_kind')!r}")
    if summary.get("verdict") != EXPECTED_VERDICT:
        _fail(ProvenanceEvidenceFailureCode.VERDICT_MISMATCH, f"actual={summary.get('verdict')!r}")

    agreement = _mapping(summary.get("primary_oracle_agreement"), "primary_oracle_agreement")
    agreement_status = _known(agreement.get("status"), {"AGREEMENT", "DISAGREEMENT"}, "primary_oracle_agreement.status")
    checks = _mapping(agreement.get("checks"), "primary_oracle_agreement.checks")
    if agreement_status != "AGREEMENT" or not checks or any(value is not True for value in checks.values()):
        _fail(ProvenanceEvidenceFailureCode.PRIMARY_ORACLE_DISAGREEMENT, "agreement checks are not all true")

    implementation = payloads["signal_ledger_implementation_review.json"]
    historical_binding = _mapping(implementation.get("historical_binding"), "historical_binding")
    generator_binding = _mapping(historical_binding.get("generator_output_binding"), "generator_output_binding")
    binding_status = _known(generator_binding.get("status"), {"PROVEN", "UNRESOLVED"}, "generator_output_binding.status")
    bound_hashes = {
        generator_binding.get("historical_committed_sha256"),
        generator_binding.get("primary_regenerated_sha256"),
        generator_binding.get("independent_reconstruction_sha256"),
    }
    if (
        binding_status != "PROVEN"
        or generator_binding.get("byte_equality") is not True
        or generator_binding.get("semantic_equality") is not True
        or bound_hashes != {EXPECTED_LEDGER_SHA256}
    ):
        _fail(ProvenanceEvidenceFailureCode.MISSING_GENERATOR_BINDING, "generator output is not bound to exact ledger bytes")
    history = _mapping(historical_binding.get("history"), "historical_binding.history")
    introduction_status = _known(
        history.get("atomic_introduction_status"),
        {"PROVEN_WITH_PRIOR_LINEAGE"},
        "atomic_introduction_status",
    )
    introduction_commit = history.get("introduction_commit")
    if not isinstance(introduction_commit, str) or len(introduction_commit) != 40:
        _fail(ProvenanceEvidenceFailureCode.HASH_MISMATCH, "invalid introduction commit")

    freeze = payloads["signal_ledger_freeze_contamination_review.json"]
    direct = _known(
        freeze.get("direct_ledger_invalidation_authority"),
        {"UNRESOLVED", "CONFIRMED"},
        "direct_ledger_invalidation_authority",
    )
    implementation_authority = _known(
        freeze.get("implementation_invalidation_authority"),
        {"UNRESOLVED", "CONFIRMED"},
        "implementation_invalidation_authority",
    )
    derived = _known(
        freeze.get("derived_ledger_invalidation_authority"),
        {"UNRESOLVED", "CONFIRMED"},
        "derived_ledger_invalidation_authority",
    )
    historical_invalidation = _mapping(freeze.get("historical_invalidation"), "historical_invalidation")
    nested_authorities = (
        historical_invalidation.get("direct_ledger_invalidation_authority"),
        historical_invalidation.get("implementation_invalidation_authority"),
        historical_invalidation.get("derived_ledger_invalidation_authority"),
    )
    if (direct, implementation_authority, derived) != ("UNRESOLVED", "CONFIRMED", "CONFIRMED") or nested_authorities != (
        direct,
        implementation_authority,
        derived,
    ):
        _fail(ProvenanceEvidenceFailureCode.INVALIDATION_CONTRADICTION, "invalidation authorities disagree")
    reason = historical_invalidation.get("derived_reason_code")
    if reason != EXPECTED_DERIVED_REASON:
        _fail(ProvenanceEvidenceFailureCode.WRONG_REASON_CODE, f"actual={reason!r}")

    ownership = payloads["signal_ledger_ownership_review.json"]
    if (
        ownership.get("aggregate_canonical_strategy_id") is not None
        or ownership.get("aggregate_ledger_owner_model") != "MULTI_OWNER_PLACEHOLDER_INVENTORY"
    ):
        _fail(ProvenanceEvidenceFailureCode.OWNERSHIP_CONTRADICTION, "aggregate owner must remain unresolved")

    return SignalLedgerProvenanceEvidence(
        evidence_dir=evidence_dir,
        physical_hash=EXPECTED_LEDGER_SHA256,
        row_count=EXPECTED_ROW_COUNT,
        artifact_kind=EXPECTED_ARTIFACT_KIND,
        verdict=EXPECTED_VERDICT,
        direct_ledger_invalidation_authority=direct,
        implementation_invalidation_authority=implementation_authority,
        derived_ledger_invalidation_authority=derived,
        derived_invalidation_reason_code=reason,
        generator_output_binding_status=binding_status,
        primary_oracle_agreement=agreement_status,
        canonical_strategy_id=None,
        introduction_commit=introduction_commit,
        introduction_status=introduction_status,
        source_physical_sha256=dict(sorted(physical_hashes.items())),
        source_semantic_sha256=dict(sorted(semantic_hashes.items())),
    )
