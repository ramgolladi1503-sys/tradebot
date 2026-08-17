"""Fail-closed prospective evaluation and integration governance."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_CERTIFICATION_EVIDENCE = (
    "prospective",
    "historical_oos",
    "cost_evidence",
    "robustness",
    "independent_verification",
)


@dataclass(frozen=True)
class EvaluationResult:
    status: str
    candidate_sha: str
    index: str
    sample_count: int
    baseline: str


def _exact_git_sha(value: object) -> str:
    text = str(value or "").strip()
    if not _GIT_SHA_RE.fullmatch(text):
        raise ValueError("EXACT_CANDIDATE_SHA_REQUIRED")
    return text


def _exact_sha256(value: object) -> str:
    text = str(value or "").strip()
    if not _SHA256_RE.fullmatch(text):
        raise ValueError("EVIDENCE_ARTIFACT_SHA256_REQUIRED")
    return text


def evaluate_prospective(
    *,
    candidate_sha: str,
    index: str,
    predictions: tuple[Mapping[str, object], ...],
    outcomes: Mapping[str, Mapping[str, object]],
    model_sha: str,
    baseline: str,
    minimum_samples: int = 30,
) -> EvaluationResult:
    candidate_sha = _exact_git_sha(candidate_sha)
    if not _SHA256_RE.fullmatch(str(model_sha or "").strip()):
        raise ValueError("EXACT_MODEL_BINDING_REQUIRED")
    if index not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
        raise ValueError("INDEX_ID_REQUIRED")
    if len(predictions) < minimum_samples:
        return EvaluationResult(
            "INSUFFICIENT_PROSPECTIVE_DATA",
            candidate_sha,
            index,
            len(predictions),
            baseline,
        )
    for row in predictions:
        key = row.get("prediction_sha")
        if (
            not key
            or key not in outcomes
            or outcomes[key].get("session") != row.get("session")
            or outcomes[key].get("index") != index
        ):
            raise ValueError("PROSPECTIVE_PROVENANCE_MISMATCH")
        if row.get("future_data") or row.get("outcome") is not None:
            raise ValueError("PROSPECTIVE_LEAKAGE")
    return EvaluationResult(
        "PROSPECTIVE_EVALUATED",
        candidate_sha,
        index,
        len(predictions),
        baseline,
    )


def _load_evidence_artifact(
    *, candidate_sha: str, name: str, descriptor: Mapping[str, object] | None
) -> Mapping[str, object]:
    """Load and verify one immutable evidence artifact from its descriptor.

    T25 never treats caller-supplied PASS fields as evidence. The descriptor may
    identify only a regular, non-symlink JSON artifact and its expected SHA-256.
    The artifact bytes themselves are hashed and parsed here. The parsed payload
    must identify the evidence kind, bind the exact candidate SHA, and carry a
    PASS status before downstream gate-specific fields are consumed.
    """
    if not isinstance(descriptor, Mapping):
        raise ValueError(f"EDGE_EVIDENCE_DESCRIPTOR_INVALID:{name}")

    raw_path = descriptor.get("artifact_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"EDGE_EVIDENCE_ARTIFACT_PATH_REQUIRED:{name}")
    expected_sha = _exact_sha256(descriptor.get("artifact_sha256"))

    path = Path(raw_path).expanduser()
    if path.is_symlink():
        raise ValueError(f"EDGE_EVIDENCE_SYMLINK_REJECTED:{name}")
    if not path.is_file():
        raise ValueError(f"EDGE_EVIDENCE_ARTIFACT_MISSING:{name}")

    try:
        payload_bytes = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"EDGE_EVIDENCE_ARTIFACT_UNREADABLE:{name}") from exc

    actual_sha = hashlib.sha256(payload_bytes).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(f"EDGE_EVIDENCE_ARTIFACT_HASH_MISMATCH:{name}")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"EDGE_EVIDENCE_ARTIFACT_JSON_INVALID:{name}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"EDGE_EVIDENCE_ARTIFACT_PAYLOAD_INVALID:{name}")
    if payload.get("evidence_kind") != name:
        raise ValueError(f"EDGE_EVIDENCE_KIND_MISMATCH:{name}")
    if payload.get("status") != "PASS":
        raise ValueError(f"EDGE_EVIDENCE_NOT_PASS:{name}")
    if payload.get("candidate_sha") != candidate_sha:
        raise ValueError(f"EDGE_EVIDENCE_SHA_MISMATCH:{name}")
    return payload


def _validate_certification_evidence(
    *, candidate_sha: str, evidence: Mapping[str, Mapping[str, object]]
) -> Mapping[str, Mapping[str, object]]:
    missing = [name for name in _REQUIRED_CERTIFICATION_EVIDENCE if name not in evidence]
    if missing:
        raise ValueError(f"EDGE_EVIDENCE_MISSING:{','.join(missing)}")
    return {
        name: _load_evidence_artifact(
            candidate_sha=candidate_sha,
            name=name,
            descriptor=evidence[name],
        )
        for name in _REQUIRED_CERTIFICATION_EVIDENCE
    }


def structural_edge_decision(
    *,
    candidate_sha: str,
    prospective_status: str,
    historical_oos: bool,
    cost_evidence: bool,
    robustness: bool,
    independent_verification: str,
    evidence: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Return a fail-closed T25 structural-edge decision.

    T25 consumes verified artifacts; it does not manufacture evidence. Caller
    booleans/status strings are compatibility assertions only. A positive
    certification requires the complete exact-SHA evidence bundle, where every
    descriptor resolves to artifact bytes whose SHA-256 is verified here. An
    upstream INVALIDATED result requires its verified prospective artifact.
    Without adequate verified evidence, the decision remains NOT_CERTIFIED.
    """
    candidate_sha = _exact_git_sha(candidate_sha)
    status = "NOT_CERTIFIED"

    if evidence is not None and not isinstance(evidence, Mapping):
        raise ValueError("EDGE_EVIDENCE_BUNDLE_INVALID")

    if prospective_status == "INVALIDATED":
        if evidence is not None:
            prospective = _load_evidence_artifact(
                candidate_sha=candidate_sha,
                name="prospective",
                descriptor=evidence.get("prospective"),
            )
            if prospective.get("evaluation_status") != "INVALIDATED":
                raise ValueError("EDGE_EVIDENCE_PROSPECTIVE_STATUS_MISMATCH")
            status = "INVALIDATED"
    elif evidence is not None:
        validated = _validate_certification_evidence(
            candidate_sha=candidate_sha, evidence=evidence
        )
        prospective = validated["prospective"]
        historical = validated["historical_oos"]
        costs = validated["cost_evidence"]
        robust = validated["robustness"]
        verifier = validated["independent_verification"]

        if prospective.get("evaluation_status") != prospective_status:
            raise ValueError("EDGE_EVIDENCE_PROSPECTIVE_STATUS_MISMATCH")
        if bool(historical.get("qualified")) != bool(historical_oos):
            raise ValueError("EDGE_EVIDENCE_HISTORICAL_STATUS_MISMATCH")
        if bool(costs.get("qualified")) != bool(cost_evidence):
            raise ValueError("EDGE_EVIDENCE_COST_STATUS_MISMATCH")
        if bool(robust.get("qualified")) != bool(robustness):
            raise ValueError("EDGE_EVIDENCE_ROBUSTNESS_STATUS_MISMATCH")
        if str(verifier.get("verdict") or "") != str(independent_verification):
            raise ValueError("EDGE_EVIDENCE_VERIFIER_STATUS_MISMATCH")

        if (
            prospective_status == "PROSPECTIVE_EVALUATED"
            and historical_oos
            and cost_evidence
            and robustness
            and independent_verification == "PASS"
        ):
            status = "CERTIFIED"

    return {
        "status": status,
        "candidate_sha": candidate_sha,
        "prediction_quality_is_not_edge": True,
        "immutable": True,
        "execution_authority": False,
    }


def trading_integration_decision(*, candidate_sha: str) -> dict[str, object]:
    candidate_sha = _exact_git_sha(candidate_sha)
    return {
        "status": "SEPARATE_AUTHORIZATION_REQUIRED",
        "candidate_sha": candidate_sha,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "immutable": True,
    }
