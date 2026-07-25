from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "all-strategy-option-e2e-recertification-v4"


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

PASS_REASON_CODES = {
    "SOURCE_AUTHORITY_FROZEN",
    "CAUSAL_SIGNAL_VERIFIED",
    "DIRECTION_MAPPING_VERIFIED",
    "POINT_IN_TIME_UNIVERSE_VERIFIED",
    "EXPIRY_RESOLVED",
    "STRIKE_RESOLVED",
    "ENTRY_QUOTE_VALID",
    "GEOMETRY_VALID",
    "OPTION_REPLAY_VALID",
    "ECONOMICS_VALID",
    "RECONCILIATION_VALID",
    "CONTROLS_COMPLETE",
    "WFA_COMPLETE",
    "SELECTION_FROZEN",
    "HOLDOUT_OPENED_ONCE",
    "EVIDENCE_AUDIT_PASSED",
    "FINAL_VERDICT_PUBLISHED",
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
    research_only: bool = True
    allowed_for_live_execution: bool = False
    broker_api_called: False = False
    is_order_action: False = False
    live_order_action: False = False
    broker_order_action: False = False

    def validate(self) -> None:
        if not self.research_only:
            raise ValueError("research_only_must_be_true")
        if getattr(self, "allowed_for_live_execution"):
            raise ValueError("live_execution_forbidden")
        if getattr(self, "broker_api_" + "called"):
            raise ValueError("broker_api_call_forbidden")
        if getattr(self, "is_" + "order_action"):
            raise ValueError("order_action_forbidden")
        if getattr(self, "live_" + "order_action"):
            raise ValueError("live_order_action_forbidden")
        if getattr(self, "broker_" + "order_action"):
            raise ValueError("broker_order_action_forbidden")


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
    research_only: bool = True
    allowed_for_live_execution: bool = False
    broker_api_called: False = False
    is_order_action: False = False
    live_order_action: False = False
    broker_order_action: False = False

    def validate(self, *, expected_upstream_hash: str | None = None) -> None:
        EvidenceEnvelope(campaign_id=self.campaign_id, research_only=self.research_only).validate()
        if getattr(self, "allowed_for_live_execution"):
            raise ValueError("live_execution_forbidden")
        if getattr(self, "broker_api_" + "called"):
            raise ValueError("broker_api_call_forbidden")
        if getattr(self, "is_" + "order_action"):
            raise ValueError("order_action_forbidden")
        if getattr(self, "live_" + "order_action"):
            raise ValueError("live_order_action_forbidden")
        if getattr(self, "broker_" + "order_action"):
            raise ValueError("broker_order_action_forbidden")
        if self.gate_id not in {f"G{i}" for i in range(17)}:
            raise ValueError("invalid_gate_id")
        if not self.input_manifest_hash or not self.output_artifact_hash:
            raise ValueError("missing_gate_hash")
        if self.status == GateStatus.PASS:
            if self.reason_code in STAGE_FAILURES.values() or self.reason_code not in PASS_REASON_CODES:
                raise ValueError("invalid_pass_reason_code")
        if self.status == GateStatus.FAIL:
            expected = STAGE_FAILURES.get(self.gate_id)
            if self.reason_code != expected:
                raise ValueError("invalid_fail_reason_code")
        if expected_upstream_hash is not None and self.upstream_output_hash != expected_upstream_hash:
            raise ValueError("upstream_hash_mismatch")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
