from core.candidate_classifier import classify_candidate, classify_candidates
from core.movement_contract import StrategyCandidate


def _candidate(
    strategy_id="s1",
    *,
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    status="VALIDATED_CANDIDATE",
    blockers=(),
    warnings=(),
):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol="NIFTY",
        direction=direction,
        status=status,
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=0.7,
        liquidity_score=0.8,
        freshness_score=0.9,
        volatility_score=0.5,
        regime_alignment_score=0.7,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
        warnings=warnings,
    )


def test_validated_clean_candidate_goes_to_ready_bucket():
    out = classify_candidate(_candidate())

    assert out.bucket == "EXECUTABLE_CANDIDATE"
    assert out.executable_candidate is True
    assert out.hard_blockers == ()
    assert "validated_without_hard_blockers" in out.reasons


def test_raw_candidate_goes_to_near_ready_bucket_without_scoring():
    out = classify_candidate(_candidate(status="RAW_CANDIDATE"))

    assert out.bucket == "NEAR_EXECUTABLE_CANDIDATE"
    assert out.executable_candidate is False
    assert "raw_candidate_needs_confirmation" in out.reasons


def test_blocked_candidate_goes_to_suppressed_and_keeps_blockers():
    out = classify_candidate(
        _candidate(
            status="BLOCKED_CANDIDATE",
            blockers=("FALLBACK_QUOTE_ONLY", "STALE_OPTION_LTP", "WIDE_SPREAD", "MISSING_DEPTH"),
            warnings=("option_ltp_stale", "depth_missing"),
        )
    )

    assert out.bucket == "SUPPRESSED_CANDIDATE"
    assert out.executable_candidate is False
    assert set(out.hard_blockers) >= {"FALLBACK_QUOTE_ONLY", "STALE_OPTION_LTP", "WIDE_SPREAD", "MISSING_DEPTH"}
    assert set(out.evidence_flags) >= {"fallback_data", "stale_feed", "liquidity_risk"}
    assert "hard_blocked_or_blocked_status" in out.reasons


def test_no_trade_candidate_goes_to_no_trade_bucket():
    out = classify_candidate(
        _candidate(
            strategy_id="no_trade_engine_v1",
            direction="NO_TRADE",
            movement_type="NO_TRADE_CHOP",
            status="NO_TRADE",
            blockers=("NO_TRADE_CHOP",),
        ),
        no_trade_active=False,
    )

    assert out.bucket == "NO_TRADE_CANDIDATE"
    assert out.executable_candidate is False
    assert "candidate_is_no_trade_signal" in out.reasons
    assert "no_trade_suppression" in out.evidence_flags


def test_global_no_trade_suppresses_clean_directional_candidate():
    out = classify_candidate(_candidate(), no_trade_active=True, no_trade_reason="NO_TRADE_CHOP")

    assert out.bucket == "SUPPRESSED_CANDIDATE"
    assert out.executable_candidate is False
    assert "suppressed_by_no_trade_assessment" in out.reasons
    assert "NO_TRADE_CHOP" in out.reasons


def test_soft_warning_keeps_validated_candidate_in_ready_bucket():
    out = classify_candidate(_candidate(warnings=("minor_context_warning",)))

    assert out.bucket == "EXECUTABLE_CANDIDATE"
    assert out.executable_candidate is True
    assert out.warnings == ("minor_context_warning",)


def test_bearish_candidate_stays_executable_when_not_blocked():
    out = classify_candidate(_candidate(direction="BUY_PUT", movement_type="MEAN_REVERSION_EXTENSION"))

    assert out.bucket == "EXECUTABLE_CANDIDATE"
    assert out.executable_candidate is True
    assert out.direction == "BUY_PUT"


def test_classification_report_counts_all_buckets():
    candidates = [
        _candidate("ready"),
        _candidate("raw", status="RAW_CANDIDATE"),
        _candidate("blocked", status="BLOCKED_CANDIDATE", blockers=("FALLBACK_QUOTE_ONLY",)),
        _candidate("no_trade", direction="NO_TRADE", movement_type="NO_TRADE_CHOP", status="NO_TRADE", blockers=("NO_TRADE_CHOP",)),
    ]

    report = classify_candidates(candidates)

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.candidate_count == 4
    assert report.executable_count == 1
    assert report.near_executable_count == 1
    assert report.suppressed_count == 1
    assert report.no_trade_count == 1
    assert report.advisory_count == 0
    assert report.metadata["scope"] == "read_only_no_execution_no_ranking"


def test_global_no_trade_suppresses_directional_but_not_no_trade_signal():
    candidates = [
        _candidate("directional"),
        _candidate("no_trade", direction="NO_TRADE", movement_type="NO_TRADE_CHOP", status="NO_TRADE", blockers=("NO_TRADE_CHOP",)),
    ]

    report = classify_candidates(candidates, no_trade_active=True, no_trade_reason="NO_TRADE_CHOP")

    assert report.executable_count == 0
    assert report.suppressed_count == 1
    assert report.no_trade_count == 1
    buckets = {item.strategy_id: item.bucket for item in report.classifications}
    assert buckets["directional"] == "SUPPRESSED_CANDIDATE"
    assert buckets["no_trade"] == "NO_TRADE_CANDIDATE"


def test_classifier_rejects_non_candidate_input():
    try:
        classify_candidates([object()])
    except TypeError as exc:
        assert "candidate_classifier_expected_strategy_candidate" in str(exc)
    else:
        raise AssertionError("classifier accepted non-candidate input")


def test_classification_report_is_json_serializable():
    report = classify_candidates([_candidate("ready")])

    payload = report.to_json()

    assert "candidate_classifier_v1" in payload
    assert "EXECUTABLE_CANDIDATE" in payload
