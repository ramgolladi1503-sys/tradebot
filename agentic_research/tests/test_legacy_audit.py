import json
from pathlib import Path

from agentic_research.tools import TradeBotReadOnlyTools


def setup_sidecar(tmp_path: Path):
    sidecar = tmp_path / "agentic_research"
    config = sidecar / "config"
    config.mkdir(parents=True)
    source = tmp_path / "strategies" / "movement"
    source.mkdir(parents=True)
    (source / "trend_pullback.py").write_text("x=1\n")
    (config / "strategy_spec.yaml").write_text(json.dumps({"strategy_id": "trend_pullback_v1", "source_path": "strategies/movement/trend_pullback.py"}))
    (config / "dataset_requirements.yaml").write_text(json.dumps({}))
    (config / "frozen_parameters.json").write_text(json.dumps({}))
    (config / "certification_gates.yaml").write_text(json.dumps({}))
    return sidecar


def test_legacy_report_audit_rejects_zero_volume_same_bar_proxy(tmp_path):
    sidecar = setup_sidecar(tmp_path)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "date": "2026-06-29",
        "verdict": "DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST",
        "entry_rule": "current_candle_close",
        "inspection": {"volume_quality": "ZERO_VOLUME"},
        "invalid_volume_or_vwap_assumption": ["movement.trend_pullback_v1"],
    }))
    result = TradeBotReadOnlyTools(tmp_path, sidecar_root=sidecar).audit_existing_research_report("r1", str(report))
    assert result.status == "REJECTED"
    assert set(result.blockers) == {
        "legacy_data_invalid_for_volume_or_vwap_assumption",
        "legacy_dataset_zero_volume",
        "legacy_report_not_executable_option_evidence",
        "legacy_same_bar_proxy_entry",
    }
