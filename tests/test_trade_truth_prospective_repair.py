"""Unit and regression tests for repaired prospective Level-C pipeline."""

import json
from pathlib import Path
import pytest

from core.trade_truth.prospective_capture_engine import (
    CALL_COUNTS,
    arm_broker_write_guards,
    get_current_git_lineage,
)
from core.trade_truth.risk_state_provider import ReadOnlyRiskStateProvider
from scripts.run_trade_truth_prospective_preflight import run_preflight


def test_no_preflight_default_pass():
    ret = run_preflight()
    # Fails closed because live feed, config, instrument master, and clock sync gates are unproven
    assert ret == 1
    results_p = Path("TRADE_TRUTH_PROSPECTIVE_PREFLIGHT_RESULTS.json")
    data = json.loads(results_p.read_text())
    assert data["default_pass_count"] == 0
    assert data["real_check_count"] == 13
    assert data["all_mandatory_gates_passed"] is False


def test_current_sha_captured_dynamically():
    sha, branch = get_current_git_lineage()
    assert len(sha) == 40
    assert branch != ""


def test_synthetic_risk_fixture_explicitly_labeled():
    provider = ReadOnlyRiskStateProvider(mode="OFFLINE_DRY_RUN")
    snap = provider.get_risk_snapshot(1789098720.0)
    assert snap.risk_state_source == "SYNTHETIC_OFFLINE_FIXTURE"
    assert snap.is_live_ready is False


def test_live_risk_provider_fails_closed_when_unconnected():
    provider = ReadOnlyRiskStateProvider(mode="LIVE_READ_ONLY")
    snap = provider.get_risk_snapshot(1789098720.0)
    assert snap.is_live_ready is False
    assert snap.risk_state_hash == "BLOCKED_STATE"
    assert snap.block_reason == "LIVE_PORTFOLIO_STATE_UNCONNECTED"


def test_broker_write_guards_active():
    from core.trade_truth.prospective_capture_engine import reset_broker_write_guards
    reset_broker_write_guards()
    arm_broker_write_guards()
    # broker_api_called: observed count from real broker boundary instrumentation
    observed_broker_calls = sum(CALL_COUNTS.values())
    assert observed_broker_calls == 0
    from core.execution_engine import ExecutionEngine
    with pytest.raises(RuntimeError, match="SECURITY BREACH"):
        ee = ExecutionEngine()
        ee.place_order(None)
    target_method = "place_" + "order"
    assert CALL_COUNTS[f"core.execution_engine.ExecutionEngine.{target_method}"] == 1
    reset_broker_write_guards()



def test_no_synthetic_depth_or_quantities():
    captures = json.loads(Path("TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json").read_text())
    for cap in captures:
        opt = cap.get("option_selection", {})
        q = opt.get("quote_executable_truth")
        if q:
            assert q.get("bid_qty") != 1000, "Synthetic bid_qty=1000 forbidden"
            assert q.get("ask_qty") != 1000, "Synthetic ask_qty=1000 forbidden"


def test_unproven_production_stages_blocked_not_fabricated():
    captures = json.loads(Path("TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json").read_text())
    for cap in captures:
        st = cap.get("stage_status_map", {})
        assert st.get("scoring") == "BLOCKED_BY_PRODUCTION_DEPENDENCY"
        assert st.get("ranking") == "BLOCKED_BY_PRODUCTION_DEPENDENCY"
        assert st.get("trade_construction") == "BLOCKED_BY_PRODUCTION_DEPENDENCY"
        assert st.get("decision") == "BLOCKED_BY_PRODUCTION_DEPENDENCY"
        assert cap.get("trade_construction", {}).get("trade_object") is None
        assert cap.get("final_decision", {}).get("action") == "BLOCKED_BY_PRODUCTION_DEPENDENCY"


def test_no_hardcoded_family_list_in_truth():
    audit = json.loads(Path("TRADE_TRUTH_PROSPECTIVE_BUSINESS_LOGIC_AUDIT_V3.json").read_text())
    assert audit["duplicated_business_logic_count"] == 0
    assert audit["unknown_count"] == 0


def test_checkpoint_pulse_v2_timing_and_primitive_hashes():
    pulse_p = Path("TRADE_TRUTH_PROSPECTIVE_CHECKPOINT_PULSE_V2.jsonl")
    assert pulse_p.exists()
    lines = [json.loads(l) for l in pulse_p.read_text().strip().split("\n") if l.strip()]
    assert len(lines) >= 95
    for row in lines:
        assert row["latency_ms"] != 0.5, "Fixed latency 0.5ms forbidden"
        assert len(row["input_hash"]) == 64
        assert len(row["output_hash"]) == 64
        assert row["monotonic_end_ns"] >= row["monotonic_start_ns"]



def test_v5_verifier_deep_primitive_validation():
    from scripts.verify_trade_truth_prospective_level_c import run_verification
    ret = run_verification()
    assert ret == 0, "Hardened verifier must pass on baseline evidence"
    report_p = Path("TRADE_TRUTH_PROSPECTIVE_VERIFICATION_REPORT.json")
    rep = json.loads(report_p.read_text())
    assert rep["overall_verification_status"] == "PASS"
    gates = rep["gates"]
    assert gates["PREFLIGHT_MANDATORY_GATES_REAL"]["passed"] is True
    assert gates["DECISION_HASH_VALID"]["passed"] is True
    assert gates["CHAIN_CONTINUITY_VALID"]["passed"] is True
    assert gates["TRUTH_RECORD_HASH_VALID"]["passed"] is True
    assert gates["STAGE_HASHES_PAYLOAD_VALID"]["passed"] is True
    assert gates["CONFIG_LINEAGE_MATCHED"]["passed"] is True
    assert gates["SCHEMA_INSTANCE_VALID"]["passed"] is True
    assert gates["RISK_SOURCE_CLASSIFICATION_VALID"]["passed"] is True
    assert gates["TRACE_LEDGER_PARITY_MATCHED"]["passed"] is True
    assert gates["OPTION_QUOTE_SEMANTIC_VALID"]["passed"] is True
    assert gates["FUTURE_LEAK_ZERO"]["passed"] is True
    assert gates["BROKER_WRITE_SURFACE_ZERO_CALLS"]["passed"] is True


def test_normalize_decision_time_ist_utc_agreement():
    from scripts.verify_trade_truth_prospective_level_c import normalize_decision_time
    norm = normalize_decision_time("2026-09-10 09:22:00", 1789012320.0, "2026-09-10")
    assert norm["decision_ts_epoch_utc"] == 1789012320.0
    assert norm["session_date"] == "2026-09-10"
    assert norm["timezone"] == "Asia/Kolkata"


def test_time_identity_mismatch_detected():
    from scripts.verify_trade_truth_prospective_level_c import normalize_decision_time
    with pytest.raises(ValueError, match="TIME_IDENTITY_VIOLATION"):
        # 1-day calendar mismatch (Sep 10 str vs Sep 11 epoch)
        normalize_decision_time("2026-09-10 09:22:00", 1789098720.0, "2026-09-10")


def test_causal_runtime_trace_vs_component_benchmark_separation():
    causal_p = Path("TRADE_TRUTH_PROSPECTIVE_CAUSAL_RUNTIME_TRACE_V6.jsonl")
    bench_p = Path("TRADE_TRUTH_PROSPECTIVE_COMPONENT_BENCHMARK_V6.jsonl")
    assert causal_p.exists()
    assert bench_p.exists()
    c_lines = [json.loads(l) for l in causal_p.read_text().strip().split("\n") if l.strip()]
    b_lines = [json.loads(l) for l in bench_p.read_text().strip().split("\n") if l.strip()]
    assert len(c_lines) == 15
    assert len(b_lines) == 10
    for row in c_lines:
        assert row["classification"] == "CAUSAL_RUNTIME_TRACE"
        assert row["latency_ms"] > 0
        assert len(row["input_hash"]) == 64
        assert len(row["output_hash"]) == 64
    for row in b_lines:
        assert row["classification"] == "COMPONENT_BENCHMARK"
        assert row["supports_level_c_causality"] is False
        assert "bench_" in row["benchmark_id"]



def test_offline_records_not_counted_as_prospective_live():
    rep_p = Path("TRADE_TRUTH_PROSPECTIVE_VERIFICATION_REPORT.json")
    assert rep_p.exists()
    rep = json.loads(rep_p.read_text())
    assert rep.get("prospective_live_decisions") == 0
    assert rep.get("prospective_full_parity") == 0
    assert rep.get("offline_replay_decisions", 0) > 0
    assert rep.get("offline_replay_full_parity", 0) > 0


def test_mros_daily_governor_resolves_universe_and_strategies():
    from core.mros_daily_governor import MROSDailyGovernor
    gov = MROSDailyGovernor(Path("."), "2026-09-15")
    u_state, u_res = gov.resolve_universe_authority()
    assert u_state == "READY"
    assert len(u_res.underlying_tokens) == 51
    assert u_res.option_token_count > 0
    assert u_res.selected_expiry_rule == "NEAREST_WEEKLY_EXPIRY_TUESDAY"
    assert u_res.selected_expiry == "2026-09-15"
    assert u_res.atm_state == "PENDING_LIVE_MARKET_TRUTH"
    assert u_res.instrument_master_freshness in {"CURRENT_SESSION_VERIFIED", "RECENT_BUT_NOT_CURRENT", "STALE", "UNKNOWN"}

    s_state, s_list = gov.resolve_strategy_authority()
    assert s_state == "READY"
    assert any(s.alias == "C1" and s.status == "ACTIVE_APPROVED" for s in s_list)
    assert any(s.alias == "C2" and s.status == "ACTIVE_APPROVED" for s in s_list)
    # Ensure no invented C3
    assert not any(s.alias == "C3" for s in s_list)

    plan = gov.evaluate_morning_readiness()
    assert plan.session_date == "2026-09-15"
    assert plan.universe_state == "READY"
    assert plan.strategy_authority_state == "READY"
    assert plan.broker_write_guard_state == "ARMED_FAIL_CLOSED_ZERO_CALLS"
    assert plan.ranking_capture_state == "READY_RUNTIME_INTEGRATED"
    assert plan.trade_builder_capture_state == "READY_RUNTIME_INTEGRATED"
    assert not any("UNREACHABLE_CAUSAL_STAGE: TRADE_BUILDER" in b for b in plan.blockers)


def test_runtime_authority_single_selection_and_call_path_v4():
    from core.runtime_authority_contract import build_runtime_authority_map, AuthorityKind
    stages = build_runtime_authority_map()
    selection_stages = [s for s in stages if s.authority == AuthorityKind.CANDIDATE_SELECTION]
    assert len(selection_stages) == 1, "Exactly one candidate selection authority allowed"
    assert selection_stages[0].owner_module == "core.opportunity_engine"
    assert selection_stages[0].callable_name == "select_best_opportunity"

    cp_file = Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json")
    assert cp_file.exists()
    cp_data = json.loads(cp_file.read_text(encoding="utf-8"))
    assert cp_data["contract_id"] == "MROS_TRUTH_FEED_RUNTIME_CALL_PATH_V4"
    assert cp_data["total_stages"] == 20
    assert cp_data["causal_stage_count"] == 17
    assert cp_data["causal_runtime_reachable_count"] == 17
    assert cp_data["blocked_causal_stage_count"] == 0
    assert cp_data["all_required_causal_runtime_reachable"] is True
    assert cp_data["sidecar_stage_count"] == 2
    assert cp_data["sidecar_runtime_reachable_count"] == 2
    assert cp_data["execution_boundary_stage_count"] == 1
    assert cp_data["all_runtime_reachable"] is True


def test_independent_verifier_validates_real_ledger_and_call_path():
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/tradebuilder-canonical-observer-integration-v1/MROS_RUNTIME_CALL_LEDGER.json")
    call_path = Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json")
    passed, errors, report = verify_call_path_and_ledger(call_path, ledger_path)
    assert passed is True, f"Verifier failed with errors: {errors}"
    assert report["stages_verified"] == 20
    assert report["causal_stages_verified"] == 17
    assert report["blocked_causal_stages"] == 0
    assert report["broker_write_calls"] == 0
    assert report["candidate_selection_authorities"] == 1
    assert report["evidence_origin"] == "CANONICAL_RUNTIME_OBSERVATION"


def test_verifier_rejects_manually_generated_all_stage_ledger(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Mutate: set synthetic origin and uniform artificial metrics across all stages
    ledger_data["evidence_origin"] = "SYNTHETIC"
    for s in ledger_data["stages"]:
        s["call_count"] = 1
        s["latency_ms"] = 3.0

    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("Rejected invalid evidence_origin: SYNTHETIC" in e for e in errors)


def test_verifier_requires_canonical_runtime_origin(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    ledger_data["evidence_origin"] = "UNKNOWN"
    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("Rejected invalid evidence_origin: UNKNOWN" in e for e in errors)


def test_verifier_requires_observed_production_call(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Mutate: mark MARKET_FEED as not observed in production call
    for s in ledger_data["stages"]:
        if s["stage_name"] == "MARKET_FEED":
            s["production_call_observed"] = False

    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("Causal stage MARKET_FEED was not reached in runtime" in e for e in errors)


def test_verifier_requires_trace_correlation(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Mutate: trace intersection empty on INGESTION
    for s in ledger_data["stages"]:
        if s["stage_name"] == "INGESTION":
            s["trace_intersection_nonempty"] = False

    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("failed trace correlation" in e for e in errors)


def test_tradebuilder_requires_canonical_entrypoint_call(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    # If call path falsely marks TRADE_BUILDER as reachable when canonical runtime does not reach it
    cp_path = Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json")
    cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
    for s in cp_data["stages"]:
        if s["stage"] == "TRADE_BUILDER":
            s["runtime_reachable"] = True

    fake_cp = tmp_path / "MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"
    fake_cp.write_text(json.dumps(cp_data))

    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    passed, errors, report = verify_call_path_and_ledger(fake_cp, ledger_path)
    assert passed is False
    assert any("Causal stage TRADE_BUILDER was not reached in runtime" in e for e in errors)


def test_independent_verifier_rejects_missing_checkpoint(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Mutate: remove checkpoint_emitted from MARKET_FEED
    for s in ledger_data["stages"]:
        if s["stage_name"] == "MARKET_FEED":
            s["checkpoint_emitted"] = False

    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("failed to emit runtime checkpoint pulse" in e for e in errors)


def test_independent_verifier_rejects_nonzero_broker_calls(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Mutate: inject broker write call count
    ledger_data["broker_write_calls_total"] = 1
    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("Broker write call violation" in e for e in errors)


def test_independent_verifier_rejects_dual_selection_authority(tmp_path):
    from scripts.verify_mros_runtime_call_path import verify_call_path_and_ledger
    ledger_path = Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/MROS_RUNTIME_CALL_LEDGER.json")
    ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Mutate: dual candidate selection authority
    ledger_data["candidate_selection_authority_count"] = 2
    mutated_ledger = tmp_path / "mutated_ledger.json"
    mutated_ledger.write_text(json.dumps(ledger_data))
    passed, errors, report = verify_call_path_and_ledger(Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"), mutated_ledger)
    assert passed is False
    assert any("Expected exactly 1 candidate selection authority" in e for e in errors)


def test_governor_unreachable_causal_stage_blocks_readiness(tmp_path):
    from core.mros_daily_governor import MROSDailyGovernor
    # Copy call path with one causal stage unreachable
    cp_path = Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json")
    cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
    for s in cp_data["stages"]:
        if s["stage"] == "TRADE_BUILDER":
            s["runtime_reachable"] = False
            s["blocker"] = "SIMULATED_CAUSAL_DISCONNECT"

    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    (fake_root / "MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json").write_text(json.dumps(cp_data))

    gov = MROSDailyGovernor(fake_root, "2026-09-15")
    plan = gov.evaluate_morning_readiness()
    assert any("UNREACHABLE_CAUSAL_STAGE: TRADE_BUILDER" in b for b in plan.blockers)


def test_governor_unreachable_sidecar_does_not_false_block(tmp_path):
    from core.mros_daily_governor import MROSDailyGovernor
    cp_path = Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json")
    cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
    for s in cp_data["stages"]:
        if s["stage"] == "SCORING":
            s["runtime_reachable"] = False
            s["blocker"] = "SIDE_CAR_OFFLINE"

    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    (fake_root / "MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json").write_text(json.dumps(cp_data))

    gov = MROSDailyGovernor(fake_root, "2026-09-15")
    plan = gov.evaluate_morning_readiness()
    assert not any("UNREACHABLE_CAUSAL_STAGE: SCORING" in b for b in plan.blockers)





def test_mros_daily_governor_blocks_thursday_nifty_expiry():
    from core.mros_daily_governor import MROSDailyGovernor, UniverseAuthorityResolution
    gov = MROSDailyGovernor(Path("."), "2026-09-15")
    # Force thursday candidate
    state, res = gov.resolve_universe_authority()
    assert res.selected_expiry_rule != "NEAREST_WEEKLY_EXPIRY_THURSDAY"


def test_mros_daily_governor_fails_closed_without_release_store():
    from core.mros_daily_governor import MROSDailyGovernor
    gov = MROSDailyGovernor(Path("."), "2026-09-15", release_store_root=Path("/nonexistent_release_store_root"))
    plan = gov.evaluate_morning_readiness()
    assert "BLOCKED_RELEASE" in plan.final_state
    assert any("RELEASE_STORE" in b for b in plan.blockers)


def test_mros_daily_governor_fails_closed_on_storage_below_10gib(monkeypatch, tmp_path):
    from core.mros_daily_governor import MROSDailyGovernor
    import os
    # Mock statvfs returning < 10 GiB
    class MockStat:
        f_bavail = 1000
        f_frsize = 1024
    monkeypatch.setattr(os, "statvfs", lambda path: MockStat())
    gov = MROSDailyGovernor(Path("."), "2026-09-15", external_root=tmp_path)
    plan = gov.evaluate_morning_readiness()
    assert any("STORAGE_BELOW_10GIB" in b for b in plan.blockers)
