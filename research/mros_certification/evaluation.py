"""Fail-closed prospective evaluation and integration governance."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping


_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_EDGE_EVIDENCE = (
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


def _validate_edge_evidence(
    *, candidate_sha: str, evidence: Mapping[str, Mapping[str, object]] | None
) -> Mapping[str, Mapping[str, object]] | None:
    """Validate the immutable evidence bundle required for a T25 decision.

    Caller-supplied booleans/status strings are compatibility inputs, not authority.
    A positive certification or upstream invalidation requires exact-candidate,
    immutable evidence instead of a caller-selected status string.
    """
    if evidence is None:
        return None
    if not isinstance(evidence, Mapping):
        raise ValueError("EDGE_EVIDENCE_BUNDLE_INVALID")
    missing = [name for name in _REQUIRED_EDGE_EVIDENCE if name not in evidence]
    if missing:
        raise ValueError(f"EDGE_EVIDENCE_MISSING:{','.join(missing)}")

    for name in _REQUIRED_EDGE_EVIDENCE:
        item = evidence[name]
        if not isinstance(item, Mapping):
            raise ValueError(f"EDGE_EVIDENCE_INVALID:{name}")
        if item.get("status") != "PASS":
            raise ValueError(f"EDGE_EVIDENCE_NOT_PASS:{name}")
        if item.get("candidate_sha") != candidate_sha:
            raise ValueError(f"EDGE_EVIDENCE_SHA_MISMATCH:{name}")
        _exact_sha256(item.get("artifact_sha256"))
    return evidence


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

    T25 is decision machinery, not evidence production. Neither CERTIFIED nor
    INVALIDATED may be manufactured from caller-selected flags. Without a complete
    exact-SHA evidence bundle the decision remains NOT_CERTIFIED.
    """
    candidate_sha = _exact_git_sha(candidate_sha)
    validated = _validate_edge_evidence(candidate_sha=candidate_sha, evidence=evidence)
    status = "NOT_CERTIFIED"

    if validated is not None:
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

        if prospective_status == "INVALIDATED":
            status = "INVALIDATED"
        elif (
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
