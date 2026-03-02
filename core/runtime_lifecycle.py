from __future__ import annotations

import atexit
import threading
from dataclasses import dataclass
from typing import Callable


StopFn = Callable[[], None]
JoinFn = Callable[[float], None] | Callable[[], None]


@dataclass
class _ManagedHandle:
    name: str
    stop_fn: StopFn
    join_fn: JoinFn | None
    thread: threading.Thread | None = None


class RuntimeLifecycle:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handles: list[_ManagedHandle] = []

    def register(
        self,
        name: str,
        stop_fn: StopFn,
        join_fn: JoinFn | None = None,
        thread: threading.Thread | None = None,
    ) -> None:
        if not callable(stop_fn):
            return
        handle_name = str(name or "runtime-handle")
        with self._lock:
            self._handles = [h for h in self._handles if h.name != handle_name]
            self._handles.append(
                _ManagedHandle(
                    name=handle_name,
                    stop_fn=stop_fn,
                    join_fn=join_fn if callable(join_fn) else None,
                    thread=thread if isinstance(thread, threading.Thread) else None,
                )
            )

    # Backward-compatible wrappers used by existing call sites.
    def register_thread(self, name: str, thread: threading.Thread | None, stop_fn: StopFn) -> None:
        if thread is None:
            return

        def _join(timeout_sec: float = 3.0) -> None:
            if thread.is_alive():
                thread.join(max(0.0, float(timeout_sec)))

        self.register(name=name, stop_fn=stop_fn, join_fn=_join, thread=thread)

    def register_resource(self, name: str, close_fn: StopFn) -> None:
        self.register(name=name, stop_fn=close_fn, join_fn=None)

    def active_thread_names(self) -> list[str]:
        with self._lock:
            handles = list(self._handles)
        out: list[str] = []
        for handle in handles:
            thread = handle.thread
            if thread is not None and thread.is_alive():
                out.append(str(handle.name))
        return sorted(set(out))

    def stop_all(self, timeout: float = 3.0) -> None:
        timeout_sec = max(0.0, float(timeout))
        with self._lock:
            handles = list(self._handles)
            self._handles.clear()

        for handle in reversed(handles):
            try:
                handle.stop_fn()
            except Exception:
                pass

        for handle in reversed(handles):
            if handle.join_fn is None:
                continue
            try:
                handle.join_fn(timeout_sec)  # type: ignore[misc]
                continue
            except TypeError:
                pass
            except Exception:
                continue
            try:
                handle.join_fn()  # type: ignore[misc]
            except Exception:
                pass


lifecycle = RuntimeLifecycle()


def get_lifecycle() -> RuntimeLifecycle:
    return lifecycle


def _stop_all_atexit() -> None:
    try:
        lifecycle.stop_all(timeout=3.0)
    except Exception:
        pass


atexit.register(_stop_all_atexit)
