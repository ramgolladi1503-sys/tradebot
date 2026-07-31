from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult


def _regime(primary="TREND_UP", **scores):
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


def _context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22550.0,
        "vwap": 22500.0,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 14.0,
        "pe_premium_change": -2.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.9,
        "ce_depth": 1200.0,
        "pe_depth": 1000.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _candidate(direction="BUY_CALL", blockers=()):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=f"unit_{direction.lower()}",
        movement_type="COMPRESSION_BREAKOUT",
        symbol="NIFTY",
        direction=direction,
        status="VALIDATED_CANDIDATE" if not blockers else "BLOCKED_CANDIDATE",
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
    )


def test_candidate_pool_report_is_read_only_and_not_order_action():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.candidate_count == 1
    assert report.movement_candidate_count == 1
    assert report.no_trade_candidate_count == 0
    assert report.report_executable_eligible_count == 1
    assert report.metadata["scope"] == "read_only_no_execution_no_ranking"
    assert report.to_dict()["is_order_action"] is False


def test_candidate_pool_report_forces_zero_executable_count_when_no_trade_active():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="CHOP", CHOP=0.85),
        candidate_generators=[generator],
    )

    assert report.no_trade_assessment.no_trade is True
    assert report.no_trade_assessment.primary_reason == "NO_TRADE_CHOP"
    assert report.eligible_candidate_count_before_suppression == 1
    assert report.report_executable_eligible_count == 0
    assert report.no_trade_candidate_count == 1
    assert any(candidate.direction == "NO_TRADE" for candidate in report.candidates)
    assert "NO_TRADE_CHOP" in report.blockers


def test_candidate_pool_report_blocks_fallback_from_becoming_executable_truth():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_candidate_pool_report(
        _context(fallback_used=True, quote_source="recovered_fallback"),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    assert report.no_trade_assessment.no_trade is True
    assert report.report_executable_eligible_count == 0
    assert "FALLBACK_QUOTE_ONLY" in report.blockers
    assert report.metadata["no_trade"] is True


def test_candidate_pool_report_collects_option_confirmation_evidence():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"), _candidate("BUY_PUT"))

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    assert report.option_pressure.dominant_direction == "BUY_CALL"
    assert len(report.option_confirmations) == 2
    effects = {confirmation.candidate_direction: confirmation.suggested_effect for confirmation in report.option_confirmations}
    assert effects["BUY_CALL"] in {"PROMOTE", "NEUTRAL"}
    assert effects["BUY_PUT"] in {"DEMOTE", "BLOCK", "NEUTRAL"}


def test_candidate_pool_report_survives_generator_failure():
    def broken_generator(ctx, regime):
        raise RuntimeError("boom")

    def good_generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[broken_generator, good_generator],
    )

    assert report.generator_count == 2
    assert report.failed_generator_count == 1
    assert report.movement_candidate_count == 1
    assert any(warning.startswith("strategy_generator_failed:broken_generator:RuntimeError") for warning in report.warnings)


def test_candidate_pool_report_is_json_serializable():
    def generator(ctx, regime):
        return (_candidate("BUY_CALL"),)

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    payload = report.to_json()

    assert "candidate_pool_orchestrator_shell" in payload
    assert "BUY_CALL" in payload


def test_candidate_pool_preserves_caller_supplied_completed_bars():
    supplied = [
        {
            "ts_epoch": 1785451020.0,
            "source_bar_end_epoch": 1785451020.0,
            "session_date": "2026-07-31",
            "index_ret1": 0.001,
            "constituent_ret1": [0.001] * 40,
            "constituent_ret1_by_symbol": {f"S{i}": 0.001 for i in range(40)},
            "participation_count": 40,
            "completed": True,
            "allowed_for_live_execution": False,
            "is_order_action": False,
            "broker_api_called": False,
        }
    ]

    report = build_candidate_pool_report(
        _context(
            ts_epoch=1785451080.0,
            metadata={
                "market_event_graph_live_source_enable": True,
                "completed_constituent_bars": supplied,
            },
        ),
        _regime(primary="RANGE", RANGE=0.8),
        candidate_generators=[],
        include_no_trade_candidate=False,
    )

    assert report.metadata["market_event_graph_constituent_source_status"] == "EXTERNAL_INPUT_PRESERVED"
    assert report.metadata["market_event_graph_constituent_source_reason"] == "caller_supplied_completed_bars"
    assert report.metadata["market_event_graph_constituent_source_evidence"]["completed_bar_count"] == 1
    assert report.candidate_count == 0
