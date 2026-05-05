"""
Adapter between ProStrategyEngine and core.decision_engine.

This does not place orders. It converts pro-layer signals into the same candidate
shape expected by evaluate_candidate_decision(), then ranks the resulting
candidate decisions.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from core.decision_engine import evaluate_candidate_decision
from strategies.pro_layer.pro_strategy_engine import ProSignal, ProStrategyEngine


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _signal_edge_score(signal: ProSignal) -> float:
    score = _safe_float(signal.score, 0.0)
    confidence = _safe_float(signal.confidence, 0.0)
    return max(0.0, min(1.0, (score * 0.65) + (confidence * 0.35)))


def pro_signal_to_candidate(signal: ProSignal, market_data: dict[str, Any]) -> dict[str, Any]:
    """Convert a ProSignal into a decision-engine candidate.

    The candidate is intentionally conservative: it does not claim tradability
    unless the upstream market_data says quote/liquidity/spread are already OK.
    """
    source_flags = dict(market_data.get("source_flags") or {})
    source_flags.update(
        {
            "strategy_layer": "pro",
            "strategy_name": signal.name,
            "strategy_reason": signal.reason,
            "pro_signal": asdict(signal),
        }
    )

    edge = _signal_edge_score(signal)
    quote_ok = bool(market_data.get("quote_ok", False))
    liquidity_ok = bool(market_data.get("liquidity_ok", False))
    spread_ok = bool(market_data.get("spread_ok", False))
    execution_allowed = bool(
        market_data.get("execution_allowed", False)
        and quote_ok
        and liquidity_ok
        and spread_ok
    )

    return {
        "symbol": market_data.get("symbol"),
        "instrument_id": market_data.get("instrument_id"),
        "direction": signal.direction,
        "side": "BUY",
        "strategy": signal.name,
        "strategy_family": "pro_layer",
        "reason": signal.reason,
        "raw_edge_score": edge,
        "confidence_raw": edge,
        "confidence": edge,
        "gating_final_confidence": edge,
        "confidence_final": edge,
        "rank_score": edge,
        "regime": market_data.get("regime"),
        "quote_ok": quote_ok,
        "fresh_quote_ok": quote_ok,
        "liquidity_ok": liquidity_ok,
        "spread_ok": spread_ok,
        "data_confidence": market_data.get("data_confidence", 1.0 if quote_ok else 0.0),
        "quote_age_sec": market_data.get("quote_age_sec"),
        "spread_pct": market_data.get("spread_pct"),
        "best_bid": market_data.get("best_bid"),
        "best_ask": market_data.get("best_ask"),
        "opt_ltp": market_data.get("opt_ltp") or market_data.get("ltp"),
        "current_ltp": market_data.get("current_ltp") or market_data.get("ltp"),
        "volume": market_data.get("volume", 0),
        "current_volume": market_data.get("current_volume", market_data.get("volume", 0)),
        "execution_entry": market_data.get("execution_entry") or market_data.get("entry_price"),
        "display_entry": market_data.get("display_entry") or market_data.get("entry_price"),
        "entry_price": market_data.get("entry_price"),
        "stop_loss": market_data.get("stop_loss"),
        "target": market_data.get("target"),
        "qty": market_data.get("qty", 1),
        "qty_units": market_data.get("qty_units", market_data.get("qty", 1)),
        "tradable": bool(market_data.get("tradable", execution_allowed)),
        "execution_allowed": execution_allowed,
        "candidate_class": "real",
        "truth_quality": "REAL",
        "source_flags": source_flags,
    }


def evaluate_pro_strategy_candidates(market_data: dict[str, Any]) -> list[dict[str, Any]]:
    engine = ProStrategyEngine()
    decisions: list[dict[str, Any]] = []
    for signal in engine.run(market_data):
        candidate = pro_signal_to_candidate(signal, market_data)
        decisions.append(evaluate_candidate_decision(candidate))
    decisions.sort(
        key=lambda item: float(item.get("final_score") or item.get("final_rank_score") or 0.0),
        reverse=True,
    )
    return decisions


def best_pro_strategy_decision(market_data: dict[str, Any]) -> dict[str, Any] | None:
    decisions = evaluate_pro_strategy_candidates(market_data)
    return decisions[0] if decisions else None
