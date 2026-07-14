# Pro Strategy Layer Shadow Wire-In Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shadow-only orchestrator attachment for the pro strategy layer so we can observe candidate quality, suppression behavior, and ranking stability without changing live execution behavior.

**Architecture:** Keep the pro strategy layer observational only at first. A dedicated shadow flag controls whether the orchestrator calls the pro pipeline during the cycle, and the pipeline returns a structured report with candidates and errors without mutating the legacy trade builder, candidate pool, or execution routing. The live path stays untouched; the shadow path exists only to measure behavior and prove stability before any later promotion design.

**Tech Stack:** Python, `pytest`, `config.config`, `core.orchestrator`, `core.pro_strategy_pipeline`, existing logging and status writers.

---

## Files in Scope

- Modify: `config/config.py` - add `ENABLE_PRO_STRATEGY_SHADOW` and include it in the pro flag snapshots.
- Modify: `core/pro_strategy_pipeline.py` - make the pro pipeline shadow-aware so the new shadow flag actually activates the report path while the live enable flag stays reserved for later promotion work.
- Modify: `core/orchestrator.py` - add a guarded pro shadow hook alongside the existing `v2` shadow pipeline, with summary logging and fail-closed exception handling.
- Modify: `tests/test_pro_strategy_pipeline.py` - extend the pipeline contract tests to cover the new shadow flag behavior.
- Create: `tests/test_orchestrator_pro_shadow.py` - prove the orchestrator shadow hook is disabled by default, emits a report when enabled, and does not alter live cycle stat-us behavior.

## Task 1: Add the shadow flag and make the pro pipeline shadow-aware

**Files:**
- Modify: `config/config.py`
- Modify: `core/pro_strategy_pipeline.py`
- Modify: `tests/test_pro_strategy_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from config import config as cfg
from core.pro_strategy_pipeline import run_pro_strategy_pipeline


def _reset_pro_flags(monkeypatch):
    for name in cfg.pro_strategy_flags_snapshot().keys():
        monkeypatch.setattr(cfg, name, False, raising=False)


def test_shadow_flag_off_is_noop(monkeypatch):
    _reset_pro_flags(monkeypatch)
    result = run_pro_strategy_pipeline([])
    assert result["enabled"] is False
    assert result["flags"]["ENABLE_PRO_STRATEGY_SHADOW"] is False
    assert result["flags"]["ENABLE_PRO_STRATEGY_LAYER"] is False
    assert result["candidates"] == []
    assert result["errors"] == []


def test_shadow_flag_on_runs_without_enabling_live_layer(monkeypatch):
    _reset_pro_flags(monkeypatch)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    market_data = {
        "symbol": "NIFTY",
        "instrument_id": "123",
        "regime": "TREND",
        "atr": 1.8,
        "ltp_change_window": 1.45,
        "vol_z": 1.7,
        "bid_qty": 860,
        "ask_qty": 120,
        "quote_age_sec": 1.1,
        "spread_pct": 0.009,
        "quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "execution_allowed": True,
        "data_confidence": 0.92,
    }
    result = run_pro_strategy_pipeline([market_data])
    assert result["enabled"] is True
    assert result["flags"]["ENABLE_PRO_STRATEGY_SHADOW"] is True
    assert result["flags"]["ENABLE_PRO_STRATEGY_LAYER"] is False
    assert isinstance(result["candidates"], list)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_pro_strategy_pipeline.py -q`
Expected: fail because `core/pro_strategy_pipeline.py` still keys activation off the live enable flag instead of the new shadow flag.

- [ ] **Step 3: Implement the shadow-aware flag contract**

```python
# config/config.py
ENABLE_PRO_STRATEGY_LAYER = os.getenv("ENABLE_PRO_STRATEGY_LAYER", "false").lower() == "true"
PRO_STRATEGY_LAYER_STRICT_MODE = os.getenv("PRO_STRATEGY_LAYER_STRICT_MODE", "true").lower() == "true"
ENABLE_PRO_STRATEGY_SHADOW = os.getenv("ENABLE_PRO_STRATEGY_SHADOW", "false").lower() == "true"

def pro_strategy_flags_snapshot() -> dict:
    return {
        "ENABLE_PRO_STRATEGY_LAYER": ENABLE_PRO_STRATEGY_LAYER,
        "PRO_STRATEGY_LAYER_STRICT_MODE": PRO_STRATEGY_LAYER_STRICT_MODE,
        "ENABLE_PRO_STRATEGY_SHADOW": ENABLE_PRO_STRATEGY_SHADOW,
    }

def pro_strategy_flags_active() -> dict:
    flags = pro_strategy_flags_snapshot()
    return {name: value for name, value in flags.items() if value}
```

```python
# core/pro_strategy_pipeline.py
def _flags_enabled() -> dict[str, bool]:
    return dict(pro_strategy_flags_snapshot())


def _shadow_enabled(flags: dict[str, bool]) -> bool:
    return bool(flags.get("ENABLE_PRO_STRATEGY_SHADOW", False))


def run_pro_strategy_pipeline(
    market_data_list: list[dict[str, Any]] | None,
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    flags = _flags_enabled()
    if not _shadow_enabled(flags):
        return {"enabled": False, "flags": flags, "candidates": [], "errors": []}

    market_data_list = list(market_data_list or [])
    result: dict[str, Any] = {
        "enabled": True,
        "flags": flags,
        "candidates": [],
        "errors": [],
    }

    candidates: list[dict[str, Any]] = []
    for market_data in market_data_list:
        try:
            decision = best_pro_strategy_decision(market_data)
            if decision:
                candidates.append(decision)
        except Exception as exc:
            logger.exception("pro_strategy_pipeline_item_failed err=%s", exc)
            result["errors"].append(f"pro_strategy_failed:{type(exc).__name__}")

    result["candidates"] = candidates
    logger.info(
        "pro_strategy_shadow_summary enabled=%s candidates=%s errors=%s strict_mode=%s",
        result["enabled"],
        len(result.get("candidates") or []),
        len(result.get("errors") or []),
        bool(getattr(cfg, "PRO_STRATEGY_LAYER_STRICT_MODE", True)),
    )
    return result
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `pytest -q tests/test_pro_strategy_pipeline.py -q`
Expected: pass, with `ENABLE_PRO_STRATEGY_SHADOW` driving the shadow report path and `ENABLE_PRO_STRATEGY_LAYER` staying off by default.

- [ ] **Step 5: Commit**

```bash
git add config/config.py core/pro_strategy_pipeline.py tests/test_pro_strategy_pipeline.py
git commit -m "feat: add shadow flag contract for pro strategy pipeline"
```

## Task 2: Wire the orchestrator shadow hook without changing live behavior

**Files:**
- Modify: `core/orchestrator.py`
- Create: `tests/test_orchestrator_pro_shadow.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.orchestrator as orch_mod
from config import config as cfg
from core.time_utils import now_ist


def test_shadow_hook_disabled_by_default_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", False, raising=False)
    called = {"count": 0}

    def _raise_if_called(*args, **kwargs):
        called["count"] += 1
        return {"enabled": True, "flags": {}, "candidates": [], "errors": []}

    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", _raise_if_called)
    orch = orch_mod.Orchestrator.__new__(orch_mod.Orchestrator)
    orch_mod.Orchestrator._run_pro_shadow_pipeline(orch, [{"symbol": "NIFTY"}])
    assert called["count"] == 0


def test_shadow_hook_enabled_logs_report_without_mutating_cycle_snapshot(monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    reports = []
    logs = []

    def _fake_shadow_pipeline(market_data_list, now_ts=None):
        reports.append(list(market_data_list or []))
        return {
            "enabled": True,
            "flags": {"ENABLE_PRO_STRATEGY_SHADOW": True, "ENABLE_PRO_STRATEGY_LAYER": False},
            "candidates": [{"symbol": "NIFTY", "final_score": 0.91}],
            "errors": [],
        }

    monkeypatch.setattr(orch_mod, "run_pro_strategy_pipeline", _fake_shadow_pipeline)
    monkeypatch.setattr(orch_mod.logger, "info", lambda msg, *args, **kwargs: logs.append((msg, args)))
    orch = orch_mod.Orchestrator.__new__(orch_mod.Orchestrator)
    source = [{"symbol": "NIFTY", "timestamp": 1.0}]
    orch_mod.Orchestrator._run_pro_shadow_pipeline(orch, source)
    assert reports == [source]
    assert any("pro_strategy_shadow_summary" in str(item[0]) for item in logs)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_orchestrator_pro_shadow.py -q`
Expected: fail because `core.orchestrator` does not yet import and invoke the pro shadow pipeline.

- [ ] **Step 3: Add the shadow hook to the orchestrator**

```python
# core/orchestrator.py
from core.pro_strategy_pipeline import run_pro_strategy_pipeline


def _run_pro_shadow_pipeline(self, market_data_list: list[dict] | None) -> None:
    if not bool(getattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", False)):
        return
    try:
        report = run_pro_strategy_pipeline(market_data_list, now_ts=time.time())
    except Exception as exc:
        logger.exception("pro_strategy_shadow_pipeline_failed err=%s", exc)
        return
    logger.info(
        "pro_strategy_shadow_summary enabled=%s candidates=%s errors=%s",
        bool(report.get("enabled")),
        len(report.get("candidates") or []),
        len(report.get("errors") or []),
    )
```

```python
# core/orchestrator.py, inside the cycle after the existing v2 shadow pipeline
try:
    self._run_pro_shadow_pipeline(market_data_list)
except Exception as exc:
    logger.warning("pro_strategy_shadow_pipeline_cycle_error err=%s", exc)
```

The orchestrator must not pass the shadow report into trade building, candidate ranking, or execution routing.

- [ ] **Step 4: Add the live-behavior regression in the same test file**

```python
def test_shadow_enabled_cycle_error_still_records_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / "data"), raising=False)
    monkeypatch.setattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", True, raising=False)
    (Path(cfg.LOGS_ROOT)).mkdir(parents=True, exist_ok=True)
    (Path(cfg.DATA_ROOT)).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(orch_mod.Orchestrator, "_start_depth_ws", lambda self: None)
    monkeypatch.setattr(orch_mod, "fetch_live_market_data", lambda: (_ for _ in ()).throw(RuntimeError("forced_cycle_error")))
    monkeypatch.setattr(orch_mod.time, "sleep", lambda _: (_ for _ in ()).throw(StopIteration()))
    monkeypatch.setattr(orch_mod.RunLock, "acquire", lambda self: (True, "ok"))
    monkeypatch.setattr(orch_mod.RunLock, "release", lambda self: None)
    monkeypatch.setattr(
        orch_mod,
        "run_pro_strategy_pipeline",
        lambda market_data_list, now_ts=None: {
            "enabled": True,
            "flags": {"ENABLE_PRO_STRATEGY_SHADOW": True, "ENABLE_PRO_STRATEGY_LAYER": False},
            "candidates": [],
            "errors": [],
        },
    )

    orch = orch_mod.Orchestrator(total_capital=100000, poll_interval=0)

    with pytest.raises(StopIteration):
        orch.live_monitoring()

    suggestions_status = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    assert suggestions_status["status"] == "error"
```

- [ ] **Step 5: Run the test and verify it passes**

Run: `pytest -q tests/test_orchestrator_pro_shadow.py -q`
Expected: pass, proving the shadow hook is disabled by default, logs a report when enabled, and does not change cycle-error behavior.

- [ ] **Step 6: Commit**

```bash
git add core/orchestrator.py tests/test_orchestrator_pro_shadow.py
git commit -m "feat: add shadow-only pro strategy orchestrator hook"
```

## Validation Sequence

Run these after both tasks are complete:

```bash
pytest -q tests/test_pro_strategy_pipeline.py tests/test_orchestrator_pro_shadow.py
pytest -q tests/strategies
pytest -q tests/test_orchestrator_reports_finally.py tests/test_kite_depth_restart.py tests/test_market_feed_race_conditions.py
pytest -q
```

Expected:
- pro strategy shadow pipeline tests pass
- orchestrator shadow hook tests pass
- existing pro strategy, replay, restart, and websocket regression slices stay green
- branch-level validation stays fail-closed with no live behavior changes

## Migration Notes

- New config key:
  - `ENABLE_PRO_STRATEGY_SHADOW` defaults to `false`
- Existing config key:
  - `ENABLE_PRO_STRATEGY_LAYER` stays `false` by default and remains reserved for later promotion work
- The shadow hook is observational only and must not feed the legacy candidate path.
- The shadow pipeline report is for telemetry and review only; it does not authorize trades.

## Rollout Steps

1. Land the shadow flag and report contract in the isolated branch.
2. Add the orchestrator shadow hook behind the new flag, keeping live behavior untouched.
3. Validate the new tests plus the existing branch safety slices.
4. Only after the branch is green and the shadow report is stable should we consider a later candidate-path wire-in design.

## Open Risks

- Shadow telemetry can become noisy if the report is too chatty.
- A shadow hook placed too early in the cycle could slow the orchestrator.
- Confusing the shadow flag with the live pro layer flag could make the branch appear more production-ready than it is.
