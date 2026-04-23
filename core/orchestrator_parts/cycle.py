import time

from config import config as cfg
from core.execution_core_fast import FastExecutionCore
from core.execution_engine_fast import FastExecutionEngine


def _fast_loop_enabled() -> bool:
    return bool(getattr(cfg, "ORCHESTRATOR_FAST_LOOP_ENABLE", True))


def run_live_monitoring(orch, run_once=False, time_module=None):
    if run_once or not _fast_loop_enabled():
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

        decision = engine.evaluate()
        result = engine.execute(decision)

        core.last_cycle_mono = float(clock.monotonic())
        if feed_epoch > 0.0:
            core.last_feed_epoch = float(feed_epoch)

        if result in {"STOP", "HALT", False}:
            return result

        clock.sleep(core.idle_sleep_sec())
