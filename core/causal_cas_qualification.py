"""Strict, read-only CAS qualification from captured, immutable exchange primitives.

No generic signal score, caller-provided direction, or completed-bar boolean
has authority to qualify a canonical CAS strategy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
import math
from typing import Any
from zoneinfo import ZoneInfo

from core.cas_morning_reversal_advisory import evaluate as evaluate_cas
from core.cas_primitive_producer import build_cas_input, verify_primitive, SPEC_SHA
from core.causal_pulse import NativePulse, sha256_canonical

IST = ZoneInfo("Asia/Kolkata")
STRATEGY_ID = "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"


@dataclass(frozen=True)
class CASQualification:
    state: str
    reason: str
    direction: str = "UNKNOWN"
    option_side: str | None = None
    advisory_ready: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)


def _primitive_time_valid(row: dict, *, session_day, hour: int, minute: int) -> bool:
    """Check exchange timestamp, original source timestamp and nonfallback clock."""
    try:
        epoch = float(row["timestamp_epoch"])
        source_epoch = float(row["source_timestamp_epoch"])
        if not math.isfinite(epoch) or not math.isfinite(source_epoch):
            return False
        if abs(epoch - source_epoch) > 0.001 or row.get("timestamp_fallback_used") is not False:
            return False
        stamp = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(IST)
        target = datetime.combine(session_day, time(hour, minute), tzinfo=IST)
        lag = (stamp - target).total_seconds()
        return 0 <= lag <= 2.0
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def qualify_cas(*, pulse: NativePulse, store: Any, token: int) -> CASQualification:
    """Evaluate CAS only from the session-bound 09:15/10:00/15:14 primitives.

    A later pulse can preserve historical qualification for diagnostic reporting,
    but only a pulse close to the authoritative 15:14 event is advisory-ready.
    Execution authority is always absent because CAS is SHADOW_ONLY.
    """
    if store is None:
        return CASQualification("UNKNOWN", "CAS_PRIMITIVE_STORE_MISSING")
    if token <= 0 or (store.session_id, store.source_sha, store.underlying_token) != (
        pulse.session_id, pulse.producer_sha, token
    ):
        return CASQualification("UNKNOWN", "CAS_STORE_IDENTITY_MISMATCH")
    try:
        now = datetime.fromtimestamp(pulse.timestamp_epoch, timezone.utc).astimezone(IST)
        recorded = datetime.fromisoformat(pulse.timestamp_ist)
        if recorded.tzinfo is None or abs(recorded.timestamp() - pulse.timestamp_epoch) > 0.001:
            return CASQualification("UNKNOWN", "PULSE_TIMESTAMP_MISMATCH")
    except (TypeError, ValueError, OverflowError):
        return CASQualification("UNKNOWN", "PULSE_TIMESTAMP_INVALID")
    cutoff = datetime.combine(now.date(), time(15, 14), tzinfo=IST)
    if now < cutoff:
        return CASQualification("NOT_IN_WINDOW", "CAS_1514_WINDOW_NOT_OPEN")
    rows = store.rows
    for name, h, m in (("0915", 9, 15), ("1000", 10, 0), ("1514", 15, 14)):
        row = rows.get(name)
        if not isinstance(row, dict):
            return CASQualification("UNKNOWN", "CAS_" + name + "_PRIMITIVE_MISSING")
        verified, why = verify_primitive(
            row, session_id=pulse.session_id, source_sha=pulse.producer_sha,
            underlying_token=token,
        )
        if not verified or not _primitive_time_valid(row, session_day=now.date(), hour=h, minute=m):
            return CASQualification("UNKNOWN", "CAS_" + name + "_PRIMITIVE_INVALID:" + why)
        if float(row["timestamp_epoch"]) > pulse.timestamp_epoch:
            return CASQualification("UNKNOWN", "CAS_FUTURE_PRIMITIVE")
    quote = rows["1514"]
    quote_dt = datetime.fromtimestamp(float(quote["timestamp_epoch"]), timezone.utc).astimezone(IST)
    receive_epoch = quote.get("receive_timestamp_epoch")
    if receive_epoch is None:
        return CASQualification("UNKNOWN", "CAS_RECEIVE_TIMESTAMP_MISSING")
    try:
        received = datetime.fromtimestamp(float(receive_epoch), timezone.utc).astimezone(IST)
    except (ValueError, TypeError, OverflowError):
        return CASQualification("UNKNOWN", "CAS_RECEIVE_TIMESTAMP_INVALID")
    if received < quote_dt or (received - cutoff).total_seconds() > 2:
        return CASQualification("UNKNOWN", "CAS_RECEIVE_TIMESTAMP_LATE")
    try:
        built = build_cas_input(
            rows, session_id=pulse.session_id, source_sha=pulse.producer_sha,
            cycle_id=pulse.pulse_id, underlying_token=token,
            observation_timestamp=quote_dt.isoformat(),
        )
        if not built:
            return CASQualification("UNKNOWN", "CAS_FROZEN_INPUT_INVALID")
        result = evaluate_cas(
            session_id=pulse.session_id, symbol="NIFTY",
            morning_return=built["morning_return"], observation_timestamp=quote_dt,
            cutoff_timestamp=cutoff, received_timestamp=received,
            source_sha=pulse.producer_sha,
            signal_input_09_15=built["signal_input_09_15"],
            signal_input_10_00=built["signal_input_10_00"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        return CASQualification("UNKNOWN", "CAS_EVALUATOR_REJECTED:" + type(exc).__name__)
    if result.get("direction") == "NO_SIGNAL":
        return CASQualification("NO_SIGNAL", "CAS_MORNING_RETURN_FLAT")
    if result.get("strategy_id") != STRATEGY_ID or result.get("direction") not in ("UP", "DOWN"):
        return CASQualification("UNKNOWN", "CAS_EVALUATOR_OUTPUT_INVALID")
    ready = 0 <= (pulse.timestamp_epoch - float(quote["timestamp_epoch"])) <= 2.5
    evidence = {
        "strategy_id": STRATEGY_ID,
        "primitive_spec_sha": SPEC_SHA,
        "evaluator": "core.cas_morning_reversal_advisory.evaluate",
        "input_record_hashes": {name: rows[name]["record_sha256"] for name in ("0915", "1000", "1514")},
        "source_sha": pulse.producer_sha,
        "session_id": pulse.session_id,
        "decision_exchange_ts_epoch": quote["timestamp_epoch"],
        "receive_ts_epoch": quote["receive_timestamp_epoch"],
        "morning_return": built["morning_return"],
        "output_sha256": sha256_canonical({
            "strategy_id": result["strategy_id"],
            "direction": result["direction"],
            "option_side": result["option_side"],
            "morning_return": result["morning_return"],
        }),
        "research_state": result["research_state"],
        "execution_status": result["execution_status"],
    }
    return CASQualification(
        "QUALIFIED", "CAS_QUALIFIED_SHADOW_ONLY",
        direction=result["direction"], option_side=result["option_side"],
        advisory_ready=ready, evidence=evidence,
    )
