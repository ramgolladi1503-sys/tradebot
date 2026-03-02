from __future__ import annotations

import threading

from core.runtime.lifecycle import Lifecycle


def _worker(stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            stop_event.wait(0.01)
    finally:
        return


def test_no_thread_teardown_noise(capsys):
    lifecycle = Lifecycle()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_worker,
        args=(stop_event,),
        name="teardown-noise-stub",
        daemon=False,
    )
    thread.start()
    lifecycle.register_thread("teardown-noise-stub", thread, stop_event.set)
    lifecycle.stop_all(timeout=1.0)

    assert not thread.is_alive()
    stderr = (capsys.readouterr().err or "").lower()
    assert "exception in thread" not in stderr
    assert "fatal python error" not in stderr

