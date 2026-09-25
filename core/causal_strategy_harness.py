"""Read-only strategy observations and CAS candidate adaptation.

Candidate qualification is delegated to the canonical CAS evaluator. Generic
signal confidence, symbol naming patterns, and completed-bar flags cannot
create candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from core.causal_pulse import NativePulse, sha256_canonical
from core.cas_morning_reversal_advisory import SPEC_SHA as CAS_SPEC_SHA
from core.cas_morning_reversal_advisory import STRATEGY_ID, evaluate as evaluate_cas
from core.cas_primitive_producer import build_cas_input, verify_primitive
from core.read_only_strategy_registry import CANONICAL_STRATEGIES
from core.signal_engine import evaluate as evaluate_signal


IST = ZoneInfo("Asia/Kolkata")
FEED_FRESHNESS_LIMIT_SECONDS = 2.5
GENERIC_CONFIDENCE_THRESHOLD = 0.70


class ApplicabilityState(str, Enum):
    APPLICABLE = "APPLICABLE"
    INAPPLICABLE = "INAPPLICABLE"
    DISABLED = "DISABLED"


class QualificationState(str, Enum):
    QUALIFIED = "QUALIFIED"
    NO_SIGNAL = "NO_SIGNAL"
    NEAR_SIGNAL = "NEAR_SIGNAL"
    UNKNOWN = "UNKNOWN"
    PREREQUISITE_MISSING = "PREREQUISITE_MISSING"


class CandidateState(str, Enum):
    QUALIFIED = "QUALIFIED"
    UNKNOWN = "UNKNOWN"


class ExecutionState(str, Enum):
    ADVISORY_ONLY_FEED_FRESH = "ADVISORY_ONLY_FEED_FRESH"
    ADVISORY_ONLY_FEED_STALE = "ADVISORY_ONLY_FEED_STALE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class StrategyObservation:
    timestamp_epoch: float
    timestamp_ist: str
    pulse_id: str
    symbol: str
    strategy_id: str
    applicability_state: ApplicabilityState
    qualification_state: QualificationState
    direction: str
    confidence: float | None
    required_inputs: list[str] = field(default_factory=list)
    missing_or_stale_inputs: list[str] = field(default_factory=list)
    reason_code: str = "NO_QUALIFIED_SIGNAL"
    source_event_or_snapshot_reference: dict[str, Any] = field(default_factory=dict)
    is_order_action: bool = False
    broker_api_called: bool = False
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_ist": self.timestamp_ist,
            "pulse_id": self.pulse_id,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "applicability_state": self.applicability_state.value,
            "qualification_state": self.qualification_state.value,
            "direction": self.direction,
            "confidence": self.confidence,
            "required_inputs": list(self.required_inputs),
            "missing_or_stale_inputs": list(self.missing_or_stale_inputs),
            "reason_code": self.reason_code,
            "source_event_or_snapshot_reference": dict(self.source_event_or_snapshot_reference),
            "is_order_action": False,
            "broker_api_called": False,
            "read_only": True,
        }


@dataclass(frozen=True)
class CausalCandidate:
    candidate_id: str
    pulse_id: str
    strategy_id: str
    symbol: str
    instrument_token: int
    direction: str
    entry_price: float | None
    stop_loss: float | None
    target_price: float | None
    regime: str
    confidence: float | None
    timestamp_epoch: float
    timestamp_ist: str
    payload_sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)
    strategy_qualified: bool = False
    qualification_evidence: dict[str, Any] = field(default_factory=dict)
    execution_eligible: bool = False
    execution_state: ExecutionState = ExecutionState.NOT_EVALUATED
    execution_block_reason: str | None = None
    feed_age_sec: float | None = None
    option_quote_age_sec: float | None = None
    candidate_state: CandidateState = CandidateState.UNKNOWN
    is_order_action: bool = False
    broker_api_called: bool = False
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "pulse_id": self.pulse_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "instrument_token": self.instrument_token,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "regime": self.regime,
            "confidence": self.confidence,
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_ist": self.timestamp_ist,
            "payload_sha256": self.payload_sha256,
            "metadata": dict(self.metadata),
            "strategy_qualified": self.strategy_qualified,
            "qualification_evidence": dict(self.qualification_evidence),
            "execution_eligible": False,
            "execution_state": self.execution_state.value,
            "execution_block_reason": self.execution_block_reason,
            "feed_age_sec": self.feed_age_sec,
            "option_quote_age_sec": self.option_quote_age_sec,
            "candidate_state": self.candidate_state.value,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "allowed_for_live_execution": False,
        }


@dataclass(frozen=True)
class StrategyEvaluationResult:
    pulse_id: str
    regime: str
    candidates: list[CausalCandidate]
    rejections: list[dict[str, Any]]
    evaluated_symbol_count: int
    timestamp_epoch: float
    observations: list[StrategyObservation] = field(default_factory=list)
    telemetry_counters: dict[str, int] = field(default_factory=dict)

    @property
    def executable_candidates(self) -> list[CausalCandidate]:
        # Feed freshness alone is not execution readiness or authority.
        return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "regime": self.regime,
            "candidates_count": len(self.candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "executable_candidates_count": 0,
            "executable_candidates": [],
            "observations_count": len(self.observations),
            "observations": [observation.to_dict() for observation in self.observations],
            "telemetry_counters": dict(self.telemetry_counters),
            "rejections_count": len(self.rejections),
            "rejections": list(self.rejections),
            "evaluated_symbol_count": self.evaluated_symbol_count,
            "timestamp_epoch": self.timestamp_epoch,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "allowed_for_live_execution": False,
            "orders_placed": 0,
        }


def _symbol_rows(
    market_snapshot: Mapping[str, Any] | None,
    feed_health_truth: Mapping[str, Any] | None,
    cas_primitive_store: Any | None = None,
) -> list[Mapping[str, Any]]:
    snapshot_symbols = market_snapshot.get("symbols", {}) if isinstance(market_snapshot, Mapping) else {}
    if isinstance(feed_health_truth, Mapping):
        rows = feed_health_truth.get("symbols")
        if not isinstance(rows, list):
            payload = feed_health_truth.get("payload")
            rows = payload.get("symbols") if isinstance(payload, Mapping) else None
        if isinstance(rows, list):
            enriched_rows: list[Mapping[str, Any]] = []
            for r in rows:
                if not isinstance(r, Mapping):
                    continue
                d = dict(r)
                sym = str(d.get("symbol") or "").upper()
                tok = _finite_float(d.get("instrument_token"))
                if tok is None or tok <= 0 or not tok.is_integer():
                    snap_sym = snapshot_symbols.get(sym, {}) if isinstance(snapshot_symbols, Mapping) else {}
                    quote = snap_sym.get("quote_truth", {}) if isinstance(snap_sym, Mapping) else {}
                    snap_tok = _finite_float(quote.get("instrument_token"))
                    if snap_tok is not None and snap_tok > 0 and snap_tok.is_integer():
                        primitive_token = _finite_float(getattr(cas_primitive_store, "underlying_token", None))
                        if sym != "NIFTY" or (primitive_token is not None and snap_tok == primitive_token):
                            d["instrument_token"] = int(snap_tok)
                enriched_rows.append(d)
            return enriched_rows
    if not isinstance(market_snapshot, Mapping):
        return []
    symbols = market_snapshot.get("symbols")
    if not isinstance(symbols, Mapping):
        return []
    result: list[Mapping[str, Any]] = []
    for symbol, row in symbols.items():
        if not isinstance(row, Mapping):
            continue
        feed = row.get("feed_health")
        quote = row.get("quote_truth")
        feed = feed if isinstance(feed, Mapping) else {}
        quote = quote if isinstance(quote, Mapping) else {}
        tok = _finite_float(quote.get("instrument_token"))
        result.append({
            "symbol": symbol,
            "feed_ok": feed.get("status") == "HEALTHY",
        "instrument_token": int(tok) if tok is not None and tok > 0 and tok.is_integer() else quote.get("instrument_token"),
            "option_last_tick_age_sec": feed.get("underlying_quote_age_sec"),
        })
    return result


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _feed_freshness(row: Mapping[str, Any]) -> tuple[bool, float | None]:
    age = _finite_float(row.get("option_last_tick_age_sec"))
    fresh = row.get("feed_ok") is True and age is not None and 0 <= age <= FEED_FRESHNESS_LIMIT_SECONDS
    return fresh, age


def _primitive_pair(
    store: Any,
    *,
    pulse: NativePulse,
    token: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return CAS inputs only when both immutable primitives verify exactly."""
    if store is None:
        return None, "CAS_PRIMITIVE_STORE_UNAVAILABLE"
    if (
        getattr(store, "session_id", None) != pulse.session_id
        or getattr(store, "source_sha", None) != pulse.producer_sha
        or _finite_float(getattr(store, "underlying_token", None)) != token
    ):
        return None, "CAS_PRIMITIVE_STORE_IDENTITY_MISMATCH"
    rows = getattr(store, "rows", None)
    if not isinstance(rows, Mapping):
        return None, "CAS_PRIMITIVES_MISSING"
    target_times = {"0915": "09:15:00.000", "1000": "10:00:00.000"}
    decision_date = datetime.fromtimestamp(pulse.timestamp_epoch, tz=timezone.utc).astimezone(IST).date()
    for name, expected_target in target_times.items():
        row = rows.get(name)
        if not isinstance(row, Mapping):
            return None, f"CAS_PRIMITIVE_{name}_MISSING"
        try:
            verified, _reason = verify_primitive(
                dict(row),
                session_id=pulse.session_id,
                source_sha=pulse.producer_sha,
                underlying_token=token,
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            verified = False
        if not verified:
            return None, f"CAS_PRIMITIVE_{name}_INVALID"
        if (
            row.get("strategy_id") != STRATEGY_ID
            or row.get("underlying_symbol") != "NIFTY"
            or row.get("primitive_name") != name
            or row.get("target_timestamp_ist") != expected_target
            or row.get("timestamp_fallback_used") is not False
            or row.get("admissible_for_prospective_campaign") is not True
            or row.get("price_field") != "last_price"
            or row.get("price_source") != "core/tick_store.py"
            or not row.get("timestamp_source_field")
        ):
            return None, f"CAS_PRIMITIVE_{name}_PROVENANCE_INCOMPLETE"
        if _finite_float(row.get("source_timestamp_epoch")) is None or _finite_float(row.get("receive_timestamp_epoch")) is None:
            return None, f"CAS_PRIMITIVE_{name}_TIMESTAMP_PROVENANCE_INCOMPLETE"
        selected_epoch = _finite_float(row.get("timestamp_epoch"))
        source_epoch = _finite_float(row.get("source_timestamp_epoch"))
        if selected_epoch is None or source_epoch is None or abs(selected_epoch - source_epoch) > 0.001:
            return None, f"CAS_PRIMITIVE_{name}_TIMESTAMP_BINDING_INVALID"
        selected_time = datetime.fromtimestamp(selected_epoch, tz=timezone.utc).astimezone(IST)
        target_hour, target_minute = (9, 15) if name == "0915" else (10, 0)
        lateness_ms = _finite_float(row.get("lateness_ms"))
        price = _finite_float(row.get("price"))
        target_epoch = datetime(
            decision_date.year, decision_date.month, decision_date.day,
            target_hour, target_minute, tzinfo=IST,
        ).timestamp()
        measured_lateness_ms = (selected_epoch - target_epoch) * 1000
        if (
            selected_time.date() != decision_date
            or selected_time.hour != target_hour
            or selected_time.minute != target_minute
            or lateness_ms is None
            or not 0 <= measured_lateness_ms <= 2000
            or abs(lateness_ms - round(measured_lateness_ms)) > 1
            or price is None
            or price <= 0
        ):
            return None, f"CAS_PRIMITIVE_{name}_TARGET_OR_PRICE_INVALID"

    cas_input = build_cas_input(
        dict(rows),
        session_id=pulse.session_id,
        source_sha=pulse.producer_sha,
        cycle_id=pulse.pulse_id,
        underlying_token=token,
    )
    if not isinstance(cas_input, dict):
        return None, "CAS_INPUT_UNAVAILABLE"
    return cas_input, None


def _qualify_cas(
    *,
    store: Any,
    pulse: NativePulse,
    symbol: str,
    token: int,
) -> tuple[dict[str, Any] | None, str | None]:
    cas_input, reason = _primitive_pair(store, pulse=pulse, token=token)
    if cas_input is None:
        return None, reason
    if cas_input.get("symbol") != symbol or cas_input.get("strategy_id") != STRATEGY_ID:
        return None, "CAS_INPUT_IDENTITY_MISMATCH"

    observation_time = datetime.fromtimestamp(pulse.timestamp_epoch, tz=timezone.utc)
    cutoff = observation_time.astimezone(IST).replace(hour=15, minute=14, second=0, microsecond=0)
    try:
        received_time = datetime.fromisoformat(str(pulse.timestamp_ist).replace("Z", "+00:00"))
        if received_time.tzinfo is None or received_time.utcoffset() is None:
            return None, "CAS_RECEIVE_TIMESTAMP_UNKNOWN"
        decision = evaluate_cas(
            session_id=pulse.session_id,
            symbol=symbol,
            morning_return=float(cas_input["morning_return"]),
            observation_timestamp=observation_time,
            cutoff_timestamp=cutoff,
            received_timestamp=received_time,
            source_sha=pulse.producer_sha,
            signal_input_09_15=float(cas_input["signal_input_09_15"]),
            signal_input_10_00=float(cas_input["signal_input_10_00"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, "CAS_EVALUATION_NOT_ADMISSIBLE"
    if (
        decision.get("strategy_id") != STRATEGY_ID
        or decision.get("spec_sha") != CAS_SPEC_SHA
        or decision.get("session_id") != pulse.session_id
        or decision.get("source_sha") != pulse.producer_sha
        or decision.get("read_only") is not True
        or decision.get("broker_write_authority") is not False
        or decision.get("order_authority") is not False
        or decision.get("live_execution_authorized") is not False
    ):
        return None, "CAS_EVALUATION_PROVENANCE_INCOMPLETE"
    return decision, None


def _telemetry(
    *,
    symbols_seen: int,
    symbols_evaluated: int,
    observations: list[StrategyObservation],
    candidates: list[CausalCandidate],
) -> dict[str, int]:
    # Counts are derived after decisions; they do not participate in qualification.
    return {
        "symbols_seen": symbols_seen,
        "symbols_evaluated": symbols_evaluated,
        "strategy_observations": len(observations),
        "near_signals": sum(o.qualification_state is QualificationState.NEAR_SIGNAL for o in observations),
        "qualified_candidates": len(candidates),
        "execution_eligible_candidates": 0,
        "blocked_feed_stale": sum(c.execution_state is ExecutionState.ADVISORY_ONLY_FEED_STALE for c in candidates),
        "qualification_unknown": sum(o.qualification_state is QualificationState.UNKNOWN for o in observations),
        "no_signal": sum(o.qualification_state is QualificationState.NO_SIGNAL for o in observations),
    }


def evaluate_causal_strategies(
    *,
    pulse: NativePulse,
    market_snapshot: Mapping[str, Any] | None,
    feed_health_truth: Mapping[str, Any] | None,
    cas_primitive_store: Any | None = None,
) -> StrategyEvaluationResult:
    """Record CAS strategy observations; generic signals cannot create candidates."""
    candidates: list[CausalCandidate] = []
    observations: list[StrategyObservation] = []
    rejections: list[dict[str, Any]] = []
    symbols_data = _symbol_rows(market_snapshot, feed_health_truth, cas_primitive_store)
    registry = tuple(item for item in CANONICAL_STRATEGIES if isinstance(item, Mapping))
    regime = "UNKNOWN"
    if isinstance(market_snapshot, Mapping):
        regime = str(market_snapshot.get("primary_regime") or market_snapshot.get("regime") or "UNKNOWN")
    if regime == "UNKNOWN" and isinstance(feed_health_truth, Mapping):
        context = feed_health_truth.get("context")
        if isinstance(context, Mapping):
            regime = str(context.get("primary_regime") or "UNKNOWN")

    symbols_evaluated = 0
    for row in symbols_data:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        symbols_evaluated += 1
        token_value = _finite_float(row.get("instrument_token"))
        token = int(token_value) if token_value is not None and token_value > 0 and token_value.is_integer() else 0
        fresh, feed_age = _feed_freshness(row)
        # Generic signal output is diagnostic only and never qualifies CAS.
        signal = evaluate_signal(snapshot=row, signal_payload=row)

        for declaration in registry:
            strategy_id = str(declaration.get("strategy_id") or "")
            required = [str(value) for value in declaration.get("inputs", ())]
            if declaration.get("enabled") is not True:
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.DISABLED,
                    QualificationState.NO_SIGNAL, "UNKNOWN", None, required,
                    reason_code="STRATEGY_DISABLED",
                    source_event_or_snapshot_reference={"symbol": symbol},
                ))
                continue

            permitted_underlyings = declaration.get("required_underlyings", ())
            # Exact membership in the canonical registry is the applicability authority.
            if not isinstance(permitted_underlyings, (list, tuple, set, frozenset)) or symbol not in permitted_underlyings:
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.INAPPLICABLE,
                    QualificationState.NO_SIGNAL, "UNKNOWN", None, required,
                    reason_code="REGISTRY_SYMBOL_NOT_APPLICABLE",
                    source_event_or_snapshot_reference={"symbol": symbol},
                ))
                continue

            primitive_token = _finite_float(getattr(cas_primitive_store, "underlying_token", None))
            if strategy_id != STRATEGY_ID or token <= 0 or (
                symbol == "NIFTY" and cas_primitive_store is not None and primitive_token != token
            ):
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.APPLICABLE,
                    QualificationState.UNKNOWN, "UNKNOWN", None, required,
                    missing_or_stale_inputs=required,
                    reason_code="CANONICAL_STRATEGY_OR_TOKEN_UNAVAILABLE",
                    source_event_or_snapshot_reference={"symbol": symbol},
                ))
                continue

            decision, block_reason = _qualify_cas(
                store=cas_primitive_store, pulse=pulse, symbol=symbol, token=token,
            )
            if decision is None:
                generic_is_high = signal.confidence is not None and signal.confidence >= GENERIC_CONFIDENCE_THRESHOLD
                reason = block_reason or "CAS_QUALIFICATION_UNKNOWN"
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.APPLICABLE,
                    QualificationState.UNKNOWN,
                    signal.direction if generic_is_high else "UNKNOWN",
                    signal.confidence, required, required,
                    reason_code=reason,
                    source_event_or_snapshot_reference={"generic_signal_used_for_qualification": False},
                ))
                rejections.append({"symbol": symbol, "strategy_id": strategy_id, "reason_code": reason})
                continue

            cas_direction = str(decision.get("direction") or "")
            if cas_direction == "NO_SIGNAL":
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.APPLICABLE,
                    QualificationState.NO_SIGNAL, "UNKNOWN", None, required,
                    reason_code="CAS_NO_DIRECTIONAL_SIGNAL",
                    source_event_or_snapshot_reference={"strategy_id": strategy_id, "spec_sha": decision.get("spec_sha")},
                ))
                continue
            if cas_direction not in {"UP", "DOWN"}:
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.APPLICABLE,
                    QualificationState.UNKNOWN, "UNKNOWN", None, required,
                    reason_code="CAS_DIRECTION_INVALID",
                ))
                rejections.append({"symbol": symbol, "strategy_id": strategy_id, "reason_code": "CAS_DIRECTION_INVALID"})
                continue

            primitive_rows = getattr(cas_primitive_store, "rows", {})
            evidence = {
                "evaluator": "core.cas_morning_reversal_advisory.evaluate",
                "registry_declaration": dict(declaration),
                "canonical_decision": dict(decision),
                "strategy_id": strategy_id,
                "spec_sha": decision.get("spec_sha"),
                "source_sha": decision.get("source_sha"),
                "session_id": decision.get("session_id"),
                "candidate_id": decision.get("candidate_id"),
                "decision_timestamp": decision.get("decision_timestamp"),
                "received_timestamp": decision.get("received_timestamp"),
                "received_lag_ms": decision.get("received_lag_ms"),
                "entry_reference_timestamp": decision.get("entry_reference_timestamp"),
                "morning_return": decision.get("morning_return"),
                "direction": cas_direction,
                "option_side": decision.get("option_side"),
                "signal_input_09_15": decision.get("signal_input_09_15"),
                "signal_input_10_00": decision.get("signal_input_10_00"),
                "primitive_references": {
                    name: {
                        "record_sha256": primitive_rows[name]["record_sha256"],
                        "timestamp_epoch": primitive_rows[name]["timestamp_epoch"],
                        "price": primitive_rows[name]["price"],
                        "primitive": dict(primitive_rows[name]),
                    }
                    for name in ("0915", "1000")
                },
                "execution_status": "advisory_only",
                "read_only": True,
                "broker_write_authority": False,
                "order_authority": False,
                "live_execution_authorized": False,
            }
            required_evidence = (
                "spec_sha", "source_sha", "session_id", "candidate_id",
                "decision_timestamp", "received_timestamp", "entry_reference_timestamp", "morning_return",
                "signal_input_09_15", "signal_input_10_00",
            )
            if (
                any(evidence.get(key) in (None, "") for key in required_evidence)
                or len(evidence["primitive_references"]) != 2
                or any(not evidence["primitive_references"][name]["record_sha256"] for name in ("0915", "1000"))
            ):
                observations.append(StrategyObservation(
                    pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                    symbol, strategy_id, ApplicabilityState.APPLICABLE,
                    QualificationState.UNKNOWN, "UNKNOWN", None, required,
                    reason_code="QUALIFICATION_EVIDENCE_INCOMPLETE",
                ))
                rejections.append({"symbol": symbol, "strategy_id": strategy_id, "reason_code": "QUALIFICATION_EVIDENCE_INCOMPLETE"})
                continue

            execution_state = (
                ExecutionState.ADVISORY_ONLY_FEED_FRESH
                if fresh else ExecutionState.ADVISORY_ONLY_FEED_STALE
            )
            evidence_sha = sha256_canonical(evidence)
            candidate = CausalCandidate(
                candidate_id=str(decision["candidate_id"]),
                pulse_id=pulse.pulse_id,
                strategy_id=strategy_id,
                symbol=symbol,
                instrument_token=token,
                direction="BUY" if cas_direction == "UP" else "SELL",
                # CAS supplies underlying references, not option entry/stop/target prices.
                entry_price=None,
                stop_loss=None,
                target_price=None,
                regime=regime,
                confidence=None,
                timestamp_epoch=pulse.timestamp_epoch,
                timestamp_ist=pulse.timestamp_ist,
                payload_sha256=evidence_sha,
                metadata={"option_side": decision.get("option_side")},
                strategy_qualified=True,
                qualification_evidence=evidence,
                execution_eligible=False,
                execution_state=execution_state,
                execution_block_reason=None if fresh else "FEED_FRESHNESS_NOT_CONFIRMED",
                feed_age_sec=feed_age,
                candidate_state=CandidateState.QUALIFIED,
            )
            candidates.append(candidate)
            observations.append(StrategyObservation(
                pulse.timestamp_epoch, pulse.timestamp_ist, pulse.pulse_id,
                symbol, strategy_id, ApplicabilityState.APPLICABLE,
                QualificationState.QUALIFIED, cas_direction, None, required,
                missing_or_stale_inputs=[] if fresh else ["feed_quote"],
                reason_code="CAS_STRATEGY_QUALIFIED_ADVISORY_ONLY",
                source_event_or_snapshot_reference={"candidate_id": candidate.candidate_id, "evidence_sha256": evidence_sha},
            ))

    telemetry = _telemetry(
        symbols_seen=len(symbols_data),
        symbols_evaluated=symbols_evaluated,
        observations=observations,
        candidates=candidates,
    )
    return StrategyEvaluationResult(
        pulse_id=pulse.pulse_id,
        regime=regime,
        candidates=candidates,
        rejections=rejections,
        evaluated_symbol_count=symbols_evaluated,
        timestamp_epoch=pulse.timestamp_epoch,
        observations=observations,
        telemetry_counters=telemetry,
    )
