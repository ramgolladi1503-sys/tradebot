from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import time
from typing import Any, Mapping, Sequence

SESSION_OPENING_MOMENTUM = "OPENING_MOMENTUM"
SESSION_MIDDAY_CONTINUATION = "MIDDAY_CONTINUATION"
SESSION_LATE_SESSION = "LATE_SESSION"
SESSION_CLOSE_RISK = "CLOSE_RISK"
SESSION_UNKNOWN = "UNKNOWN"

TOP_MOVER_TOP_10 = "TOP_10"
TOP_MOVER_TOP_25 = "TOP_25"
TOP_MOVER_TOP_50 = "TOP_50"
TOP_MOVER_OUTSIDE = "OUTSIDE_TOP_MOVERS"
TOP_MOVER_UNKNOWN = "UNKNOWN"

INVALID_ENTRY_PRICE = "INVALID_ENTRY_PRICE"
EMPTY_PRICE_PATH = "EMPTY_PRICE_PATH"
MISSING_CANDIDATE_ID = "MISSING_CANDIDATE_ID"
INVALID_PRICE_PATH = "INVALID_PRICE_PATH"
INVALID_EXIT_PRICE = "INVALID_EXIT_PRICE"
OK_REASON = "OK"


@dataclass(frozen=True)
class SessionPathReplayEvidence:
    candidate_id: str
    symbol: str
    entry_time: str
    exit_time: str
    session_window: str
    entry_price: float
    exit_price: float
    mfe_abs: float
    mae_abs: float
    mfe_pct: float
    mae_pct: float
    open_to_close_pct: float
    hit_target_before_close: bool
    gave_back_profit: bool
    closed_near_high: bool
    closed_near_low: bool
    top_mover_rank: int | None
    top_mover_bucket: str
    relative_strength_percentile: float | None
    regime_at_entry: str
    valid: bool
    reason: str
    read_only: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["read_only"] = True
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


def classify_session_window(entry_time: str | None) -> str:
    parsed = _parse_time(entry_time)
    if parsed is None:
        return SESSION_UNKNOWN
    if time(9, 15) <= parsed < time(10, 30):
        return SESSION_OPENING_MOMENTUM
    if time(10, 30) <= parsed < time(13, 30):
        return SESSION_MIDDAY_CONTINUATION
    if time(13, 30) <= parsed < time(15, 15):
        return SESSION_LATE_SESSION
    if time(15, 15) <= parsed <= time(15, 30):
        return SESSION_CLOSE_RISK
    return SESSION_UNKNOWN


def classify_top_mover_bucket(rank: int | None) -> str:
    if rank is None:
        return TOP_MOVER_UNKNOWN
    try:
        normalized = int(rank)
    except (TypeError, ValueError):
        return TOP_MOVER_UNKNOWN
    if normalized <= 0:
        return TOP_MOVER_UNKNOWN
    if normalized <= 10:
        return TOP_MOVER_TOP_10
    if normalized <= 25:
        return TOP_MOVER_TOP_25
    if normalized <= 50:
        return TOP_MOVER_TOP_50
    return TOP_MOVER_OUTSIDE


def build_session_path_replay_evidence(
    *,
    candidate_id: str | None,
    symbol: str | None,
    entry_time: str | None,
    exit_time: str | None,
    entry_price: float | int | str | None,
    price_path: Sequence[float | int | str] | None,
    target_pct: float = 4.0,
    top_mover_rank: int | None = None,
    relative_strength_percentile: float | int | None = None,
    regime_at_entry: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> SessionPathReplayEvidence:
    candidate = (candidate_id or "").strip()
    if not candidate:
        return _invalid_evidence(
            candidate_id="",
            symbol=symbol,
            entry_time=entry_time,
            exit_time=exit_time,
            reason=MISSING_CANDIDATE_ID,
            top_mover_rank=top_mover_rank,
            relative_strength_percentile=relative_strength_percentile,
            regime_at_entry=regime_at_entry,
            metadata=metadata,
        )

    entry = _coerce_positive_float(entry_price)
    if entry is None:
        return _invalid_evidence(
            candidate_id=candidate,
            symbol=symbol,
            entry_time=entry_time,
            exit_time=exit_time,
            reason=INVALID_ENTRY_PRICE,
            top_mover_rank=top_mover_rank,
            relative_strength_percentile=relative_strength_percentile,
            regime_at_entry=regime_at_entry,
            metadata=metadata,
        )

    if not price_path:
        return _invalid_evidence(
            candidate_id=candidate,
            symbol=symbol,
            entry_time=entry_time,
            exit_time=exit_time,
            reason=EMPTY_PRICE_PATH,
            entry_price=entry,
            top_mover_rank=top_mover_rank,
            relative_strength_percentile=relative_strength_percentile,
            regime_at_entry=regime_at_entry,
            metadata=metadata,
        )

    prices = [_coerce_positive_float(value) for value in price_path]
    if any(value is None for value in prices):
        return _invalid_evidence(
            candidate_id=candidate,
            symbol=symbol,
            entry_time=entry_time,
            exit_time=exit_time,
            reason=INVALID_PRICE_PATH,
            entry_price=entry,
            top_mover_rank=top_mover_rank,
            relative_strength_percentile=relative_strength_percentile,
            regime_at_entry=regime_at_entry,
            metadata=metadata,
        )

    normalized_prices = [float(value) for value in prices if value is not None]
    exit_price = normalized_prices[-1]
    if exit_price <= 0:
        return _invalid_evidence(
            candidate_id=candidate,
            symbol=symbol,
            entry_time=entry_time,
            exit_time=exit_time,
            reason=INVALID_EXIT_PRICE,
            entry_price=entry,
            top_mover_rank=top_mover_rank,
            relative_strength_percentile=relative_strength_percentile,
            regime_at_entry=regime_at_entry,
            metadata=metadata,
        )

    max_after_entry = max(normalized_prices)
    min_after_entry = min(normalized_prices)
    mfe_abs = max_after_entry - entry
    mae_abs = min_after_entry - entry
    mfe_pct = _pct(mfe_abs, entry)
    mae_pct = _pct(mae_abs, entry)
    open_to_close_pct = _pct(exit_price - entry, entry)
    hit_target_before_close = mfe_pct >= float(target_pct)

    return SessionPathReplayEvidence(
        candidate_id=candidate,
        symbol=(symbol or "UNKNOWN").strip() or "UNKNOWN",
        entry_time=entry_time or "",
        exit_time=exit_time or "",
        session_window=classify_session_window(entry_time),
        entry_price=entry,
        exit_price=exit_price,
        mfe_abs=_round(mfe_abs),
        mae_abs=_round(mae_abs),
        mfe_pct=_round(mfe_pct),
        mae_pct=_round(mae_pct),
        open_to_close_pct=_round(open_to_close_pct),
        hit_target_before_close=hit_target_before_close,
        gave_back_profit=_gave_back_profit(
            hit_target_before_close=hit_target_before_close,
            mfe_abs=mfe_abs,
            exit_price=exit_price,
            entry_price=entry,
        ),
        closed_near_high=_closed_near_high(exit_price, max_after_entry, entry),
        closed_near_low=_closed_near_low(exit_price, min_after_entry, entry),
        top_mover_rank=top_mover_rank,
        top_mover_bucket=classify_top_mover_bucket(top_mover_rank),
        relative_strength_percentile=_coerce_optional_float(relative_strength_percentile),
        regime_at_entry=(regime_at_entry or "UNKNOWN").strip() or "UNKNOWN",
        valid=True,
        reason=OK_REASON,
        metadata=dict(metadata or {}),
    )


def _invalid_evidence(
    *,
    candidate_id: str,
    symbol: str | None,
    entry_time: str | None,
    exit_time: str | None,
    reason: str,
    entry_price: float = 0.0,
    top_mover_rank: int | None,
    relative_strength_percentile: float | int | None,
    regime_at_entry: str | None,
    metadata: Mapping[str, Any] | None,
) -> SessionPathReplayEvidence:
    return SessionPathReplayEvidence(
        candidate_id=candidate_id,
        symbol=(symbol or "UNKNOWN").strip() or "UNKNOWN",
        entry_time=entry_time or "",
        exit_time=exit_time or "",
        session_window=classify_session_window(entry_time),
        entry_price=_round(entry_price),
        exit_price=0.0,
        mfe_abs=0.0,
        mae_abs=0.0,
        mfe_pct=0.0,
        mae_pct=0.0,
        open_to_close_pct=0.0,
        hit_target_before_close=False,
        gave_back_profit=False,
        closed_near_high=False,
        closed_near_low=False,
        top_mover_rank=top_mover_rank,
        top_mover_bucket=classify_top_mover_bucket(top_mover_rank),
        relative_strength_percentile=_coerce_optional_float(relative_strength_percentile),
        regime_at_entry=(regime_at_entry or "UNKNOWN").strip() or "UNKNOWN",
        valid=False,
        reason=reason,
        metadata=dict(metadata or {}),
    )


def _parse_time(raw: str | None) -> time | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if "T" in value:
        value = value.split("T", 1)[1]
    value = value.removesuffix("Z")
    if "+" in value:
        value = value.split("+", 1)[0]
    if value.count(":") >= 2:
        value = ":".join(value.split(":")[:2])
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        return time(int(parts[0]), int(parts[1]))
    except (TypeError, ValueError):
        return None


def _coerce_positive_float(raw: float | int | str | None) -> float | None:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _coerce_optional_float(raw: float | int | None) -> float | None:
    if raw is None:
        return None
    try:
        return _round(float(raw))
    except (TypeError, ValueError):
        return None


def _pct(delta: float, base: float) -> float:
    return (delta / base) * 100.0


def _round(value: float) -> float:
    return round(float(value), 6)


def _gave_back_profit(
    *,
    hit_target_before_close: bool,
    mfe_abs: float,
    exit_price: float,
    entry_price: float,
) -> bool:
    if not hit_target_before_close or mfe_abs <= 0:
        return False
    retained_abs = exit_price - entry_price
    retained_ratio = retained_abs / mfe_abs
    return retained_ratio < 0.5


def _closed_near_high(exit_price: float, high_price: float, entry_price: float) -> bool:
    move = high_price - entry_price
    if move <= 0:
        return False
    return ((exit_price - entry_price) / move) >= 0.8


def _closed_near_low(exit_price: float, low_price: float, entry_price: float) -> bool:
    adverse = entry_price - low_price
    if adverse <= 0:
        return False
    return ((entry_price - exit_price) / adverse) >= 0.8
