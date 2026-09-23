"""Causal Strategy Observation Adapter (Hops 5-8).

Wraps canonical strategy registry and signal evaluation primitives into immutable
NativePulse trace envelopes without duplicating strategy logic or inventing fake setups.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.causal_pulse import NativePulse, sha256_canonical
from core.read_only_strategy_registry import CANONICAL_STRATEGIES
from core.signal_engine import evaluate as evaluate_signal


@dataclass(frozen=True)
class StrategyObservation:
    timestamp_epoch: float
    timestamp_ist: str
    pulse_id: str
    symbol: str
    strategy_id: str
    applicability_state: str  # APPLICABLE, INAPPLICABLE, DISABLED
    qualification_state: str  # QUALIFIED, NO_SIGNAL, NEAR_SIGNAL, UNKNOWN, PREREQUISITE_MISSING
    direction: str  # BUY, SELL, UNKNOWN
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
    confidence: float
    timestamp_epoch: float
    timestamp_ist: str
    payload_sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)
    strategy_qualified: bool = True
    qualification_evidence: dict[str, Any] = field(default_factory=dict)
    execution_eligible: bool = True
    execution_block_reason: str | None = None
    feed_age_sec: float | None = None
    option_quote_age_sec: float | None = None
    candidate_state: str = "QUALIFIED"
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
    telemetry_counters: dict[str, int] = field(default_factory=dict)

    @property
    def executable_candidates(self) -> list[CausalCandidate]:
        return [c for c in self.candidates if c.execution_eligible]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "regime": self.regime,
            "candidates_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "executable_candidates_count": len(self.executable_candidates),
            "executable_candidates": [c.to_dict() for c in self.executable_candidates],
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
    """Evaluate frozen canonical strategies against incoming pulse and normalized feed."""
    candidates: list[CausalCandidate] = []
    rejections: list[dict[str, Any]] = []

    symbols_evaluated = 0
    symbols_data = []
    if isinstance(feed_health_truth, Mapping):
        symbols_data = feed_health_truth.get("symbols") or (feed_health_truth.get("payload") or {}).get("symbols") or ((feed_health_truth.get("feed_health_truth") or {}).get("symbols")) or []
    if not symbols_data and isinstance(market_snapshot, Mapping):
        # Fallback to market_snapshot symbols if feed_health_truth symbols list is not populated
        snap_symbols = market_snapshot.get("symbols") if isinstance(market_snapshot.get("symbols"), Mapping) else {}
        for sym_k, sym_v in snap_symbols.items():
            if isinstance(sym_v, Mapping):
                fh = sym_v.get("feed_health") or {}
                qt = sym_v.get("quote_truth") or {}
                symbols_data.append({
                    "symbol": sym_k,
                    "feed_ok": fh.get("status") == "HEALTHY",
                    "instrument_token": int(qt.get("instrument_token") or 256265 if sym_k == "NIFTY" else 0),
                    "option_last_tick_age_sec": fh.get("underlying_quote_age_sec"),
                    "ltp": sym_v.get("ltp"),
                })
    
    # Extract canonical regime from feed health / market snapshot context
    regime = "UNKNOWN"
    if isinstance(market_snapshot, Mapping):
        regime = str(market_snapshot.get("primary_regime") or market_snapshot.get("regime") or "UNKNOWN")
    if regime == "UNKNOWN" and isinstance(feed_health_truth, Mapping):
        regime = str((feed_health_truth.get("context") or {}).get("primary_regime") or "UNKNOWN")

    # Telemetry counters tracking
    telemetry = {
        "symbols_seen": len(symbols_data),
        "symbols_evaluated": 0,
        "strategy_observations": 0,
        "near_signals": 0,
        "qualified_candidates": 0,
        "execution_eligible_candidates": 0,
        "blocked_feed_stale": 0,
        "blocked_option_quote_stale": 0,
        "blocked_spread": 0,
        "blocked_depth": 0,
        "blocked_liquidity": 0,
        "blocked_prerequisites": 0,
        "blocked_session": 0,
        "blocked_risk": 0,
        "blocked_governance": 0,
        "no_signal": 0,
        "qualification_unknown": 0,
    }

    observations: list[StrategyObservation] = []

    # Canonical Strategy Registry Reference
    registered_strategy_ids = [s["strategy_id"] for s in CANONICAL_STRATEGIES if s.get("enabled")]

    for sym_info in symbols_data:
        if not isinstance(sym_info, Mapping):
            continue
        symbol = str(sym_info.get("symbol", "")).upper()
        if not symbol:
            continue
        symbols_evaluated += 1
        telemetry["symbols_evaluated"] += 1

        feed_ok = bool(sym_info.get("feed_ok", False))
        token = int(sym_info.get("instrument_token", 0) or 0)
        age_sec = sym_info.get("option_last_tick_age_sec")
        is_completed_bar = bool(sym_info.get("is_completed_bar_signal", False) or sym_info.get("signal_mode") == "COMPLETED_BARS")
        missing_prereqs = list(sym_info.get("missing_prerequisites") or [])

        # 1. Strategy Applicability
        applicable_strategy_ids = []
        for strat in CANONICAL_STRATEGIES:
            strat_id = strat["strategy_id"]
            if not strat.get("enabled"):
                telemetry["strategy_observations"] += 1
                observations.append(StrategyObservation(
                    timestamp_epoch=pulse.timestamp_epoch,
                    timestamp_ist=pulse.timestamp_ist,
                    pulse_id=pulse.pulse_id,
                    symbol=symbol,
                    strategy_id=strat_id,
                    applicability_state="DISABLED",
                    qualification_state="NO_SIGNAL",
                    direction="UNKNOWN",
                    confidence=None,
                    required_inputs=list(strat.get("inputs", ())),
                    missing_or_stale_inputs=[],
                    reason_code="STRATEGY_DISABLED",
                    source_event_or_snapshot_reference={"symbol": symbol},
                ))
                continue

            req_underlyings = strat.get("required_underlyings", ())
            # Non-equity / out-of-universe commodities are strictly INAPPLICABLE for canonical equity/index advisory
            is_commodity = any(symbol.startswith(prefix) for prefix in ("CRUDE", "GOLD", "SILVER", "NATURAL", "COPPER", "MCX"))
            if is_commodity or (req_underlyings and not any(symbol == u or symbol.startswith(u) for u in req_underlyings) and not any(symbol.startswith(p) for p in ("NIFTY", "BANKNIFTY", "FINNIFTY", "RELIANCE", "TCS", "INFY"))):
                telemetry["strategy_observations"] += 1
                observations.append(StrategyObservation(
                    timestamp_epoch=pulse.timestamp_epoch,
                    timestamp_ist=pulse.timestamp_ist,
                    pulse_id=pulse.pulse_id,
                    symbol=symbol,
                    strategy_id=strat_id,
                    applicability_state="INAPPLICABLE",
                    qualification_state="NO_SIGNAL",
                    direction="UNKNOWN",
                    confidence=None,
                    required_inputs=list(strat.get("inputs", ())),
                    missing_or_stale_inputs=[],
                    reason_code="STRATEGY_INAPPLICABLE",
                    source_event_or_snapshot_reference={"symbol": symbol},
                ))
            else:
                applicable_strategy_ids.append(strat_id)

        # If no strategies are applicable for this symbol, continue
        if not applicable_strategy_ids:
            continue

        # Missing Prerequisites Gate
        if missing_prereqs:
            telemetry["blocked_prerequisites"] += 1
            for strat_id in applicable_strategy_ids:
                telemetry["strategy_observations"] += 1
                observations.append(StrategyObservation(
                    timestamp_epoch=pulse.timestamp_epoch,
                    timestamp_ist=pulse.timestamp_ist,
                    pulse_id=pulse.pulse_id,
                    symbol=symbol,
                    strategy_id=strat_id,
                    applicability_state="APPLICABLE",
                    qualification_state="PREREQUISITE_MISSING",
                    direction="UNKNOWN",
                    confidence=None,
                    required_inputs=list(missing_prereqs),
                    missing_or_stale_inputs=list(missing_prereqs),
                    reason_code="PREREQUISITE_MISSING",
                    source_event_or_snapshot_reference={"symbol": symbol, "missing": missing_prereqs},
                ))
                rejections.append({
                    "symbol": symbol,
                    "strategy_id": strat_id,
                    "reason_code": "PREREQUISITE_MISSING",
                    "detail": f"missing={missing_prereqs}",
                })
            continue

        # Evaluate Signal (Hops 7 & 8)
        signal_res = evaluate_signal(snapshot=sym_info, signal_payload=sym_info)
        conf = signal_res.confidence
        direction = signal_res.direction

        feed_stale = (not feed_ok) or (age_sec is not None and float(age_sec) > 2.5)
        stale_inputs = ["feed_quote"] if feed_stale else []

        # Check Near Signal (e.g. 0.50 <= conf < 0.70)
        if conf is not None and 0.50 <= conf < 0.70 and direction in ("BUY", "SELL"):
            telemetry["near_signals"] += 1
            for strat_id in applicable_strategy_ids:
                telemetry["strategy_observations"] += 1
                observations.append(StrategyObservation(
                    timestamp_epoch=pulse.timestamp_epoch,
                    timestamp_ist=pulse.timestamp_ist,
                    pulse_id=pulse.pulse_id,
                    symbol=symbol,
                    strategy_id=strat_id,
                    applicability_state="APPLICABLE",
                    qualification_state="NEAR_SIGNAL",
                    direction=direction,
                    confidence=conf,
                    required_inputs=["feed_quote"],
                    missing_or_stale_inputs=stale_inputs,
                    reason_code="NO_QUALIFIED_SIGNAL",
                    source_event_or_snapshot_reference={"confidence": conf, "direction": direction},
                ))
                rejections.append({
                    "symbol": symbol,
                    "strategy_id": strat_id,
                    "reason_code": "NO_QUALIFIED_SIGNAL",
                    "detail": f"confidence={conf} direction={direction}",
                })
            continue

        # Case: Signal naturally qualifies
        if conf is not None and conf >= 0.70 and direction in ("BUY", "SELL"):
            if feed_stale:
                if is_completed_bar:
                    # Example A: Completed bar signal is causally qualified even if current execution quote is stale!
                    telemetry["qualified_candidates"] += 1
                    telemetry["blocked_feed_stale"] += 1
                    for strat_id in applicable_strategy_ids:
                        telemetry["strategy_observations"] += 1
                        observations.append(StrategyObservation(
                            timestamp_epoch=pulse.timestamp_epoch,
                            timestamp_ist=pulse.timestamp_ist,
                            pulse_id=pulse.pulse_id,
                            symbol=symbol,
                            strategy_id=strat_id,
                            applicability_state="APPLICABLE",
                            qualification_state="QUALIFIED",
                            direction=direction,
                            confidence=conf,
                            required_inputs=["completed_bars"],
                            missing_or_stale_inputs=stale_inputs,
                            reason_code="FEED_STALE_EXECUTION_BLOCK",
                            source_event_or_snapshot_reference={"features": signal_res.features},
                        ))

                    from strategies.trade_builder import TradeBuilder
                    builder = TradeBuilder()
                    builder_input = {
                        "symbol": symbol,
                        "ltp": sym_info.get("ltp") or 100.0,
                        "regime": regime,
                        "option_chain": sym_info.get("option_chain") or [],
                    }
                    built_trade = builder.build(builder_input) if hasattr(builder, "build") else None

                    cand_body = {
                        "pulse_id": pulse.pulse_id,
                        "symbol": symbol,
                        "direction": direction,
                        "confidence": conf,
                    }
                    cand_hash = sha256_canonical(cand_body)
                    cand = CausalCandidate(
                        candidate_id=f"cand_{pulse.sequence_num}_{token}",
                        pulse_id=pulse.pulse_id,
                        strategy_id=str(getattr(built_trade, "strategy", None) or applicable_strategy_ids[0] if applicable_strategy_ids else "CANONICAL_ADVISORY"),
                        symbol=symbol,
                        instrument_token=token,
                        direction=direction,
                        entry_price=float(getattr(built_trade, "entry_price", sym_info.get("ltp") or 0.0)),
                        stop_loss=float(getattr(built_trade, "stop_loss", sym_info.get("stop_loss") or 0.0)),
                        target_price=float(getattr(built_trade, "target", sym_info.get("target_price") or 0.0)),
                        regime=regime,
                        confidence=float(conf),
                        timestamp_epoch=pulse.timestamp_epoch,
                        timestamp_ist=pulse.timestamp_ist,
                        payload_sha256=cand_hash,
                        metadata={"features": signal_res.features, "trade_object": getattr(built_trade, "trade_id", None)},
                        strategy_qualified=True,
                        qualification_evidence={"is_completed_bar_signal": True, "confidence": conf},
                        execution_eligible=False,
                        execution_block_reason="FEED_STALE_EXECUTION_BLOCK",
                        feed_age_sec=float(age_sec) if age_sec is not None else None,
                        candidate_state="QUALIFIED_EXECUTION_BLOCKED",
                    )
                    candidates.append(cand)
                else:
                    # Example B: Signal itself requires live quote/tick. Stale quote -> qualification unknown!
                    telemetry["qualification_unknown"] += 1
                    telemetry["blocked_feed_stale"] += 1
                    for strat_id in applicable_strategy_ids:
                        telemetry["strategy_observations"] += 1
                        observations.append(StrategyObservation(
                            timestamp_epoch=pulse.timestamp_epoch,
                            timestamp_ist=pulse.timestamp_ist,
                            pulse_id=pulse.pulse_id,
                            symbol=symbol,
                            strategy_id=strat_id,
                            applicability_state="APPLICABLE",
                            qualification_state="UNKNOWN",
                            direction=direction,
                            confidence=conf,
                            required_inputs=["feed_quote"],
                            missing_or_stale_inputs=stale_inputs,
                            reason_code="REQUIRED_LIVE_INPUT_STALE",
                            source_event_or_snapshot_reference={"symbol": symbol, "age_sec": age_sec},
                        ))
                        rejections.append({
                            "symbol": symbol,
                            "strategy_id": strat_id,
                            "reason_code": "REJECT_FEED_DEGRADED_OR_STALE",
                            "detail": f"age_sec={age_sec} feed_ok={feed_ok}",
                        })
            else:
                # Fresh feed + Qualified signal
                telemetry["qualified_candidates"] += 1
                telemetry["execution_eligible_candidates"] += 1
                for strat_id in applicable_strategy_ids:
                    telemetry["strategy_observations"] += 1
                    observations.append(StrategyObservation(
                        timestamp_epoch=pulse.timestamp_epoch,
                        timestamp_ist=pulse.timestamp_ist,
                        pulse_id=pulse.pulse_id,
                        symbol=symbol,
                        strategy_id=strat_id,
                        applicability_state="APPLICABLE",
                        qualification_state="QUALIFIED",
                        direction=direction,
                        confidence=conf,
                        required_inputs=["feed_quote"],
                        missing_or_stale_inputs=[],
                        reason_code="EXECUTION_ELIGIBLE",
                        source_event_or_snapshot_reference={"features": signal_res.features},
                    ))

                from strategies.trade_builder import TradeBuilder
                builder = TradeBuilder()
                builder_input = {
                    "symbol": symbol,
                    "ltp": sym_info.get("ltp") or 100.0,
                    "regime": regime,
                    "option_chain": sym_info.get("option_chain") or [],
                }
                built_trade = builder.build(builder_input) if hasattr(builder, "build") else None

                cand_body = {
                    "pulse_id": pulse.pulse_id,
                    "symbol": symbol,
                    "direction": direction,
                    "confidence": conf,
                }
                cand_hash = sha256_canonical(cand_body)
                cand = CausalCandidate(
                    candidate_id=f"cand_{pulse.sequence_num}_{token}",
                    pulse_id=pulse.pulse_id,
                    strategy_id=str(getattr(built_trade, "strategy", None) or applicable_strategy_ids[0] if applicable_strategy_ids else "CANONICAL_ADVISORY"),
                    symbol=symbol,
                    instrument_token=token,
                    direction=direction,
                    entry_price=float(getattr(built_trade, "entry_price", sym_info.get("ltp") or 0.0)),
                    stop_loss=float(getattr(built_trade, "stop_loss", sym_info.get("stop_loss") or 0.0)),
                    target_price=float(getattr(built_trade, "target", sym_info.get("target_price") or 0.0)),
                    regime=regime,
                    confidence=float(conf),
                    timestamp_epoch=pulse.timestamp_epoch,
                    timestamp_ist=pulse.timestamp_ist,
                    payload_sha256=cand_hash,
                    metadata={"features": signal_res.features, "trade_object": getattr(built_trade, "trade_id", None)},
                    strategy_qualified=True,
                    qualification_evidence={"confidence": conf},
                    execution_eligible=True,
                    execution_block_reason=None,
                    feed_age_sec=float(age_sec) if age_sec is not None else None,
                    candidate_state="QUALIFIED",
                )
                candidates.append(cand)
        else:
            # No qualified signal
            telemetry["no_signal"] += 1
            if feed_stale and not is_completed_bar and (conf is None or conf == 0):
                for strat_id in applicable_strategy_ids:
                    telemetry["strategy_observations"] += 1
                    observations.append(StrategyObservation(
                        timestamp_epoch=pulse.timestamp_epoch,
                        timestamp_ist=pulse.timestamp_ist,
                        pulse_id=pulse.pulse_id,
                        symbol=symbol,
                        strategy_id=strat_id,
                        applicability_state="APPLICABLE",
                        qualification_state="UNKNOWN",
                        direction=direction,
                        confidence=conf,
                        required_inputs=["feed_quote"],
                        missing_or_stale_inputs=stale_inputs,
                        reason_code="REQUIRED_LIVE_INPUT_STALE",
                        source_event_or_snapshot_reference={"symbol": symbol, "age_sec": age_sec},
                    ))
                    rejections.append({
                        "symbol": symbol,
                        "strategy_id": strat_id,
                        "reason_code": "REJECT_FEED_DEGRADED_OR_STALE",
                        "detail": f"age_sec={age_sec} feed_ok={feed_ok}",
                    })
            else:
                for strat_id in applicable_strategy_ids:
                    telemetry["strategy_observations"] += 1
                    observations.append(StrategyObservation(
                        timestamp_epoch=pulse.timestamp_epoch,
                        timestamp_ist=pulse.timestamp_ist,
                        pulse_id=pulse.pulse_id,
                        symbol=symbol,
                        strategy_id=strat_id,
                        applicability_state="APPLICABLE",
                        qualification_state="NO_SIGNAL",
                        direction=direction,
                        confidence=conf,
                        required_inputs=["feed_quote"],
                        missing_or_stale_inputs=stale_inputs,
                        reason_code="NO_QUALIFIED_SIGNAL",
                        source_event_or_snapshot_reference={"confidence": conf, "direction": direction},
                    ))
                    rejections.append({
                        "symbol": symbol,
                        "strategy_id": strat_id,
                        "reason_code": "NO_QUALIFIED_SIGNAL",
                        "detail": f"confidence={conf} direction={direction}",
                    })

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
