from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.result_manifest import sha256_file, write_engine_result_manifest
from core.strategy_pipeline.statistics_stage_adapter import (
    StatisticsStageError,
    evaluate_statistics,
    run_statistics_stage,
)


def _signed_stage(root, *, engine, run_id, verdict, artifact_payload):
    run_root = root / "runtime" / "strategy_pipeline" / "s1" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    artifact = run_root / f"{engine.value.lower()}.stage.json"
    artifact.write_text(json.dumps(artifact_payload, sort_keys=True), encoding="utf-8")
    result = EngineResult(
        engine=engine,
        state=PipelineState.SUCCESS,
        run_id=run_id,
        strategy_id="s1",
        artifacts_generated=[str(artifact.resolve())],
        output_hashes={str(artifact.resolve()): sha256_file(artifact)},
        verdict=verdict,
        verified=True,
        exit_code=0,
    )
    manifest = run_root / f"{engine.value.lower()}.result.json"
    write_engine_result_manifest(manifest, result)
    return artifact, manifest


def _fixture(tmp_path: Path, run_id: str = "pipeline12345"):
    _, research_manifest = _signed_stage(
        tmp_path,
        engine=EngineType.RESEARCH,
        run_id=run_id,
        verdict="FROZEN_HYPOTHESIS_VERIFIED",
        artifact_payload={
            "pipeline_run_id": run_id,
            "strategy_id": "s1",
            "decision": "FROZEN_HYPOTHESIS_VERIFIED",
            "development_window": "2026-01-01/2026-01-31",
            "holdout_window": "2026-02-01/2026-02-28",
            "allowed_for_live_execution": False,
        },
    )
    _, registry_manifest = _signed_stage(
        tmp_path,
        engine=EngineType.REGISTRY,
        run_id=run_id,
        verdict="CANONICAL_STRATEGY_CONTRACT_VERIFIED",
        artifact_payload={
            "pipeline_run_id": run_id,
            "strategy_id": "s1",
            "decision": "CANONICAL_STRATEGY_CONTRACT_VERIFIED",
            "research_result_manifest": str(research_manifest.resolve()),
        },
    )
    _, truth_manifest = _signed_stage(
        tmp_path,
        engine=EngineType.TRUTH,
        run_id=run_id,
        verdict="IMPLEMENTATION_VERIFIED",
        artifact_payload={
            "pipeline_run_id": run_id,
            "strategy_id": "s1",
            "decision": "IMPLEMENTATION_VERIFIED",
            "registry_result_manifest": str(registry_manifest.resolve()),
        },
    )

    candidate = tmp_path / "candidate.jsonl"
    metadata_rows = []
    pnl_values = [10.0, 12.0, 9.0, -1.0, 11.0, 8.0, 7.0, -1.0, 9.0]
    for index, _ in enumerate(pnl_values):
        development = index < 6
        day = index + 1 if development else index - 5
        metadata_rows.append(
            {
                "candidate_id": f"c{index + 1}",
                "strategy_id": "s1",
                "sample_partition": "DEVELOPMENT" if development else "HOLDOUT",
                "session_date": f"2026-{'01' if development else '02'}-{day:02d}",
                "regime": "TREND",
            }
        )
    candidate.write_text(
        "".join(json.dumps(row) + "\n" for row in metadata_rows),
        encoding="utf-8",
    )
    outcome_rows = [
        {
            "candidate_id": f"c{index + 1}",
            "strategy_id": "s1",
            "status": "COMPLETE",
            "gross_pnl": pnl + 1.0,
            "net_pnl": pnl,
            "costs": {"total_cost": 1.0},
        }
        for index, pnl in enumerate(pnl_values)
    ]
    outcomes_artifact, outcomes_manifest = _signed_stage(
        tmp_path,
        engine=EngineType.OUTCOMES,
        run_id=run_id,
        verdict="CAUSAL_OUTCOME_EVIDENCE_VERIFIED",
        artifact_payload={
            "pipeline_run_id": run_id,
            "strategy_id": "s1",
            "decision": "CAUSAL_OUTCOME_EVIDENCE_VERIFIED",
            "truth_result_manifest": str(truth_manifest.resolve()),
            "candidate_file": str(candidate.resolve()),
            "candidate_file_sha256": sha256_file(candidate),
            "causal_contract": {
                "completed_bar_required": True,
                "execution_eligible_after_signal": True,
                "same_timestamp_signal_entry_forbidden": True,
                "ltp_fallback_forbidden": True,
                "spread_double_count_forbidden": True,
            },
            "records": outcome_rows,
        },
    )
    config = tmp_path / "validation.json"
    config_payload = {
        "schema_version": 1,
        "source_as_of": "fixture-2026-07-22",
        "min_total_sample": 9,
        "min_development_sample": 6,
        "min_holdout_sample": 3,
        "min_net_expectancy": 1.0,
        "min_profit_factor": 1.5,
        "max_drawdown_abs": 5.0,
        "bootstrap_iterations": 1000,
        "bootstrap_seed": 17,
        "bootstrap_confidence": 0.90,
        "min_bootstrap_lower_bound": 1.0,
        "null_iterations": 1000,
        "max_null_pvalue": 0.10,
        "wfa_folds": 3,
        "min_wfa_profitable_fold_ratio": 1.0,
        "cost_sensitivity_multipliers": [1.0, 1.5, 2.0],
        "min_worst_cost_expectancy": 0.5,
    }
    config.write_text(json.dumps(config_payload), encoding="utf-8")
    combined = [
        {
            **row,
            "total_cost": row["costs"]["total_cost"],
            **metadata_rows[index],
        }
        for index, row in enumerate(outcome_rows)
    ]
    return {
        "outcomes_artifact": outcomes_artifact,
        "outcomes_manifest": outcomes_manifest,
        "candidate": candidate,
        "config": config,
        "config_payload": config_payload,
        "records": combined,
    }


def _runtime(monkeypatch, tmp_path, outcomes, config):
    result_manifest = (
        tmp_path
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / "pipeline12345"
        / "statistics.result.json"
    )
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", "pipeline12345")
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", "STATISTICS")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps(
            {
                str(outcomes.resolve()): sha256_file(outcomes),
                str(config.resolve()): sha256_file(config),
            }
        ),
    )
    return PipelineAdapterRuntime.from_environment(
        EngineType.STATISTICS,
        repo_root=tmp_path,
    )


def test_evaluation_is_deterministic_and_all_gates_pass(tmp_path):
    fixture = _fixture(tmp_path)
    first = evaluate_statistics(fixture["records"], fixture["config_payload"])
    second = evaluate_statistics(fixture["records"], fixture["config_payload"])
    assert first == second
    assert all(first["gates"].values())
    assert first["sample_counts"] == {"total": 9, "development": 6, "holdout": 3}
    assert first["negative_controls"]["sign_randomization"]["pvalue"] <= 0.10


def test_statistics_stage_success(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    runtime = _runtime(
        monkeypatch,
        tmp_path,
        fixture["outcomes_manifest"],
        fixture["config"],
    )
    result = run_statistics_stage(runtime, validation_config_file=fixture["config"])
    payload = json.loads(Path(result.artifacts_generated[0]).read_text(encoding="utf-8"))
    assert result.state == PipelineState.SUCCESS
    assert result.verdict == "STATISTICAL_VALIDATION_VERIFIED"
    assert payload["evaluation"]["holdout"]["expectancy"] > 0
    assert payload["allowed_for_live_execution"] is False


def test_statistics_stage_blocks_when_threshold_fails(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    config = dict(fixture["config_payload"])
    config["min_holdout_sample"] = 99
    fixture["config"].write_text(json.dumps(config), encoding="utf-8")
    runtime = _runtime(monkeypatch, tmp_path, fixture["outcomes_manifest"], fixture["config"])
    result = run_statistics_stage(runtime, validation_config_file=fixture["config"])
    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "STATISTICAL_VALIDATION_FAILED"
    assert "minimum_holdout_sample" in result.blockers
    assert len(result.artifacts_generated) == 1


def test_statistics_rejects_holdout_outside_frozen_window(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    rows = [json.loads(line) for line in fixture["candidate"].read_text().splitlines()]
    rows[-1]["session_date"] = "2026-03-01"
    fixture["candidate"].write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    outcomes = json.loads(fixture["outcomes_artifact"].read_text())
    outcomes["candidate_file_sha256"] = sha256_file(fixture["candidate"])
    fixture["outcomes_artifact"].write_text(json.dumps(outcomes), encoding="utf-8")
    result = EngineResult(
        engine=EngineType.OUTCOMES,
        state=PipelineState.SUCCESS,
        run_id="pipeline12345",
        strategy_id="s1",
        artifacts_generated=[str(fixture["outcomes_artifact"].resolve())],
        output_hashes={
            str(fixture["outcomes_artifact"].resolve()): sha256_file(
                fixture["outcomes_artifact"]
            )
        },
        verdict="CAUSAL_OUTCOME_EVIDENCE_VERIFIED",
        verified=True,
        exit_code=0,
    )
    write_engine_result_manifest(fixture["outcomes_manifest"], result)
    runtime = _runtime(monkeypatch, tmp_path, fixture["outcomes_manifest"], fixture["config"])
    with pytest.raises(StatisticsStageError, match="holdout_date_outside_frozen_window"):
        run_statistics_stage(runtime, validation_config_file=fixture["config"])


def test_statistics_rejects_candidate_file_changed_after_outcomes(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    runtime = _runtime(monkeypatch, tmp_path, fixture["outcomes_manifest"], fixture["config"])
    fixture["candidate"].write_text(
        fixture["candidate"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(StatisticsStageError, match="candidate_file_changed_after_outcomes"):
        run_statistics_stage(runtime, validation_config_file=fixture["config"])
