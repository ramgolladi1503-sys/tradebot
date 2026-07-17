from __future__ import annotations

import pytest

from core.movement_regime import MovementRegimeResult
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
from tests.vwap_reclaim_test_support import (
    bearish_history,
    bullish_history,
    runtime_truth_payload,
    vwap_reclaim_context,
)


def _regime(*, primary: str = "TREND_UP", **scores: float) -> MovementRegimeResult:
    base = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


def _fingerprint(candidates):
    return [
        (
            candidate.strategy_id,
            round(float(candidate.raw_score), 6),
            candidate.direction,
            candidate.status,
            candidate.entry_trigger,
            candidate.invalid_if,
            candidate.rank_reason,
        )
        for candidate in candidates
    ]


def _causal_vwap(history):
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


def test_vwap_reclaim_runtime_and_direct_fingerprints_match_for_causal_snapshot():
    direct = vwap_reclaim_context()
    runtime = _strategy_context_from_market_symbol("NIFTY", runtime_truth_payload())
    regime = _regime(TREND_UP=0.6, CHOP=0.1)

    direct_candidates = generate_vwap_reclaim_rejection_candidates(direct, regime)
    runtime_candidates = generate_vwap_reclaim_rejection_candidates(runtime, regime)

    assert _fingerprint(runtime_candidates) == _fingerprint(direct_candidates)
    assert _fingerprint(direct_candidates) == [
        (
            "vwap_reclaim_rejection_v1",
            0.392377,
            "BUY_CALL",
            "RAW_CANDIDATE",
            "confirmed_vwap_reclaim_or_rejection",
            "price_crosses_back_through_vwap",
            "confirmed VWAP reclaim/rejection in a non-chop regime",
        )
    ]
    candidate = direct_candidates[0]
    temporal = candidate.evidence["temporal_evidence"]
    assert temporal["contract_version"] == "vwap_reclaim_causal_v1"
    assert temporal["bar_interval"] == "1m"
    assert temporal["minimum_bar_count"] == 3
    assert temporal["vwap_provenance"] == "VWAP_AUTHORITATIVE"
    assert temporal["sequence_bar_timestamps"] == (
        "2026-07-14T09:16:00+05:30",
        "2026-07-14T09:17:00+05:30",
        "2026-07-14T09:18:00+05:30",
    )


@pytest.mark.parametrize("first_bar_volume", [0.0, None])
def test_vwap_reclaim_sequence_provenance_uses_any_proxy_weighted_bar(first_bar_volume):
    history = [dict(bar) for bar in bullish_history()]
    history[0]["volume"] = first_bar_volume
    causal_vwap = _causal_vwap(history)
    direct = vwap_reclaim_context(history=history, vwap=causal_vwap)
    runtime_payload = runtime_truth_payload(history=history)
    runtime_payload["vwap"] = causal_vwap
    runtime_payload["metadata"]["strategy_context_truth"]["vwap"] = causal_vwap
    runtime_payload["metadata"]["strategy_context_truth"]["completed_bar_history"] = history
    runtime_payload["metadata"]["completed_bar_history"] = history
    runtime = _strategy_context_from_market_symbol("NIFTY", runtime_payload)
    regime = _regime(TREND_UP=0.6, CHOP=0.1)

    direct_candidates = generate_vwap_reclaim_rejection_candidates(direct, regime)
    runtime_candidates = generate_vwap_reclaim_rejection_candidates(runtime, regime)

    assert _fingerprint(runtime_candidates) == _fingerprint(direct_candidates)
    assert runtime_candidates
    temporal = runtime_candidates[0].evidence["temporal_evidence"]
    assert temporal["vwap_provenance"] == "VWAP_UNIT_WEIGHT_PROXY"
    assert temporal["completed_bar_history_provenance"]["status"] == "VWAP_UNIT_WEIGHT_PROXY"
    assert temporal["completed_bar_history_provenance"]["complete"] is True


def test_vwap_reclaim_completed_history_required_blocks_closed():
    assert generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(history=[]),
        _regime(TREND_UP=0.6, CHOP=0.1),
    ) == ()


def test_vwap_reclaim_short_history_blocks_closed():
    short_history = bullish_history()[:2]
    assert generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(history=short_history),
        _regime(TREND_UP=0.6, CHOP=0.1),
    ) == ()


def test_previous_spot_only_cross_cannot_fabricate_a_reclaim():
    assert generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(
            history=[],
            metadata={"previous_spot_ltp": 22520.0, "vwap_reclaim_up_confirmed": True},
        ),
        _regime(TREND_UP=0.6, CHOP=0.1),
    ) == ()


def test_metadata_only_confirmation_does_not_overrule_contradictory_completed_history():
    candidates = generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(
            history=bearish_history(),
            bullish=False,
            metadata={"vwap_reclaim_up_confirmed": True},
        ),
        _regime(TREND_DOWN=0.6, CHOP=0.1),
    )

    assert len(candidates) == 1
    assert candidates[0].direction == "BUY_PUT"


def test_future_mutation_after_cutoff_does_not_change_candidate_identity():
    base = vwap_reclaim_context()
    with_future = vwap_reclaim_context(history=bullish_history(include_future=True))
    regime = _regime(TREND_UP=0.6, CHOP=0.1)

    base_candidates = generate_vwap_reclaim_rejection_candidates(base, regime)
    future_candidates = generate_vwap_reclaim_rejection_candidates(
        with_future,
        regime,
    )

    assert _fingerprint(base_candidates) == _fingerprint(future_candidates)


def test_physical_truncation_matches_full_dataset_before_the_cutoff():
    full_history = bullish_history(include_future=True)
    truncated_history = full_history[:3]

    full_candidates = generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(history=full_history),
        _regime(TREND_UP=0.6, CHOP=0.1),
    )
    truncated_candidates = generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(history=truncated_history),
        _regime(TREND_UP=0.6, CHOP=0.1),
    )

    assert _fingerprint(full_candidates) == _fingerprint(truncated_candidates)


def test_bearish_causal_sequence_emits_put_candidate():
    candidates = generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(bullish=False),
        _regime(TREND_DOWN=0.6, CHOP=0.1),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "vwap_reclaim_rejection_v1"
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.evidence["temporal_evidence"]["vwap_provenance"] == "VWAP_AUTHORITATIVE"
