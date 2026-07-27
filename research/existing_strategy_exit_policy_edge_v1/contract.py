from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

CONTRACT_VERSION = "existing_strategy_exit_policy_edge_v1"
TARGET_R_MULTIPLES = (0.30, 0.40, 0.50, 0.65, 0.75, 1.00, 1.25, 1.50, 2.00)
PRIMARY_STOP_R = 1.00
MAX_HOLD_MINUTES = (5, 10, 15, 20, 30)
PRIORITY_STRATEGIES = (
    "opening_range_retest_v1",
    "vwap_reclaim_v1",
    "trend_pullback_v1",
    "compression_breakout_v1",
)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class ExitPolicy:
    target_r: float
    stop_r: float = PRIMARY_STOP_R
    max_hold_minutes: int = 15

    def __post_init__(self) -> None:
        if self.target_r not in TARGET_R_MULTIPLES:
            raise ValueError(f"unsupported target_r={self.target_r}")
        if self.stop_r <= 0:
            raise ValueError("stop_r must be positive")
        if self.max_hold_minutes not in MAX_HOLD_MINUTES:
            raise ValueError(f"unsupported max_hold_minutes={self.max_hold_minutes}")

    @property
    def policy_id(self) -> str:
        return f"t{self.target_r:.2f}_s{self.stop_r:.2f}_h{self.max_hold_minutes}"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "policy_id": self.policy_id}


def frozen_contract(*, base_commit_sha: str, source_manifest: str) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "base_commit_sha": base_commit_sha,
        "source_manifest": source_manifest,
        "priority_strategies": list(PRIORITY_STRATEGIES),
        "entry_ownership": "FROZEN_EXISTING_CAUSAL_STRATEGY_SIGNAL",
        "entry_execution": "NEXT_EXECUTABLE_SAME_CONTRACT_OPTION_QUOTE",
        "target_r_multiples": list(TARGET_R_MULTIPLES),
        "primary_stop_r": PRIMARY_STOP_R,
        "max_hold_minutes": list(MAX_HOLD_MINUTES),
        "same_bar_ambiguity": "STOP_FIRST_AUTHORITATIVE",
        "selection": "NESTED_CHRONOLOGICAL_WFA_NET_EXPECTANCY_AFTER_COSTS",
        "claim_boundary": [
            "RESEARCH_ONLY",
            "NOT_PRODUCTION_READY",
            "NO_STRATEGY_FORMULA_CHANGES",
            "NO_LIVE_EXECUTION_CHANGES",
        ],
        "safety": {
            "read_only_market_data": True,
            "broker_api_called": False,
            "is_order_action": False,
            "allowed_for_live_execution": False,
        },
    }
    payload["contract_hash"] = sha256_payload(payload)
    return payload
