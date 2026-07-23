from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.result_manifest import sha256_file, write_engine_result_manifest
from core.strategy_pipeline.truth_oracle import (
    TruthOracleClassification,
    evaluate_truth_oracle,
)
from core.strategy_pipeline.truth_stage_adapter import TruthStageError, run_truth_stage
from core.strategy_registry.strategy_contract import StrategyContract


def _jsonable_contract(contract: StrategyContract) -> dict[str, object]:
    payload = asdict(contract)
    payload["created_date"] = contract.created_date.isoformat()
    for field in (
        "implementation_status",
        "audit_status",
        "replay_status",
        "certification_status",
        "paper_validation_status",
        "production_status",
    ):
        payload[field] = getattr(contract, field).name
    return payload


def _contract() -> StrategyContract:
    return StrategyContract(
        strategy_id="s1",
        strategy_name="ORB Fixture",
        version="1.0.0",
        owner="research",
        created_date=date(2026, 7, 22),
        description="ORB opening range breakout",
        market_hypothesis="Opening range breakout continuation.",
        primary_market="NIFTY",
        supported_indices=["NIFTY"],
        supported_option_types=["CE", "PE"],
        entry_rules_summary="Enter after opening range breakout confirmation.",
        exit_rules_summary="Exit on stop target or time stop.",
        stop_logic_summary="Stop below opening range.",
        target_logic_summary="Target at fixed reward multiple.",
        time_stop="Exit after 30 minutes.",
        required_indicators=["OPENING_RANGE"],
        required_market_data=["OHLCV"],
        required_option_data=["BID_ASK"],
        required_sessions=["OPEN"],
        required_liquidity="Tight spread",
        allowed_regimes=["TREND"],
        forbidden_regimes=["HALTED"],
        required_confirmations=["COMPLETED_BAR"],
        known_limitations=["Fixture"],
        known_assumptions=["Deterministic data"],
    )


def _source() -> str:
    return '''def opening_range_entry(session_time, range_high, close, confirm):
    """Entry after opening range breakout confirmation."""
    if session_time and close > range_high and confirm:
        return "candidate"
    return None


def exit_rule(price, stop, target, elapsed_minutes):
    """Exit on stop target or time stop."""
    if price < stop or price > target or elapsed_minutes > 30:
        return True
    return False
'''


def _registry_fixture(
    tmp_path: Path,
    *,
    run_id: str = "pipeline12345",
) -> tuple[Path, Path]:
    implementation = tmp_path / "strategies" / "orb_fixture.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text(_source(), encoding="utf-8")
    contract_payload = _jsonable_contract(_contract())
    contract_hash = hashlib.sha256(
        json.dumps(
            contract_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    run_root = tmp_path / "runtime" / "strategy_pipeline" / "s1" / run_id
    run_root.mkdir(parents=True)
    artifact = run_root / "registry.stage.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "engine": "REGISTRY",
                "pipeline_run_id": run_id,
                "strategy_id": "s1",
                "decision": "CANONICAL_STRATEGY_CONTRACT_VERIFIED",
                "module_path": "strategies.orb_fixture",
                "implementation_file": str(implementation.resolve()),
                "implementation_file_sha256": sha256_file(implementation),
                "contract_sha256": contract_hash,
                "contract": contract_payload,
                "allowed_for_live_execution": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    result = EngineResult(
        engine=EngineType.REGISTRY,
        state=PipelineState.SUCCESS,
        run_id=run_id,
        strategy_id="s1",
        artifacts_generated=[str(artifact.resolve())],
        output_hashes={str(artifact.resolve()): sha256_file(artifact)},
        verdict="CANONICAL_STRATEGY_CONTRACT_VERIFIED",
        verified=True,
        exit_code=0,
    )
    manifest = run_root / "registry.result.json"
    write_engine_result_manifest(manifest, result)
    return implementation, manifest


def _truth_runtime(
    monkeypatch,
    tmp_path: Path,
    manifest: Path,
    *,
    run_id: str = "pipeline12345",
) -> PipelineAdapterRuntime:
    result_manifest = (
        tmp_path
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / run_id
        / "truth.result.json"
    )
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", run_id)
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", "TRUTH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps({str(manifest.resolve()): sha256_file(manifest)}),
    )
    return PipelineAdapterRuntime.from_environment(
        EngineType.TRUTH,
        repo_root=tmp_path,
    )


def test_independent_oracle_verifies_orb_structure():
    result = evaluate_truth_oracle(_source(), "ORB opening range breakout")
    assert result.classification == TruthOracleClassification.PASS
    assert result.checks["opening_window_reference"] is True
    assert result.checks["breakout_comparison"] is True


def test_independent_oracle_blocks_orb_without_window():
    result = evaluate_truth_oracle(
        "def entry(close, level):\n    return close > level\n",
        "ORB opening range breakout",
    )
    assert result.classification == TruthOracleClassification.BLOCK
    assert result.checks["opening_window_reference"] is False


def test_truth_stage_success_requires_auditor_and_oracle(monkeypatch, tmp_path):
    _, registry_manifest = _registry_fixture(tmp_path)
    runtime = _truth_runtime(monkeypatch, tmp_path, registry_manifest)

    def auditor(manifest, implementation):
        return (
            "IMPLEMENTATION_VERIFIED",
            {
                "verdict": "IMPLEMENTATION_VERIFIED",
                "file": str(implementation),
            },
            [],
        )

    result = run_truth_stage(runtime, auditor=auditor)
    payload = json.loads(
        Path(result.artifacts_generated[0]).read_text(encoding="utf-8")
    )
    assert result.state == PipelineState.SUCCESS
    assert result.verdict == "IMPLEMENTATION_VERIFIED"
    assert payload["independent_oracle"]["classification"] == "PASS"
    assert payload["allowed_for_live_execution"] is False


def test_truth_stage_mismatch_keeps_verified_diagnostic(monkeypatch, tmp_path):
    _, registry_manifest = _registry_fixture(tmp_path)
    runtime = _truth_runtime(monkeypatch, tmp_path, registry_manifest)

    def auditor(manifest, implementation):
        return (
            "IMPLEMENTATION_MISMATCH",
            {"verdict": "IMPLEMENTATION_MISMATCH"},
            ["rule:entry:CONFLICT"],
        )

    result = run_truth_stage(runtime, auditor=auditor)
    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "IMPLEMENTATION_NOT_VERIFIED"
    assert len(result.artifacts_generated) == 1
    artifact = Path(result.artifacts_generated[0])
    assert result.output_hashes[str(artifact.resolve())] == sha256_file(artifact)


def test_truth_stage_rejects_implementation_changed_after_registry(
    monkeypatch,
    tmp_path,
):
    implementation, registry_manifest = _registry_fixture(tmp_path)
    runtime = _truth_runtime(monkeypatch, tmp_path, registry_manifest)
    implementation.write_text(_source() + "\n# changed\n", encoding="utf-8")

    with pytest.raises(
        TruthStageError,
        match="implementation_changed_after_registry",
    ):
        run_truth_stage(
            runtime,
            auditor=lambda *_: ("IMPLEMENTATION_VERIFIED", {}, []),
        )


def test_truth_stage_rejects_unrelated_extra_input(monkeypatch, tmp_path):
    _, registry_manifest = _registry_fixture(tmp_path)
    extra = tmp_path / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")
    result_manifest = (
        tmp_path
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / "pipeline12345"
        / "truth.result.json"
    )
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", "pipeline12345")
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", "TRUTH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps(
            {
                str(registry_manifest.resolve()): sha256_file(registry_manifest),
                str(extra.resolve()): sha256_file(extra),
            }
        ),
    )
    runtime = PipelineAdapterRuntime.from_environment(
        EngineType.TRUTH,
        repo_root=tmp_path,
    )

    with pytest.raises(TruthStageError, match="exactly_one_registry"):
        run_truth_stage(
            runtime,
            auditor=lambda *_: ("IMPLEMENTATION_VERIFIED", {}, []),
        )
