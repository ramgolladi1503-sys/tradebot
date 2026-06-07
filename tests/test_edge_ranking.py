from __future__ import annotations

import inspect

from core.expectancy.edge_ranking import apply_edge_ranking
from core import review_queue


def _row(**overrides):
    row = {
        "trade_id": "T-EDGE-RANK",
        "candidate_id": "C-EDGE-RANK",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "regime": "LIVE",
        "index": "NIFTY",
        "expiry_type": "WEEKLY",
        "option_type": "CE",
        "direction": "BUY",
        "setup_id": "breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE",
        "rank_score": 0.62,
        "opportunity_score": 0.57,
        "confidence_final": 0.64,
        "liquidity_score": 0.82,
        "timing_score": 0.74,
        "regime_fit": 0.79,
        "rr_score": 0.68,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_status": "executable",
        "reportable_executable": True,
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
        "candidate_status": "executable",
        "candidate_class": "primary",
        "candidate_type": "directional",
        "quote_source": "tick_store",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
    }
    row.update(overrides)
    return row


def test_keep_positive_expectancy_candidate_gets_high_edge_rank_score():
    out = apply_edge_ranking(
        _row(
            expectancy_status="KEEP",
            expectancy_sample_count=60,
            expectancy_avg_cost_adjusted_r=0.22,
        )
    )

    assert out["expectancy_status"] == "KEEP"
    assert out["expectancy_sample_count"] == 60
    assert out["expectancy_avg_cost_adjusted_r"] == 0.22
    assert out["edge_rank_score"] > 0.75
    assert "expectancy_keep" in out["edge_rank_reason"]
    assert out["edge_rank_components"]["raw_edge_rank_score"] >= out["edge_rank_score"]


def test_review_queue_wires_edge_rank_fields_without_touching_rank_score():
    row = _row(
        rank_score=0.61,
        expectancy_lookup={
            "breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": {
                "expectancy_status": "KEEP",
                "expectancy_sample_count": 48,
                "expectancy_avg_cost_adjusted_r": 0.19,
            }
        },
    )

    out = review_queue._apply_expectancy_gate_if_present(row)

    assert out["rank_score"] == 0.61
    assert out["edge_rank_score"] > 0.70
    assert out["expectancy_status"] == "KEEP"
    assert out["edge_rank_components"]["expectancy_status"] == "KEEP"


def test_kill_candidate_gets_zero_score_and_non_executable():
    row = review_queue._apply_expectancy_gate_if_present(
        _row(
            expectancy_lookup={"breakout__LIVE__HIGH__HIGH__WIDE__T08_11_UTC__WEEKLY__BUY__NIFTY__CE": "KILL"},
            reportable_executable=True,
            execution_allowed=True,
            eligible_for_execution=True,
        )
    )

    assert row["expectancy_status"] == "KILL"
    assert row["edge_rank_score"] == 0.0
    assert row["reportable_executable"] is False
    assert row["execution_allowed"] is False
    assert row["eligible_for_execution"] is False
    assert row["permission"] == "BLOCK"


def test_insufficient_data_candidate_is_capped_low():
    out = apply_edge_ranking(
        _row(
            expectancy_status="INSUFFICIENT_DATA",
            expectancy_sample_count=8,
            expectancy_avg_cost_adjusted_r=0.05,
            confidence_final=0.88,
            rank_score=0.82,
        )
    )

    assert out["expectancy_status"] == "INSUFFICIENT_DATA"
    assert out["edge_rank_score"] <= 0.30
    assert "expectancy_insufficient_data" in out["edge_rank_reason"]


def test_watch_candidate_is_capped_medium_and_advisory():
    out = apply_edge_ranking(
        _row(
            expectancy_status="WATCH",
            expectancy_sample_count=22,
            expectancy_avg_cost_adjusted_r=0.10,
            permission="QUEUE_ONLY",
            final_action="QUEUE_ONLY",
            readiness="QUEUE_ONLY",
            execution_status="queue_only",
            candidate_status="advisory_only",
            reportable_executable=False,
            execution_allowed=False,
            eligible_for_execution=False,
            selected_for_execution=False,
        )
    )

    assert out["expectancy_status"] == "WATCH"
    assert 0.0 < out["edge_rank_score"] <= 0.55
    assert "expectancy_watch" in out["edge_rank_reason"]


def test_fallback_candidate_cannot_rank_executable():
    out = apply_edge_ranking(
        _row(
            expectancy_status="KEEP",
            expectancy_sample_count=70,
            expectancy_avg_cost_adjusted_r=0.30,
            row_kind="recovered_fallback",
            candidate_class="fallback",
            candidate_origin="fallback_rest",
            quote_source="rest_fallback",
            trade_id="softrej_T-FALLBACK",
        )
    )

    assert out["edge_rank_score"] == 0.0
    assert "fallback_not_rankable" in out["edge_rank_reason"]
    assert out["edge_rank_components"]["fallback_candidate"] is True


def test_stale_feed_candidate_cannot_rank_executable():
    out = apply_edge_ranking(
        _row(
            expectancy_status="KEEP",
            expectancy_sample_count=90,
            expectancy_avg_cost_adjusted_r=0.25,
            blockers=["STALE_OPTION_LTP"],
            execution_truth_blockers=["LTP_STALE AGE=4.17 MAX=2.50"],
            feed_truth_state="DEAD",
            runtime_state="RECOVERY_BLOCKED",
            ws_connected=False,
            process_restart_required=True,
        )
    )

    assert out["edge_rank_score"] == 0.0
    assert "feed_truth_blocked" in out["edge_rank_reason"]
    assert out["edge_rank_components"]["feed_blocked"] is True


def test_positive_lower_confidence_outranks_unproven_high_confidence():
    proven = apply_edge_ranking(
        _row(
            trade_id="T-PROVEN",
            confidence_final=0.42,
            rank_score=0.40,
            expectancy_status="KEEP",
            expectancy_sample_count=50,
            expectancy_avg_cost_adjusted_r=0.18,
        )
    )
    unproven = apply_edge_ranking(
        _row(
            trade_id="T-UNPROVEN",
            confidence_final=0.88,
            rank_score=0.84,
            expectancy_status="INSUFFICIENT_DATA",
            expectancy_sample_count=0,
            expectancy_avg_cost_adjusted_r=None,
        )
    )

    assert proven["edge_rank_score"] > unproven["edge_rank_score"]
    assert proven["rank_score"] == 0.40
    assert unproven["rank_score"] == 0.84


def test_duplicate_correlated_candidate_is_penalized_below_clean_candidate():
    clean = apply_edge_ranking(
        _row(
            trade_id="T-CLEAN-CROWD",
            expectancy_status="KEEP",
            expectancy_sample_count=58,
            expectancy_avg_cost_adjusted_r=0.21,
            liquidity_score=0.86,
            spread_score=0.81,
            timing_score=0.79,
            regime_fit=0.88,
            rr_score=0.74,
            family_consensus_score=0.88,
            correlation_penalty=0.0,
        )
    )
    crowded = apply_edge_ranking(
        _row(
            trade_id="T-CROWDED",
            expectancy_status="KEEP",
            expectancy_sample_count=58,
            expectancy_avg_cost_adjusted_r=0.21,
            liquidity_score=0.86,
            spread_score=0.81,
            timing_score=0.79,
            regime_fit=0.88,
            rr_score=0.74,
            family_consensus_score=0.24,
            correlation_penalty=0.42,
            duplicate_candidate_count=2,
            duplicate_group_count=1,
            same_symbol_candidate_count=3,
        )
    )

    assert clean["edge_rank_score"] > crowded["edge_rank_score"]
    assert crowded["edge_rank_reason"].count("correlated_concentration") >= 1
    assert crowded["edge_rank_components"]["crowding_penalty"] > 0.0


def test_regime_mismatch_candidate_ranks_below_regime_aligned_candidate():
    aligned = apply_edge_ranking(
        _row(
            trade_id="T-REGIME-ALIGNED",
            expectancy_status="KEEP",
            expectancy_sample_count=60,
            expectancy_avg_cost_adjusted_r=0.19,
            regime_fit=0.91,
        )
    )
    mismatched = apply_edge_ranking(
        _row(
            trade_id="T-REGIME-MISMATCH",
            expectancy_status="KEEP",
            expectancy_sample_count=60,
            expectancy_avg_cost_adjusted_r=0.19,
            regime_fit=0.22,
        )
    )

    assert aligned["edge_rank_score"] > mismatched["edge_rank_score"]
    assert aligned["edge_rank_components"]["regime_match"] > mismatched["edge_rank_components"]["regime_match"]


def test_positive_expectancy_does_not_override_regime_mismatch_completely():
    aligned = apply_edge_ranking(
        _row(
            trade_id="T-ALIGN-EXPECTANCY",
            strategy_family="breakout",
            regime_fit=0.90,
            expectancy_status="KEEP",
            expectancy_sample_count=62,
            expectancy_avg_cost_adjusted_r=0.24,
        )
    )
    mismatched = apply_edge_ranking(
        _row(
            trade_id="T-MISMATCH-EXPECTANCY",
            strategy_family="mean_reversion",
            regime_fit=0.24,
            expectancy_status="KEEP",
            expectancy_sample_count=62,
            expectancy_avg_cost_adjusted_r=0.24,
            correlation_penalty=0.18,
            duplicate_candidate_count=1,
        )
    )

    assert aligned["edge_rank_score"] > mismatched["edge_rank_score"]
    assert mismatched["edge_rank_score"] > 0.0
    assert "correlated_concentration" in mismatched["edge_rank_reason"] or "duplicate_candidate_cluster" in mismatched["edge_rank_reason"]


def test_baseline_underperformance_penalizes_edge_rank_but_keeps_safety_intact():
    out = apply_edge_ranking(
        _row(
            expectancy_status="KEEP",
            expectancy_sample_count=60,
            expectancy_avg_cost_adjusted_r=0.20,
            baseline_verdict="UNDERPERFORMS",
            baseline_penalty_or_boost=-0.08,
            baseline_source="same_regime",
            baseline_reason="same_regime_baseline_underperforms",
        )
    )

    assert out["baseline_verdict"] == "UNDERPERFORMS"
    assert out["baseline_penalty_or_boost"] < 0
    assert out["edge_rank_score"] < 0.8
    assert out["permission"] == "EXECUTE"
    assert out["reportable_executable"] is True


def test_baseline_outperformance_boost_is_capped_and_conservative():
    out = apply_edge_ranking(
        _row(
            expectancy_status="KEEP",
            expectancy_sample_count=60,
            expectancy_avg_cost_adjusted_r=0.20,
            baseline_verdict="OUTPERFORMS",
            baseline_penalty_or_boost=0.05,
            baseline_source="same_regime",
            baseline_reason="same_regime_baseline_outperforms",
        )
    )

    assert out["baseline_verdict"] == "OUTPERFORMS"
    assert out["baseline_penalty_or_boost"] > 0
    assert out["edge_rank_score"] <= 1.0
    assert "baseline=OUTPERFORMS" in out["edge_rank_reason"]


def test_edge_ranking_module_does_not_import_broker_or_order_modules():
    source = inspect.getsource(__import__("core.expectancy.edge_ranking", fromlist=["*"]))
    assert "from core.broker" not in source
    assert "import core.broker" not in source
    assert "from core.order" not in source
    assert "import core.order" not in source
