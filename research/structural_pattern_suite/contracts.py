from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any


SUITE_ID = "STRUCTURAL_PATTERN_STRATEGY_SUITE"
SUITE_VERSION = "v1"
RESEARCH_ONLY_FLAGS = {
    "execution_eligibility": False,
    "research_only": True,
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
}


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class StrategyId(str, Enum):
    GAP_GO_LEADER = "GAP_GO_LEADER_V1"
    PRIOR_RANGE_LEADER = "PRIOR_RANGE_LEADER_V1"
    LATE_DAY_PERSISTENCE = "LATE_DAY_PERSISTENCE_V1"


@dataclass(frozen=True)
class Bar:
    symbol: str
    session: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class PreviousSession:
    symbol: str
    session: str
    high: float
    low: float
    close: float

    @property
    def range(self) -> float:
        return self.high - self.low


@dataclass(frozen=True)
class Candidate:
    strategy_id: StrategyId
    strategy_version: str
    symbol: str
    side: Side
    session: str
    decision_timestamp: str
    entry_timestamp: str
    source_manifest_hash: str
    feature_contract_hash: str
    candidate_bundle_hash: str
    gap_normalized: float | None = None
    opening_return_bps: float | None = None
    leader_spread_bps: float | None = None
    prior_boundary_relation: str | None = None
    late_displacement: float | None = None
    close_location: float | None = None
    execution_eligibility: bool = False
    research_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id.value,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "side": self.side.value,
            "session": self.session,
            "decision_timestamp": self.decision_timestamp,
            "entry_timestamp": self.entry_timestamp,
            "source_manifest_hash": self.source_manifest_hash,
            "feature_contract_hash": self.feature_contract_hash,
            "candidate_bundle_hash": self.candidate_bundle_hash,
            "gap_normalized": self.gap_normalized,
            "opening_return_bps": self.opening_return_bps,
            "leader_spread_bps": self.leader_spread_bps,
            "prior_boundary_relation": self.prior_boundary_relation,
            "late_displacement": self.late_displacement,
            "close_location": self.close_location,
            "execution_eligibility": self.execution_eligibility,
            "research_only": self.research_only,
        }


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode("utf-8")


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


THRESHOLD_FREEZE = {
    "schema_version": "1.0",
    "suite_id": SUITE_ID,
    "suite_version": SUITE_VERSION,
    "thresholds_frozen_before_outcomes": True,
    "do_not_modify_after_outcome_inspection": True,
    "strategies": {
        StrategyId.GAP_GO_LEADER.value: {
            "decision_bar_completion": "09:45",
            "entry": "next_legal_bar_open",
            "gap_normalized_min": 0.33,
            "opening_return_abs_bps_min": 5.0,
            "directed_leader_spread_bps_min": 20.0,
        },
        StrategyId.PRIOR_RANGE_LEADER.value: {
            "decision_bar_completion": "09:45",
            "entry": "next_legal_bar_open",
            "directed_leader_spread_bps_min": 20.0,
            "forbidden_filters": ["ADX", "RSI", "EMA", "VWAP", "volume", "weekday", "expiry", "hand_selected_time_filters"],
        },
        StrategyId.LATE_DAY_PERSISTENCE.value: {
            "decision_bar_completion": "14:00",
            "entry": "next_legal_bar_open",
            "directional_displacement_normalized_min": 0.50,
            "long_close_location_min": 0.80,
            "short_close_location_max": 0.20,
        },
    },
    "parameter_neighbourhoods": {
        "gap_normalized": [0.28, 0.33, 0.38],
        "leader_spread_bps": [15, 20, 25],
        "late_displacement": [0.45, 0.50, 0.55],
        "outer_close_location": [[0.75, 0.25], [0.80, 0.20], [0.85, 0.15]],
    },
    **RESEARCH_ONLY_FLAGS,
}


FEATURE_CONTRACT_HASH = canonical_hash(THRESHOLD_FREEZE)

