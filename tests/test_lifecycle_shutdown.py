from __future__ import annotations

import threading

from core.runtime.lifecycle import Lifecycle


def _loop_until_stopped(stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            stop_event.wait(0.02)
    finally:
        # Explicit finally to ensure thread exits cleanly on teardown.
        return


def test_lifecycle_stops_registered_threads_in_reverse_order():
    lifecycle = Lifecycle()
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

    lifecycle.register_thread(
        "depth-ws-stub",
        depth_thread,
        lambda: (stop_order.append("depth-ws-stub"), depth_stop.set()),
    )
    lifecycle.register_thread(
        "recon-daemon-stub",
        recon_thread,
        lambda: (stop_order.append("recon-daemon-stub"), recon_stop.set()),
    )

    lifecycle.stop_all(timeout=1.0)

    assert stop_order[:2] == ["recon-daemon-stub", "depth-ws-stub"]
    assert not depth_thread.is_alive()
    assert not recon_thread.is_alive()

