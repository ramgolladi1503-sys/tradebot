from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any


class GapClass(str, Enum):
    GAP_DOWN = "GAP_DOWN"
    FLAT = "FLAT"
    GAP_UP = "GAP_UP"
    ABSTAIN = "ABSTAIN"


class GapResponseState(str, Enum):
    NO_GAP = "NO_GAP"
    CONTINUING = "CONTINUING"
    RETAINING = "RETAINING"
    REJECTING = "REJECTING"
    FILLED = "FILLED"
    OVERFILLED = "OVERFILLED"


@dataclass(frozen=True)
class EvidenceAuthority:
    """Hard safety boundary for pre-market evidence artifacts."""

    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    append: bool = False


@dataclass(frozen=True)
class PreMarketSnapshot:
    """Immutable inputs visible no later than the prediction cutoff."""

    index: str
    cutoff_ts: datetime
    previous_close: float
    gift_last: float
    gift_previous_settlement: float
    gift_ts: datetime
    lower_uncertainty_points: float
    upper_uncertainty_points: float
    flat_band_pct: float = 0.0015
    shock_adjustment_points: float = 0.0
    auction_adjustment_points: float | None = None
    auction_available: bool = False
    max_gift_age_seconds: float = 600.0
    model_version: str = "premarket-gap-baseline-v1"
    sources: tuple[str, ...] = field(default_factory=tuple)
    authority: EvidenceAuthority = field(default_factory=EvidenceAuthority)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "index": self.index.strip().upper(),
            "cutoff_ts": _iso(self.cutoff_ts),
            "previous_close": self.previous_close,
            "gift_last": self.gift_last,
            "gift_previous_settlement": self.gift_previous_settlement,
            "gift_ts": _iso(self.gift_ts),
            "lower_uncertainty_points": self.lower_uncertainty_points,
            "upper_uncertainty_points": self.upper_uncertainty_points,
            "flat_band_pct": self.flat_band_pct,
            "shock_adjustment_points": self.shock_adjustment_points,
            "auction_adjustment_points": self.auction_adjustment_points,
            "auction_available": self.auction_available,
            "max_gift_age_seconds": self.max_gift_age_seconds,
            "model_version": self.model_version,
            "sources": list(self.sources),
            "authority": asdict(self.authority),
        }

    @property
    def sha256(self) -> str:
        raw = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class GapPrediction:
    index: str
    status: str
    model_version: str
    snapshot_sha256: str
    previous_basis_points: float | None
    gift_gap_points: float | None
    central_gap_points: float | None
    predicted_open: float | None
    lower_gap_points: float | None
    upper_gap_points: float | None
    gap_class: GapClass
    input_quality: str
    reasons: tuple[str, ...]
    authority: EvidenceAuthority = field(default_factory=EvidenceAuthority)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["gap_class"] = self.gap_class.value
        return payload


@dataclass(frozen=True)
class GapScore:
    index: str
    predicted_gap_points: float
    actual_gap_points: float
    actual_gap_class: GapClass
    sign_correct: bool
    class_correct: bool
    central_error_points: float
    central_abs_error_points: float
    interval_hit: bool
    interval_miss_distance_points: float
    authority: EvidenceAuthority = field(default_factory=EvidenceAuthority)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["actual_gap_class"] = self.actual_gap_class.value
        return payload


@dataclass(frozen=True)
class GapResponse:
    index: str
    previous_close: float
    actual_open: float
    current_price: float
    actual_gap_points: float
    gap_surprise_points: float | None
    retention_ratio: float | None
    fill_ratio: float | None
    state: GapResponseState
    authority: EvidenceAuthority = field(default_factory=EvidenceAuthority)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


def build_gap_prediction(snapshot: PreMarketSnapshot) -> GapPrediction:
    """Build a deterministic, basis-corrected gap baseline or fail closed."""

    reasons = _validate_snapshot(snapshot)
    if reasons:
        return GapPrediction(
            index=snapshot.index.strip().upper(),
            status="ABSTAIN",
            model_version=snapshot.model_version,
            snapshot_sha256=_safe_snapshot_sha(snapshot),
            previous_basis_points=None,
            gift_gap_points=None,
            central_gap_points=None,
            predicted_open=None,
            lower_gap_points=None,
            upper_gap_points=None,
            gap_class=GapClass.ABSTAIN,
            input_quality="INVALID",
            reasons=tuple(reasons),
            authority=snapshot.authority,
        )

    previous_basis = snapshot.gift_previous_settlement - snapshot.previous_close
    implied_cash_open = snapshot.gift_last - previous_basis
    gift_gap = implied_cash_open - snapshot.previous_close

    auction_adjustment = (
        float(snapshot.auction_adjustment_points)
        if snapshot.auction_available and snapshot.auction_adjustment_points is not None
        else 0.0
    )
    central_gap = gift_gap + snapshot.shock_adjustment_points + auction_adjustment
    predicted_open = snapshot.previous_close + central_gap
    lower_gap = central_gap - snapshot.lower_uncertainty_points
    upper_gap = central_gap + snapshot.upper_uncertainty_points

    age_seconds = (snapshot.cutoff_ts - snapshot.gift_ts).total_seconds()
    if snapshot.auction_available and age_seconds <= 180.0:
        input_quality = "HIGH_INPUT_QUALITY"
    elif age_seconds <= 180.0:
        input_quality = "MEDIUM_INPUT_QUALITY"
    else:
        input_quality = "LOW_INPUT_QUALITY"

    return GapPrediction(
        index=snapshot.index.strip().upper(),
        status="PREDICTED",
        model_version=snapshot.model_version,
        snapshot_sha256=snapshot.sha256,
        previous_basis_points=previous_basis,
        gift_gap_points=gift_gap,
        central_gap_points=central_gap,
        predicted_open=predicted_open,
        lower_gap_points=lower_gap,
        upper_gap_points=upper_gap,
        gap_class=classify_gap(central_gap, snapshot.previous_close, snapshot.flat_band_pct),
        input_quality=input_quality,
        reasons=(),
        authority=snapshot.authority,
    )


def score_gap_prediction(
    prediction: GapPrediction,
    *,
    actual_open: float,
    flat_band_pct: float = 0.0015,
) -> GapScore:
    """Strictly score the frozen prediction against the actual opening print."""

    if prediction.status != "PREDICTED":
        raise ValueError("cannot score an abstained prediction")
    required = (
        prediction.central_gap_points,
        prediction.predicted_open,
        prediction.lower_gap_points,
        prediction.upper_gap_points,
    )
    if any(value is None for value in required):
        raise ValueError("prediction is incomplete")
    _require_finite_positive("actual_open", actual_open)
    previous_close = float(prediction.predicted_open) - float(prediction.central_gap_points)
    actual_gap = float(actual_open) - previous_close
    central = float(prediction.central_gap_points)
    lower = float(prediction.lower_gap_points)
    upper = float(prediction.upper_gap_points)
    actual_class = classify_gap(actual_gap, previous_close, flat_band_pct)

    interval_hit = lower <= actual_gap <= upper
    if interval_hit:
        miss_distance = 0.0
    elif actual_gap < lower:
        miss_distance = lower - actual_gap
    else:
        miss_distance = actual_gap - upper

    return GapScore(
        index=prediction.index,
        predicted_gap_points=central,
        actual_gap_points=actual_gap,
        actual_gap_class=actual_class,
        sign_correct=_sign(central) == _sign(actual_gap),
        class_correct=prediction.gap_class == actual_class,
        central_error_points=actual_gap - central,
        central_abs_error_points=abs(actual_gap - central),
        interval_hit=interval_hit,
        interval_miss_distance_points=miss_distance,
        authority=prediction.authority,
    )


def measure_gap_response(
    *,
    index: str,
    previous_close: float,
    actual_open: float,
    current_price: float,
    predicted_gap_points: float | None = None,
    no_gap_epsilon_points: float = 1e-9,
) -> GapResponse:
    """Measure post-open gap retention/fill without changing the pre-open forecast."""

    for name, value in (
        ("previous_close", previous_close),
        ("actual_open", actual_open),
        ("current_price", current_price),
    ):
        _require_finite_positive(name, value)
    if predicted_gap_points is not None and not _finite(predicted_gap_points):
        raise ValueError("predicted_gap_points must be finite")
    if not _finite(no_gap_epsilon_points) or no_gap_epsilon_points < 0:
        raise ValueError("no_gap_epsilon_points must be finite and >= 0")

    actual_gap = actual_open - previous_close
    surprise = (
        actual_gap - float(predicted_gap_points)
        if predicted_gap_points is not None
        else None
    )
    if abs(actual_gap) <= no_gap_epsilon_points:
        return GapResponse(
            index=index.strip().upper(),
            previous_close=previous_close,
            actual_open=actual_open,
            current_price=current_price,
            actual_gap_points=actual_gap,
            gap_surprise_points=surprise,
            retention_ratio=None,
            fill_ratio=None,
            state=GapResponseState.NO_GAP,
        )

    retention = (current_price - previous_close) / actual_gap
    fill = 1.0 - retention

    if retention > 1.05:
        state = GapResponseState.CONTINUING
    elif retention >= 0.50:
        state = GapResponseState.RETAINING
    elif retention > 1e-9:
        state = GapResponseState.REJECTING
    elif retention >= -1e-9:
        state = GapResponseState.FILLED
    else:
        state = GapResponseState.OVERFILLED

    return GapResponse(
        index=index.strip().upper(),
        previous_close=previous_close,
        actual_open=actual_open,
        current_price=current_price,
        actual_gap_points=actual_gap,
        gap_surprise_points=surprise,
        retention_ratio=retention,
        fill_ratio=fill,
        state=state,
    )


def classify_gap(
    gap_points: float,
    previous_close: float,
    flat_band_pct: float = 0.0015,
) -> GapClass:
    if not _finite(gap_points):
        raise ValueError("gap_points must be finite")
    _require_finite_positive("previous_close", previous_close)
    if not _finite(flat_band_pct) or flat_band_pct < 0:
        raise ValueError("flat_band_pct must be finite and >= 0")

    gap_pct = gap_points / previous_close
    if gap_pct > flat_band_pct:
        return GapClass.GAP_UP
    if gap_pct < -flat_band_pct:
        return GapClass.GAP_DOWN
    return GapClass.FLAT


def _validate_snapshot(snapshot: PreMarketSnapshot) -> list[str]:
    reasons: list[str] = []
    if not snapshot.index or not snapshot.index.strip():
        reasons.append("MISSING_INDEX")
    for name, value in (
        ("previous_close", snapshot.previous_close),
        ("gift_last", snapshot.gift_last),
        ("gift_previous_settlement", snapshot.gift_previous_settlement),
    ):
        if not _finite(value) or float(value) <= 0:
            reasons.append(f"INVALID_{name.upper()}")
    for name, value in (
        ("lower_uncertainty_points", snapshot.lower_uncertainty_points),
        ("upper_uncertainty_points", snapshot.upper_uncertainty_points),
        ("flat_band_pct", snapshot.flat_band_pct),
        ("max_gift_age_seconds", snapshot.max_gift_age_seconds),
    ):
        if not _finite(value) or float(value) < 0:
            reasons.append(f"INVALID_{name.upper()}")
    if not _finite(snapshot.shock_adjustment_points):
        reasons.append("INVALID_SHOCK_ADJUSTMENT")
    if snapshot.auction_adjustment_points is not None and not _finite(snapshot.auction_adjustment_points):
        reasons.append("INVALID_AUCTION_ADJUSTMENT")
    if snapshot.auction_available and snapshot.auction_adjustment_points is None:
        reasons.append("AUCTION_AVAILABLE_WITHOUT_ADJUSTMENT")
    if not snapshot.auction_available and snapshot.auction_adjustment_points not in (None, 0, 0.0):
        reasons.append("AUCTION_ADJUSTMENT_WITHOUT_AUTHORITY")

    if not _aware(snapshot.cutoff_ts):
        reasons.append("CUTOFF_TIMESTAMP_NOT_TIMEZONE_AWARE")
    if not _aware(snapshot.gift_ts):
        reasons.append("GIFT_TIMESTAMP_NOT_TIMEZONE_AWARE")
    if _aware(snapshot.cutoff_ts) and _aware(snapshot.gift_ts):
        if snapshot.gift_ts > snapshot.cutoff_ts:
            reasons.append("FUTURE_DATA_VIOLATION")
        else:
            age = (snapshot.cutoff_ts - snapshot.gift_ts).total_seconds()
            if age > snapshot.max_gift_age_seconds:
                reasons.append("STALE_GIFT_DATA")

    authority = snapshot.authority
    if not authority.read_only:
        reasons.append("READ_ONLY_AUTHORITY_REQUIRED")
    if authority.is_order_action:
        reasons.append("ORDER_ACTION_FORBIDDEN")
    if authority.broker_api_called:
        reasons.append("BROKER_API_CALL_FORBIDDEN")
    if authority.allowed_for_live_execution:
        reasons.append("LIVE_EXECUTION_AUTHORITY_FORBIDDEN")
    if authority.append:
        reasons.append("APPEND_AUTHORITY_FORBIDDEN")

    return reasons


def _safe_snapshot_sha(snapshot: PreMarketSnapshot) -> str:
    try:
        return snapshot.sha256
    except Exception:
        return "UNAVAILABLE"


def _iso(value: datetime) -> str:
    return value.isoformat()


def _aware(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _require_finite_positive(name: str, value: Any) -> None:
    if not _finite(value) or float(value) <= 0:
        raise ValueError(f"{name} must be finite and > 0")


def _sign(value: float, epsilon: float = 1e-12) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0
