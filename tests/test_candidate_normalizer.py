from core.candidate_normalizer import normalize_candidates
from core.movement_contract import StrategyCandidate


def _candidate(
    strategy_id="s1",
    *,
    symbol="NIFTY",
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    status="VALIDATED_CANDIDATE",
    raw_score=0.6,
    confidence_score=0.6,
    option_confirmation_score=0.6,
    price_structure_score=0.6,
    liquidity_score=0.7,
    freshness_score=0.8,
    blockers=(),
    warnings=(),
    source_signals=(),
    evidence=None,
    lineage=None,
):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol=symbol,
        direction=direction,
        status=status,
        raw_score=raw_score,
        confidence_score=confidence_score,
        price_structure_score=price_structure_score,
        option_confirmation_score=option_confirmation_score,
        liquidity_score=liquidity_score,
        freshness_score=freshness_score,
        volatility_score=0.5,
        regime_alignment_score=0.6,
        timing_score=0.5,
        trap_risk_score=0.1,
        confluence_score=0.4,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
        warnings=warnings,
        source_signals=source_signals,
        evidence=evidence or {},
        lineage=lineage or {},
    )


def test_normalize_candidates_is_read_only_and_not_order_action():
    result = normalize_candidates([_candidate()])

    assert result.read_only is True
    assert result.is_order_action is False
    assert result.append is False
    assert result.raw_count == 1
    assert result.normalized_count == 1
    assert result.duplicate_group_count == 0
    assert result.metadata["scope"] == "read_only_no_execution_no_ranking"


def test_normalize_candidates_deduplicates_same_symbol_direction_and_movement_type():
    weak = _candidate("weak", confidence_score=0.4, raw_score=0.4, warnings=("weak_signal",))
    strong = _candidate("strong", confidence_score=0.9, raw_score=0.8, source_signals=("breakout",))

    result = normalize_candidates([weak, strong])

    assert result.raw_count == 2
    assert result.normalized_count == 1
    assert result.duplicate_group_count == 1
    assert result.duplicate_candidate_count == 1
    canonical = result.candidates[0]
    assert canonical.strategy_id == "strong"
    assert canonical.status == "VALIDATED_CANDIDATE"
    assert canonical.executable_eligible is True
    assert "weak_signal" in canonical.warnings
    assert "breakout" in canonical.source_signals
    assert set(canonical.source_signals) >= {"weak", "strong"}
    assert result.duplicate_groups[0].canonical_strategy_id == "strong"


def test_normalize_candidates_preserves_blockers_and_downgrades_canonical_status():
    strong = _candidate("strong", confidence_score=0.9, raw_score=0.9)
    blocked_duplicate = _candidate(
        "blocked",
        status="BLOCKED_CANDIDATE",
        blockers=("FALLBACK_QUOTE_ONLY", "STALE_OPTION_LTP"),
        warnings=("fallback_used",),
        confidence_score=0.3,
        raw_score=0.3,
    )

    result = normalize_candidates([strong, blocked_duplicate])

    candidate = result.candidates[0]
    assert candidate.strategy_id == "strong"
    assert candidate.status == "BLOCKED_CANDIDATE"
    assert candidate.executable_eligible is False
    assert set(candidate.blockers) >= {"FALLBACK_QUOTE_ONLY", "STALE_OPTION_LTP"}
    assert "fallback_used" in candidate.warnings
    assert result.merged_blocker_count == 2
    assert any(w.startswith("canonical_status_downgraded:strong") for w in result.warnings)
    assert result.duplicate_groups[0].canonical_status_before_merge == "VALIDATED_CANDIDATE"
    assert result.duplicate_groups[0].canonical_status_after_merge == "BLOCKED_CANDIDATE"


def test_normalize_candidates_keeps_different_directions_and_movements_separate():
    call = _candidate("call", direction="BUY_CALL", movement_type="COMPRESSION_BREAKOUT")
    put = _candidate("put", direction="BUY_PUT", movement_type="COMPRESSION_BREAKOUT")
    trend = _candidate("trend", direction="BUY_CALL", movement_type="TREND_PULLBACK")

    result = normalize_candidates([call, put, trend])

    assert result.raw_count == 3
    assert result.normalized_count == 3
    assert result.duplicate_group_count == 0
    keys = {(candidate.direction, candidate.movement_type) for candidate in result.candidates}
    assert keys == {
        ("BUY_CALL", "COMPRESSION_BREAKOUT"),
        ("BUY_PUT", "COMPRESSION_BREAKOUT"),
        ("BUY_CALL", "TREND_PULLBACK"),
    }


def test_normalize_candidates_preserves_range_like_setup_metadata():
    range_candidate = _candidate(
        "range",
        direction="BUY_CALL",
        movement_type="MEAN_REVERSION_EXTENSION",
        source_signals=("mean_reversion", "range_context"),
    )

    result = normalize_candidates([range_candidate])

    candidate = result.candidates[0]
    assert candidate.direction == "BUY_CALL"
    assert candidate.movement_type == "MEAN_REVERSION_EXTENSION"
    assert "mean_reversion" in candidate.source_signals
    assert "range_context" in candidate.source_signals


def test_normalize_candidates_can_include_strategy_id_in_key():
    first = _candidate("same_setup_a")
    second = _candidate("same_setup_b")

    result = normalize_candidates([first, second], include_strategy_id_in_key=True)

    assert result.raw_count == 2
    assert result.normalized_count == 2
    assert result.duplicate_group_count == 0
    assert result.metadata["key_fields"] == ["symbol", "direction", "movement_type", "strategy_id"]


def test_normalize_candidates_merges_evidence_and_lineage_for_audit():
    first = _candidate("a", evidence={"reason": "first"}, lineage={"module": "alpha"})
    second = _candidate("b", evidence={"reason": "second"}, lineage={"module": "beta"}, confidence_score=0.9)

    result = normalize_candidates([first, second])

    candidate = result.candidates[0]
    assert candidate.strategy_id == "b"
    assert candidate.evidence["normalization"]["canonical_strategy_id"] == "b"
    assert candidate.evidence["normalization"]["merged_count"] == 2
    assert set(candidate.evidence["normalization"]["merged_strategy_ids"]) == {"a", "b"}
    assert candidate.lineage["normalization"]["source_statuses"] == {
        "a": "VALIDATED_CANDIDATE",
        "b": "VALIDATED_CANDIDATE",
    }


def test_normalize_candidates_rejects_non_candidate_input():
    try:
        normalize_candidates([object()])
    except TypeError as exc:
        assert "candidate_normalizer_expected_strategy_candidate" in str(exc)
    else:
        raise AssertionError("normalizer accepted non-candidate input")


def test_normalization_result_is_json_serializable():
    result = normalize_candidates([_candidate("a"), _candidate("b", confidence_score=0.9)])

    payload = result.to_json()

    assert "candidate_normalizer_v1" in payload
    assert "duplicate_groups" in payload
