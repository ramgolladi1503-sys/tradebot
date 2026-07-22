from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.strategy_pipeline.adapter_runtime import PipelineAdapterRuntime
from core.strategy_pipeline.outcomes_stage_adapter import OutcomesStageError, run_outcomes_stage
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.result_manifest import sha256_file, write_engine_result_manifest


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _truth_manifest(tmp_path: Path, run_id: str = "pipeline12345") -> Path:
    root = tmp_path / "runtime" / "strategy_pipeline" / "s1" / run_id
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / "truth.stage.json"
    artifact.write_text(
        json.dumps(
            {
                "pipeline_run_id": run_id,
                "strategy_id": "s1",
                "decision": "IMPLEMENTATION_VERIFIED",
            }
        ),
        encoding="utf-8",
    )
    result = EngineResult(
        engine=EngineType.TRUTH,
        state=PipelineState.SUCCESS,
        run_id=run_id,
        strategy_id="s1",
        artifacts_generated=[str(artifact.resolve())],
        output_hashes={str(artifact.resolve()): sha256_file(artifact)},
        verdict="IMPLEMENTATION_VERIFIED",
        verified=True,
        exit_code=0,
    )
    manifest = root / "truth.result.json"
    write_engine_result_manifest(manifest, result)
    return manifest


def _cost_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_as_of": "fixture-2026-07-22",
                "lot_size": 65,
                "brokerage_per_order": 20.0,
                "stt_sell_rate": 0.001,
                "exchange_turnover_rate": 0.0005,
                "sebi_turnover_rate": 0.000001,
                "stamp_buy_rate": 0.00003,
                "gst_rate": 0.18,
                "entry_slippage_bps": 10.0,
                "exit_slippage_bps": 10.0,
                "max_entry_delay_seconds": 60.0,
                "default_time_stop_seconds": 180.0,
            }
        ),
        encoding="utf-8",
    )


def _runtime(
    monkeypatch,
    tmp_path: Path,
    truth: Path,
    candidate: Path,
    trace: Path,
    cost: Path,
    run_id: str = "pipeline12345",
) -> PipelineAdapterRuntime:
    result_manifest = (
        tmp_path / "runtime" / "strategy_pipeline" / "s1" / run_id / "outcomes.result.json"
    )
    inputs = [truth, candidate, trace, cost]
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", run_id)
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", "OUTCOMES")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps({str(path.resolve()): sha256_file(path) for path in inputs}),
    )
    return PipelineAdapterRuntime.from_environment(EngineType.OUTCOMES, repo_root=tmp_path)


def _base_files(tmp_path: Path):
    truth = _truth_manifest(tmp_path)
    candidate = tmp_path / "candidate.jsonl"
    trace = tmp_path / "trace.jsonl"
    cost = tmp_path / "cost.json"
    _cost_config(cost)
    _write_jsonl(
        candidate,
        [
            {
                "candidate_id": "c1",
                "strategy_id": "s1",
                "signal_timestamp": 100.0,
                "execution_eligible_at": 105.0,
                "instrument_id": "NIFTY_CE",
                "side": "LONG",
                "stop_price": 95.0,
                "target_price": 110.0,
                "execution_ok": True,
                "completed_bar": True,
                "time_stop_seconds": 180.0,
            }
        ],
    )
    _write_jsonl(
        trace,
        [
            {"timestamp": 100.0, "instrument_id": "NIFTY_CE", "bid": 99.0, "ask": 101.0},
            {"timestamp": 105.0, "instrument_id": "NIFTY_CE", "bid": 100.0, "ask": 102.0},
            {"timestamp": 120.0, "instrument_id": "NIFTY_CE", "bid": 111.0, "ask": 112.0},
        ],
    )
    return truth, candidate, trace, cost


def test_outcomes_uses_next_eligible_ask_and_exit_bid(monkeypatch, tmp_path):
    truth, candidate, trace, cost = _base_files(tmp_path)
    runtime = _runtime(monkeypatch, tmp_path, truth, candidate, trace, cost)

    result = run_outcomes_stage(
        runtime,
        candidate_file=candidate,
        trace_file=trace,
        cost_config_file=cost,
    )

    payload = json.loads(Path(result.artifacts_generated[0]).read_text(encoding="utf-8"))
    record = payload["records"][0]
    assert result.state == PipelineState.SUCCESS
    assert result.verdict == "CAUSAL_OUTCOME_EVIDENCE_VERIFIED"
    assert record["entry_quote_timestamp"] == 105.0
    assert record["entry_ask"] == 102.0
    assert record["exit_bid"] == 111.0
    assert record["exit_reason"] == "TARGET"
    assert record["causal_checks"]["signal_strictly_before_entry"] is True
    assert record["costs"]["spread_cost_separately_added"] == 0.0
    assert record["costs"]["slippage_cost_separately_added"] == 0.0


def test_outcomes_rejects_same_timestamp_execution_eligibility(monkeypatch, tmp_path):
    truth, candidate, trace, cost = _base_files(tmp_path)
    _write_jsonl(
        candidate,
        [
            {
                "candidate_id": "c1",
                "strategy_id": "s1",
                "signal_timestamp": 100.0,
                "execution_eligible_at": 100.0,
                "instrument_id": "NIFTY_CE",
                "side": "LONG",
                "stop_price": 95.0,
                "target_price": 110.0,
                "execution_ok": True,
                "completed_bar": True,
            }
        ],
    )
    runtime = _runtime(monkeypatch, tmp_path, truth, candidate, trace, cost)

    with pytest.raises(OutcomesStageError, match="execution_not_after_signal"):
        run_outcomes_stage(runtime, candidate_file=candidate, trace_file=trace, cost_config_file=cost)


def test_outcomes_requires_bid_and_ask(monkeypatch, tmp_path):
    truth, candidate, trace, cost = _base_files(tmp_path)
    _write_jsonl(
        trace,
        [{"timestamp": 105.0, "instrument_id": "NIFTY_CE", "ltp": 102.0}],
    )
    runtime = _runtime(monkeypatch, tmp_path, truth, candidate, trace, cost)

    with pytest.raises(OutcomesStageError, match="trace_missing_fields"):
        run_outcomes_stage(runtime, candidate_file=candidate, trace_file=trace, cost_config_file=cost)


def test_outcomes_blocks_when_no_complete_trace(monkeypatch, tmp_path):
    truth, candidate, trace, cost = _base_files(tmp_path)
    _write_jsonl(
        trace,
        [{"timestamp": 500.0, "instrument_id": "NIFTY_CE", "bid": 100.0, "ask": 101.0}],
    )
    runtime = _runtime(monkeypatch, tmp_path, truth, candidate, trace, cost)

    result = run_outcomes_stage(runtime, candidate_file=candidate, trace_file=trace, cost_config_file=cost)
    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "OUTCOME_EVIDENCE_INSUFFICIENT"
    assert len(result.artifacts_generated) == 1


def test_outcomes_rejects_extra_undeclared_input(monkeypatch, tmp_path):
    truth, candidate, trace, cost = _base_files(tmp_path)
    extra = tmp_path / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")
    result_manifest = (
        tmp_path / "runtime" / "strategy_pipeline" / "s1" / "pipeline12345" / "outcomes.result.json"
    )
    inputs = [truth, candidate, trace, cost, extra]
    monkeypatch.setenv("EXECUTION_MODE", "RESEARCH")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RUN_ID", "pipeline12345")
    monkeypatch.setenv("TRADEBOT_PIPELINE_STRATEGY_ID", "s1")
    monkeypatch.setenv("TRADEBOT_PIPELINE_ENGINE", "OUTCOMES")
    monkeypatch.setenv("TRADEBOT_PIPELINE_RESULT_MANIFEST", str(result_manifest))
    monkeypatch.setenv(
        "TRADEBOT_PIPELINE_INPUT_HASHES_JSON",
        json.dumps({str(path.resolve()): sha256_file(path) for path in inputs}),
    )
    runtime = PipelineAdapterRuntime.from_environment(EngineType.OUTCOMES, repo_root=tmp_path)

    with pytest.raises(OutcomesStageError, match="requires_truth_manifest"):
        run_outcomes_stage(runtime, candidate_file=candidate, trace_file=trace, cost_config_file=cost)
