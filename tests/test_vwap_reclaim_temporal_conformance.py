from __future__ import annotations

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
