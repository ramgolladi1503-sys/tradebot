"""Structural ensemble aggregator.

This module does not implement trend, ORB, mean-reversion, event, or micro-pattern
alpha logic. It aggregates only child-strategy signals that were produced by the
canonical strategy implementations and carry immutable structural provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategySignal:
    direction: str
    score: float
    reason: str
    confidence: float = 1.0
    source_strategy_id: str = ""
    source_sha256: str = ""
    structural_status: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


def _coerce_child(raw: Any) -> StrategySignal | None:
    if isinstance(raw, StrategySignal):
        sig = raw
    elif isinstance(raw, dict):
        try:
            sig = StrategySignal(
                direction=str(raw.get("direction") or ""),
                score=float(raw.get("score")),
                reason=str(raw.get("reason") or ""),
                confidence=float(raw.get("confidence", 1.0)),
                source_strategy_id=str(raw.get("source_strategy_id") or raw.get("strategy_id") or ""),
                source_sha256=str(raw.get("source_sha256") or ""),
                structural_status=str(raw.get("structural_status") or ""),
                evidence=dict(raw.get("evidence") or {}),
            )
        except Exception:
            return None
    else:
        return None
    if sig.direction not in {"BUY_CALL", "BUY_PUT"}:
        return None
    if not (0.0 <= float(sig.score) <= 1.0 and 0.0 <= float(sig.confidence) <= 1.0):
        return None
    if not sig.source_strategy_id or not sig.source_sha256:
        return None
    if sig.structural_status != "STRUCTURALLY_VALID":
        return None
    if sig.evidence.get("freshness_valid") is not True:
        return None
    if sig.evidence.get("contract_valid") is not True:
        return None
    return sig


def ensemble_signal(market_data: dict) -> StrategySignal | None:
    """Aggregate structurally valid child signals; never synthesize alpha itself."""
    if not isinstance(market_data, dict):
        return None
    raw_children = market_data.get("child_signals")
    if not isinstance(raw_children, (list, tuple)) or not raw_children:
        return None
    children = [sig for raw in raw_children if (sig := _coerce_child(raw)) is not None]
    if not children:
        return None

    call_strength = sum(sig.score * sig.confidence for sig in children if sig.direction == "BUY_CALL")
    put_strength = sum(sig.score * sig.confidence for sig in children if sig.direction == "BUY_PUT")
    if call_strength and put_strength:
        weaker = min(call_strength, put_strength)
        stronger = max(call_strength, put_strength)
        if weaker / max(stronger, 1e-12) >= 0.50:
            return None
    direction = "BUY_CALL" if call_strength > put_strength else "BUY_PUT"
    selected = [sig for sig in children if sig.direction == direction]
    if not selected:
        return None
    total_weight = sum(max(sig.confidence, 1e-9) for sig in selected)
    score = sum(sig.score * max(sig.confidence, 1e-9) for sig in selected) / total_weight
    confidence = min(1.0, sum(sig.confidence for sig in selected) / len(selected))
    sources = tuple(sorted({sig.source_strategy_id for sig in selected}))
    hashes = tuple(sorted({sig.source_sha256 for sig in selected}))
    return StrategySignal(
        direction=direction,
        score=round(score, 4),
        confidence=round(confidence, 4),
        reason="structurally_valid_child_consensus:" + ",".join(sources),
        source_strategy_id="ensemble",
        source_sha256="|".join(hashes),
        structural_status="STRUCTURALLY_VALID",
        evidence={
            "contract_valid": True,
            "freshness_valid": True,
            "child_strategy_ids": sources,
            "child_source_sha256": hashes,
            "child_count": len(selected),
        },
    )


def equity_signal(market_data: dict) -> StrategySignal | None:
    """Compatibility alias: equities use the same proven-child aggregation contract."""
    return ensemble_signal(market_data)


def futures_signal(market_data: dict) -> StrategySignal | None:
    """Compatibility alias: futures use the same proven-child aggregation contract."""
    return ensemble_signal(market_data)


def mean_reversion_signal(market_data: dict) -> StrategySignal | None:
    """Compatibility alias; does not implement or certify mean-reversion alpha."""
    return ensemble_signal(market_data)


def event_breakout_signal(market_data: dict) -> StrategySignal | None:
    """Compatibility alias; does not implement or certify event-breakout alpha."""
    return ensemble_signal(market_data)


def micro_pattern_signal(market_data: dict) -> StrategySignal | None:
    """Compatibility alias; does not implement or certify micro-pattern alpha."""
    return ensemble_signal(market_data)


__all__ = [
    "StrategySignal",
    "ensemble_signal",
    "equity_signal",
    "futures_signal",
    "mean_reversion_signal",
    "event_breakout_signal",
    "micro_pattern_signal",
]
