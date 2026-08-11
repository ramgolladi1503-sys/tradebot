import logging
import time

from config import config as cfg
from core.execution_core_fast import FastExecutionCore
from core.execution_engine_fast import FastExecutionEngine
from core.market_event_graph_constituent_refresh import refresh_market_event_graph_constituent_source
from core.runtime_startup_lifecycle import record_runtime_startup_event


logger = logging.getLogger(__name__)


def _fast_loop_enabled() -> bool:
    return bool(getattr(cfg, "ORCHESTRATOR_FAST_LOOP_ENABLE", True))


def _record_runtime_boundary(event: str, *, details=None, error: str | None = None) -> None:
    if str(event).startswith(("FAST_ENGINE_", "ORCHESTRATOR_CYCLE_", "RUNTIME_STATUS_")):
        if event not in {"ORCHESTRATOR_CYCLE_FAILED", "ORCHESTRATOR_CYCLE_DEGRADED"}:
            return
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


def _market_event_graph_live_source_enabled() -> bool:
    import os

    raw = os.getenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE")
    if raw is None:
        raw = getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _refresh_constituent_source_for_cycle(*, feed_epoch: float | None) -> dict | None:
    if not _market_event_graph_live_source_enabled():
        return None
    try:
        as_of_epoch = float(feed_epoch or 0.0)
    except (TypeError, ValueError):
        as_of_epoch = 0.0
    if as_of_epoch <= 0.0:
        as_of_epoch = time.time()
    result = refresh_market_event_graph_constituent_source(
        symbol="NIFTY",
        as_of_epoch=as_of_epoch,
        metadata={
            "market_event_graph_live_source_enable": True,
            "owner": "NIFTY",
            "identity": "NIFTY",
        },
    )
    _record_runtime_boundary(
        "PR749_CONSTITUENT_SOURCE_REFRESH",
        details={
            "feed_epoch": feed_epoch,
            "status": result.get("status"),
            "reason": result.get("reason"),
            "invoked": result.get("invoked"),
            "completed_bar_count": result.get("completed_bar_count"),
            "target_boundary_count": result.get("target_boundary_count"),
            "state_created": result.get("state_created"),
            "state_persisted": result.get("state_persisted"),
        },
    )
    return result


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
            t0 = time.perf_counter()
            _record_runtime_boundary("RUNTIME_STATUS_WRITE_ATTEMPTED", details={"stage": "fast_engine_cycle"})
            source_refresh = _refresh_constituent_source_for_cycle(feed_epoch=feed_epoch)
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
            t1 = time.perf_counter()
            _record_runtime_boundary(
                "FAST_ENGINE_EVALUATE_COMPLETED",
                details={
                    "decision_type": type(decision).__name__,
                    "pr749_refresh_status": (source_refresh or {}).get("status"),
                },
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
            core.last_cycle_mono = float(clock.monotonic())
            if feed_epoch is not None and float(feed_epoch) > 0.0:
                core.last_feed_epoch = float(feed_epoch)
            core.last_result = result
            _record_runtime_boundary(
                "RUNTIME_STATUS_WRITE_COMPLETED",
                details={"stage": "fast_engine_cycle", "result": str(result)},
            )
            t2 = time.perf_counter()
            if (t2 - t0) > 1.0:
                logger.warning("CYCLE_TIMINGS evaluate=%.3f execute=%.3f", t1 - t0, t2 - t1)
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

        cycle_end_mono = float(clock.monotonic())
        cycle_latency_ms = (cycle_end_mono - now_mono) * 1000.0
        
        if cycle_latency_ms > getattr(cfg, "ORCHESTRATOR_DEGRADED_LATENCY_MS", 500.0):
            _record_runtime_boundary(
                "ORCHESTRATOR_CYCLE_DEGRADED",
                details={"latency_ms": cycle_latency_ms, "feed_epoch": feed_epoch}
            )
            logger.warning("orchestrator_cycle_degraded latency_ms=%.1f", cycle_latency_ms)

        core.last_cycle_mono = cycle_end_mono
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
