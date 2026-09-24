"""Causal Strategy Observation Adapter (Hops 5-8).

Wraps canonical strategy registry and signal evaluation primitives into immutable
NativePulse trace envelopes without duplicating strategy logic or inventing fake setups.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.causal_pulse import NativePulse, sha256_canonical
from core.read_only_strategy_registry import CANONICAL_STRATEGIES
from core.causal_cas_qualification import STRATEGY_ID


@dataclass(frozen=True)
class StrategyObservation:
    timestamp_epoch: float
    timestamp_ist: str
    pulse_id: str
    symbol: str
    strategy_id: str
    applicability_state: str  # APPLICABLE, INAPPLICABLE, DISABLED
    qualification_state: str  # QUALIFIED, NO_SIGNAL, NEAR_SIGNAL, UNKNOWN, PREREQUISITE_MISSING
    direction: str  # UP, DOWN, UNKNOWN for CAS underlying direction
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
            "applicability_state": self.applicability_state,
            "qualification_state": self.qualification_state,
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
    advisory_ready: bool = False
    execution_eligible: bool = False
    execution_block_reason: str | None = None
    feed_age_sec: float | None = None
    option_quote_age_sec: float | None = None
    candidate_state: str = "UNKNOWN"
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
            "execution_eligible": self.execution_eligible,
            "advisory_ready": self.advisory_ready,
            "execution_block_reason": self.execution_block_reason,
            "feed_age_sec": self.feed_age_sec,
            "option_quote_age_sec": self.option_quote_age_sec,
            "candidate_state": self.candidate_state,
            "is_order_action": False,
            "broker_api_called": False,
            "read_only": True,
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
    telemetry_counters: dict[str, Any] = field(default_factory=dict)

    @property
    def executable_candidates(self) -> list[CausalCandidate]:
        return [c for c in self.candidates if c.execution_eligible]

    @property
    def advisory_candidates(self) -> list[CausalCandidate]:
        return [c for c in self.candidates if c.advisory_ready and c.strategy_qualified]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "regime": self.regime,
            "candidates_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "executable_candidates_count": len(self.executable_candidates),
            "executable_candidates": [c.to_dict() for c in self.executable_candidates],
            "advisory_candidates_count": len(self.advisory_candidates),
            "advisory_candidates": [c.to_dict() for c in self.advisory_candidates],
            "observations_count": len(self.observations),
            "observations": [o.to_dict() for o in self.observations],
            "telemetry_counters": dict(self.telemetry_counters),
            "rejections_count": len(self.rejections),
            "rejections": self.rejections,
            "evaluated_symbol_count": self.evaluated_symbol_count,
            "timestamp_epoch": self.timestamp_epoch,
            "read_only": True,
            "is_order_action": False,
        }


def evaluate_causal_strategies(
    *,
    pulse: NativePulse,
    market_snapshot: Mapping[str, Any] | None,
    feed_health_truth: Mapping[str, Any] | None,
    cas_primitive_store: Any | None = None,
) -> StrategyEvaluationResult:
    """Observe registered strategies. Only a genuine evaluator may qualify one.

    CAS is SHADOW_ONLY: it may emit a causally supported advisory candidate,
    never an executable candidate or invented option entry/SL/target.
    """
    snapshot = market_snapshot if isinstance(market_snapshot, Mapping) else {}
    feed = feed_health_truth if isinstance(feed_health_truth, Mapping) else {}
    symbols_data = feed.get("symbols") or (feed.get("payload") or {}).get("symbols") or []
    symbols_data = list(symbols_data) if isinstance(symbols_data, (list, tuple)) else []
    # The aggregate health report may cover options without listing the index.
    # Read NIFTY only from an actual market snapshot rather than fabricate one.
    snapshots = snapshot.get("symbols") or {}
    if isinstance(snapshots, Mapping):
        listed = {str(row.get("symbol") or "").upper() for row in symbols_data if isinstance(row, Mapping)}
        for sym, payload in snapshots.items():
            if not isinstance(payload, Mapping) or str(sym).upper() in listed:
                continue
            quote = payload.get("quote_truth") or {}
            health = payload.get("feed_health") or {}
            symbols_data.append({
                "symbol": sym,
                "instrument_token": quote.get("instrument_token"),
                "feed_ok": health.get("status") == "HEALTHY",
                "underlying_quote_age_sec": health.get("underlying_quote_age_sec"),
            })
    regime = str(snapshot.get("primary_regime") or snapshot.get("regime") or
                 (feed.get("context") or {}).get("primary_regime") or "UNKNOWN")
    candidates: list[CausalCandidate] = []
    observations: list[StrategyObservation] = []
    rejections: list[dict[str, Any]] = []
    seen = 0
    tc: dict[str, Any] = {
        "symbols_seen": len(symbols_data), "symbols_evaluated": 0,
        "strategy_observations": 0, "qualified_candidates": 0,
        "execution_eligible_candidates": 0, "advisory_ready_candidates": 0,
        "qualification_unknown": 0, "no_signal": 0,
        "blocked_prerequisites": 0,
        # Execution gates cannot be inferred from a fresh underlying quote.
        "execution_gates": "NOT_EVALUATED_SHADOW_ONLY",
    }
    for info in symbols_data:
        if not isinstance(info, Mapping):
            continue
        symbol = str(info.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        seen += 1
        tc["symbols_evaluated"] += 1
        token = int(info.get("instrument_token") or 0)
        if (symbol == "NIFTY" and token <= 0 and cas_primitive_store is not None
                and getattr(cas_primitive_store, "session_id", None) == pulse.session_id
                and getattr(cas_primitive_store, "source_sha", None) == pulse.producer_sha):
            # The store token was resolved against the runtime's NIFTY mapping.
            token = int(getattr(cas_primitive_store, "underlying_token", 0) or 0)
        for strategy in CANONICAL_STRATEGIES:
            strategy_id = str(strategy["strategy_id"])
            required = list(strategy.get("inputs", ()))
            applicability = "APPLICABLE"
            qualification = "UNKNOWN"
            reason = "STRATEGY_EVALUATOR_NOT_WIRED"
            direction = "UNKNOWN"
            missing: list[str] = []
            confidence: float | None = None
            evidence: dict[str, Any] = {"symbol": symbol}
            qualified = None

            if not strategy.get("enabled", False):
                applicability = "DISABLED"
                reason = "STRATEGY_DISABLED"
            elif strategy.get("required_underlyings") and symbol not in strategy["required_underlyings"]:
                applicability = "INAPPLICABLE"
                reason = "STRATEGY_INAPPLICABLE"
            elif strategy_id == STRATEGY_ID:
                from core.causal_cas_qualification import qualify_cas
                qualified = qualify_cas(pulse=pulse, store=cas_primitive_store, token=token)
                qualification, reason, direction = qualified.state, qualified.reason, qualified.direction
                evidence = dict(qualified.evidence)
                if qualification == "NOT_IN_WINDOW":
                    applicability, qualification = "INAPPLICABLE", "UNKNOWN"
                if qualification == "UNKNOWN":
                    missing = [reason]
                    tc["qualification_unknown"] += 1
                    tc["blocked_prerequisites"] += 1
                elif qualification == "NO_SIGNAL":
                    tc["no_signal"] += 1
            else:
                tc["qualification_unknown"] += 1

            obs = StrategyObservation(
                timestamp_epoch=pulse.timestamp_epoch,
                timestamp_ist=pulse.timestamp_ist,
                pulse_id=pulse.pulse_id,
                symbol=symbol,
                strategy_id=strategy_id,
                applicability_state=applicability,
                qualification_state=qualification,
                direction=direction,
                confidence=confidence,
                required_inputs=required,
                missing_or_stale_inputs=missing,
                reason_code=reason,
                source_event_or_snapshot_reference=evidence,
            )
            observations.append(obs)
            tc["strategy_observations"] += 1
            if qualification != "QUALIFIED" or qualified is None:
                if applicability == "APPLICABLE":
                    rejections.append({
                        "symbol": symbol, "strategy_id": strategy_id,
                        "reason_code": reason,
                        "detail": "No qualified strategy-specific candidate.",
                    })
                continue

            # A frozen 15:14 signal is NOT a perpetual intraday opportunity.
            # Later pulses may report the observation, but must not emit a
            # new candidate after the advisory window has expired.
            decision_epoch = float(qualified.evidence["decision_exchange_ts_epoch"])
            decision_lag = pulse.timestamp_epoch - decision_epoch
            if not 0 <= decision_lag <= 2.5:
                rejections.append({
                    "symbol": symbol, "strategy_id": strategy_id,
                    "reason_code": "CAS_ADVISORY_WINDOW_EXPIRED",
                })
                continue
            feed_ok = info.get("feed_ok") is True
            advisory_ready = qualified.advisory_ready and feed_ok
            # No option contract, option depth, or portfolio risk is established
            # by the underlying-only CAS evaluator. Do NOT call TradeBuilder.
            candidate_id = f"cas:{pulse.session_id}:{symbol}:1514"
            candidate_body = {
                "candidate_id": candidate_id,
                "strategy_id": strategy_id,
                "input_record_hashes": qualified.evidence["input_record_hashes"],
            }
            cand = CausalCandidate(
                candidate_id=candidate_id,
                pulse_id=pulse.pulse_id,
                strategy_id=strategy_id,
                symbol=symbol,
                instrument_token=token,
                direction=direction,
                entry_price=None,
                stop_loss=None,
                target_price=None,
                regime=regime,
                confidence=None,
                timestamp_epoch=pulse.timestamp_epoch,
                timestamp_ist=pulse.timestamp_ist,
                payload_sha256=sha256_canonical(candidate_body),
                metadata={
                    "underlying_direction": direction,
                    "buy_only_option_side": qualified.option_side,
                    "research_state": "HYPOTHESIS",
                    "execution_status": "advisory_only",
                },
                strategy_qualified=True,
                qualification_evidence=qualified.evidence,
                advisory_ready=advisory_ready,
                execution_eligible=False,
                execution_block_reason="SHADOW_ONLY_NO_EXECUTION_AUTHORITY",
                feed_age_sec=None,
                option_quote_age_sec=None,
                candidate_state="QUALIFIED_SHADOW_ADVISORY" if advisory_ready else "QUALIFIED_ADVISORY_BLOCKED",
            )
            candidates.append(cand)
            tc["qualified_candidates"] += 1
            if advisory_ready:
                tc["advisory_ready_candidates"] += 1
    return StrategyEvaluationResult(
        pulse_id=pulse.pulse_id, regime=regime, candidates=candidates,
        rejections=rejections, evaluated_symbol_count=seen,
        timestamp_epoch=pulse.timestamp_epoch, observations=observations,
        telemetry_counters=tc,
    )
