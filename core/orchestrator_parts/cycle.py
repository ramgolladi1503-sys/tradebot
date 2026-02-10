def run_live_monitoring(orch, run_once=False, time_module=None):
    """
    Cycle coordinator wrapper. The legacy loop is retained for behavior parity.
    """
    _ = time_module
    return orch._legacy_live_monitoring(run_once=run_once)

