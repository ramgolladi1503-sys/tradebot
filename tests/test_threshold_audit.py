from __future__ import annotations

from config import config as cfg
from core.adaptive_thresholds import adjust_threshold
from core.threshold_audit import (
    compute_starvation_diagnostics,
    rank_rejection_impact,
    normalize_candidate_decision,
    summarize_rejection_impact,
    summarize_rejections_by_stage,
    summarize_score_distributions,
    summarize_starvation_by_group,
    summarize_survival_vs_expectancy,
    summarize_threshold_behavior,
    summarize_top_damaging_gates,
)


def _decision(
    *,
    decision_phase: str = "selector",
    strategy_family: str = "continuation",
    direction_family: str = "bullish",
    session_mode: str = "MIDDAY",
    strategy_regime_mode: str = "TRENDING",
    candidate_class: str = "EXECUTABLE",
    selected_for_execution: bool = False,
    rejected_at_stage: str | None = None,
    rejection_reason_code: str | None = None,
    selector_outcome: str | None = "NO_EXECUTABLE_OPPORTUNITY",
    setup_score: float | None = 0.60,
    trigger_score: float | None = 0.58,
    entry_quality_score: float | None = 0.57,
    family_survival_score: float | None = 0.56,
    priority_score: float | None = 0.55,
    realized_r_multiple: float | None = None,
) -> dict:
    return {
        "timestamp": "2026-04-04T09:15:00+00:00",
        "decision_phase": decision_phase,
        "decision_scope": "unit:audit",
        "decision_batch_id": "batch-1",
        "trade_id": None,
        "symbol": "NIFTY",
        "strategy": "OPP_DIRECTIONAL",
        "strategy_family": strategy_family,
        "direction_family": direction_family,
        "candidate_class": candidate_class,
        "candidate_status": candidate_class.lower(),
        "selector_outcome": selector_outcome,
        "selected_for_execution": selected_for_execution,
        "selection_reason": rejection_reason_code,
        "market_mode": "SIM",
        "session_mode": session_mode,
        "strategy_regime_mode": strategy_regime_mode,
        "setup_score": setup_score,
        "trigger_score": trigger_score,
        "entry_quality_score": entry_quality_score,
        "family_survival_score": family_survival_score,
        "priority_score": priority_score,
        "final_score": priority_score,
        "selection_probability": 0.44,
        "rejected_at_stage": rejected_at_stage,
        "rejection_reason_code": rejection_reason_code,
        "realized_r_multiple": realized_r_multiple,
    }


def test_threshold_audit_summarizes_score_distributions():
    summary = summarize_score_distributions(
        [
            _decision(setup_score=0.20, trigger_score=0.30, entry_quality_score=0.40, family_survival_score=0.50, priority_score=0.60, realized_r_multiple=-0.5),
            _decision(setup_score=0.40, trigger_score=0.50, entry_quality_score=0.60, family_survival_score=0.70, priority_score=0.80, realized_r_multiple=0.5),
            _decision(setup_score=0.60, trigger_score=0.70, entry_quality_score=0.80, family_survival_score=0.90, priority_score=0.95, realized_r_multiple=1.5),
        ]
    )

    assert summary["setup_score"]["p50"] == 0.4
    assert summary["trigger_score"]["p90"] is not None
    assert summary["realized_r_multiple"]["p10"] is not None


def test_threshold_audit_counts_rejections_by_stage():
    summary = summarize_rejections_by_stage(
        [
            _decision(rejected_at_stage="setup", rejection_reason_code="family_consensus_below_threshold"),
            _decision(rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
            _decision(rejected_at_stage="selector", rejection_reason_code="rank_outside_top_n"),
        ]
    )

    assert summary["rejections_by_stage"]["selector"] == 2
    assert summary["rejections_by_reason"]["family_consensus_below_threshold"] == 1


def test_rejection_impact_summary_identifies_missed_win_heavy_gate():
    summary = summarize_rejection_impact(
        [
            _decision(
                strategy_family="continuation",
                direction_family="bullish",
                rejected_at_stage="selector",
                rejection_reason_code="below_survival_floor",
            ),
            _decision(
                strategy_family="continuation",
                direction_family="bullish",
                rejected_at_stage="selector",
                rejection_reason_code="low_selection_probability",
            ),
        ],
        [
            {
                "trade_id": None,
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "would_have_worked": True,
                "rejection_missed_win": True,
                "rejection_saved_loss": False,
                "simulated_pnl": 5.0,
                "realized_r_multiple": 0.6,
            }
        ],
    )

    row = summary["by_stage_strategy_family"]["selector|continuation"]
    assert row["reject_count"] == 2
    assert row["missed_win_count"] >= 1
    assert float(row["missed_win_rate"]) > float(row["saved_loss_rate"])
    assert float(row["impact_score"]) > 0.0


def test_rejection_impact_summary_identifies_saved_loss_heavy_gate():
    summary = summarize_rejection_impact(
        [
            _decision(
                strategy_family="mean_reversion",
                direction_family="sideways",
                rejected_at_stage="risk_budget",
                rejection_reason_code="risk_budget_reject",
            ),
            _decision(
                strategy_family="mean_reversion",
                direction_family="sideways",
                rejected_at_stage="risk_budget",
                rejection_reason_code="risk_budget_reject",
            ),
        ],
        [
            {
                "trade_id": None,
                "strategy_family": "mean_reversion",
                "direction_family": "sideways",
                "strategy_regime_mode": "SIDEWAYS",
                "session_mode": "MIDDAY",
                "would_have_worked": False,
                "rejection_missed_win": False,
                "rejection_saved_loss": True,
                "simulated_pnl": -4.0,
                "realized_r_multiple": -0.7,
            }
        ],
    )

    row = summary["by_stage_strategy_family"]["risk_budget|mean_reversion"]
    assert row["reject_count"] == 2
    assert row["saved_loss_count"] >= 1
    assert float(row["impact_score"]) < 0.0


def test_rejection_impact_identifies_bad_filters():
    impact = rank_rejection_impact(
        [
            _decision(
                strategy_family="continuation",
                direction_family="bullish",
                rejected_at_stage="selector",
                rejection_reason_code="below_survival_floor",
            ),
            _decision(
                strategy_family="continuation",
                direction_family="bullish",
                rejected_at_stage="selector",
                rejection_reason_code="low_selection_probability",
            ),
        ],
        [
            {
                "trade_id": None,
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "would_have_worked": True,
                "rejection_missed_win": True,
                "rejection_saved_loss": False,
                "simulated_pnl": 5.0,
                "realized_r_multiple": 0.6,
            }
        ],
    )

    row = impact["selector:continuation"]
    assert row["count"] == 2
    assert row["missed_win"] >= 1
    assert float(row["impact_score"]) > 0.0


def test_threshold_audit_normalize_preserves_liquidity_telemetry():
    normalized = normalize_candidate_decision(
        {
            "timestamp": "2026-05-04T14:11:00+05:30",
            "decision_phase": "selector",
            "decision_scope": "unit:audit",
            "symbol": "NIFTY",
            "market_mode": "SIM",
            "liquidity_score": 0.8125,
            "quote_consistency_score": 0.91,
            "liquidity_flow_score": 0.74,
            "liquidity_book_score": 0.88,
            "liquidity_spread_score": 0.81,
            "liquidity_volume_score": 0.77,
            "liquidity_oi_score": 0.69,
            "rank_score": 0.578174,
            "raw_rank_score": 0.746802,
            "terminal_rank_score": 0.578174,
            "opportunity_score": 0.654476,
            "quote_validation_status": "OK",
        }
    )

    assert normalized["liquidity_score"] == 0.8125
    assert normalized["quote_consistency_score"] == 0.91
    assert normalized["liquidity_flow_score"] == 0.74
    assert normalized["liquidity_book_score"] == 0.88
    assert normalized["liquidity_spread_score"] == 0.81
    assert normalized["liquidity_volume_score"] == 0.77
    assert normalized["liquidity_oi_score"] == 0.69
    assert normalized["rank_score"] == 0.578174
    assert normalized["raw_rank_score"] == 0.746802
    assert normalized["terminal_rank_score"] == 0.578174
    assert normalized["opportunity_score"] == 0.654476
    assert normalized["quote_validation_status"] == "OK"


def test_threshold_audit_normalize_backfills_raw_rank_from_rank():
    normalized = normalize_candidate_decision(
        {
            "timestamp": "2026-05-04T14:11:00+05:30",
            "decision_phase": "selector",
            "decision_scope": "unit:audit",
            "symbol": "NIFTY",
            "market_mode": "SIM",
            "rank_score": 0.578174,
            "terminal_rank_score": 0.578174,
            "opportunity_score": 0.654476,
            "quote_validation_status": "OK",
        }
    )

    assert normalized["rank_score"] == 0.578174
    assert normalized["raw_rank_score"] == 0.578174
    assert normalized["terminal_rank_score"] == 0.578174
    assert normalized["opportunity_score"] == 0.654476
    assert normalized["quote_validation_status"] == "OK"


def test_threshold_adjustment_is_bounded(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_LEARNING_MAX_STEP_PCT", 0.02, raising=False)

    loosened = adjust_threshold(0.60, 1.0)
    tightened = adjust_threshold(0.60, -1.0)

    assert 0.588 <= loosened <= 0.60
    assert 0.60 <= tightened <= 0.612
    assert adjust_threshold(0.60, 0.0) == 0.60


def test_session_policy_bundle_preserves_existing_defaults():
    midday = cfg.get_session_policy("MIDDAY")
    opening = cfg.get_session_policy("OPENING")

    assert midday["entry_penalty"] == float(cfg.SESSION_MIDDAY_ENTRY_PENALTY)
    assert midday["directional_trigger_min"] == float(cfg.SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN)
    assert opening["entry_penalty"] == float(cfg.SESSION_OPENING_ENTRY_PENALTY)
    assert opening["directional_trigger_min"] is None


def test_regime_policy_bundle_maps_existing_config_values():
    sideways = cfg.get_regime_policy("SIDEWAYS")
    low_vol = cfg.get_regime_policy("LOW_VOL")

    assert sideways["direction_family_max_candidates"] == int(cfg.NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES)
    assert sideways["sideways_direction_family_max_candidates"] == int(cfg.NONLIVE_SIDEWAYS_DIRECTION_FAMILY_MAX_CANDIDATES)
    assert low_vol["family_consensus_min_score"] == float(cfg.FAMILY_CONSENSUS_LOW_VOL_MIN_SCORE)


def test_starvation_flag_trips_when_survival_rate_collapses(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR", 0.40, raising=False)

    summary = compute_starvation_diagnostics(
        [
            _decision(rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
            _decision(rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
            _decision(rejected_at_stage="selector", rejection_reason_code="risk_budget_reject"),
            _decision(selected_for_execution=True, selector_outcome="EXECUTE_TOP", rejection_reason_code=None, rejected_at_stage=None),
        ]
    )

    assert summary["starvation_flag"] is True
    assert summary["starvation_reason"] == "survival_rate_below_floor"


def test_top_family_share_flags_directional_dominance(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_AUDIT_TOP_FAMILY_SHARE_WARN", 0.70, raising=False)

    summary = compute_starvation_diagnostics(
        [
            _decision(direction_family="bullish", rejected_at_stage=None, rejection_reason_code=None, selected_for_execution=True, selector_outcome="EXECUTE_TOP"),
            _decision(direction_family="bullish", rejected_at_stage=None, rejection_reason_code=None),
            _decision(direction_family="bullish", rejected_at_stage=None, rejection_reason_code=None),
            _decision(direction_family="sideways", rejected_at_stage=None, rejection_reason_code=None),
        ]
    )

    assert summary["starvation_flag"] is True
    assert summary["starvation_reason"] == "family_dominance"
    assert float(summary["top_family_share"]) >= 0.75


def test_starvation_summary_groups_by_family_session_regime(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.40, raising=False)

    summary = summarize_starvation_by_group(
        [
            _decision(strategy_family="continuation", session_mode="MIDDAY", strategy_regime_mode="TRENDING", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
            _decision(strategy_family="continuation", session_mode="MIDDAY", strategy_regime_mode="TRENDING", rejected_at_stage=None, rejection_reason_code=None, selected_for_execution=True, selector_outcome="EXECUTE_TOP"),
            _decision(strategy_family="mean_reversion", direction_family="sideways", session_mode="OPENING", strategy_regime_mode="SIDEWAYS", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
        ]
    )

    assert "continuation" in summary["strategy_family"]
    assert "MIDDAY" in summary["session_mode"]
    assert "TRENDING" in summary["strategy_regime_mode"]
    assert "continuation|MIDDAY" in summary["strategy_family__session_mode"]
    assert "continuation|TRENDING" in summary["strategy_family__strategy_regime_mode"]


def test_starvation_summary_flags_collapsed_survival(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.60, raising=False)

    summary = summarize_starvation_by_group(
        [
            _decision(strategy_family="continuation", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
            _decision(strategy_family="continuation", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
            _decision(strategy_family="continuation", rejected_at_stage=None, rejection_reason_code=None, selected_for_execution=True, selector_outcome="EXECUTE_TOP"),
        ]
    )

    group = summary["strategy_family"]["continuation"]
    assert group["starvation_flag"] is True
    assert group["starvation_reason"] == "survival_rate_below_floor"


def test_survival_expectancy_summary_distinguishes_filtering_from_edge_improvement(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR", 0.50, raising=False)
    decisions = [
        _decision(strategy_family="continuation", direction_family="bullish", session_mode="MIDDAY", strategy_regime_mode="TRENDING", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
        _decision(strategy_family="continuation", direction_family="bullish", session_mode="MIDDAY", strategy_regime_mode="TRENDING", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
        _decision(strategy_family="continuation", direction_family="bullish", session_mode="MIDDAY", strategy_regime_mode="TRENDING", rejected_at_stage=None, rejection_reason_code=None, selected_for_execution=True, selector_outcome="EXECUTE_TOP"),
        _decision(strategy_family="mean_reversion", direction_family="sideways", session_mode="MIDDAY", strategy_regime_mode="SIDEWAYS", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
        _decision(strategy_family="mean_reversion", direction_family="sideways", session_mode="MIDDAY", strategy_regime_mode="SIDEWAYS", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
    ]
    outcomes = [
        {
            "strategy_family": "continuation",
            "direction_family": "bullish",
            "strategy_regime_mode": "TRENDING",
            "session_mode": "MIDDAY",
            "simulated_pnl": 12.0,
            "mfe": 16.0,
            "mae": -4.0,
            "realized_r_multiple": 1.2,
            "rejection_saved_loss": True,
            "rejection_missed_win": False,
        },
        {
            "strategy_family": "mean_reversion",
            "direction_family": "sideways",
            "strategy_regime_mode": "SIDEWAYS",
            "session_mode": "MIDDAY",
            "simulated_pnl": -3.0,
            "mfe": 2.0,
            "mae": -7.0,
            "realized_r_multiple": -0.6,
            "rejection_saved_loss": False,
            "rejection_missed_win": True,
        },
    ]

    summary = summarize_survival_vs_expectancy(decisions, outcomes)
    improved = summary["groups"]["continuation|bullish|TRENDING|MIDDAY"]
    masked = summary["groups"]["mean_reversion|sideways|SIDEWAYS|MIDDAY"]

    assert improved["edge_improved_under_strict_filter"] is True
    assert masked["filtering_without_edge_improvement"] is True


def test_survival_expectancy_marks_edge_improved_when_r_improves(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.50, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EDGE_IMPROVEMENT_MIN_R_DELTA", 0.10, raising=False)

    summary = summarize_survival_vs_expectancy(
        [
            _decision(strategy_family="continuation", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
            _decision(strategy_family="continuation", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
        ],
        [
            {
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "simulated_pnl": 8.0,
                "mfe": 10.0,
                "mae": -2.0,
                "realized_r_multiple": 0.35,
                "rejection_saved_loss": True,
                "rejection_missed_win": False,
            }
        ],
    )

    group = summary["groups"]["continuation|bullish|TRENDING|MIDDAY"]
    assert group["edge_improved_flag"] is True
    assert group["filtering_without_edge_flag"] is False


def test_survival_expectancy_marks_filtering_without_edge_when_r_does_not_improve(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", 0.50, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_EDGE_IMPROVEMENT_MIN_R_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FILTERING_WITHOUT_EDGE_WARN", True, raising=False)

    summary = summarize_survival_vs_expectancy(
        [
            _decision(strategy_family="mean_reversion", direction_family="sideways", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
            _decision(strategy_family="mean_reversion", direction_family="sideways", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
        ],
        [
            {
                "strategy_family": "mean_reversion",
                "direction_family": "sideways",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "simulated_pnl": 0.0,
                "mfe": 2.0,
                "mae": -4.0,
                "realized_r_multiple": 0.0,
                "rejection_saved_loss": False,
                "rejection_missed_win": True,
            }
        ],
    )

    group = summary["groups"]["mean_reversion|sideways|TRENDING|MIDDAY"]
    assert group["edge_improved_flag"] is False
    assert group["filtering_without_edge_flag"] is True


def test_survival_expectancy_summary_surfaces_missed_win_vs_saved_loss():
    summary = summarize_survival_vs_expectancy(
        [
            _decision(
                strategy_family="continuation",
                direction_family="bullish",
                rejected_at_stage="selector",
                rejection_reason_code="below_survival_floor",
            )
        ],
        [
            {
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "simulated_pnl": 4.0,
                "mfe": 8.0,
                "mae": -2.0,
                "realized_r_multiple": 0.4,
                "rejection_saved_loss": True,
                "rejection_missed_win": False,
            },
            {
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "simulated_pnl": 6.0,
                "mfe": 9.0,
                "mae": -3.0,
                "realized_r_multiple": 0.6,
                "rejection_saved_loss": False,
                "rejection_missed_win": True,
            },
        ],
    )
    group = summary["groups"]["continuation|bullish|TRENDING|MIDDAY"]

    assert group["rejection_saved_loss_rate"] == 0.5
    assert group["rejection_missed_win_rate"] == 0.5
    assert group["saved_loss_rate"] == 0.5
    assert group["missed_win_rate"] == 0.5


def test_top_damaging_gates_returns_ranked_negative_impact_filters():
    summary = summarize_top_damaging_gates(
        [
            _decision(strategy_family="continuation", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
            _decision(strategy_family="continuation", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
            _decision(strategy_family="mean_reversion", direction_family="sideways", rejected_at_stage="risk_budget", rejection_reason_code="risk_budget_reject"),
        ],
        [
            {
                "strategy_family": "continuation",
                "direction_family": "bullish",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "simulated_pnl": 9.0,
                "mfe": 11.0,
                "mae": -2.0,
                "realized_r_multiple": 0.9,
                "rejection_saved_loss": False,
                "rejection_missed_win": True,
            },
            {
                "strategy_family": "mean_reversion",
                "direction_family": "sideways",
                "strategy_regime_mode": "TRENDING",
                "session_mode": "MIDDAY",
                "simulated_pnl": -5.0,
                "mfe": 1.0,
                "mae": -6.0,
                "realized_r_multiple": -0.8,
                "rejection_saved_loss": True,
                "rejection_missed_win": False,
            },
        ],
        top_n=2,
    )

    assert summary["gates"][0]["gate_key"] == "selector|continuation"
    assert float(summary["gates"][0]["impact_score"]) > 0.0


def test_threshold_behavior_reports_selector_and_warning_rates(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_AUDIT_NO_EXECUTABLE_RATE_WARN", 0.50, raising=False)
    summary = summarize_threshold_behavior(
        [
            _decision(selector_outcome="NO_EXECUTABLE_OPPORTUNITY", rejected_at_stage="selector", rejection_reason_code="low_selection_probability"),
            _decision(selector_outcome="NO_EXECUTABLE_OPPORTUNITY", rejected_at_stage="selector", rejection_reason_code="below_survival_floor"),
        ]
    )

    assert summary["selector_outcome_counts"]["NO_EXECUTABLE_OPPORTUNITY"] == 1
    assert summary["warning_engine_too_timid"] is True
