from __future__ import annotations

import atexit
import importlib
import threading
from dataclasses import dataclass
from typing import Callable

from core.runtime_lifecycle import RuntimeLifecycle, lifecycle as _runtime_lifecycle


StopFn = Callable[[], None]
ShutdownHookFn = Callable[[float, str], None]


@dataclass(frozen=True)
class _ShutdownHook:
    name: str
    fn: ShutdownHookFn


def _safe_stop_depth_ws(reason: str) -> None:
    try:
        module = importlib.import_module("core.kite_depth_ws")
        stop_fn = getattr(module, "stop_depth_ws", None)
        if callable(stop_fn):
            stop_fn(reason=reason)
    except Exception:
        # Shutdown must be best-effort and idempotent.
        pass


def _safe_stop_reconciliation_daemon(timeout_sec: float) -> None:
    try:
        module = importlib.import_module("core.order_reconciliation_daemon")
        stop_fn = getattr(module, "stop_reconciliation_daemon", None)
        if callable(stop_fn):
            stop_fn(timeout_sec=float(timeout_sec))
    except Exception:
        # Shutdown must be best-effort and idempotent.
        pass


class Lifecycle:
    """
    Unified lifecycle facade used by tests and runtime shutdown paths.

    It wraps the existing runtime lifecycle registry and adds explicit
    best-effort stop hooks for known long-running background components.
    """

    def __init__(self, runtime: RuntimeLifecycle | None = None) -> None:
        self._runtime = runtime or RuntimeLifecycle()
        self._hooks_lock = threading.RLock()
        self._hooks: list[_ShutdownHook] = []

    def register_thread(self, name: str, thread: threading.Thread | None, stop_fn: StopFn) -> None:
        self._runtime.register_thread(name=name, thread=thread, stop_fn=stop_fn)

    def register_resource(self, name: str, close_fn: StopFn) -> None:
        self._runtime.register_resource(name=name, close_fn=close_fn)

    def register(
        self,
        name: str,
        stop_fn: StopFn,
        join_fn: Callable[[float], None] | Callable[[], None] | None = None,
        thread: threading.Thread | None = None,
    ) -> None:
        self._runtime.register(name=name, stop_fn=stop_fn, join_fn=join_fn, thread=thread)

    def register_shutdown_hook(self, name: str, fn: ShutdownHookFn) -> None:
        if not callable(fn):
            return
        hook_name = str(name or "shutdown-hook")
        with self._hooks_lock:
            self._hooks = [hook for hook in self._hooks if hook.name != hook_name]
            self._hooks.append(_ShutdownHook(name=hook_name, fn=fn))

    def active_thread_names(self) -> list[str]:
        return self._runtime.active_thread_names()

    def stop_all(self, timeout: float = 3.0, reason: str = "lifecycle_stop") -> None:
        timeout_sec = max(0.0, float(timeout))
        with self._hooks_lock:
            hooks = list(self._hooks)
        for hook in reversed(hooks):
            try:
                hook.fn(timeout_sec, str(reason))
            except Exception:
                pass
        self._runtime.stop_all(timeout=timeout_sec)


lifecycle = Lifecycle(runtime=_runtime_lifecycle)
lifecycle.register_shutdown_hook(
    "depth_ws",
    lambda timeout_sec, reason: _safe_stop_depth_ws(reason=reason),
)
lifecycle.register_shutdown_hook(
    "order_reconciliation_daemon",
    lambda timeout_sec, reason: _safe_stop_reconciliation_daemon(timeout_sec=timeout_sec),
)


def stop_all(timeout: float = 3.0, reason: str = "lifecycle_stop") -> None:
    lifecycle.stop_all(timeout=timeout, reason=reason)


def _atexit_stop_all() -> None:
    try:
        stop_all(timeout=3.0, reason="atexit")
    except Exception:
        pass


atexit.register(_atexit_stop_all)


__all__ = ["Lifecycle", "lifecycle", "stop_all"]
