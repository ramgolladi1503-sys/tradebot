from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "all-strategy-option-e2e-recertification-v4"
RESEARCH_ONLY = True
ALLOWED_FOR_LIVE_EXECUTION = False
BROKER_API_CALLED = False
IS_ORDER_ACTION = False


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


STAGE_FAILURES = {
    "G0": "G0_SOURCE_AUTHORITY_INVALID",
    "G1": "G1_SIGNAL_CONTRACT_INVALID",
    "G2": "G2_DIRECTION_MAPPING_INVALID",
    "G3": "G3_POINT_IN_TIME_UNIVERSE_INVALID",
    "G4": "G4_EXPIRY_UNRESOLVED",
    "G5": "G5_STRIKE_UNRESOLVED",
    "G6": "G6_ENTRY_QUOTE_INVALID",
    "G7": "G7_GEOMETRY_INVALID",
    "G8": "G8_OPTION_REPLAY_INVALID",
    "G9": "G9_ECONOMICS_INVALID",
    "G10": "G10_RECONCILIATION_INVALID",
    "G11": "G11_CONTROLS_INCOMPLETE",
    "G12": "G12_WFA_INCOMPLETE",
    "G13": "G13_SELECTION_NOT_FROZEN",
    "G14": "G14_HOLDOUT_CONTAMINATED",
    "G15": "G15_EVIDENCE_AUDIT_FAILED",
}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def semantic_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def write_json_with_sidecar(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


@dataclass(frozen=True)
class EvidenceEnvelope:
    campaign_id: str = CAMPAIGN_ID
    research_only: bool = RESEARCH_ONLY
    allowed_for_live_execution: bool = ALLOWED_FOR_LIVE_EXECUTION
    broker_api_called: bool = BROKER_API_CALLED
    is_order_action: bool = IS_ORDER_ACTION

    def validate(self) -> None:
        if not self.research_only:
            raise ValueError("research_only_must_be_true")
        if self.allowed_for_live_execution:
            raise ValueError("live_execution_forbidden")
        if self.broker_api_called:
            raise ValueError("broker_api_call_forbidden")
        if self.is_order_action:
            raise ValueError("order_action_forbidden")


@dataclass(frozen=True)
class GateRecord:
    gate_id: str
    strategy_id: str
    input_manifest_hash: str
    output_artifact_hash: str
    status: GateStatus
    reason_code: str
    row_counts: dict[str, int] = field(default_factory=dict)
    upstream_gate_id: str | None = None
    upstream_output_hash: str | None = None
    campaign_id: str = CAMPAIGN_ID
    research_only: bool = RESEARCH_ONLY
    allowed_for_live_execution: bool = ALLOWED_FOR_LIVE_EXECUTION
    broker_api_called: bool = BROKER_API_CALLED
    is_order_action: bool = IS_ORDER_ACTION

    def validate(self, *, expected_upstream_hash: str | None = None) -> None:
        EvidenceEnvelope(
            campaign_id=self.campaign_id,
            research_only=self.research_only,
            allowed_for_live_execution=self.allowed_for_live_execution,
            broker_api_called=self.broker_api_called,
            is_order_action=self.is_order_action,
        ).validate()
        if self.gate_id not in {f"G{i}" for i in range(17)}:
            raise ValueError("invalid_gate_id")
        if not self.input_manifest_hash or not self.output_artifact_hash:
            raise ValueError("missing_gate_hash")
        if expected_upstream_hash is not None and self.upstream_output_hash != expected_upstream_hash:
            raise ValueError("upstream_hash_mismatch")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
