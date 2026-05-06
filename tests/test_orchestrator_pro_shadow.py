from __future__ import annotations

import json
import time
from pathlib import Path
from types import MappingProxyType
from unittest.mock import Mock

import core.orchestrator as orch_mod
from config import config as cfg
from core.execution_engine_fast import FastExecutionEngine


def _make_orchestrator_sentinel():
    orch = object.__new__(orch_mod.Orchestrator)
    orch._gate_status_cycle_id = "cycle-123"
    orch._cycle_market_snapshot_by_symbol = {"NIFTY": {"sentinel": True}}
    return orch


def _wait_for(condition, timeout_sec: float = 5.0, interval_sec: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval_sec)
    return bool(condition())


class _InlineProcess:
    def __init__(self, target, args, name=None, daemon=None):
        self._target = target
        self._args = args
        self.name = name
        self.daemon = daemon
        self.exitcode = None
        self._alive = False
        self.terminated = False
        self.join_calls: list[float | None] = []

    def start(self):
        self._alive = True
        try:
            self._target(*self._args)
        except Exception:
            self.exitcode = 1
        else:
            self.exitcode = 0
        finally:
            self._alive = False

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self._alive = False

    def terminate(self):
        self.terminated = True
        self.exitcode = -15
        self._alive = False


def _prepare_cycle_harness(monkeypatch, tmp_path, *, shadow_enabled: bool, pipeline_behavior: str = "return"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    logs_root = tmp_path / "logs"
    data_root = tmp_path / "data"
    monkeypatch.setenv("LOGS_ROOT", str(logs_root))
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("EXECUTION_MODE", "SIM")
    monkeypatch.setenv("ENABLE_PRO_STRATEGY_SHADOW", "true" if shadow_enabled else "false")
    monkeypatch.setenv("PRO_STRATEGY_LAYER_STRICT_MODE", "true")
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "DATA_ROOT", str(data_root), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", shadow_enabled, raising=False)
    monkeypatch.setattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True, raising=False)
    logs_root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(orch_mod, "verify_audit_chain", Mock(return_value=(True, "ok")))
    monkeypatch.setattr(orch_mod.Orchestrator, "_run_startup_warmup_bootstrap", lambda self: [])

    orch = orch_mod.Orchestrator(total_capital=100000, poll_interval=0, start_depth_ws_enabled=False)
    orch._cycle_market_snapshot_by_symbol = {}
    records: list[str] = []

    def _record(label: str):
        records.append(label)

    monkeypatch.setattr(orch_mod, "resolve_global_halt_reason", lambda _cb: None)
    monkeypatch.setattr(
        orch_mod,
        "evaluate_slo_status",
        lambda enforce_failover=True: {"status": "OK", "reasons": [], "failover_triggered": False},
    )
    monkeypatch.setattr(orch, "_maybe_auto_clear_runtime_slo_failover_halt", lambda: _record("maybe_auto_clear_runtime_slo_failover_halt"))
    monkeypatch.setattr(orch, "_refresh_decay_report", lambda: _record("refresh_decay_report"))
    monkeypatch.setattr(orch, "_build_cycle_market_data", lambda market_data_list: list(market_data_list or []))
    monkeypatch.setattr(orch, "_update_decision_breakers", lambda market_data_list: _record(f"update_decision_breakers:{len(market_data_list or [])}"))
    monkeypatch.setattr(orch, "_update_pilot_unlock_clean_cycles", lambda: _record("update_pilot_unlock_clean_cycles"))
    monkeypatch.setattr(orch, "_evaluate_suggestions", lambda market_data_list: _record(f"evaluate_suggestions:{len(market_data_list or [])}"))
    monkeypatch.setattr(orch, "_run_v2_shadow_pipeline", lambda market_data_list: _record("v2_shadow_pipeline"))
    monkeypatch.setattr(orch_mod, "produce_and_store_market_snapshot", lambda **kwargs: _record("produce_market_snapshot"))
    monkeypatch.setattr(orch_mod, "produce_and_store_runtime_snapshots", lambda **kwargs: _record("produce_runtime_snapshots"))
    monkeypatch.setattr(orch, "_maybe_run_suggestion_reliability_check", lambda: _record("maybe_run_suggestion_reliability_check"))
    monkeypatch.setattr(orch_mod, "maybe_auto_tune", lambda: _record("maybe_auto_tune"))
    monkeypatch.setattr(orch.risk_state, "update_portfolio", lambda portfolio: _record("update_portfolio"))
    monkeypatch.setattr(orch, "_update_risk_pct_fields", lambda: _record("update_risk_pct_fields"))
    monkeypatch.setattr(orch, "_pilot_exec_degradation", lambda: _record("pilot_exec_degradation"))
    monkeypatch.setattr(orch_mod, "write_runtime_health_snapshot", lambda **kwargs: _record("write_runtime_health_snapshot"))
    monkeypatch.setattr(orch_mod, "_create_pro_shadow_process", lambda market_data_list, loop_id, started_at: _InlineProcess(
        target=orch_mod._run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    ))

    if pipeline_behavior == "raise":
        def _raise(*_args, **_kwargs):
            _record("pro_strategy_pipeline")
            raise RuntimeError("boom")

        pipeline_spy = Mock(side_effect=_raise)
    else:
        pipeline_spy = Mock(side_effect=lambda *args, **kwargs: _record("pro_strategy_pipeline") or {"enabled": True, "candidates": [], "errors": []})
    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", pipeline_spy)
    monkeypatch.setattr(orch_mod.time, "time", Mock(return_value=123.456))
    monkeypatch.setattr(orch_mod, "fetch_live_market_data", lambda: [])
    monkeypatch.setattr(orch, "_sync_trades", lambda: _record("sync_trades"))

    return orch, records, pipeline_spy


def test_pro_shadow_pipeline_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", False, raising=False)
    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", Mock())
    monkeypatch.setattr(orch_mod, "write_json_atomic", Mock())
    info_spy = Mock()
    exception_spy = Mock()
    monkeypatch.setattr(orch_mod.logger, "info", info_spy)
    monkeypatch.setattr(orch_mod.logger, "exception", exception_spy)
    monkeypatch.setattr(orch_mod, "_create_pro_shadow_process", lambda market_data_list, loop_id, started_at: _InlineProcess(
        target=orch_mod._run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    ))

    orch = _make_orchestrator_sentinel()
    before_cycle_id = orch._gate_status_cycle_id
    before_snapshot = dict(orch._cycle_market_snapshot_by_symbol)

    orch._run_pro_shadow_pipeline([{"symbol": "NIFTY"}])
    assert _wait_for(lambda: orch_mod.run_pro_strategy_pipeline.call_count == 0)

    orch_mod.run_pro_strategy_pipeline.assert_not_called()
    info_spy.assert_not_called()
    exception_spy.assert_not_called()
    assert orch._gate_status_cycle_id == before_cycle_id
    assert orch._cycle_market_snapshot_by_symbol == before_snapshot


def test_pro_shadow_pipeline_enabled_calls_pipeline_and_logs_summary(monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    monkeypatch.setattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", False, raising=False)
    pipeline_spy = Mock(return_value={"enabled": True, "candidates": [{"symbol": "NIFTY", "final_score": 0.91}], "errors": []})
    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", pipeline_spy)
    monkeypatch.setattr(orch_mod, "write_json_atomic", Mock())
    info_spy = Mock()
    exception_spy = Mock()
    monkeypatch.setattr(orch_mod.logger, "info", info_spy)
    monkeypatch.setattr(orch_mod.logger, "exception", exception_spy)
    monkeypatch.setattr(orch_mod, "_create_pro_shadow_process", lambda market_data_list, loop_id, started_at: _InlineProcess(
        target=orch_mod._run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    ))

    orch = _make_orchestrator_sentinel()
    before_cycle_id = orch._gate_status_cycle_id
    before_snapshot = dict(orch._cycle_market_snapshot_by_symbol)

    orch._run_pro_shadow_pipeline([{"symbol": "NIFTY", "market_open": True}])
    assert _wait_for(lambda: pipeline_spy.call_count == 1)
    assert _wait_for(lambda: info_spy.call_count == 1)
    exception_spy.assert_not_called()
    assert orch._gate_status_cycle_id == before_cycle_id
    assert orch._cycle_market_snapshot_by_symbol == before_snapshot


def test_pro_shadow_pipeline_swallows_pipeline_errors(monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    monkeypatch.setattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True, raising=False)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    pipeline_spy = Mock(side_effect=_raise)
    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", pipeline_spy)
    monkeypatch.setattr(orch_mod, "write_json_atomic", Mock())
    info_spy = Mock()
    exception_spy = Mock()
    monkeypatch.setattr(orch_mod.logger, "info", info_spy)
    monkeypatch.setattr(orch_mod.logger, "exception", exception_spy)
    monkeypatch.setattr(orch_mod, "_create_pro_shadow_process", lambda market_data_list, loop_id, started_at: _InlineProcess(
        target=orch_mod._run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    ))

    orch = _make_orchestrator_sentinel()
    before_cycle_id = orch._gate_status_cycle_id
    before_snapshot = dict(orch._cycle_market_snapshot_by_symbol)

    orch._run_pro_shadow_pipeline([{"symbol": "BANKNIFTY"}])
    assert _wait_for(lambda: pipeline_spy.call_count == 1)
    assert _wait_for(lambda: exception_spy.call_count == 1)
    assert _wait_for(lambda: info_spy.call_count == 1)
    assert orch._gate_status_cycle_id == before_cycle_id
    assert orch._cycle_market_snapshot_by_symbol == before_snapshot


def test_pro_shadow_cycle_path_is_observational_only(monkeypatch, tmp_path):
    shadow_orch, _, shadow_pipeline = _prepare_cycle_harness(
        monkeypatch,
        tmp_path / "shadow",
        shadow_enabled=True,
    )
    before_snapshot = dict(shadow_orch._cycle_market_snapshot_by_symbol)
    before_trades = shadow_orch.portfolio.get("trades_today", 0)
    original_execute = FastExecutionEngine.execute

    def _execute_once(self, decision):
        original_execute(self, decision)
        return "STOP"

    monkeypatch.setattr(FastExecutionEngine, "execute", _execute_once)
    shadow_orch.live_monitoring()

    assert _wait_for(lambda: shadow_pipeline.call_count == 1)
    assert dict(shadow_orch._cycle_market_snapshot_by_symbol) == before_snapshot == {}
    assert shadow_orch.portfolio.get("trades_today", 0) == before_trades == 0


def test_pro_shadow_cycle_failure_is_swallowed(monkeypatch, tmp_path):
    orch, _, pipeline_spy = _prepare_cycle_harness(
        monkeypatch,
        tmp_path / "failure",
        shadow_enabled=True,
        pipeline_behavior="raise",
    )
    original_execute = FastExecutionEngine.execute

    def _execute_once(self, decision):
        original_execute(self, decision)
        return "STOP"

    monkeypatch.setattr(FastExecutionEngine, "execute", _execute_once)
    orch.live_monitoring()

    assert _wait_for(lambda: pipeline_spy.call_count == 1)
    assert dict(orch._cycle_market_snapshot_by_symbol) == {}
    assert orch.portfolio.get("trades_today", 0) == 0


def test_pro_shadow_pipeline_persists_shadow_report(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGS_ROOT", str(logs_root))
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_root), raising=False)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    monkeypatch.setattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(orch_mod.time, "time", Mock(return_value=321.0))
    monkeypatch.setattr(
        orch_mod,
        "run_pro_strategy_pipeline",
        Mock(return_value={"enabled": True, "candidates": [{"symbol": "NIFTY", "final_score": 0.77}], "errors": []}),
    )
    monkeypatch.setattr(orch_mod.logger, "info", Mock())
    monkeypatch.setattr(orch_mod.logger, "exception", Mock())
    monkeypatch.setattr(orch_mod, "_create_pro_shadow_process", lambda market_data_list, loop_id, started_at: _InlineProcess(
        target=orch_mod._run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    ))

    orch = _make_orchestrator_sentinel()
    orch._run_pro_shadow_pipeline([{"symbol": "NIFTY"}])

    report_path = logs_root / "pro_strategy_shadow_cycle-123.json"
    assert _wait_for(report_path.exists)
    payload = json.loads(report_path.read_text())
    assert payload["loop_id"] == "cycle-123"
    assert payload["enabled"] is True
    assert payload["candidate_count"] == 1
    assert payload["error_count"] == 0
    assert payload["report"]["candidates"][0]["symbol"] == "NIFTY"


def test_pro_shadow_pipeline_restarts_stale_worker(monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    monkeypatch.setattr(cfg, "PRO_STRATEGY_SHADOW_THREAD_TTL_SEC", 1.0, raising=False)
    pipeline_spy = Mock(return_value={"enabled": True, "candidates": [{"symbol": "BANKNIFTY", "final_score": 0.88}], "errors": []})
    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", pipeline_spy)
    monkeypatch.setattr(orch_mod, "write_json_atomic", Mock())
    monkeypatch.setattr(orch_mod.logger, "info", Mock())
    monkeypatch.setattr(orch_mod.logger, "warning", Mock())
    monkeypatch.setattr(orch_mod.logger, "exception", Mock())
    monkeypatch.setattr(orch_mod, "_create_pro_shadow_process", lambda market_data_list, loop_id, started_at: _InlineProcess(
        target=orch_mod._run_pro_shadow_pipeline_worker_entry,
        args=(market_data_list, loop_id, started_at),
        name=f"pro-shadow-{loop_id or 'cycle'}",
        daemon=True,
    ))

    orch = _make_orchestrator_sentinel()

    stale = _InlineProcess(target=lambda *_args: None, args=(), name="stale-shadow", daemon=True)
    stale._alive = True
    stale.exitcode = None
    orch._pro_shadow_process = stale
    orch._pro_shadow_process_started_at = time.time() - 120.0

    orch._run_pro_shadow_pipeline([{"symbol": "BANKNIFTY"}])

    assert stale.terminated is True
    assert _wait_for(lambda: pipeline_spy.call_count == 1)


def test_pro_shadow_row_sanitizer_preserves_mapping_payloads():
    row = MappingProxyType({"symbol": "NIFTY", "quote_age_sec": 1.5})
    out = orch_mod._sanitize_pro_shadow_rows([row, "raw"])

    assert isinstance(out[0], dict)
    assert out[0]["symbol"] == "NIFTY"
    assert out[0]["quote_age_sec"] == 1.5
    assert out[1] == {"value": "raw"}
