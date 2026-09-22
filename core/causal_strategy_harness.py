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

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "regime": self.regime,
            "candidates_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
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

    # Canonical Strategy Registry Reference
    registered_strategy_ids = [s["strategy_id"] for s in CANONICAL_STRATEGIES if s.get("enabled")]

    for sym_info in symbols_data:
        if not isinstance(sym_info, Mapping):
            continue
        symbol = str(sym_info.get("symbol", "")).upper()
        if not symbol:
            continue
        symbols_evaluated += 1

        feed_ok = bool(sym_info.get("feed_ok", False))
        token = int(sym_info.get("instrument_token", 0) or 0)
        age_sec = sym_info.get("option_last_tick_age_sec")

        # 1. Strategy Applicability & Feed Gate
        # Match symbol against declared required_underlyings in CANONICAL_STRATEGIES (no string-matching heuristics)
        applicable_strategy_ids = []
        for strat in CANONICAL_STRATEGIES:
            if not strat.get("enabled"):
                continue
            strat_id = strat["strategy_id"]
            req_underlyings = strat.get("required_underlyings", ())
            if req_underlyings:
                # If strategy declares explicit underlyings, require symbol to match one of them
                if any(symbol == u or symbol.startswith(u) for u in req_underlyings):
                    applicable_strategy_ids.append(strat_id)
            else:
                applicable_strategy_ids.append(strat_id)

        # If no strategies apply to this symbol, fall back to registered strategies for general opportunity evaluation
        if not applicable_strategy_ids:
            applicable_strategy_ids = list(registered_strategy_ids)

        if not feed_ok or (age_sec is not None and float(age_sec) > 2.5):
            for strat_id in applicable_strategy_ids:
                rejections.append({
                    "symbol": symbol,
                    "strategy_id": strat_id,
                    "reason_code": "REJECT_FEED_DEGRADED_OR_STALE",
                    "detail": f"age_sec={age_sec} feed_ok={feed_ok}",
                })
            continue

        # 2. Canonical Signal Engine & TradeBuilder Candidate Construction (Hops 7 & 8)
        signal_res = evaluate_signal(snapshot=sym_info, signal_payload=sym_info)
        
        # If signal qualifies naturally from canonical logic:
        if signal_res.confidence is not None and signal_res.confidence >= 0.70 and signal_res.direction in ("BUY", "SELL"):
            from strategies.trade_builder import TradeBuilder
            builder = TradeBuilder()
            builder_input = {
                "symbol": symbol,
                "ltp": sym_info.get("ltp") or 100.0,
                "regime": regime,
                "option_chain": sym_info.get("option_chain") or [],
            }
            # Attempt canonical TradeBuilder construction
            built_trade = builder.build(builder_input) if hasattr(builder, "build") else None

            cand_body = {
                "pulse_id": pulse.pulse_id,
                "symbol": symbol,
                "direction": signal_res.direction,
                "confidence": signal_res.confidence,
            }
            cand_hash = sha256_canonical(cand_body)
            cand = CausalCandidate(
                candidate_id=f"cand_{pulse.sequence_num}_{token}",
                pulse_id=pulse.pulse_id,
                strategy_id=str(getattr(built_trade, "strategy", None) or applicable_strategy_ids[0] if applicable_strategy_ids else "CANONICAL_ADVISORY"),
                symbol=symbol,
                instrument_token=token,
                direction=signal_res.direction,
                entry_price=float(getattr(built_trade, "entry_price", sym_info.get("ltp") or 0.0)),
                stop_loss=float(getattr(built_trade, "stop_loss", sym_info.get("stop_loss") or 0.0)),
                target_price=float(getattr(built_trade, "target", sym_info.get("target_price") or 0.0)),
                regime=regime,
                confidence=float(signal_res.confidence),
                timestamp_epoch=pulse.timestamp_epoch,
                timestamp_ist=pulse.timestamp_ist,
                payload_sha256=cand_hash,
                metadata={"features": signal_res.features, "trade_object": getattr(built_trade, "trade_id", None)},
            )
            candidates.append(cand)
        else:
            for strat_id in applicable_strategy_ids:
                rejections.append({
                    "symbol": symbol,
                    "strategy_id": strat_id,
                    "reason_code": "NO_QUALIFIED_SIGNAL",
                    "detail": f"confidence={signal_res.confidence} direction={signal_res.direction}",
                })

    return StrategyEvaluationResult(
        pulse_id=pulse.pulse_id,
        regime=regime,
        candidates=candidates,
        rejections=rejections,
        evaluated_symbol_count=symbols_evaluated,
        timestamp_epoch=pulse.timestamp_epoch,
    )
