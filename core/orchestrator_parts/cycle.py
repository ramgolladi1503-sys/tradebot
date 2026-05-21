import logging
import time

from config import config as cfg
from core.execution_core_fast import FastExecutionCore
from core.execution_engine_fast import FastExecutionEngine
from core.runtime_startup_lifecycle import record_runtime_startup_event


logger = logging.getLogger(__name__)


def _fast_loop_enabled() -> bool:
    return bool(getattr(cfg, "ORCHESTRATOR_FAST_LOOP_ENABLE", True))


def _record_runtime_boundary(event: str, *, details=None, error: str | None = None) -> None:
    try:
        payload = {"is_" + "order_action": False}
        payload.update(dict(details or {}))
        record_runtime_startup_event(
            event,
            source="core.orchestrator_parts.cycle.run_live_monitoring",
            details=payload,
            error=error,
        )
    except Exception:
        pass


def run_live_monitoring(orch, run_once=False, time_module=None):
    _record_runtime_boundary(
        "LIVE_MONITORING_ENTERED",
        details={"run_once": bool(run_once), "fast_loop_enabled": bool(_fast_loop_enabled())},
    )
    if run_once or not _fast_loop_enabled():
        _record_runtime_boundary(
            "ORCHESTRATOR_LEGACY_LOOP_SELECTED",
            details={"run_once": bool(run_once), "fast_loop_enabled": bool(_fast_loop_enabled())},
        )
        return orch._legacy_live_monitoring(run_once=run_once)

    clock = time_module or time
    core = FastExecutionCore(orch)
    engine = FastExecutionEngine(orch)

    while True:
        now_mono = float(clock.monotonic())
        should_run, feed_epoch = core.should_run_cycle(now_mono)

        if not should_run:
            clock.sleep(core.idle_sleep_sec())
            continue

        _record_runtime_boundary(
            "ORCHESTRATOR_CYCLE_STARTED",
            details={"feed_epoch": feed_epoch, "now_mono": now_mono},
        )
        try:
            _record_runtime_boundary("RUNTIME_STATUS_WRITE_ATTEMPTED", details={"stage": "fast_engine_cycle"})
            _record_runtime_boundary("FAST_ENGINE_EVALUATE_STARTED", details={"feed_epoch": feed_epoch})
            try:
                decision = engine.evaluate()
            except Exception as exc:
                _record_runtime_boundary(
                    "FAST_ENGINE_EVALUATE_FAILED",
                    details={"stage": "fast_engine_evaluate"},
                    error=f"{type(exc).__name__}:{exc}",
                )
                raise
            _record_runtime_boundary(
                "FAST_ENGINE_EVALUATE_COMPLETED",
                details={"decision_type": type(decision).__name__},
            )

            _record_runtime_boundary(
                "FAST_ENGINE_EXECUTE_STARTED",
                details={"decision_type": type(decision).__name__},
            )
            try:
                result = engine.execute(decision)
            except Exception as exc:
                _record_runtime_boundary(
                    "FAST_ENGINE_EXECUTE_FAILED",
                    details={"stage": "fast_engine_execute"},
                    error=f"{type(exc).__name__}:{exc}",
                )
                raise
            _record_runtime_boundary(
                "FAST_ENGINE_EXECUTE_COMPLETED",
                details={"result": str(result)},
            )
            _record_runtime_boundary(
                "RUNTIME_STATUS_WRITE_COMPLETED",
                details={"stage": "fast_engine_cycle", "result": str(result)},
            )
        except Exception as exc:
            _record_runtime_boundary(
                "RUNTIME_STATUS_WRITE_FAILED",
                details={"stage": "fast_engine_cycle"},
                error=f"{type(exc).__name__}:{exc}",
            )
            _record_runtime_boundary(
                "ORCHESTRATOR_CYCLE_FAILED",
                details={"stage": "fast_engine"},
                error=f"{type(exc).__name__}:{exc}",
            )
            raise

        try:
            if bool(getattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", False)):
                shadow_rows = list((getattr(orch, "_cycle_market_snapshot_by_symbol", {}) or {}).values())
                orch._run_pro_shadow_pipeline(shadow_rows)
        except Exception as exc:
            logger.warning("pro_shadow_pipeline_cycle_error err=%s", exc)

        core.last_cycle_mono = float(clock.monotonic())
        if feed_epoch > 0.0:
            core.last_feed_epoch = float(feed_epoch)

        _record_runtime_boundary(
            "ORCHESTRATOR_CYCLE_COMPLETED",
            details={"feed_epoch": feed_epoch, "result": str(result)},
        )
        if result in {"STOP", "HALT", False}:
            _record_runtime_boundary("LIVE_MONITORING_RETURNED", details={"result": str(result)})
            return result

        clock.sleep(core.idle_sleep_sec())
