from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
import pandas as pd
from typing import Any


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NO_TRADE = "NO_TRADE"


class OptionRight(str, Enum):
    CE = "CE"
    PE = "PE"


@dataclass(frozen=True)
class CanonicalSignal:
    strategy_id: str
    signal_id: str
    session: str
    feature_cutoff_ts: str
    signal_ts: str
    earliest_entry_ts: str
    direction: Direction
    signal_strength: float
    params_hash: str
    source_hash: str
    is_oos: bool
    fold_id: str

    def validate(self) -> None:
        required = (
            self.strategy_id,
            self.signal_id,
            self.session,
            self.feature_cutoff_ts,
            self.signal_ts,
            self.earliest_entry_ts,
            self.params_hash,
            self.source_hash,
            self.fold_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("missing_signal_field")
        feature_cutoff = pd.Timestamp(self.feature_cutoff_ts)
        signal = pd.Timestamp(self.signal_ts)
        earliest_entry = pd.Timestamp(self.earliest_entry_ts)
        if not (feature_cutoff < signal < earliest_entry):
            raise ValueError("signal_timing_not_strictly_causal")
        if signal.tzinfo is None:
            raise ValueError("signal_timestamp_must_be_timezone_aware")
        if signal.tz_convert("Asia/Kolkata").date().isoformat() != self.session:
            raise ValueError("signal_session_date_mismatch")
        if not math.isfinite(float(self.signal_strength)):
            raise ValueError("non_finite_signal_strength")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["direction"] = self.direction.value
        return payload


def map_direction_to_option_right(direction: Direction | str) -> OptionRight | None:
    value = Direction(direction)
    if value == Direction.BULLISH:
        return OptionRight.CE
    if value == Direction.BEARISH:
        return OptionRight.PE
    return None
