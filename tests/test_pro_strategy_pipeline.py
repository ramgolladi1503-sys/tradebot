from __future__ import annotations

from unittest.mock import Mock

from config import config as cfg
import core.pro_strategy_pipeline as pipeline_mod
from core.pro_strategy_pipeline import run_pro_strategy_pipeline


def _reset_pro_flags(monkeypatch):
    for name in cfg.pro_strategy_flags_snapshot().keys():
        monkeypatch.setattr(cfg, name, False, raising=False)

def test_pro_pipeline_shadow_flag_off_is_noop(monkeypatch):
    _reset_pro_flags(monkeypatch)
    result = run_pro_strategy_pipeline([])
    assert result["enabled"] is False
    assert result["flags"]["ENABLE_PRO_STRATEGY_SHADOW"] is False
    assert result["flags"]["ENABLE_PRO_STRATEGY_LAYER"] is False
    assert result["candidates"] == []
    assert result["errors"] == []


def test_pro_pipeline_shadow_flag_on_enables_report_path(monkeypatch):
    _reset_pro_flags(monkeypatch)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    stub_decision = {"symbol": "NIFTY", "final_score": 0.91}
    monkeypatch.setattr(pipeline_mod, "evaluate_pro_strategy_candidates", Mock(return_value=[stub_decision]))

    market_data = {"symbol": "NIFTY", "instrument_id": "789"}
    result = run_pro_strategy_pipeline([market_data])

    assert result["enabled"] is True
    assert result["flags"]["ENABLE_PRO_STRATEGY_SHADOW"] is True
    assert result["flags"]["ENABLE_PRO_STRATEGY_LAYER"] is False
    assert isinstance(result["candidates"], list)
    assert result["candidates"] == [stub_decision]
    assert result["errors"] == []


def test_pro_pipeline_error_includes_symbol_and_message(monkeypatch):
    _reset_pro_flags(monkeypatch)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)

    def _raise(_market_data, *, error_sink=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline_mod, "evaluate_pro_strategy_candidates", _raise)

    result = run_pro_strategy_pipeline([{"symbol": "NIFTY"}])

    assert result["enabled"] is True
    assert result["candidates"] == []
    assert len(result["errors"]) == 1
    assert "symbol=NIFTY" in result["errors"][0]
    assert "boom" in result["errors"][0]


def test_pro_pipeline_error_handles_non_dict_payload(monkeypatch):
    _reset_pro_flags(monkeypatch)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)

    def _raise(_market_data, *, error_sink=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline_mod, "evaluate_pro_strategy_candidates", _raise)

    result = run_pro_strategy_pipeline([None])

    assert result["enabled"] is True
    assert result["candidates"] == []
    assert len(result["errors"]) == 1
    assert "symbol=unknown" in result["errors"][0]
    assert "boom" in result["errors"][0]


def test_pro_pipeline_surfaces_strategy_errors_in_report(monkeypatch):
    _reset_pro_flags(monkeypatch)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)

    def _fake_eval(_market_data, *, error_sink=None):
        if error_sink is not None:
            error_sink.append("strategy_failed:broken_family:RuntimeError:boom")
        return []

    monkeypatch.setattr(pipeline_mod, "evaluate_pro_strategy_candidates", _fake_eval)

    result = run_pro_strategy_pipeline([{"symbol": "NIFTY"}])

    assert result["enabled"] is True
    assert result["candidates"] == []
    assert result["errors"] == ["strategy_failed:broken_family:RuntimeError:boom"]


def test_pro_strategy_flags_snapshot_includes_shadow_flag():
    flags = cfg.pro_strategy_flags_snapshot()
    assert "ENABLE_PRO_STRATEGY_SHADOW" in flags
    assert "PRO_STRATEGY_SHADOW_WORKER_TTL_SEC" in flags
