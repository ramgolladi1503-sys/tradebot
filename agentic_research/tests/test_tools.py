import json
from pathlib import Path

from agentic_research.tools import TradeBotReadOnlyTools


def make_sidecar(tmp_path: Path) -> Path:
    sidecar = tmp_path / "agentic_research"
    config = sidecar / "config"
    config.mkdir(parents=True)
    source = tmp_path / "strategies" / "movement"
    source.mkdir(parents=True)
    (source / "trend_pullback.py").write_text("STRATEGY_ID='trend_pullback_v1'\n")
    (config / "strategy_spec.yaml").write_text(json.dumps({"strategy_id": "trend_pullback_v1", "source_path": "strategies/movement/trend_pullback.py"}))
    (config / "dataset_requirements.yaml").write_text(json.dumps({
        "required_top_level_fields": ["timestamp", "context", "regime", "forward_return_bps", "split"],
        "required_context_fields": ["symbol", "spot_ltp", "vwap", "completed_bar_history"],
        "required_regime_fields": ["primary_regime", "scores"],
        "allowed_splits": ["train", "validation", "holdout"],
        "require_unique_timestamp": True,
        "require_monotonic_timestamp": True,
    }))
    (config / "frozen_parameters.json").write_text(json.dumps({"round_trip_cost_bps": 2.0}))
    (config / "certification_gates.yaml").write_text(json.dumps({}))
    return sidecar


def test_contract_tool_reads_only_and_hashes_source(tmp_path):
    sidecar = make_sidecar(tmp_path)
    tools = TradeBotReadOnlyTools(tmp_path, sidecar_root=sidecar)
    result = tools.get_strategy_contract("r1", "trend_pullback_v1")
    assert result.status == "SUCCESS"
    assert result.payload["read_only"] is True
    assert result.payload["source_hash"]


def test_dataset_validator_fails_closed(tmp_path):
    sidecar = make_sidecar(tmp_path)
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(json.dumps({"timestamp": "2026-01-01", "split": "train"}) + "\n")
    tools = TradeBotReadOnlyTools(tmp_path, sidecar_root=sidecar)
    result = tools.validate_dataset("r2", str(dataset))
    assert result.status == "REJECTED"
    assert any(item.startswith("missing_field:context") for item in result.blockers)
