from core.candidate_classifier import CandidateClassification, classify_candidates
from core.hard_downgrade_engine import apply_hard_downgrades, downgrade_classification
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


def _classification(**overrides):
    payload = {
        "strategy_id": "s1",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "movement_type": "COMPRESSION_BREAKOUT",
        "candidate_status": "VALIDATED_CANDIDATE",
        "bucket": "EXECUTABLE_CANDIDATE",
        "executable_candidate": True,
        "reasons": ("validated_without_hard_blockers",),
        "blockers": (),
        "warnings": (),
        "hard_blockers": (),
        "evidence_flags": (),
    }
    payload.update(overrides)
    return CandidateClassification(**payload)


def test_clean_executable_classification_remains_executable():
    decision = downgrade_classification(_classification())

    assert decision.original_bucket == "EXECUTABLE_CANDIDATE"
    assert decision.downgraded_bucket == "EXECUTABLE_CANDIDATE"
    assert decision.downgraded is False
    assert decision.executable_candidate is True
    assert decision.downgrade_reasons == ("validated_without_hard_blockers",)


def test_fallback_hard_blocker_downgrades_to_suppressed():
    decision = downgrade_classification(
        _classification(
            blockers=("FALLBACK_QUOTE_ONLY",),
            hard_blockers=("FALLBACK_QUOTE_ONLY",),
            evidence_flags=("fallback_data",),
        )
    )

    assert decision.downgraded_bucket == "SUPPRESSED_CANDIDATE"
    assert decision.downgraded is True
    assert decision.executable_candidate is False
    assert "fallback_quote_data" in decision.downgrade_reasons
    assert "fallback_data" in decision.safety_flags


def test_stale_spread_and_depth_blockers_are_explicit_reasons():
    decision = downgrade_classification(
        _classification(
            blockers=("STALE_OPTION_LTP", "WIDE_SPREAD", "MISSING_DEPTH"),
            hard_blockers=("STALE_OPTION_LTP", "WIDE_SPREAD", "MISSING_DEPTH"),
            evidence_flags=("stale_feed", "liquidity_risk"),
        )
    )

    assert decision.downgraded_bucket == "SUPPRESSED_CANDIDATE"
    assert set(decision.downgrade_reasons) >= {
        "stale_option_ltp",
        "wide_spread",
        "missing_depth",
        "liquidity_quality_failure",
    }
    assert set(decision.safety_flags) >= {"stale_feed", "liquidity_risk"}


def test_no_trade_active_suppresses_otherwise_executable_classification():
    decision = downgrade_classification(
        _classification(),
        no_trade_active=True,
        no_trade_reason="NO_TRADE_CHOP",
    )

    assert decision.downgraded_bucket == "SUPPRESSED_CANDIDATE"
    assert decision.downgraded is True
    assert decision.executable_candidate is False
    assert "global_no_trade_active" in decision.downgrade_reasons
    assert "no_trade_chop" in decision.downgrade_reasons
    assert "no_trade_suppression" in decision.safety_flags


def test_no_trade_candidate_stays_no_trade_bucket():
    decision = downgrade_classification(
        _classification(
            strategy_id="no_trade_engine_v1",
            direction="NO_TRADE",
            movement_type="NO_TRADE_CHOP",
            candidate_status="NO_TRADE",
            bucket="NO_TRADE_CANDIDATE",
            executable_candidate=False,
            blockers=("NO_TRADE_CHOP",),
            hard_blockers=("NO_TRADE_CHOP",),
            evidence_flags=("no_trade_suppression",),
        )
    )

    assert decision.downgraded_bucket == "NO_TRADE_CANDIDATE"
    assert decision.executable_candidate is False
    assert "candidate_is_no_trade_signal" in decision.downgrade_reasons
    assert "no_trade_suppression" in decision.safety_flags


def test_soft_safety_evidence_downgrades_executable_to_near_executable():
    decision = downgrade_classification(
        _classification(
            warnings=("quote_source_untrusted_soft_warning",),
            evidence_flags=("stale_feed",),
        )
    )

    assert decision.downgraded_bucket == "NEAR_EXECUTABLE_CANDIDATE"
    assert decision.downgraded is True
    assert decision.executable_candidate is False
    assert "soft_safety_evidence_requires_confirmation" in decision.downgrade_reasons


def test_apply_hard_downgrades_accepts_classification_report_and_counts():
    classification_report = classify_candidates(
        [
            _candidate("ready"),
            _candidate("fallback", status="BLOCKED_CANDIDATE", blockers=("FALLBACK_QUOTE_ONLY",)),
            _candidate("raw", status="RAW_CANDIDATE"),
            _candidate("nt", direction="NO_TRADE", movement_type="NO_TRADE_CHOP", status="NO_TRADE", blockers=("NO_TRADE_CHOP",)),
        ]
    )

    report = apply_hard_downgrades(classification_report)

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.candidate_count == 4
    assert report.executable_after_downgrade_count == 1
    assert report.suppressed_count == 1
    assert report.no_trade_count == 1
    assert "FALLBACK_QUOTE_ONLY" in report.blockers
    assert report.metadata["scope"] == "read_only_no_execution_no_ranking"


def test_apply_hard_downgrades_global_no_trade_zeroes_executable_count():
    classification_report = classify_candidates([_candidate("ready"), _candidate("raw", status="RAW_CANDIDATE")])

    report = apply_hard_downgrades(classification_report, no_trade_active=True, no_trade_reason="NO_TRADE_CHOP")

    assert report.executable_after_downgrade_count == 0
    assert report.suppressed_count == 2
    assert report.downgraded_count == 2
    assert "no_trade_suppression" in report.safety_flags


def test_hard_downgrade_report_is_json_serializable():
    report = apply_hard_downgrades([_classification()])

    payload = report.to_json()

    assert "hard_downgrade_engine_v1" in payload
    assert "EXECUTABLE_CANDIDATE" in payload


def test_hard_downgrade_rejects_non_classification_input():
    try:
        apply_hard_downgrades([object()])
    except TypeError as exc:
        assert "hard_downgrade_expected_candidate_classification" in str(exc)
    else:
        raise AssertionError("downgrade engine accepted non-classification input")
