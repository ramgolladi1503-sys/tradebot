from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ReadinessState(str, Enum):
    BOOTING = "BOOTING"
    MARKET_CLOSED = "MARKET_CLOSED"
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


@dataclass
class ReadinessResult:
    state: ReadinessState
    can_trade: bool
    market_open: bool
    holiday: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks: Dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, object]:
        return {
            "state": self.state.value,
            "can_trade": self.can_trade,
            "market_open": self.market_open,
            "holiday": self.holiday,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "checks": self.checks,
        }

