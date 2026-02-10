"""Decision model for a single trade decision.

This module defines an immutable Decision object and related dataclasses
to represent a trade or no-trade outcome. It is self-contained and safe
to import without side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import json


class DecisionStatus(str, Enum):
    PLANNED = "planned"
    SUBMITTED = "submitted"
    FILLED = "filled"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class DecisionMeta:
    ts_epoch: float
    run_id: str
    symbol: str
    timeframe: str


@dataclass(frozen=True)
class DecisionMarket:
    spot: float
    vwap: Optional[float] = None
    trend_state: str = ""
    regime: str = ""
    vol_state: str = ""
    iv: Optional[float] = None
    ivp: Optional[float] = None


@dataclass(frozen=True)
class DecisionSignals:
    pattern_flags: List[str] = field(default_factory=list)
    rank_score: Optional[float] = None
    confidence: Optional[float] = None


@dataclass(frozen=True)
class DecisionStrategy:
    name: str
    legs: List[Dict[str, Any]] = field(default_factory=list)
    direction: str = ""
    entry_reason: str = ""
    stop: float = 0.0
    target: float = 0.0
    rr: float = 0.0
    max_loss: float = 0.0
    size: float = 0.0


@dataclass(frozen=True)
class DecisionRisk:
    daily_loss_limit: float = 0.0
    position_limit: float = 0.0
    slippage_bps_assumed: float = 0.0


@dataclass(frozen=True)
class DecisionOutcome:
    status: DecisionStatus = DecisionStatus.PLANNED
    reject_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    meta: DecisionMeta
    market: DecisionMarket
    signals: DecisionSignals
    strategy: DecisionStrategy
    risk: DecisionRisk
    outcome: DecisionOutcome = field(default_factory=DecisionOutcome)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def decision_id(self) -> str:
        """Stable decision identifier derived from key fields."""
        payload = {
            "ts_epoch": self.meta.ts_epoch,
            "run_id": self.meta.run_id,
            "symbol": self.meta.symbol,
            "timeframe": self.meta.timeframe,
            "strategy": self.strategy.name,
            "direction": self.strategy.direction,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        data = asdict(self)
        data["outcome"]["status"] = self.outcome.status.value
        data["decision_id"] = self.decision_id
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Decision":
        """Deserialize from dict; unknown keys are preserved in `extra`."""
        extra = {k: v for k, v in data.items() if k not in {
            "meta", "market", "signals", "strategy", "risk", "outcome", "decision_id"
        }}

        meta = DecisionMeta(**data.get("meta", {}))
        market = DecisionMarket(**data.get("market", {}))
        signals = DecisionSignals(**data.get("signals", {}))
        strategy = DecisionStrategy(**data.get("strategy", {}))
        risk = DecisionRisk(**data.get("risk", {}))
        outcome_raw = data.get("outcome", {})
        status_val = outcome_raw.get("status", DecisionStatus.PLANNED.value)
        outcome = DecisionOutcome(
            status=DecisionStatus(status_val),
            reject_reasons=outcome_raw.get("reject_reasons", []),
        )
        return Decision(
            meta=meta,
            market=market,
            signals=signals,
            strategy=strategy,
            risk=risk,
            outcome=outcome,
            extra=extra,
        )


# Usage example:
#
# decision = Decision(
#     meta=DecisionMeta(ts_epoch=1720000000.0, run_id="R1", symbol="NIFTY", timeframe="1m"),
#     market=DecisionMarket(spot=25200.0, trend_state="UP", regime="TREND", vol_state="LOW"),
#     signals=DecisionSignals(pattern_flags=["breakout"], rank_score=0.72, confidence=0.6),
#     strategy=DecisionStrategy(name="trend_breakout", direction="BUY", entry_reason="breakout",
#                               stop=25100.0, target=25450.0, rr=2.5, max_loss=5000.0, size=1),
#     risk=DecisionRisk(daily_loss_limit=0.02, position_limit=3, slippage_bps_assumed=8),
# )
# payload = decision.to_dict()
# restored = Decision.from_dict(payload)
