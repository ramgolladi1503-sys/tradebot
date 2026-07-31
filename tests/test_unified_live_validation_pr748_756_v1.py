from pathlib import Path
import json
import subprocess
import sys

import pytest

from core.unified_live_validation_pr748_756.campaign_contract import (
    ENABLE_ENV,
    PR_HEADS,
    build_campaign_identity,
    build_composition_manifest,
    campaign_enabled,
    enrich_row,
    reject_presession_live_run_id,
    require_campaign_enabled,
)
from core.unified_live_validation_pr748_756.launcher import (
    build_child_environment,
    launch_runtime_child,
)
from core.unified_live_validation_pr748_756.recorder import AppendOnlyRecorder
from core.unified_live_validation_pr748_756.seal import seal_evidence_root
from core.unified_live_validation_pr748_756.validators import (
    scan_preoutcome_fields,
    validate_jsonl_file,
)
from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.hard_downgrade_engine import HardDowngradeDecision
from core.market_event_graph_breadth_producer import (
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.opportunity_scoring import score_opportunities
from core.unified_live_validation_pr748_756 import runtime_observer
import main as tradebot_main


def test_campaign_is_disabled_by_default_and_requires_explicit_env():
    assert campaign_enabled({}) is False
    with pytest.raises(RuntimeError):
        require_campaign_enabled({})
    assert campaign_enabled({ENABLE_ENV: "true"}) is True


def test_manifest_preserves_pr_heads_and_read_only_authority():
    manifest = build_composition_manifest(origin_main_sha="abc", integrated_commit_sha="def")

    assert manifest["read_only"] is True
    assert manifest["is_order_action"] is False
    assert manifest["broker_api_called"] is False
    assert manifest["allowed_for_live_execution"] is False
    assert manifest["selected_live_constituent_producer"] == (
        "pr_749_constituent_source_feeds_pr_748_validator_exporter"
    )
    assert manifest["pr_heads"]["750"] == PR_HEADS[750]
    assert "composition_manifest_sha256" in manifest


def test_enrich_row_overwrites_unsafe_inputs_fail_closed(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="f" * 64,
        nonce="test",
    )
    row = enrich_row(
        identity,
        {
            "symbol": "NIFTY",
            "read_only": False,
            "is_order_action": True,
            "broker_api_called": True,
            "allowed_for_live_execution": True,
        },
        pr_number=748,
    )

    assert row["run_id"] == "unified-pr748-756-20260731-ffffffffffff-presession-test"
    assert row["read_only"] is True
    assert row["is_order_action"] is False
    assert row["broker_api_called"] is False
    assert row["allowed_for_live_execution"] is False


def test_recorder_appends_jsonl_and_validator_checks_safety(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="1" * 64,
        nonce="n",
    )
    recorder = AppendOnlyRecorder(identity)
    path = recorder.append(
        "live/heartbeat.jsonl",
        {"source_timestamp": "2026-07-31T09:16:00+05:30", "symbol": "NIFTY"},
        pr_number=750,
    )

    result = validate_jsonl_file(path, expected_run_id=identity.run_id)
    assert result["pass"] is True
    assert result["rows"] == 1
    assert result["unsafe_rows"] == 0


def test_preoutcome_field_scan_blocks_future_authority_terms():
    bad = scan_preoutcome_fields({"next_minute_entry": 1, "safe_feature": 2, "pnl_label": 3})

    assert bad == ["next_minute_entry", "pnl_label"]


def test_seal_writes_manifest_hash_and_prevents_reseal(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (root / "live.jsonl").write_text("{}\n", encoding="utf-8")

    manifest = seal_evidence_root(root)

    assert manifest["artifact_count"] == 1
    assert (root / "SHA256SUMS").exists()
    assert (root / "SEALED").exists()
    with pytest.raises(RuntimeError):
        seal_evidence_root(root)


def test_presession_run_id_cannot_launch_live(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="2" * 64,
        nonce="blocked",
    )

    with pytest.raises(ValueError):
        reject_presession_live_run_id(identity.run_id)


def test_enabled_live_identity_sets_exact_child_environment(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="3" * 64,
        nonce="env",
        live=True,
    )

    env = build_child_environment(identity, base_env={})

    assert "presession" not in identity.run_id
    assert env["UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE"] == "true"
    assert env["UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID"] == identity.run_id
    assert env["UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT"] == identity.evidence_root
    assert env["UNIFIED_LIVE_VALIDATION_PR748_756_COMPOSITION_SHA"] == "3" * 64
    assert env["TRADEBOT_READ_ONLY"] == "true"
    assert env["MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE"] == "true"
    assert env["MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH"] == (
        "runtime/reference/market_event_graph/"
        "nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
    )


def test_process_level_smoke_launches_one_child_records_and_seals(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="4" * 64,
        nonce="smoke",
        live=True,
    )

    result = launch_runtime_child(
        identity,
        [sys.executable, "-m", "core.unified_live_validation_pr748_756.launcher"],
        cwd=Path.cwd(),
        timeout_sec=10,
    )

    root = Path(result.evidence_root)
    assert result.exit_code == 0
    assert result.child_pid is not None
    assert result.sealed is True
    assert result.artifact_manifest_sha256
    assert (root / "SEALED").exists()
    process_identity = json.loads((root / "live" / "process_identity.json").read_text(encoding="utf-8"))
    assert process_identity["child_pid"] == result.child_pid
    heartbeat = validate_jsonl_file(root / "live" / "heartbeat.jsonl", expected_run_id=identity.run_id)
    feed_sample = validate_jsonl_file(
        root / "live" / "feed_truth_samples.jsonl",
        expected_run_id=identity.run_id,
    )
    assert heartbeat["pass"] is True
    assert heartbeat["rows"] >= 1
    assert feed_sample["pass"] is True
    assert feed_sample["rows"] == 1


def test_governed_wrapper_reports_runtime_wired_without_launching_market_process(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_unified_live_validation_pr748_756_v1.py",
            "--origin-main-sha",
            "abc",
            "--nonce",
            "dry",
            "--evidence-root",
            str(tmp_path),
        ],
        cwd=Path.cwd(),
        env={"PYTHONPATH": ".", "UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE": "true"},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "READY_FOR_LIVE_START"
    assert payload["campaign_runtime_wired"] is True
    assert payload["recorder_instantiated"] is False
    assert payload["single_runtime_process_proven"] is False
    assert payload["presession_run_id_rejected"] is True


def _returns(negative_count: int, total: int = 50, value: float = 0.001):
    return [-value] * negative_count + [value] * (total - negative_count)


def _bar(ts_epoch: float, source_bar_end_epoch: float, *, negative_count: int, index_ret1: float):
    return {
        "ts_epoch": ts_epoch,
        "source_bar_end_epoch": source_bar_end_epoch,
        "session_date": "2026-07-31",
        "index_ret1": index_ret1,
        "constituent_ret1": _returns(negative_count),
        "completed": True,
    }


def test_dry_integration_real_paths_record_and_seal(tmp_path, monkeypatch):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="5" * 64,
        nonce="dry",
        live=True,
    )
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE", "true")
    monkeypatch.setenv("TRADEBOT_READ_ONLY", "true")
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID", identity.run_id)
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT", identity.evidence_root)
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_COMPOSITION_SHA", identity.composition_manifest_sha)

    observer = runtime_observer.init_from_env()
    observer.write_process_identity({"exec_mode": "SIM_DRY_INTEGRATION"})
    metadata = {
        **frozen_threshold_metadata(),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-07-31"),
        "completed_constituent_bars": [
            _bar(100.0, 90.0, negative_count=40, index_ret1=-0.001),
            _bar(160.0, 150.0, negative_count=25, index_ret1=-0.004),
            _bar(220.0, 210.0, negative_count=5, index_ret1=0.001),
            _bar(280.0, 270.0, negative_count=8, index_ret1=0.001),
        ],
    }
    ctx = StrategyContext(
        symbol="NIFTY",
        ts_epoch=280.0,
        spot_ltp=22550.0,
        option_ce_ltp=120.0,
        option_pe_ltp=90.0,
        ce_premium_change=14.0,
        pe_premium_change=-2.0,
        ce_spread_pct=0.8,
        pe_spread_pct=0.9,
        ce_depth=1200.0,
        pe_depth=1000.0,
        option_ltp_age_sec=0.4,
        quote_source="live_option_tick",
        fallback_used=False,
        metadata=metadata,
    )
    regime = MovementRegimeResult(schema_version=1, primary_regime="TREND_UP", scores={"TREND_UP": 0.8})
    report = build_candidate_pool_report(ctx, regime, include_no_trade_candidate=False)
    candidate = report.candidates[0]
    decision = HardDowngradeDecision(
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        movement_type=candidate.movement_type,
        original_bucket="ADVISORY_CANDIDATE",
        downgraded_bucket="ADVISORY_CANDIDATE",
        downgraded=False,
        executable_candidate=False,
        downgrade_reasons=(),
        blockers=(),
        hard_blockers=(),
        warnings=(),
        safety_flags=(),
        evidence_flags=(),
    )
    score_opportunities([candidate], [decision])
    accounting = runtime_observer.shutdown_current(seal=True, state="DRY_INTEGRATION_COMPLETE")

    root = Path(identity.evidence_root)
    assert accounting["sealed"] is True
    for relative in (
        "live/process_identity.json",
        "live/heartbeat.jsonl",
        "live/constituent_completed_bars.jsonl",
        "live/market_event_graph_intervals.jsonl",
        "live/market_event_graph_states.jsonl",
        "live/regime_outputs.jsonl",
        "live/regime_policy_decisions.jsonl",
        "live/candidate_lineage.jsonl",
        "live/ranking_decisions.jsonl",
        "live/execution_eligibility.jsonl",
        "live/research_preoutcome_states.jsonl",
        "postmarket/evidence_accounting.json",
        "SEALED",
    ):
        assert (root / relative).exists(), relative
    assert validate_jsonl_file(root / "live/market_event_graph_intervals.jsonl", expected_run_id=identity.run_id)["pass"]


def test_main_unified_campaign_shutdown_helper_is_idempotent(monkeypatch, capsys):
    calls = []

    def fake_shutdown_current(*, seal: bool, state: str):
        calls.append({"seal": seal, "state": state})
        if len(calls) == 1:
            return {"sealed": True}
        return None

    monkeypatch.setattr(tradebot_main._unified_live_campaign, "shutdown_current", fake_shutdown_current)

    tradebot_main._shutdown_unified_live_campaign()
    tradebot_main._shutdown_unified_live_campaign(state="STOPPED")

    assert calls == [{"seal": True, "state": "PROCESS_EXIT"}, {"seal": True, "state": "STOPPED"}]
    assert "[UNIFIED_LIVE_VALIDATION] shutdown sealed=True" in capsys.readouterr().out
