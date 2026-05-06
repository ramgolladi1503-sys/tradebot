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


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


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


def _quality_penalty(market_data: dict[str, Any]) -> float:
    quote_age = _safe_float(market_data.get("quote_age_sec"), 0.0)
    spread_pct = _safe_float(market_data.get("spread_pct"), 0.0)
    data_confidence = _safe_float(market_data.get("data_confidence"), 1.0)
    quote_ok = bool(market_data.get("quote_ok", False))
    liquidity_ok = bool(market_data.get("liquidity_ok", False))
    spread_ok = bool(market_data.get("spread_ok", False))

    freshness = max(0.0, 1.0 - min(quote_age / 8.0, 1.0))
    spread_quality = max(0.0, 1.0 - min(spread_pct / 0.02, 1.0))
    coarse_quality = 1.0 if (quote_ok and liquidity_ok and spread_ok) else 0.45
    return max(
        0.0,
        min(
            1.0,
            (freshness * 0.38) + (spread_quality * 0.30) + (data_confidence * 0.24) + (coarse_quality * 0.08),
        ),
    )


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
    quality = _quality_penalty(market_data)
    rank = max(0.0, min(1.0, (edge * 0.76) + (quality * 0.24)))
    quote_ok = _safe_bool(market_data.get("quote_ok"), default=False)
    liquidity_ok = _safe_bool(market_data.get("liquidity_ok"), default=False)
    spread_ok = _safe_bool(market_data.get("spread_ok"), default=False)
    execution_input_ok = bool(
        _safe_bool(market_data.get("execution_allowed"), default=False)
        and quote_ok
        and liquidity_ok
        and spread_ok
    )
    strategy_family = str(getattr(signal, "family", None) or "pro_layer").strip().lower() or "pro_layer"
    regime_tags = list(getattr(signal, "regime_tags", []) or [])
    strategy_regime_mode = str(
        regime_tags[0] if regime_tags else (market_data.get("regime") or "UNKNOWN")
    ).strip().upper() or "UNKNOWN"
    tradable = bool(execution_input_ok and edge >= 0.60 and quality >= 0.65)
    return {
        "symbol": market_data.get("symbol"),
        "instrument_id": market_data.get("instrument_id"),
        "direction": signal.direction,
        "side": "BUY",
        "strategy": signal.name,
        "strategy_family": strategy_family,
        "setup_variant": str(signal.name or "").strip().lower() or strategy_family,
        "candidate_type": strategy_family,
        "strategy_regime_mode": strategy_regime_mode,
        "reason": signal.reason,
        "raw_edge_score": edge,
        "confidence_raw": edge,
        "confidence": edge,
        "gating_final_confidence": rank,
        "confidence_final": rank,
        "rank_score": rank,
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
        "tradable": bool(tradable and _safe_bool(market_data.get("tradable"), default=True)),
        "execution_allowed": tradable,
        "candidate_class": "real",
        "truth_quality": "REAL",
        "source_flags": {
            **source_flags,
            "strategy_family": strategy_family,
            "strategy_regime_mode": strategy_regime_mode,
            "pro_rank_quality": round(quality, 4),
            "pro_rank_edge": round(edge, 4),
        },
    }


def evaluate_pro_strategy_candidates(
    market_data: dict[str, Any],
    *,
    error_sink: list[str] | None = None,
) -> list[dict[str, Any]]:
    engine = ProStrategyEngine()
    decisions: list[dict[str, Any]] = []
    for signal in engine.run(market_data, error_sink=error_sink):
        candidate = pro_signal_to_candidate(signal, market_data)
        decisions.append(evaluate_candidate_decision(candidate))
    decisions.sort(
        key=lambda item: float(item.get("final_score") or item.get("final_rank_score") or 0.0),
        reverse=True,
    )
    return decisions


def best_pro_strategy_decision(
    market_data: dict[str, Any],
    *,
    error_sink: list[str] | None = None,
) -> dict[str, Any] | None:
    decisions = evaluate_pro_strategy_candidates(market_data, error_sink=error_sink)
    return decisions[0] if decisions else None
