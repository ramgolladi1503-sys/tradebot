from __future__ import annotations

import json
import time
from dataclasses import replace

from core.feed_health_truth import FeedHealthTruthDecision
from core.feed_health_truth import classify_feed_health_truth
from core.feed_hold_gate import FEED_HOLD_BLOCKER
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.runtime_cycle_context import RuntimeCycleContext, StageTiming
from core.ranking_orchestrator import (
    FEED_HOLD_PIPELINE_STAGE_ORDER,
    PIPELINE_STAGE_ORDER,
    _homogeneous_scoring_symbol,
    build_ranked_opportunity_report,
)
from core.runtime_snapshot_stages import build_feed_health_truth_latest_payload


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


def _candidate(
    strategy_id="candidate",
    *,
    direction="BUY_CALL",
    movement_type="COMPRESSION_BREAKOUT",
    status="VALIDATED_CANDIDATE",
    blockers=(),
    warnings=(),
    raw_score=0.75,
    confidence_score=0.75,
    price_structure_score=0.8,
    option_confirmation_score=0.8,
    liquidity_score=0.8,
    freshness_score=0.9,
    volatility_score=0.5,
    regime_alignment_score=0.8,
    timing_score=0.7,
    trap_risk_score=0.05,
    confluence_score=0.6,
):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol="NIFTY",
        direction=direction,
        status=status,
        raw_score=raw_score,
        confidence_score=confidence_score,
        price_structure_score=price_structure_score,
        option_confirmation_score=option_confirmation_score,
        liquidity_score=liquidity_score,
        freshness_score=freshness_score,
        volatility_score=volatility_score,
        regime_alignment_score=regime_alignment_score,
        timing_score=timing_score,
        trap_risk_score=trap_risk_score,
        confluence_score=confluence_score,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=blockers,
        warnings=warnings,
        lineage={"promotion_state": "PROMOTED"},
    )


def _generator(*candidates):
    def _inner(ctx, regime):
        return candidates

    return _inner


def _failing_generator(ctx, regime):
    raise RuntimeError("boom")


def _feed_truth(feed_ok=True, *reasons):
    return FeedHealthTruthDecision(
        feed_ok=feed_ok,
        reason_code="ok" if feed_ok else "feed_health_truth_failed",
        reasons=tuple(reasons),
        global_feed_ok=feed_ok,
        websocket_ok=feed_ok,
    )


def test_ranked_opportunity_report_builds_full_read_only_pipeline():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[
            _generator(
                _candidate("call_high", direction="BUY_CALL", price_structure_score=0.9, option_confirmation_score=0.9),
                _candidate("call_mid", direction="BUY_CALL", movement_type="TREND_PULLBACK", price_structure_score=0.7),
            )
        ],
        include_strategy_id_in_normalization_key=True,
    )

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.pipeline_stage_order == PIPELINE_STAGE_ORDER
    assert "feed_hold_gate" not in report.pipeline_stage_order
    assert report.raw_candidate_count == 2
    assert report.normalized_candidate_count == 2
    assert report.ranked_candidate_count == 2
    assert report.executable_rank_count == 2
    assert report.top_rank_strategy_id == "call_high"
    assert report.ranking.ranks[0].rank == 1
    assert report.metadata["orchestrator"] == "ranked_opportunity_pipeline_v1"
    assert report.metadata["source_ranker"] == "candidate_ranking_v1"
    assert report.metadata["feed_health_input_present"] is False
    assert report.metadata["feed_hold_active"] is False


def test_ranked_pipeline_applies_feed_hold_when_feed_truth_is_unhealthy():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
        feed_health=_feed_truth(False, "global_feed_unhealthy", "websocket_disconnected"),
    )

    assert report.pipeline_stage_order == FEED_HOLD_PIPELINE_STAGE_ORDER
    assert report.ranked_candidate_count == 0
    assert report.executable_rank_count == 0
    assert report.near_executable_rank_count == 0
    assert report.top_rank_strategy_id is None
    assert FEED_HOLD_BLOCKER in report.blockers
    assert "global_feed_unhealthy" in report.blockers
    assert "websocket_disconnected" in report.blockers
    assert FEED_HOLD_BLOCKER in report.safety_flags
    assert report.metadata["source_feed_gate"] == "feed_hold_gate_v1"
    assert report.metadata["feed_health_input_present"] is True
    assert report.metadata["feed_hold_active"] is True
    assert report.ranking.metadata["feed_hold_active"] is True


def test_ranked_pipeline_preserves_ranking_when_feed_truth_is_healthy():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
        feed_health=_feed_truth(True),
    )

    assert report.pipeline_stage_order == FEED_HOLD_PIPELINE_STAGE_ORDER
    assert report.ranked_candidate_count == 1
    assert report.executable_rank_count == 1
    assert report.top_rank_strategy_id == "clean"
    assert FEED_HOLD_BLOCKER not in report.blockers
    assert report.metadata["source_feed_gate"] is None
    assert report.metadata["feed_health_input_present"] is True
    assert report.metadata["feed_hold_active"] is False


def test_ranked_pipeline_accepts_feed_health_mapping_and_fails_closed_when_invalid():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
        feed_health={"feed_ok": False, "effective_ws_connected": False},
    )

    assert report.pipeline_stage_order == FEED_HOLD_PIPELINE_STAGE_ORDER
    assert report.ranked_candidate_count == 0
    assert report.executable_rank_count == 0
    assert FEED_HOLD_BLOCKER in report.blockers
    assert "websocket_disconnected" in report.blockers
    assert report.metadata["feed_hold_active"] is True


def test_ranked_pipeline_keeps_suppressed_fallback_visible_below_safer_candidate():
    executable = _candidate("exec", direction="BUY_CALL", price_structure_score=0.7)
    fallback = _candidate(
        "fallback",
        direction="BUY_PUT",
        status="BLOCKED_CANDIDATE",
        blockers=("FALLBACK_QUOTE_ONLY",),
        warnings=("fallback_used",),
        raw_score=1.0,
        confidence_score=1.0,
        price_structure_score=1.0,
        option_confirmation_score=1.0,
        liquidity_score=1.0,
        freshness_score=1.0,
        regime_alignment_score=1.0,
    )

    report = build_ranked_opportunity_report(
        _context(fallback_used=True, quote_source="recovered_fallback"),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(fallback, executable)],
        include_strategy_id_in_normalization_key=True,
    )

    assert [rank.strategy_id for rank in report.ranking.ranks] == ["exec", "fallback", "no_trade_engine_v1"]
    assert report.suppressed_rank_count >= 1
    assert report.no_trade_rank_count == 1
    assert "FALLBACK_QUOTE_ONLY" in report.blockers
    assert "fallback_data" in report.safety_flags


def test_ranked_pipeline_uses_cycle_context_feed_truth_and_exposes_stage_timings():
    cycle_context = RuntimeCycleContext(
        cycle_id="cycle-1",
        feed_truth=_feed_truth(True).to_payload(),
        stage_timings=(StageTiming(stage="feed_health_truth", elapsed_ms=1.25, metadata={"producer": "unit"}),),
        metadata={"producer": "unit"},
    )

    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
        cycle_context=cycle_context,
    )

    assert report.metadata["cycle_context_present"] is True
    assert report.metadata["stage_timings"][0]["stage"] == "feed_health_truth"
    assert report.metadata["stage_timings"][0]["elapsed_ms"] == 1.25
    assert report.ranked_candidate_count == 1


def test_ranked_pipeline_scopes_explicit_cycle_health_to_report_symbol():
    observed_epoch = time.time()
    session_identity = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": "session-test",
        "feed_epoch": 9,
        "reconnect_generation": 3,
        "observed_epoch": observed_epoch,
    }
    runtime_feed = {
            "ts_epoch": observed_epoch,
            "feed_session_identity": session_identity,
            "underlying_feed_identity_by_symbol": {
                symbol: {
                    "status": "HEALTHY",
                    "symbol": symbol,
                    "identity_domain": "INDEX_SPOT",
                    "instrument_token": token,
                    "feed_session_id": "session-test",
                    "feed_epoch": 9,
                    "reconnect_generation": 3,
                    "active_subscription": True,
                    "subscription_succeeded": True,
                    "receipt_epoch": observed_epoch - 0.3,
                    "age_sec": 0.3,
                    "max_age_sec": 2.5,
                    "generated_epoch": observed_epoch,
                }
                for symbol, token in (("NIFTY", 256265), ("BANKNIFTY", 260105))
            },
            "feed_ok": False,
            "feed_ok_scope": "symbol_aggregate",
            "global_feed_blocked": False,
            "effective_ws_connected": True,
            "runtime_state": "RUNNING",
            "state_machine": {"state": "LIVE"},
            "last_tick_age_sec": 0.4,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {
                "NIFTY": "OK",
                "BANKNIFTY": "SUBSCRIPTION_FAILED",
            },
            "option_last_tick_age_by_symbol": {"NIFTY": 0.3, "BANKNIFTY": 0.2},
        }
    _feed_truth_payload, cycle_truth = build_feed_health_truth_latest_payload(runtime_feed)
    assert cycle_truth.feed_ok is False
    cycle_context = RuntimeCycleContext(cycle_id="mixed-cycle", feed_truth=cycle_truth.to_payload())

    report = build_ranked_opportunity_report(
        _context(symbol="NIFTY"),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
        cycle_context=cycle_context,
    )

    assert report.ranked_candidate_count == 1
    assert report.executable_rank_count == 1
    assert FEED_HOLD_BLOCKER not in report.blockers
    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False


def test_mixed_symbol_candidate_pool_cannot_use_context_symbol_health_scope():
    observed_epoch = time.time()
    session_identity = {
        "provider": "kite", "token_domain": "kite_instrument_token",
        "feed_session_id": "session-test", "feed_epoch": 9,
        "reconnect_generation": 3, "observed_epoch": observed_epoch,
    }
    runtime_feed = {
        "ts_epoch": observed_epoch,
        "feed_session_identity": session_identity,
        "underlying_feed_identity_by_symbol": {
            symbol: {
                "status": "HEALTHY", "symbol": symbol, "identity_domain": "INDEX_SPOT",
                "instrument_token": token, "feed_session_id": "session-test",
                "feed_epoch": 9, "reconnect_generation": 3,
                "active_subscription": True, "subscription_succeeded": True,
                "receipt_epoch": observed_epoch - 0.3, "age_sec": 0.3,
                "max_age_sec": 2.5, "generated_epoch": observed_epoch,
            }
            for symbol, token in (("NIFTY", 256265), ("BANKNIFTY", 260105))
        },
        "feed_ok": False, "feed_ok_scope": "symbol_aggregate", "global_feed_blocked": False,
        "effective_ws_connected": True, "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE"}, "last_tick_age_sec": 0.4,
        "last_depth_age_sec": 1.0,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK", "BANKNIFTY": "SUBSCRIPTION_FAILED"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.3, "BANKNIFTY": 0.2},
    }
    _, cycle_truth = build_feed_health_truth_latest_payload(runtime_feed)
    banknifty_candidate = replace(_candidate("banknifty", direction="BUY_CALL"), symbol="BANKNIFTY")

    report = build_ranked_opportunity_report(
        _context(symbol="NIFTY"),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("nifty"), banknifty_candidate)],
        include_strategy_id_in_normalization_key=True,
        cycle_context=RuntimeCycleContext(cycle_id="mixed-symbol", feed_truth=cycle_truth.to_payload()),
    )

    assert report.candidate_pool.symbol == "NIFTY"
    assert {score.symbol for score in report.scoring.scores} == {"NIFTY", "BANKNIFTY"}
    assert report.ranked_candidate_count == 0
    assert FEED_HOLD_BLOCKER in report.blockers
    assert report.ranking.metadata["feed_hold_scope"] == "global_or_unknown"


def test_homogeneous_scope_requires_nonempty_canonical_exact_symbol_identities():
    class Score:
        def __init__(self, symbol):
            self.symbol = symbol

    class Scores:
        def __init__(self, *symbols):
            self.scores = tuple(Score(symbol) for symbol in symbols)

    assert _homogeneous_scoring_symbol(Scores("NIFTY", "NIFTY"), "NIFTY") == "NIFTY"
    assert _homogeneous_scoring_symbol(Scores(), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores(""), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores("   "), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores(None), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores(["NIFTY"]), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores(" nifty"), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores("NIFTY "), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores("BANKNIFTY"), "NIFTY") is None
    assert _homogeneous_scoring_symbol(Scores("NIFTY"), " nifty ") is None


def test_ranked_pipeline_global_no_trade_suppresses_directional_candidates():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="CHOP", CHOP=0.85),
        candidate_generators=[_generator(_candidate("call", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
    )

    assert report.candidate_pool.no_trade_assessment.no_trade is True
    assert report.executable_rank_count == 0
    assert report.suppressed_rank_count >= 1
    assert report.no_trade_rank_count >= 1
    assert report.ranking.ranks[-1].score_eligibility == "NO_TRADE_ONLY"
    assert "NO_TRADE_CHOP" in report.blockers


def test_ranked_pipeline_tolerates_generator_failure_and_still_ranks_valid_candidates():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_failing_generator, _generator(_candidate("valid", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
    )

    assert report.candidate_pool.failed_generator_count == 1
    assert report.raw_candidate_count == 1
    assert report.ranked_candidate_count == 1
    assert report.top_rank_strategy_id == "valid"
    assert any(warning.startswith("strategy_generator_failed") for warning in report.warnings)


def test_ranked_pipeline_handles_empty_candidate_pool_safely():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator()],
    )

    assert report.raw_candidate_count == 0
    assert report.normalized_candidate_count == 0
    assert report.ranked_candidate_count == 0
    assert report.top_rank_strategy_id is None
    assert report.top_rank_score is None
    assert report.ranking.ranks == ()


def test_ranked_pipeline_report_is_json_serializable():
    report = build_ranked_opportunity_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_generator(_candidate("clean", direction="BUY_CALL"))],
        include_strategy_id_in_normalization_key=True,
        feed_health=_feed_truth(False, "global_feed_unhealthy"),
    )

    payload = report.to_json()

    assert "ranked_opportunity_pipeline_v1" in payload
    assert "feed_hold_gate_v1" in payload
    json.loads(payload)
