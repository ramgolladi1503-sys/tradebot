"""Fail-closed prospective evaluation and integration governance."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from typing import Mapping

@dataclass(frozen=True)
class EvaluationResult:
    status: str
    candidate_sha: str
    index: str
    sample_count: int
    baseline: str

def evaluate_prospective(*, candidate_sha: str, index: str, predictions: tuple[Mapping[str, object], ...], outcomes: Mapping[str, Mapping[str, object]], model_sha: str, baseline: str, minimum_samples: int = 30) -> EvaluationResult:
    if len(candidate_sha) != 40 or len(model_sha) != 64: raise ValueError("EXACT_MODEL_BINDING_REQUIRED")
    if index not in {"NIFTY", "BANKNIFTY", "SENSEX"}: raise ValueError("INDEX_ID_REQUIRED")
    if len(predictions) < minimum_samples: return EvaluationResult("INSUFFICIENT_PROSPECTIVE_DATA", candidate_sha, index, len(predictions), baseline)
    for row in predictions:
        key = row.get("prediction_sha")
        if not key or key not in outcomes or outcomes[key].get("session") != row.get("session") or outcomes[key].get("index") != index:
            raise ValueError("PROSPECTIVE_PROVENANCE_MISMATCH")
        if row.get("future_data") or row.get("outcome") is not None: raise ValueError("PROSPECTIVE_LEAKAGE")
    return EvaluationResult("PROSPECTIVE_EVALUATED", candidate_sha, index, len(predictions), baseline)

def structural_edge_decision(*, candidate_sha: str, prospective_status: str, historical_oos: bool, cost_evidence: bool, robustness: bool, independent_verification: str) -> dict[str, object]:
    if len(candidate_sha) != 40: raise ValueError("EXACT_CANDIDATE_SHA_REQUIRED")
    status = "NOT_CERTIFIED"
    if prospective_status == "INVALIDATED": status = "INVALIDATED"
    elif prospective_status == "PROSPECTIVE_EVALUATED" and historical_oos and cost_evidence and robustness and independent_verification == "PASS": status = "CERTIFIED"
    return {"status": status, "candidate_sha": candidate_sha, "prediction_quality_is_not_edge": True, "immutable": True, "execution_authority": False}

def trading_integration_decision(*, candidate_sha: str) -> dict[str, object]:
    if len(candidate_sha) != 40: raise ValueError("EXACT_CANDIDATE_SHA_REQUIRED")
    return {"status": "SEPARATE_AUTHORIZATION_REQUIRED", "candidate_sha": candidate_sha, "broker_write_authority": False, "order_authority": False, "paper_authorized": False, "live_authorized": False, "immutable": True}
