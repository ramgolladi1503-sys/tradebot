from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest

from core.governed_strategy_research import GovernedResearchStore
from core.strategy_pipeline.adapter_runtime import (
    AdapterRuntimeError,
    PipelineAdapterRuntime,
)
from core.strategy_pipeline.pipeline_models import EngineType, PipelineState
from core.strategy_pipeline.registry_stage_adapter import (
    RegistryStageError,
    run_registry_stage,
)
from core.strategy_pipeline.research_stage_adapter import (
    ResearchStageError,
    run_research_stage,
)
from core.strategy_pipeline.result_manifest import sha256_file


def _hypothesis_payload() -> dict[str, object]:
    return {
        "thesis": "Opening imbalance may persist after a causal confirmation.",
        "market": "NIFTY",
        "timeframe": "5m",
        "data_universe": "development_fixture_v1",
        "development_window": "2024-01-01/2024-12-31",
        "holdout_window": "2025-01-01/2025-03-31",
        "signal_definition": "Completed-bar imbalance and continuation confirmation.",
        "entry_rule": "Enter on the next bar after confirmation.",
        "exit_rule": "Exit on stop, target, or time stop.",
        "cost_model": "Indian index-option fees plus spread and slippage.",
        "negative_controls": ["time_shuffle", "direction_flip"],
        "primary_metric": "net_expectancy_r",
        "rejection_criteria": "Reject non-positive holdout expectancy.",
    }


def _create_governed_run(root: Path) -> Path:
    run_dir = root / "runtime" / "governed_research" / "s1"
    store = GovernedResearchStore.initialize(
        run_dir,
        strategy_id="s1",
        title="Fixture research",
        objective="Verify pipeline research lineage",
    )
    store.freeze_hypothesis(_hypothesis_payload())
    return run_dir


def _set_runtime_environment(
    monkeypatch,
    root: Path,
    *,
    engine: EngineType,
    inputs: list[Path],
    run_id: str = "pipeline12345",
) -> PipelineAdapterRuntime:
    result_manifest = (
        root
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / run_id
        / f"{engine.value.lower()}.result.json"
    )
    hashes = {str(path.resolve()): sha256_file(path) for path in inputs}
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", run_id)
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", engine.value)
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps(hashes, sort_keys=True),
    )
    return PipelineAdapterRuntime.from_environment(engine, repo_root=root)


def _write_strategy_fixture(root: Path) -> Path:
    strategies = root / "strategies"
    strategies.mkdir(parents=True, exist_ok=True)
    (strategies / "__init__.py").write_text("", encoding="utf-8")
    implementation = strategies / "fixture_strategy.py"
    implementation.write_text(
        """from datetime import date
from core.strategy_registry.strategy_contract import StrategyContract

STRATEGY_CONTRACT = StrategyContract(
    strategy_id="s1",
    strategy_name="Fixture Strategy",
    version="1.0.0",
    owner="research",
    created_date=date(2026, 7, 22),
    description="Fixture contract for registry lineage testing.",
    market_hypothesis="Opening imbalance continuation.",
    primary_market="NIFTY",
    supported_indices=["NIFTY"],
    supported_option_types=["CE", "PE"],
    entry_rules_summary="Causal next-bar entry.",
    exit_rules_summary="Stop, target, or time exit.",
    stop_logic_summary="Frozen stop rule.",
    target_logic_summary="Frozen target rule.",
    time_stop="30 minutes",
    required_indicators=["VWAP"],
    required_market_data=["OHLCV"],
    required_option_data=["BID_ASK"],
    required_sessions=["OPEN"],
    required_liquidity="Tight spread",
    allowed_regimes=["TREND"],
    forbidden_regimes=["HALTED"],
    required_confirmations=["COMPLETED_BAR"],
    known_limitations=["Research fixture"],
    known_assumptions=["Deterministic data"],
)
""",
        encoding="utf-8",
    )
    return implementation


def test_adapter_runtime_rejects_forged_input_hash(monkeypatch, tmp_path):
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    result_manifest = (
        tmp_path
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / "pipeline12345"
        / "research.result.json"
    )
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", "pipeline12345")
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps({str(source.resolve()): "0" * 64}),
    )

    with pytest.raises(AdapterRuntimeError, match="pipeline_input_hash_mismatch"):
        PipelineAdapterRuntime.from_environment(EngineType.RESEARCH, repo_root=tmp_path)


def test_research_stage_writes_verified_signed_result(monkeypatch, tmp_path):
    governed = _create_governed_run(tmp_path)
    runtime = _set_runtime_environment(
        monkeypatch,
        tmp_path,
        engine=EngineType.RESEARCH,
        inputs=[governed / "manifest.json", governed / "hypothesis_frozen.json"],
    )

    result = run_research_stage(runtime, governed_run_dir=governed)

    artifact = Path(result.artifacts_generated[0])
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert result.state == PipelineState.SUCCESS
    assert result.verified is True
    assert result.verdict == "FROZEN_HYPOTHESIS_VERIFIED"
    assert payload["strategy_id"] == "s1"
    assert payload["outcomes_observed"] is False
    assert payload["allowed_for_live_execution"] is False
    assert runtime.result_manifest.is_file()


def test_research_stage_rejects_tampered_hypothesis(monkeypatch, tmp_path):
    governed = _create_governed_run(tmp_path)
    runtime = _set_runtime_environment(
        monkeypatch,
        tmp_path,
        engine=EngineType.RESEARCH,
        inputs=[governed / "manifest.json", governed / "hypothesis_frozen.json"],
    )
    hypothesis = governed / "hypothesis_frozen.json"
    payload = json.loads(hypothesis.read_text(encoding="utf-8"))
    payload["thesis"] = "tampered"
    hypothesis.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ResearchStageError, match="integrity_invalid"):
        run_research_stage(runtime, governed_run_dir=governed)


def test_research_stage_rejects_extra_undeclared_scope(monkeypatch, tmp_path):
    governed = _create_governed_run(tmp_path)
    extra = tmp_path / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")
    runtime = _set_runtime_environment(
        monkeypatch,
        tmp_path,
        engine=EngineType.RESEARCH,
        inputs=[
            governed / "manifest.json",
            governed / "hypothesis_frozen.json",
            extra,
        ],
    )

    with pytest.raises(ResearchStageError, match="inputs_must_be_exact"):
        run_research_stage(runtime, governed_run_dir=governed)


def test_registry_stage_binds_exact_contract_to_research(monkeypatch, tmp_path):
    governed = _create_governed_run(tmp_path)
    research_runtime = _set_runtime_environment(
        monkeypatch,
        tmp_path,
        engine=EngineType.RESEARCH,
        inputs=[governed / "manifest.json", governed / "hypothesis_frozen.json"],
    )
    research_result = run_research_stage(
        research_runtime,
        governed_run_dir=governed,
    )
    implementation = _write_strategy_fixture(tmp_path)

    package = types.ModuleType("strategies")
    package.__path__ = [str((tmp_path / "strategies").resolve())]
    monkeypatch.setitem(sys.modules, "strategies", package)
    registry_runtime = _set_runtime_environment(
        monkeypatch,
        tmp_path,
        engine=EngineType.REGISTRY,
        inputs=[implementation, Path(research_result.manifest_path)],
    )

    result = run_registry_stage(
        registry_runtime,
        implementation_file=implementation,
    )

    artifact = Path(result.artifacts_generated[0])
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert result.state == PipelineState.SUCCESS
    assert result.verdict == "CANONICAL_STRATEGY_CONTRACT_VERIFIED"
    assert payload["strategy_id"] == "s1"
    assert payload["implementation_file_sha256"] == sha256_file(implementation)
    assert payload["research_result_manifest_file_sha256"] == sha256_file(
        research_result.manifest_path
    )
    assert payload["allowed_for_live_execution"] is False


def test_registry_stage_rejects_unrelated_upstream(monkeypatch, tmp_path):
    implementation = _write_strategy_fixture(tmp_path)
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text("{}\n", encoding="utf-8")
    runtime = _set_runtime_environment(
        monkeypatch,
        tmp_path,
        engine=EngineType.REGISTRY,
        inputs=[implementation, unrelated],
    )

    with pytest.raises(RegistryStageError, match="upstream_must_be_research"):
        run_registry_stage(runtime, implementation_file=implementation)
