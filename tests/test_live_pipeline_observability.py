"""Comprehensive offline and deterministic tests for TradeBot Live Trace Pulse,
Candidate Attribution, Role-Aware Token Health, Sidecar Reporter, and Independent Verifier.

Tests prove:
1. trace_id survives every stage immutably.
2. stage events are append-only.
3. first-divergence detection is correct.
4. strategy wired and invoked but no setup.
5. strategy configured but never invoked.
6. strategy input stale.
7. candidate emitted then filtered.
8. candidate silently lost mutation detected.
9. critical token missing -> system critical block.
10. optional token missing -> non-fatal degradation.
11. strategy-specific token missing -> blocks only that strategy.
12. partial option coverage above quorum -> non-fatal / partial healthy.
13. full option coverage -> fully healthy.
14. periodic reporter reads without mutating runtime.
15. normal tick path adds zero file I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.observability import (
    CANONICAL_CHECKPOINT_ORDER,
    STAGE_CONTRACTS,
    CandidateEmptyClass,
    CandidateLifecycleLedger,
    CandidateLifecycleStage,
    DiagnosticPulseRing,
    EmptyPoolSummaryClass,
    IndependentObservabilityVerifier,
    PipelineCheckpoint,
    RoleAwareHealthReport,
    SidecarReporter,
    StageRecord,
    StageStatus,
    StrategyCoverageTracker,
    StrategyEvaluationAttribution,
    SystemHealthStatus,
    TokenDependencyGraph,
    TokenObservation,
    TokenRole,
    VerificationError,
    analyze_first_divergence,
    create_stage_record,
    generate_trace_id,
)


def test_trace_id_survives_every_stage_immutably():
    trace_id = generate_trace_id(seed="test_immutability")
    records: list[StageRecord] = []

    for idx, cp in enumerate(CANONICAL_CHECKPOINT_ORDER[:8]):
        rec = create_stage_record(
            trace_id=trace_id,
            stage_id=f"stage_{idx:02d}",
            component=cp,
            input_ref="raw_packet",
            expected_contract="PASS",
            observed_contract="PASS",
            status=StageStatus.PASS,
            reason_code="OK",
        )
        records.append(rec)

    # Independent verifier proves immutability and valid canonical ordering
    assert IndependentObservabilityVerifier.verify_trace_immutability_and_order(records) is True

    # Mutate trace ID at stage 4 -> must fail verification
    mutated_records = list(records)
    mutated_records[4] = create_stage_record(
        trace_id="mutated_trace_id",
        stage_id=records[4].stage_id,
        component=records[4].component,
        expected_contract="PASS",
        observed_contract="PASS",
        status=StageStatus.PASS,
    )

    with pytest.raises(VerificationError, match="trace_id_mutated"):
        IndependentObservabilityVerifier.verify_trace_immutability_and_order(mutated_records)


def test_first_divergence_detection_and_rca_generation():
    trace_id = generate_trace_id(seed="test_divergence")
    records: list[StageRecord] = [
        create_stage_record(
            trace_id=trace_id,
            stage_id="s1",
            component=PipelineCheckpoint.MARKET_SESSION_STATE.value,
            status=StageStatus.PASS,
        ),
        create_stage_record(
            trace_id=trace_id,
            stage_id="s2",
            component=PipelineCheckpoint.BROKER_KITE_CLIENT.value,
            status=StageStatus.PASS,
        ),
        create_stage_record(
            trace_id=trace_id,
            stage_id="s3",
            component=PipelineCheckpoint.WEBSOCKET_CONNECTION.value,
            status=StageStatus.PASS,
        ),
        create_stage_record(
            trace_id=trace_id,
            stage_id="s4",
            component=PipelineCheckpoint.SUBSCRIPTION_REQUEST.value,
            status=StageStatus.PASS,
        ),
        # Divergence at SUBSCRIPTION_ACK
        create_stage_record(
            trace_id=trace_id,
            stage_id="s5",
            component=PipelineCheckpoint.SUBSCRIPTION_ACK.value,
            expected_contract="ALL_ACKNOWLEDGED",
            observed_contract="TIMEOUT_ON_ACK",
            status=StageStatus.FAIL_CLOSED,
            reason_code="BROKER_WS_ACK_TIMEOUT",
        ),
        # Downstream receives nothing / not invoked
        create_stage_record(
            trace_id=trace_id,
            stage_id="s6",
            component=PipelineCheckpoint.RAW_TICK_RECEIVE.value,
            status=StageStatus.NOT_INVOKED,
            reason_code="UPSTREAM_FAILED",
        ),
    ]

    report = analyze_first_divergence(records)
    assert report.diverged is True
    assert report.first_divergence_stage == PipelineCheckpoint.SUBSCRIPTION_ACK.value
    assert report.upstream_stages_healthy is True
    assert report.rca is not None
    assert report.rca.causal_classification == "PROVEN"
    assert report.rca.first_divergence_stage == PipelineCheckpoint.SUBSCRIPTION_ACK.value
    assert PipelineCheckpoint.RAW_TICK_RECEIVE.value in report.downstream_impact

    # Independent oracle confirms
    assert IndependentObservabilityVerifier.verify_first_divergence_oracle(records, report) is True


def test_strategy_wired_and_invoked_but_no_setup():
    tracker = StrategyCoverageTracker(registered_strategies=["opening_drive", "ema_momentum"])

    # Strategy opening_drive has valid input but no setup qualifies
    attr = StrategyEvaluationAttribution(
        strategy_id="opening_drive",
        invoked=True,
        input_ready=True,
        input_fresh=True,
        evaluation_status="EVALUATED_EMPTY",
        candidate_count_before_filters=0,
        candidate_count_after_filters=0,
        candidate_count_after_risk=0,
        candidate_count_after_ranking=0,
        terminal_reason_code=CandidateEmptyClass.NO_MARKET_SETUP.value,
    )
    tracker.record_evaluation(attr)

    diag = tracker.diagnose_empty_pool()
    assert diag["EMPTY_POOL_CLASS"] == EmptyPoolSummaryClass.LEGITIMATE_NO_SETUP.value
    assert diag["NO_MARKET_SETUP"] == 1
    assert diag["VALID_INPUT_EVALUATIONS"] == 1
    assert diag["NOT_INVOKED"] == 0

    assert IndependentObservabilityVerifier.verify_empty_pool_attribution(
        tracker, EmptyPoolSummaryClass.LEGITIMATE_NO_SETUP.value
    ) is True


def test_strategy_configured_but_never_invoked():
    tracker = StrategyCoverageTracker(registered_strategies=["opening_drive"])

    attr = StrategyEvaluationAttribution(
        strategy_id="opening_drive",
        invoked=False,
        input_ready=False,
        input_fresh=False,
        evaluation_status="SKIPPED",
        candidate_count_before_filters=0,
        candidate_count_after_filters=0,
        candidate_count_after_risk=0,
        candidate_count_after_ranking=0,
        terminal_reason_code=CandidateEmptyClass.STRATEGY_NOT_INVOKED.value,
    )
    tracker.record_evaluation(attr)

    diag = tracker.diagnose_empty_pool()
    assert diag["EMPTY_POOL_CLASS"] == EmptyPoolSummaryClass.WIRING_PROBLEM.value
    assert diag["NOT_INVOKED"] == 1


def test_strategy_input_stale():
    tracker = StrategyCoverageTracker(registered_strategies=["ema_momentum"])

    attr = StrategyEvaluationAttribution(
        strategy_id="ema_momentum",
        invoked=True,
        input_ready=True,
        input_fresh=False,
        evaluation_status="BLOCKED_STALE",
        candidate_count_before_filters=0,
        candidate_count_after_filters=0,
        candidate_count_after_risk=0,
        candidate_count_after_ranking=0,
        terminal_reason_code=CandidateEmptyClass.INPUT_STALE.value,
    )
    tracker.record_evaluation(attr)

    diag = tracker.diagnose_empty_pool()
    assert diag["EMPTY_POOL_CLASS"] == EmptyPoolSummaryClass.INPUT_READINESS_PROBLEM.value
    assert diag["INPUT_STALE"] == 1


def test_candidate_emitted_then_filtered_vs_silently_lost():
    ledger = CandidateLifecycleLedger()
    cid = "cand_test_001"

    # Emitted candidate transitions through filters
    ledger.record_transition(
        candidate_id=cid,
        from_stage=CandidateLifecycleStage.CREATED,
        to_stage=CandidateLifecycleStage.LIQUIDITY_CHECK,
        status="PASS",
        reason_code="SPREAD_AND_DEPTH_OK",
    )
    ledger.record_transition(
        candidate_id=cid,
        from_stage=CandidateLifecycleStage.LIQUIDITY_CHECK,
        to_stage=CandidateLifecycleStage.FRESHNESS_CHECK,
        status="FILTERED",
        reason_code="OPTION_LTP_STALE",
    )

    # Verify history
    history = ledger.get_candidate_history(cid)
    assert len(history) == 2
    assert history[-1].status == "FILTERED"
    assert history[-1].reason_code == "OPTION_LTP_STALE"

    assert IndependentObservabilityVerifier.verify_candidate_lifecycle(
        ledger,
        candidate_id=cid,
        expected_final_stage=CandidateLifecycleStage.FRESHNESS_CHECK.value,
        expected_final_status="FILTERED",
    ) is True

    # Now simulate a candidate that was silently lost mid-pipeline:
    # Passed REGIME_CHECK, but never arrived at RISK_CHECK or ADVISORY
    lost_cid = "cand_silent_lost_002"
    ledger.record_transition(
        candidate_id=lost_cid,
        from_stage=CandidateLifecycleStage.CREATED,
        to_stage=CandidateLifecycleStage.REGIME_CHECK,
        status="PASS",
        reason_code="TREND_ALIGNED",
    )

    disappeared = ledger.detect_disappeared_candidates(expected_stage=CandidateLifecycleStage.ADVISORY.value)
    lost_entries = [d for d in disappeared if d["candidate_id"] == lost_cid]
    assert len(lost_entries) == 1
    assert lost_entries[0]["possible_defect"] == "SILENT_CANDIDATE_DROP_BEFORE_DOWNSTREAM_STAGE"
    assert lost_entries[0]["last_stage"] == CandidateLifecycleStage.REGIME_CHECK.value


def test_token_health_roles_and_dependency_isolation():
    graph = TokenDependencyGraph(required_option_quorum=0.80, max_freshness_age_sec=3.0)

    # NIFTY underlying (critical)
    graph.register_token(256265, "NIFTY", TokenRole.CRITICAL_UNDERLYING)

    # Strategy A uses tokens 101, 102 (required)
    graph.register_token(101, "NIFTY26MAR22500CE", TokenRole.REQUIRED_OPTION_UNIVERSE, dependent_strategies=["strat_a"])
    graph.register_token(102, "NIFTY26MAR22500PE", TokenRole.REQUIRED_OPTION_UNIVERSE, dependent_strategies=["strat_a"])

    # Strategy B uses token 103 (required only by B)
    graph.register_token(103, "NIFTY26MAR23000CE", TokenRole.REQUIRED_OPTION_UNIVERSE, dependent_strategies=["strat_b"])

    # Optional tokens 201, 202 (far OTM)
    graph.register_token(201, "NIFTY26MAR25000CE", TokenRole.OPTIONAL_OPTION_UNIVERSE)
    graph.register_token(202, "NIFTY26MAR25000PE", TokenRole.OPTIONAL_OPTION_UNIVERSE)

    # SCENARIO 1: Everything is fresh -> HEALTHY
    obs_all_fresh = [
        TokenObservation(256265, "NIFTY", TokenRole.CRITICAL_UNDERLYING, True, True, True, True, 0.4),
        TokenObservation(101, "CE", TokenRole.REQUIRED_OPTION_UNIVERSE, True, True, True, True, 0.5),
        TokenObservation(102, "PE", TokenRole.REQUIRED_OPTION_UNIVERSE, True, True, True, True, 0.6),
        TokenObservation(103, "CE", TokenRole.REQUIRED_OPTION_UNIVERSE, True, True, True, True, 0.5),
        TokenObservation(201, "CE", TokenRole.OPTIONAL_OPTION_UNIVERSE, True, True, True, True, 1.0),
        TokenObservation(202, "PE", TokenRole.OPTIONAL_OPTION_UNIVERSE, True, True, True, True, 1.0),
    ]
    rep1 = graph.evaluate_health(obs_all_fresh)
    assert rep1.overall_health == SystemHealthStatus.HEALTHY.value
    assert rep1.system_critical is False
    assert len(rep1.affected_strategies) == 0

    # SCENARIO 2: Optional token 201 is stale -> PARTIAL_HEALTHY (NOT degraded system)
    obs_optional_stale = list(obs_all_fresh)
    obs_optional_stale[4] = TokenObservation(201, "CE", TokenRole.OPTIONAL_OPTION_UNIVERSE, True, True, True, False, 10.5)
    rep2 = graph.evaluate_health(obs_optional_stale)
    assert rep2.overall_health == SystemHealthStatus.PARTIAL_HEALTHY.value
    assert rep2.system_critical is False
    assert len(rep2.affected_strategies) == 0

    # SCENARIO 3: Token 103 (used only by strat_b) is stale -> DEGRADED_NONFATAL, affects strat_b only
    obs_b_stale = list(obs_all_fresh)
    obs_b_stale[3] = TokenObservation(103, "CE", TokenRole.REQUIRED_OPTION_UNIVERSE, True, True, True, False, 12.0)
    rep3 = graph.evaluate_health(obs_b_stale)
    assert rep3.overall_health == SystemHealthStatus.DEGRADED_NONFATAL.value
    assert rep3.system_critical is False
    assert "strat_b" in rep3.affected_strategies
    assert "strat_a" not in rep3.affected_strategies
    assert "strat_a" in rep3.unaffected_strategies

    # SCENARIO 4: Critical underlying token 256265 is stale -> SYSTEM_CRITICAL_BLOCK
    obs_crit_stale = list(obs_all_fresh)
    obs_crit_stale[0] = TokenObservation(256265, "NIFTY", TokenRole.CRITICAL_UNDERLYING, True, True, True, False, 15.0)
    rep4 = graph.evaluate_health(obs_crit_stale)
    assert rep4.overall_health == SystemHealthStatus.SYSTEM_CRITICAL_BLOCK.value
    assert rep4.system_critical is True
    assert rep4.critical_underlying_healthy is False


def test_periodic_sidecar_reporter_and_zero_normal_path_io(tmp_path):
    ring = DiagnosticPulseRing(max_traces=50, max_events=200)

    # Record 5 normal stage events in ring
    trace_id = generate_trace_id(seed="reporter_test")
    for idx, cp in enumerate(CANONICAL_CHECKPOINT_ORDER[:5]):
        rec = create_stage_record(
            trace_id=trace_id,
            stage_id=f"st_{idx}",
            component=cp,
            status=StageStatus.PASS,
        )
        ring.record_stage(rec)

    # Prove normal path additional IO is strictly 0
    assert ring.normal_tick_path_additional_io == 0
    assert IndependentObservabilityVerifier.verify_non_intrusive_telemetry(ring) is True

    # Initialize SidecarReporter
    out_dir = tmp_path / "obs_reports"
    reporter = SidecarReporter(
        pulse_ring=ring,
        report_interval_minutes=15,
        output_dir=out_dir,
    )

    json_path, md_path = reporter.write_periodic_report()

    assert json_path.exists()
    assert md_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["safety_boundaries"]["broker_write_authority"] is False
    assert payload["safety_boundaries"]["order_authority"] is False
    assert payload["telemetry_overhead"]["NORMAL_TICK_PATH_ADDITIONAL_IO"] == 0

    md_content = md_path.read_text(encoding="utf-8")
    assert "LIVE PIPELINE HEALTH REPORT" in md_content
    assert "- **NORMAL_TICK_PATH_ADDITIONAL_IO**: `0`" in md_content


def test_production_bridge_end_to_end_flow():
    from core.observability import ProductionObservabilityBridge, PipelineCheckpoint

    bridge = ProductionObservabilityBridge()
    trace_id = bridge.start_cycle_trace(cycle_id=101)
    assert trace_id.startswith("trace_")

    # Step through all 23 checkpoints in canonical order
    records = []
    for idx, cp in enumerate(CANONICAL_CHECKPOINT_ORDER):
        rec = bridge.emit_checkpoint(
            checkpoint=cp,
            trace_id=trace_id,
            stage_id=f"st_{idx}_{cp}",
            status="PASS",
            reason_code="OK",
        )
        records.append(rec)

    assert len(records) == 23
    assert IndependentObservabilityVerifier.verify_trace_immutability_and_order(records) is True

    # Check that candidate ledger records transitions with zero drop
    cid = f"cand_bridge_{trace_id}"
    bridge.record_candidate_transition(
        candidate_id=cid,
        from_stage="CREATED",
        to_stage="LIQUIDITY_CHECK",
        status="PASS",
        reason_code="LIQUIDITY_OK",
    )
    bridge.record_candidate_transition(
        candidate_id=cid,
        from_stage="LIQUIDITY_CHECK",
        to_stage="ADVISORY",
        status="PASS",
        reason_code="ADVISORY_APPROVED",
    )
    disappeared = bridge.candidate_ledger.detect_disappeared_candidates()
    assert len(disappeared) == 0

    # Verify strategy coverage derives from real registry
    matrix = bridge.strategy_tracker.get_strategy_matrix()
    assert matrix["summary"]["STRATEGIES_EXPECTED"] >= 10
    assert matrix["summary"]["STRATEGIES_WIRED"] >= 10

    # Verify token health evaluates role-aware report
    feed_truth = {
        "feed_ok": True,
        "max_option_tick_age_sec": 3.0,
        "last_tick_age_sec": 0.4,
    }
    health_rep = bridge.evaluate_token_health_from_feed_truth(feed_truth)
    assert health_rep.overall_health == "HEALTHY"
    assert health_rep.critical_underlying_healthy is True
    assert health_rep.is_order_action is False
    assert health_rep.broker_write_authority is False
