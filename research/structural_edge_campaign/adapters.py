from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import CampaignContract


class CampaignAdapterError(ValueError):
    """Raised when upstream research artifacts cannot be adapted safely."""


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json_object(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise CampaignAdapterError(f"required artifact is missing: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise CampaignAdapterError(f"artifact must contain a JSON object: {source}")
    return payload


def _require_upstream_safety(payload: Mapping[str, Any], *, name: str) -> None:
    required = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    for field, expected in required.items():
        if payload.get(field) is not expected:
            raise CampaignAdapterError(
                f"{name}:{field} expected {expected}, got {payload.get(field)!r}"
            )


def build_ml_v2_development_evidence(
    *,
    contract: CampaignContract,
    hypothesis_id: str,
    side: str,
    frozen_candidates_path: str | Path,
    partition_registry_path: str | Path,
) -> dict[str, Any]:
    side = side.upper()
    if side not in {"LONG", "SHORT"}:
        raise CampaignAdapterError("side must be LONG or SHORT")
    try:
        hypothesis = next(
            item for item in contract.hypotheses if item.hypothesis_id == hypothesis_id
        )
    except StopIteration as exc:
        raise CampaignAdapterError(
            f"hypothesis is not preregistered: {hypothesis_id}"
        ) from exc
    expected_family = f"causal_ml_rule_discovery_{side.lower()}"
    if hypothesis.family != expected_family:
        raise CampaignAdapterError(
            f"{hypothesis_id}: family must be {expected_family!r}"
        )

    frozen_path = Path(frozen_candidates_path)
    partition_path = Path(partition_registry_path)
    frozen = load_json_object(frozen_path)
    partition = load_json_object(partition_path)
    _require_upstream_safety(frozen, name="frozen_candidates")
    _require_upstream_safety(partition, name="partition_registry")

    if partition.get("loaded_partition") != "DEVELOPMENT_V1":
        raise CampaignAdapterError("V2 development adapter requires DEVELOPMENT_V1")
    protected = {
        "validation_v1_consumed_loaded": partition.get(
            "validation_v1_consumed_loaded"
        ),
        "holdout_v1_locked_loaded": partition.get("holdout_v1_locked_loaded"),
        "fresh_confirmation_loaded": partition.get("fresh_confirmation_loaded"),
    }
    if any(value is not False for value in protected.values()):
        raise CampaignAdapterError(
            f"protected partition was loaded during development: {protected}"
        )

    candidates = frozen.get("candidates")
    if not isinstance(candidates, list):
        raise CampaignAdapterError("frozen_candidates:candidates must be a list")
    if len(candidates) > 1:
        raise CampaignAdapterError(
            "side-specific V2 run produced more than one frozen candidate"
        )

    candidate_hash: str | None = None
    verdict = "NO_STABLE_CANDIDATE"
    if candidates:
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            raise CampaignAdapterError("frozen candidate must be a JSON object")
        if candidate.get("side") != side:
            raise CampaignAdapterError(
                f"frozen candidate side mismatch: expected {side}"
            )
        candidate_hash = str(candidate.get("candidate_bundle_hash", "")).lower()
        if len(candidate_hash) != 64 or any(
            character not in "0123456789abcdef" for character in candidate_hash
        ):
            raise CampaignAdapterError("candidate_bundle_hash is invalid")
        if frozen.get("confirmation_token_issued") is not False:
            raise CampaignAdapterError(
                "development adapter refuses an already-unlocked candidate"
            )
        verdict = "CANDIDATE_FROZEN"

    upstream_verdict = str(frozen.get("verdict", ""))
    if not candidates and upstream_verdict != "NO_STABLE_CANDIDATE":
        raise CampaignAdapterError(
            "zero-candidate V2 artifact has an inconsistent verdict"
        )
    if candidates and "CANDIDATE_FROZEN" not in upstream_verdict:
        raise CampaignAdapterError(
            "frozen V2 candidate artifact has an inconsistent verdict"
        )

    return {
        "schema_version": "1.0",
        "stage": "development",
        "hypothesis_id": hypothesis.hypothesis_id,
        "family": hypothesis.family,
        "frozen_spec_sha256": hypothesis.frozen_spec_sha256,
        "verdict": verdict,
        "candidate_count": len(candidates),
        "candidate_bundle_hash": candidate_hash,
        **protected,
        "source_artifacts": {
            "frozen_candidates_sha256": sha256_file(frozen_path),
            "partition_registry_sha256": sha256_file(partition_path),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
