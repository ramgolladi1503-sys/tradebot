from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Iterable, Mapping


CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION = 1

TARGET_HIT = "TARGET_HIT"
STOP_HIT = "STOP_HIT"
TIMEOUT = "TIMEOUT"
NO_OBSERVATIONS = "NO_OBSERVATIONS"
INVALID_INPUT = "INVALID_INPUT"
NOT_EXECUTABLE = "NOT_EXECUTABLE"
AMBIGUOUS_SAME_BAR = "AMBIGUOUS_SAME_BAR"

_SUPPORTED_OUTCOME_STATUSES = {
    TARGET_HIT,
    STOP_HIT,
    TIMEOUT,
    NO_OBSERVATIONS,
    INVALID_INPUT,
    NOT_EXECUTABLE,
    AMBIGUOUS_SAME_BAR,
}

_SUPPORTED_DIRECTIONS = {"BUY", "LONG"}


@dataclass(frozen=True)
class CandidateOutcomeInput:
    candidate_id: str | None = None
    trade_id: str | None = None
    strategy_family: str = ""
    symbol: str = ""
    index: str | None = None
    regime: str | None = None
    expiry_type: str | None = None
    signal_epoch: float | int | None = None
    entry_price: float | int | None = None
    stop_loss_price: float | int | None = None
    target_price: float | int | None = None
    timeout_epoch: float | int | None = None
    side: str | None = None
    direction: str | None = None
    feed_truth_state: str | None = None
    reportable_executable: bool = False
    execution_allowed: bool = False
    estimated_cost_r: float | int | None = None
    estimated_cost_abs: float | int | None = None


@dataclass(frozen=True)
class PriceObservation:
    observed_epoch: float | int
    ltp: float | int
    bid: float | int | None = None
    ask: float | int | None = None
    spread: float | int | None = None
    source: str | None = None
    quote_age_sec: float | int | None = None


@dataclass(frozen=True)
class CandidateOutcomeTruth:
    schema_version: int
    read_only: bool
    append: bool
    is_order_action: bool  # is_order_action=false
    broker_api_called: bool  # broker_api_called=false
    live_order_allowed: bool  # live_order_allowed=false
    live_order_action: bool  # live_order_action=false
    broker_order_action: bool  # broker_order_action=false
    candidate_id: str | None
    trade_id: str | None
    strategy_family: str
    symbol: str
    index: str | None
    regime: str | None
    expiry_type: str | None
    signal_epoch: float | None
    outcome_status: str
    outcome_reason: str
    entry_price: float | None
    stop_loss_price: float | None
    target_price: float | None
    timeout_epoch: float | None
    max_favorable_price: float | None
    max_adverse_price: float | None
    mfe_abs: float
    mae_abs: float
    mfe_r: float
    mae_r: float
    gross_r: float
    estimated_cost_r: float
    cost_adjusted_r: float
    target_hit: bool
    stop_hit: bool
    timeout_hit: bool
    first_hit_epoch: float | None
    observation_count: int
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION
        return payload


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _candidate_identifier(candidate: CandidateOutcomeInput) -> str | None:
    return candidate.candidate_id or candidate.trade_id


def _direction(candidate: CandidateOutcomeInput) -> str:
    raw = _normalize_text(candidate.direction or candidate.side or "BUY")
    if raw in {"BUY", "LONG"}:
        return "BUY"
    return raw


def _coerce_observation(value: PriceObservation | Mapping[str, Any]) -> PriceObservation | None:
    if isinstance(value, PriceObservation):
        return value
    if not isinstance(value, Mapping):
        return None
    observed_epoch = _finite_float(value.get("observed_epoch"))
    ltp = _finite_float(value.get("ltp"))
    if observed_epoch is None or ltp is None:
        return None
    return PriceObservation(
        observed_epoch=observed_epoch,
        ltp=ltp,
        bid=_finite_float(value.get("bid")),
        ask=_finite_float(value.get("ask")),
        spread=_finite_float(value.get("spread")),
        source=str(value.get("source") or "").strip() or None,
        quote_age_sec=_finite_float(value.get("quote_age_sec")),
    )


def _invalid_truth(candidate: CandidateOutcomeInput, *, reason: str, blocker: str, warning: str | None = None) -> CandidateOutcomeTruth:
    return CandidateOutcomeTruth(
        schema_version=CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION,
        read_only=True,
        append=False,
        is_order_action=False,
        broker_api_called=False,
        live_order_allowed=False,
        live_order_action=False,
        broker_order_action=False,
        candidate_id=candidate.candidate_id,
        trade_id=candidate.trade_id,
        strategy_family=candidate.strategy_family,
        symbol=candidate.symbol,
        index=candidate.index,
        regime=candidate.regime,
        expiry_type=candidate.expiry_type,
        signal_epoch=_finite_float(candidate.signal_epoch),
        outcome_status=INVALID_INPUT,
        outcome_reason=reason,
        entry_price=_finite_float(candidate.entry_price),
        stop_loss_price=_finite_float(candidate.stop_loss_price),
        target_price=_finite_float(candidate.target_price),
        timeout_epoch=_finite_float(candidate.timeout_epoch),
        max_favorable_price=None,
        max_adverse_price=None,
        mfe_abs=0.0,
        mae_abs=0.0,
        mfe_r=0.0,
        mae_r=0.0,
        gross_r=0.0,
        estimated_cost_r=0.0,
        cost_adjusted_r=0.0,
        target_hit=False,
        stop_hit=False,
        timeout_hit=False,
        first_hit_epoch=None,
        observation_count=0,
        blockers=(blocker,),
        warnings=(warning,) if warning else (),
    )


def build_candidate_outcome_truth(
    candidate: CandidateOutcomeInput,
    observations: Iterable[PriceObservation | Mapping[str, Any]] | None = None,
) -> CandidateOutcomeTruth:
    obs_list = [_coerce_observation(item) for item in (observations or [])]
    valid_observations = [item for item in obs_list if item is not None]
    ordered_observations = sorted(valid_observations, key=lambda item: (item.observed_epoch, item.ltp))
    identifier = _candidate_identifier(candidate)
    direction = _direction(candidate)
    signal_epoch = _finite_float(candidate.signal_epoch)
    entry_price = _finite_float(candidate.entry_price)
    stop_loss_price = _finite_float(candidate.stop_loss_price)
    target_price = _finite_float(candidate.target_price)
    timeout_epoch = _finite_float(candidate.timeout_epoch)
    estimated_cost_r = _finite_float(candidate.estimated_cost_r)
    estimated_cost_abs = _finite_float(candidate.estimated_cost_abs)

    if not candidate.reportable_executable or not candidate.execution_allowed:
        return CandidateOutcomeTruth(
            schema_version=CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION,
            read_only=True,
            append=False,
            is_order_action=False,
            broker_api_called=False,
            live_order_allowed=False,
            live_order_action=False,
            broker_order_action=False,
            candidate_id=candidate.candidate_id,
            trade_id=candidate.trade_id,
            strategy_family=candidate.strategy_family,
            symbol=candidate.symbol,
            index=candidate.index,
            regime=candidate.regime,
            expiry_type=candidate.expiry_type,
            signal_epoch=signal_epoch,
            outcome_status=NOT_EXECUTABLE,
            outcome_reason="candidate_not_reportable_or_execution_not_allowed",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            timeout_epoch=timeout_epoch,
            max_favorable_price=None,
            max_adverse_price=None,
            mfe_abs=0.0,
            mae_abs=0.0,
            mfe_r=0.0,
            mae_r=0.0,
            gross_r=0.0,
            estimated_cost_r=0.0 if estimated_cost_r is None else float(estimated_cost_r),
            cost_adjusted_r=0.0,
            target_hit=False,
            stop_hit=False,
            timeout_hit=False,
            first_hit_epoch=None,
            observation_count=len(valid_observations),
            blockers=("NOT_EXECUTABLE",),
            warnings=(),
        )

    missing_fields = [
        name
        for name, value in (
            ("ENTRY_PRICE_MISSING", entry_price),
            ("STOP_LOSS_PRICE_MISSING", stop_loss_price),
            ("TARGET_PRICE_MISSING", target_price),
            ("SIGNAL_EPOCH_MISSING", signal_epoch),
            ("TIMEOUT_EPOCH_MISSING", timeout_epoch),
        )
        if value is None
    ]
    if missing_fields:
        return _invalid_truth(candidate, reason="missing_required_price_or_time_fields", blocker=missing_fields[0])

    if direction not in _SUPPORTED_DIRECTIONS:
        return _invalid_truth(candidate, reason="unsupported_direction", blocker="UNSUPPORTED_DIRECTION")

    if not (entry_price is not None and stop_loss_price is not None and target_price is not None and signal_epoch is not None and timeout_epoch is not None):
        return _invalid_truth(candidate, reason="missing_required_price_or_time_fields", blocker="MISSING_REQUIRED_FIELDS")

    if not (isfinite(entry_price) and isfinite(stop_loss_price) and isfinite(target_price) and isfinite(signal_epoch) and isfinite(timeout_epoch)):
        return _invalid_truth(candidate, reason="non_finite_required_fields", blocker="NON_FINITE_REQUIRED_FIELDS")

    if direction == "BUY" and not (stop_loss_price < entry_price < target_price):
        return _invalid_truth(candidate, reason="invalid_buy_risk_model", blocker="INVALID_RISK_MODEL")

    active_observations = [
        item
        for item in ordered_observations
        if signal_epoch <= item.observed_epoch <= timeout_epoch
    ]
    if not active_observations:
        return CandidateOutcomeTruth(
            schema_version=CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION,
            read_only=True,
            append=False,
            is_order_action=False,
            broker_api_called=False,
            live_order_allowed=False,
            live_order_action=False,
            broker_order_action=False,
            candidate_id=candidate.candidate_id,
            trade_id=candidate.trade_id,
            strategy_family=candidate.strategy_family,
            symbol=candidate.symbol,
            index=candidate.index,
            regime=candidate.regime,
            expiry_type=candidate.expiry_type,
            signal_epoch=signal_epoch,
            outcome_status=NO_OBSERVATIONS,
            outcome_reason="no_observations_after_signal_epoch",
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            timeout_epoch=timeout_epoch,
            max_favorable_price=None,
            max_adverse_price=None,
            mfe_abs=0.0,
            mae_abs=0.0,
            mfe_r=0.0,
            mae_r=0.0,
            gross_r=0.0,
            estimated_cost_r=0.0 if estimated_cost_r is None else float(estimated_cost_r),
            cost_adjusted_r=0.0,
            target_hit=False,
            stop_hit=False,
            timeout_hit=False,
            first_hit_epoch=None,
            observation_count=0,
            blockers=("NO_OBSERVATIONS",),
            warnings=(),
        )

    if direction != "BUY":
        return _invalid_truth(candidate, reason="unsupported_direction", blocker="UNSUPPORTED_DIRECTION")

    max_favorable_price = max(item.ltp for item in active_observations)
    min_favorable_price = min(item.ltp for item in active_observations)
    mfe_abs = max(0.0, max_favorable_price - entry_price)
    mae_abs = max(0.0, entry_price - min_favorable_price)
    risk_per_unit = entry_price - stop_loss_price
    if risk_per_unit <= 0:
        return _invalid_truth(candidate, reason="invalid_risk_per_unit", blocker="INVALID_RISK_MODEL")

    mfe_r = mfe_abs / risk_per_unit
    mae_r = mae_abs / risk_per_unit
    cost_r = float(estimated_cost_r) if estimated_cost_r is not None else 0.0
    if estimated_cost_r is None and estimated_cost_abs is not None:
        cost_r = float(estimated_cost_abs) / risk_per_unit

    target_hit_epoch: float | None = None
    stop_hit_epoch: float | None = None
    ambiguous_epoch: float | None = None
    for observation in active_observations:
        target_hit = observation.ltp >= target_price
        stop_hit = observation.ltp <= stop_loss_price
        if observation.bid is not None and observation.ask is not None:
            if observation.bid <= stop_loss_price and observation.ask >= target_price:
                target_hit = True
                stop_hit = True
        if observation.spread is not None and observation.spread < 0:
            return _invalid_truth(candidate, reason="negative_spread", blocker="INVALID_OBSERVATION")
        if target_hit and stop_hit:
            ambiguous_epoch = observation.observed_epoch
            break
        if target_hit:
            target_hit_epoch = observation.observed_epoch
            break
        if stop_hit:
            stop_hit_epoch = observation.observed_epoch
            break

    outcome_status = TIMEOUT
    outcome_reason = "timeout_reached_before_target_or_stop"
    target_hit = False
    stop_hit = False
    timeout_hit = True
    first_hit_epoch: float | None = None
    gross_r = (active_observations[-1].ltp - entry_price) / risk_per_unit

    if ambiguous_epoch is not None:
        outcome_status = AMBIGUOUS_SAME_BAR
        outcome_reason = "target_and_stop_hit_same_observation"
        target_hit = False
        stop_hit = False
        timeout_hit = False
        first_hit_epoch = ambiguous_epoch
        gross_r = 0.0
    elif target_hit_epoch is not None:
        outcome_status = TARGET_HIT
        outcome_reason = "target_hit_before_stop"
        target_hit = True
        stop_hit = False
        timeout_hit = False
        first_hit_epoch = target_hit_epoch
        gross_r = (target_price - entry_price) / risk_per_unit
    elif stop_hit_epoch is not None:
        outcome_status = STOP_HIT
        outcome_reason = "stop_hit_before_target"
        target_hit = False
        stop_hit = True
        timeout_hit = False
        first_hit_epoch = stop_hit_epoch
        gross_r = -1.0
    else:
        if timeout_epoch is not None and active_observations[-1].observed_epoch > timeout_epoch:
            outcome_reason = "timeout_reached"
        else:
            outcome_reason = "no_exit_before_timeout"
        if active_observations[-1].observed_epoch < timeout_epoch:
            outcome_reason = "timeout_not_reached_but_no_target_or_stop"

    return CandidateOutcomeTruth(
        schema_version=CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION,
        read_only=True,
        append=False,
        is_order_action=False,
        broker_api_called=False,
        live_order_allowed=False,
        live_order_action=False,
        broker_order_action=False,
        candidate_id=candidate.candidate_id,
        trade_id=candidate.trade_id,
        strategy_family=candidate.strategy_family,
        symbol=candidate.symbol,
        index=candidate.index,
        regime=candidate.regime,
        expiry_type=candidate.expiry_type,
        signal_epoch=signal_epoch,
        outcome_status=outcome_status,
        outcome_reason=outcome_reason,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        target_price=target_price,
        timeout_epoch=timeout_epoch,
        max_favorable_price=max_favorable_price,
        max_adverse_price=min_favorable_price,
        mfe_abs=mfe_abs,
        mae_abs=mae_abs,
        mfe_r=mfe_r,
        mae_r=mae_r,
        gross_r=gross_r,
        estimated_cost_r=cost_r,
        cost_adjusted_r=gross_r - cost_r,
        target_hit=target_hit,
        stop_hit=stop_hit,
        timeout_hit=timeout_hit,
        first_hit_epoch=first_hit_epoch,
        observation_count=len(active_observations),
        blockers=(),
        warnings=(),
    )


__all__ = [
    "AMBIGUOUS_SAME_BAR",
    "CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION",
    "CandidateOutcomeInput",
    "CandidateOutcomeTruth",
    "INVALID_INPUT",
    "NO_OBSERVATIONS",
    "NOT_EXECUTABLE",
    "PriceObservation",
    "STOP_HIT",
    "TARGET_HIT",
    "TIMEOUT",
    "build_candidate_outcome_truth",
]
