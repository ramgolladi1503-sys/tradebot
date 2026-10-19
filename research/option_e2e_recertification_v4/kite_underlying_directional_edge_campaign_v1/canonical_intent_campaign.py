from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Callable, Mapping

import pandas as pd

from core.movement_contract import StrategyCandidate
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1 import (
    canonical_adapter,
)

IST = "Asia/Kolkata"
DIRECTION_TO_OPTION = {"BUY_CALL": "CE", "BUY_PUT": "PE"}
STRUCTURAL_INTENT_BLOCKERS = {"NO_TRADE_CHOP", "CONFLICTING_TRAP_SIGNAL"}


class CanonicalIntentError(ValueError):
    """Raised when canonical signal-to-intent conversion is not trustworthy."""


@dataclass(frozen=True)
class CanonicalIntentPolicy:
    timeframe_minutes: int = 5
    minimum_completed_bars: int = 2
    max_intents_per_strategy_session: int = 1
    option_entry_delay_minutes: int = 1

    def __post_init__(self) -> None:
        if self.timeframe_minutes <= 0:
            raise CanonicalIntentError("timeframe_minutes_must_be_positive")
        if self.minimum_completed_bars <= 0:
            raise CanonicalIntentError("minimum_completed_bars_must_be_positive")
        if self.max_intents_per_strategy_session <= 0:
            raise CanonicalIntentError(
                "max_intents_per_strategy_session_must_be_positive"
            )
        if self.option_entry_delay_minutes <= 0:
            raise CanonicalIntentError("option_entry_delay_minutes_must_be_positive")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _normalize_timestamp(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize(IST)
    return stamp.tz_convert(IST)


def _decision_timestamp(bar_start: Any, *, timeframe_minutes: int) -> pd.Timestamp:
    return _normalize_timestamp(bar_start) + pd.Timedelta(minutes=timeframe_minutes)


def _minutes_from_session_open(stamp: pd.Timestamp) -> int:
    session_open = pd.Timestamp(f"{stamp.date().isoformat()} 09:15:00", tz=IST)
    return max(0, int((stamp - session_open).total_seconds() // 60))


def _minutes_to_session_close(stamp: pd.Timestamp) -> int:
    session_close = pd.Timestamp(f"{stamp.date().isoformat()} 15:30:00", tz=IST)
    return max(0, int((session_close - stamp).total_seconds() // 60))


def _history_rows(
    frame: pd.DataFrame, end_index: int, *, timeframe_minutes: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    duration = timedelta(minutes=timeframe_minutes)
    for row in frame.iloc[: end_index + 1].to_dict("records"):
        rows.append(
            {
                "timestamp": _normalize_timestamp(row["timestamp"]),
                "bar_duration": duration,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0.0),
            }
        )
    return rows


def candidate_is_intent_eligible(candidate: StrategyCandidate) -> bool:
    if candidate.direction not in DIRECTION_TO_OPTION:
        return False
    if candidate.status == "NO_TRADE":
        return False
    blockers = {str(value).strip().upper() for value in candidate.blockers}
    return not bool(blockers.intersection(STRUCTURAL_INTENT_BLOCKERS))


def _identity_payload(
    *,
    strategy_key: str,
    candidate: StrategyCandidate,
    signal_timestamp: pd.Timestamp,
    signal_price: float,
    callable_identity: str,
    callable_source_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "canonical_option_intent_identity_v1",
        "strategy_key": strategy_key,
        "candidate_strategy_id": candidate.strategy_id,
        "movement_type": candidate.movement_type,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "signal_timestamp": signal_timestamp.isoformat(),
        "signal_price": float(signal_price),
        "entry_trigger": candidate.entry_trigger,
        "invalid_if": candidate.invalid_if,
        "source_signals": list(candidate.source_signals),
        "callable_identity": callable_identity,
        "callable_source_hash": callable_source_hash,
    }


def candidate_to_intent_row(
    *,
    strategy_key: str,
    candidate: StrategyCandidate,
    signal_timestamp: pd.Timestamp,
    signal_price: float,
    partition: str,
    callable_identity: str,
    callable_source_hash: str,
    policy: CanonicalIntentPolicy,
) -> dict[str, Any]:
    if not candidate_is_intent_eligible(candidate):
        raise CanonicalIntentError("candidate_not_intent_eligible")
    option_type = DIRECTION_TO_OPTION[candidate.direction]
    earliest = signal_timestamp + pd.Timedelta(
        minutes=policy.option_entry_delay_minutes
    )
    identity_payload = _identity_payload(
        strategy_key=strategy_key,
        candidate=candidate,
        signal_timestamp=signal_timestamp,
        signal_price=signal_price,
        callable_identity=callable_identity,
        callable_source_hash=callable_source_hash,
    )
    identity_hash = hashlib.sha256(
        _canonical_json(identity_payload).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "canonical_option_intent_v1",
        "strategy_id": strategy_key,
        "candidate_strategy_id": candidate.strategy_id,
        "movement_type": candidate.movement_type,
        "underlying": candidate.symbol,
        "signal_timestamp": signal_timestamp.isoformat(),
        "earliest_entry_timestamp": earliest.isoformat(),
        "direction": candidate.direction,
        "signal_time_underlying_price": float(signal_price),
        "intended_option_type": option_type,
        "intended_expiry_rule": "nearest_non_expired",
        "strike_rule": "ATM",
        "strike_offset_steps": 0,
        "signal_identity_hash": identity_hash,
        "partition": partition,
        "candidate_status": candidate.status,
        "candidate_blockers": json.dumps(list(candidate.blockers), sort_keys=True),
        "candidate_warnings": json.dumps(list(candidate.warnings), sort_keys=True),
        "candidate_raw_score": candidate.raw_score,
        "candidate_confidence_score": candidate.confidence_score,
        "candidate_price_structure_score": candidate.price_structure_score,
        "entry_trigger": candidate.entry_trigger,
        "invalid_if": candidate.invalid_if,
        "canonical_callable_identity": callable_identity,
        "canonical_callable_source_hash": callable_source_hash,
        "intent_status": "RESEARCH_ONLY_CANONICAL_PRICE_STRUCTURE_INTENT",
        "allowed_for_live_execution": False,
    }


def generate_session_intents(
    *,
    strategy_key: str,
    frame: pd.DataFrame,
    session_date: str,
    symbol: str,
    partition: str,
    policy: CanonicalIntentPolicy | None = None,
    invoker: Callable[..., Any] = canonical_adapter.invoke_canonical,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    policy = policy or CanonicalIntentPolicy()
    if partition not in {"development", "validation", "holdout"}:
        raise CanonicalIntentError(f"invalid_partition:{partition}")
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise CanonicalIntentError(
            f"underlying_columns_missing:{','.join(sorted(missing))}"
        )
    rows = frame.copy()
    rows["timestamp"] = rows["timestamp"].map(_normalize_timestamp)
    rows = rows.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if "volume" not in rows.columns:
        rows["volume"] = 0.0

    intents: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    invocation_count = 0
    candidate_count = 0
    exception_count = 0
    callable_identities: set[str] = set()
    callable_source_hashes: set[str] = set()
    exact_reasons: set[str] = set()

    start_index = policy.minimum_completed_bars - 1
    for index in range(start_index, len(rows)):
        history_rows = _history_rows(
            rows, index, timeframe_minutes=policy.timeframe_minutes
        )
        decision_stamp = _decision_timestamp(
            rows.iloc[index]["timestamp"],
            timeframe_minutes=policy.timeframe_minutes,
        )
        current = dict(rows.iloc[index].to_dict())
        current["timestamp"] = decision_stamp
        history = canonical_adapter.build_completed_history(
            history_rows,
            symbol=symbol,
            session_date=session_date,
            timeframe=f"{policy.timeframe_minutes}m",
        )
        context = canonical_adapter.build_context(
            symbol=symbol,
            current=current,
            completed_history=history,
            minutes_since_open=_minutes_from_session_open(decision_stamp),
            minutes_to_close=_minutes_to_session_close(decision_stamp),
        )
        candidates, record = invoker(strategy_key, context)
        invocation_count += int(record.invocation_count)
        candidate_count += int(record.candidate_count)
        exception_count += int(record.exception_count)
        callable_identities.add(record.callable_identity)
        callable_source_hashes.add(record.callable_source_hash)
        if record.exact_reason:
            exact_reasons.add(record.exact_reason)

        for candidate in candidates:
            if candidate.symbol != symbol.upper():
                exact_reasons.add(
                    f"candidate_symbol_mismatch:{candidate.symbol}:{symbol.upper()}"
                )
                continue
            if not candidate_is_intent_eligible(candidate):
                continue
            row = candidate_to_intent_row(
                strategy_key=strategy_key,
                candidate=candidate,
                signal_timestamp=decision_stamp,
                signal_price=float(rows.iloc[index]["close"]),
                partition=partition,
                callable_identity=record.callable_identity,
                callable_source_hash=record.callable_source_hash,
                policy=policy,
            )
            identity_hash = str(row["signal_identity_hash"])
            if identity_hash in seen_hashes:
                continue
            seen_hashes.add(identity_hash)
            intents.append(row)
            if len(intents) >= policy.max_intents_per_strategy_session:
                break
        if len(intents) >= policy.max_intents_per_strategy_session:
            break

    invocation_summary = {
        "schema_version": "canonical_invocation_summary_v1",
        "strategy_id": strategy_key,
        "underlying": symbol.upper(),
        "session_date": session_date,
        "partition": partition,
        "invocation_count": invocation_count,
        "candidate_count": candidate_count,
        "intent_count": len(intents),
        "exception_count": exception_count,
        "callable_identities": json.dumps(sorted(callable_identities), sort_keys=True),
        "callable_source_hashes": json.dumps(
            sorted(callable_source_hashes), sort_keys=True
        ),
        "exact_reasons": json.dumps(sorted(exact_reasons), sort_keys=True),
        "holdout_outcomes_read": False,
        "allowed_for_live_execution": False,
    }
    return intents, invocation_summary


def policy_to_dict(policy: CanonicalIntentPolicy) -> dict[str, Any]:
    return asdict(policy)
