from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class ProfileNode:
    price: float
    node_type: str
    strength: float
    width_ticks: int


@dataclass
class SessionProfile:
    vah: Optional[float]
    val: Optional[float]
    poc: Optional[float]
    hvns: List[ProfileNode]
    lvns: List[ProfileNode]
    profile_width: Optional[float]
    value_area_width: Optional[float]


@dataclass
class RegimeDecision:
    allow_mean_reversion: bool
    regime: str
    confidence: float
    reasons: List[str]


@dataclass
class ProfileRejectionSetup:
    detected: bool
    direction: str
    setup_score: float
    trigger_score: float
    entry_quality_score: float
    rr: float
    entry: float
    stop: float
    target: float
    reasons: List[str]
    telemetry: Dict[str, Any]
