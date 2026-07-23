from core.strategy_pipeline.pipeline_models import PipelineState
from core.strategy_pipeline.truth_oracle import (
    TruthOracleClassification,
    evaluate_truth_oracle,
)
from core.strategy_pipeline.truth_stage_adapter import run_truth_stage
from tests.strategy_pipeline.test_truth_stage_adapter import (
    _registry_fixture,
    _truth_runtime,
)


def test_verified_auditor_with_blocker_still_blocks(monkeypatch, tmp_path):
    _, registry_manifest = _registry_fixture(tmp_path)
    runtime = _truth_runtime(monkeypatch, tmp_path, registry_manifest)

    result = run_truth_stage(
        runtime,
        auditor=lambda *_: (
            "IMPLEMENTATION_VERIFIED",
            {"verdict": "IMPLEMENTATION_VERIFIED"},
            ["indicator:VWAP:DECLARED_BUT_NOT_FOUND"],
        ),
    )

    assert result.state == PipelineState.BLOCKED
    assert "indicator:VWAP:DECLARED_BUT_NOT_FOUND" in result.blockers


def test_independent_oracle_blocks_direct_order_call():
    source = '''def opening_range_entry(session_time, range_high, close):
    if session_time and close > range_high:
        return broker.place_order()
'''
    result = evaluate_truth_oracle(source, "ORB opening range breakout")
    assert result.classification == TruthOracleClassification.BLOCK
    assert result.checks["no_direct_broker_coupling"] is False
