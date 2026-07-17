import json
from pathlib import Path

from agentic_research.portfolio_demo import run_portfolio_demo


def prepare_repo(root: Path):
    config = root / "agentic_research" / "config"
    config.mkdir(parents=True)
    source = root / "strategies" / "movement"
    source.mkdir(parents=True)
    (source / "trend_pullback.py").write_text("STRATEGY_ID='trend_pullback_v1'\n")
    (config / "strategy_spec.yaml").write_text(json.dumps({"strategy_id": "trend_pullback_v1", "source_path": "strategies/movement/trend_pullback.py"}))
    (config / "dataset_requirements.yaml").write_text("{}")
    (config / "frozen_parameters.json").write_text("{}")
    (config / "certification_gates.yaml").write_text(json.dumps({"promotion_ceiling": "READY_FOR_OPTION_REPLAY"}))
    report_dir = root / "runtime" / "backtests" / "all_strategy_20260629"
    report_dir.mkdir(parents=True)
    (report_dir / "all_strategy_report_20260629.json").write_text(json.dumps({
        "date": "2026-06-29",
        "verdict": "DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST",
        "entry_rule": "current_candle_close",
        "inspection": {"volume_quality": "ZERO_VOLUME"},
        "invalid_volume_or_vwap_assumption": ["movement.trend_pullback_v1"],
    }))


def test_one_command_demo_produces_rejection_and_eval_evidence(tmp_path):
    prepare_repo(tmp_path)
    summary = run_portfolio_demo(tmp_path, "demo")
    assert summary["paused_for_approval"] is True
    assert summary["final_status"] == "COMPLETED"
    assert summary["final_verdict"] == "REJECTED_DATA_INELIGIBLE"
    assert summary["eval_total_cases"] >= 64
    assert summary["eval_unsafe_actions"] == 0
    assert "propose_next_hypotheses" in summary["tools_executed"]
