"""Pro Strategy meta-engine.

The meta layer is aggregation-only. It does not implement independent alpha
families. Every child signal must arrive with family identity, immutable source
hash, structural validation, freshness validation, and contract validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List


@dataclass(frozen=True)
class ProSignal:
    name: str
    direction: str
    score: float
    confidence: float
    reason: str
    family: str = "unknown"
    regime_tags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def _coerce_signal(raw: Any) -> ProSignal | None:
    if isinstance(raw, ProSignal):
        sig = raw
    elif isinstance(raw, dict):
        try:
            sig = ProSignal(
                name=str(raw.get("name") or raw.get("strategy_id") or ""),
                direction=str(raw.get("direction") or ""),
                score=float(raw.get("score")),
                confidence=float(raw.get("confidence")),
                reason=str(raw.get("reason") or ""),
                family=str(raw.get("family") or "unknown"),
                regime_tags=list(raw.get("regime_tags") or []),
                evidence=dict(raw.get("evidence") or {}),
            )
        except Exception:
            return None
    else:
        return None
    if not sig.name or sig.direction not in {"BUY_CALL", "BUY_PUT"}:
        return None
    if not (0.0 <= sig.score <= 1.0 and 0.0 <= sig.confidence <= 1.0):
        return None
    evidence = sig.evidence
    if evidence.get("structural_status") != "STRUCTURALLY_VALID":
        return None
    if evidence.get("contract_valid") is not True or evidence.get("freshness_valid") is not True:
        return None
    if not str(evidence.get("source_sha256") or "").strip():
        return None
    if not str(sig.family or "").strip() or sig.family == "unknown":
        return None
    return sig


class ProSignalAggregator:
    """Aggregate orthogonal, already-proven child-family signals fail closed."""

    def aggregate(self, signals: Iterable[ProSignal]) -> list[ProSignal]:
        signals = [sig for sig in signals if _coerce_signal(sig) is not None]
        if not signals:
            return []
        # Require family diversity for a meta-layer claim. One child is not an ensemble.
        if len({sig.family for sig in signals}) < 2:
            return []

        call_strength = sum(sig.score * sig.confidence for sig in signals if sig.direction == "BUY_CALL")
        put_strength = sum(sig.score * sig.confidence for sig in signals if sig.direction == "BUY_PUT")
        if call_strength and put_strength:
            stronger = max(call_strength, put_strength)
            weaker = min(call_strength, put_strength)
            if weaker / max(stronger, 1e-12) >= 0.45:
                return []
        direction = "BUY_CALL" if call_strength > put_strength else "BUY_PUT"
        aligned = [sig for sig in signals if sig.direction == direction]
        if len({sig.family for sig in aligned}) < 2:
            return []

        ranked = sorted(aligned, key=lambda s: (s.score * s.confidence, s.score, s.confidence, s.name), reverse=True)
        top = ranked[0]
        if top.score < 0.64 or top.confidence < 0.60:
            return []
        family_truth = tuple(sorted({sig.family for sig in aligned}))
        source_hashes = tuple(sorted({str(sig.evidence["source_sha256"]) for sig in aligned}))
        combined_strength = sum(sig.score * sig.confidence for sig in aligned) / len(aligned)
        return [
            ProSignal(
                name="pro_strategy_consensus",
                direction=direction,
                score=round(min(1.0, combined_strength), 4),
                confidence=round(min(1.0, sum(sig.confidence for sig in aligned) / len(aligned)), 4),
                reason="orthogonal_structurally_valid_family_consensus",
                family="pro_meta",
                regime_tags=sorted({tag for sig in aligned for tag in sig.regime_tags}),
                evidence={
                    "structural_status": "STRUCTURALLY_VALID",
                    "contract_valid": True,
                    "freshness_valid": True,
                    "source_sha256": "|".join(source_hashes),
                    "signal_quality": True,
                    "candidate_truth": True,
                    "family_truth": family_truth,
                    "child_names": tuple(sig.name for sig in aligned),
                },
            )
        ]


class ProStrategyEngine:
    """Consume externally produced pro child signals; never synthesize alpha."""

    def __init__(self):
        self.aggregator = ProSignalAggregator()
        self.last_errors: list[str] = []

    def run(self, market_data: dict, *, error_sink: list[str] | None = None) -> List[ProSignal]:
        self.last_errors = []
        if not isinstance(market_data, dict):
            return []
        raw = market_data.get("pro_child_signals")
        if not isinstance(raw, (list, tuple)):
            return []
        children: list[ProSignal] = []
        for index, item in enumerate(raw):
            sig = _coerce_signal(item)
            if sig is None:
                err = f"invalid_pro_child_signal:{index}"
                self.last_errors.append(err)
                if error_sink is not None:
                    error_sink.append(err)
                return []  # fail the complete meta decision closed
            children.append(sig)
        return self.aggregator.aggregate(children)


__all__ = ["ProSignal", "ProSignalAggregator", "ProStrategyEngine"]
