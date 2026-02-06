"""
Test harness that runs one Orchestrator cycle without modifying production code.
"""
import types
import time


def run_orchestrator_once(orch, monkeypatch, market_data_list=None, fake_kite=None, fake_telegram=None):
    """Run a single loop iteration by patching time.sleep to break."""
    import core.orchestrator as orch_mod

    # Patch external dependencies
    if market_data_list is not None:
        monkeypatch.setattr(orch_mod, "fetch_live_market_data", lambda: market_data_list)
    if fake_kite is not None:
        monkeypatch.setattr(orch_mod, "kite_client", fake_kite)
    if fake_telegram is not None:
        monkeypatch.setattr(orch_mod, "send_telegram_message", fake_telegram)

    # Prevent websocket startup
    monkeypatch.setattr(orch_mod.Orchestrator, "_start_depth_ws", lambda self: None)

    # Break after first sleep
    def _break_sleep(_):
        raise StopIteration()

    monkeypatch.setattr(time, "sleep", _break_sleep)

    try:
        orch.live_monitoring()
    except StopIteration:
        pass
