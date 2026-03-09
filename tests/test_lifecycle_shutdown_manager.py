from __future__ import annotations

import threading

import core.lifecycle as lifecycle_module
from core.lifecycle import Lifecycle


def _loop_until_stopped(stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            stop_event.wait(0.02)
    finally:
        return


def test_lifecycle_manager_stops_representative_threads_and_is_idempotent():
    manager = Lifecycle()
    stop_order: list[str] = []

    depth_stop = threading.Event()
    depth_thread = threading.Thread(
        target=_loop_until_stopped,
        args=(depth_stop,),
        name="depth-ws-stub",
        daemon=False,
    )
    recon_stop = threading.Event()
    recon_thread = threading.Thread(
        target=_loop_until_stopped,
        args=(recon_stop,),
        name="recon-daemon-stub",
        daemon=False,
    )
    depth_thread.start()
    recon_thread.start()

    manager.register_thread(
        "depth-ws-stub",
        depth_thread,
        lambda: (stop_order.append("depth-ws-stub"), depth_stop.set()),
    )
    manager.register_thread(
        "recon-daemon-stub",
        recon_thread,
        lambda: (stop_order.append("recon-daemon-stub"), recon_stop.set()),
    )

    manager.stop_all(timeout=1.0, reason="unit_test")
    manager.stop_all(timeout=1.0, reason="unit_test_repeat")

    assert stop_order[:2] == ["recon-daemon-stub", "depth-ws-stub"]
    assert not depth_thread.is_alive()
    assert not recon_thread.is_alive()


def test_global_lifecycle_stop_all_runs_component_shutdown_hooks(capsys, monkeypatch):
    lifecycle_module.stop_all(timeout=0.1, reason="pre_clean")
    calls: list[str] = []

    monkeypatch.setattr(
        lifecycle_module,
        "_safe_stop_depth_ws",
        lambda reason: calls.append(f"depth:{reason}"),
    )
    monkeypatch.setattr(
        lifecycle_module,
        "_safe_stop_reconciliation_daemon",
        lambda timeout_sec: calls.append(f"recon:{float(timeout_sec):.1f}"),
    )

    lifecycle_module.stop_all(timeout=0.5, reason="pytest_teardown")

    assert any(call.startswith("depth:pytest_teardown") for call in calls)
    assert any(call.startswith("recon:0.5") for call in calls)
    stderr = (capsys.readouterr().err or "").lower()
    assert "exception in thread" not in stderr
    assert "fatal python error" not in stderr
