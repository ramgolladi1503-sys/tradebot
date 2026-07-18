from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

HORIZONS_MINUTES: tuple[int, ...] = (1, 3, 5, 10, 15, 30)


class OutcomeContractError(ValueError):
    pass


@dataclass(frozen=True)
class OutcomeCandidate:
    candidate_id: str
    session_key: str
    symbol: str
    direction: str
    proposal_ready_at: str
    source_hash: str
    candidate_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        direction = str(self.direction or "").strip().upper()
        if direction not in {"BUY_CALL", "BUY_PUT"}:
            raise OutcomeContractError(f"unsupported_direction:{direction}")
        for name in ("candidate_id", "session_key", "symbol", "proposal_ready_at"):
            if not str(getattr(self, name) or "").strip():
                raise OutcomeContractError(f"required_field_empty:{name}")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "symbol", str(self.symbol).strip().upper())

    @property
    def side_multiplier(self) -> int:
        return 1 if self.direction == "BUY_CALL" else -1

    def canonical_hash(self) -> str:
        payload = asdict(self)
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OutcomeBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    session_key: str = ""

    def __post_init__(self) -> None:
        for name in ("open", "high", "low", "close"):
            value = float(getattr(self, name))
            if value <= 0:
                raise OutcomeContractError(f"invalid_price:{name}")
            object.__setattr__(self, name, value)
        if self.high < max(self.open, self.close, self.low):
            raise OutcomeContractError("invalid_ohlc_high")
        if self.low > min(self.open, self.close, self.high):
            raise OutcomeContractError("invalid_ohlc_low")


@dataclass(frozen=True)
class OutcomeStatus:
    candidate_id: str
    status: str
    reason: str


def canonical_json_hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
