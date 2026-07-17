from __future__ import annotations

import pytest

from core.movement_regime import MovementRegimeResult
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
from tests.vwap_reclaim_test_support import bullish_history, runtime_truth_payload, vwap_reclaim_context


def _regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.6,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.1,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.0,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _causal_vwap(history: list[dict[str, object]]) -> float:
    running_tp_weight = 0.0
    running_volume = 0.0
    for bar in history:
        volume = bar.get("volume")
        if volume in (None, "", "None"):
            weight = 1.0
        else:
            weight = float(volume)
            if weight <= 0:
                weight = 1.0
        typical_price = (float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3.0
        running_tp_weight += typical_price * weight
        running_volume += weight
    return running_tp_weight / running_volume


def test_vwap_reclaim_runtime_uses_canonical_vwap_not_final_close() -> None:
    history = bullish_history()
    causal_vwap = _causal_vwap(history)
    runtime_payload = runtime_truth_payload(history=history)

    ctx = _strategy_context_from_market_symbol("NIFTY", runtime_payload)
    runtime_candidates = generate_vwap_reclaim_rejection_candidates(ctx, _regime())
    direct_candidates = generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(history=history, vwap=causal_vwap),
        _regime(),
    )

    assert ctx.vwap == pytest.approx(causal_vwap)
    assert ctx.vwap != history[-1]["close"]
    assert runtime_candidates
    assert [(
        c.strategy_id,
        round(float(c.raw_score), 6),
        c.direction,
        c.status,
        c.entry_trigger,
        c.invalid_if,
        c.rank_reason,
    ) for c in runtime_candidates] == [(
        c.strategy_id,
        round(float(c.raw_score), 6),
        c.direction,
        c.status,
        c.entry_trigger,
        c.invalid_if,
        c.rank_reason,
    ) for c in direct_candidates]
    assert direct_candidates
    candidate = direct_candidates[0]
    assert candidate.strategy_id == "vwap_reclaim_rejection_v1"
    assert candidate.direction == "BUY_CALL"
    assert round(float(candidate.raw_score), 6) == 0.392377
    assert candidate.evidence["temporal_evidence"]["vwap_provenance"] == "VWAP_AUTHORITATIVE"
