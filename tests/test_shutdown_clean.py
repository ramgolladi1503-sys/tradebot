from __future__ import annotations

import threading

from core.runtime_lifecycle import lifecycle


def _wait_until_stopped(stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            stop_event.wait(0.02)
    finally:
        return


def test_lifecycle_stop_all_shuts_down_registered_threads():
    lifecycle.stop_all(timeout=0.1)
    ws_stop = threading.Event()
    recon_stop = threading.Event()

    ws_thread = threading.Thread(
        target=_wait_until_stopped,
        args=(ws_stop,),
        name="kite-depth-watchdog-stub",
        daemon=False,
    )
    recon_thread = threading.Thread(
        target=_wait_until_stopped,
        args=(recon_stop,),
        name="order-reconciliation-daemon-stub",
        daemon=False,
    )
    ws_thread.start()
    recon_thread.start()

    lifecycle.register(
        "kite-depth-watchdog-stub",
        stop_fn=ws_stop.set,
        join_fn=lambda timeout_sec=1.0: ws_thread.join(timeout_sec),
    )
    lifecycle.register(
        "order-reconciliation-daemon-stub",
        stop_fn=recon_stop.set,
        join_fn=lambda timeout_sec=1.0: recon_thread.join(timeout_sec),
    )

    lifecycle.stop_all(timeout=1.0)

    assert not ws_thread.is_alive()
    assert not recon_thread.is_alive()
    active_names = {thread.name for thread in threading.enumerate()}
    assert "kite-depth-watchdog-stub" not in active_names
    assert "order-reconciliation-daemon-stub" not in active_names

