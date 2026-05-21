from __future__ import annotations

from typing import Any

_PATCHED = False


def _record(event: str, *, source: str, details: dict[str, Any] | None = None, error: str | None = None) -> None:
    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        payload = {"is_order_action": False}
        if details:
            payload.update(dict(details))
        record_runtime_startup_event(event, source=source, details=payload, error=error)
    except Exception:
        pass


def _safe_details(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {
        "args_count": max(0, len(args) - 1),
        "kwargs": sorted(str(key) for key in kwargs.keys()),
    }
    if args:
        details["instance_type"] = type(args[0]).__name__
    for key in ("mode", "execution_mode", "trading_mode", "limit", "include_terminal"):
        if key in kwargs:
            details[key] = kwargs.get(key)
    return details


def _result_details(result: Any) -> dict[str, Any]:
    details: dict[str, Any] = {}
    try:
        if isinstance(result, (list, tuple, set, dict)):
            details["result_count"] = len(result)
        elif result is not None:
            details["result_type"] = type(result).__name__
    except Exception:
        pass
    for attr, key in (
        ("scanned_orders", "scanned_orders"),
        ("corrections", "corrections"),
        ("errors", "errors"),
        ("broker_open_orders", "broker_open_orders"),
        ("broker_positions", "broker_positions"),
        ("started_at", "started_at"),
        ("ended_at", "ended_at"),
    ):
        try:
            if hasattr(result, attr):
                details[key] = getattr(result, attr)
        except Exception:
            pass
    try:
        if "started_at" in details and "ended_at" in details:
            details["duration_ms"] = round((float(details["ended_at"]) - float(details["started_at"])) * 1000.0, 3)
    except Exception:
        pass
    return details


def _wrap_method(cls: Any, method_name: str, started: str, completed: str, failed: str) -> None:
    original = getattr(cls, method_name, None)
    if original is None or getattr(original, "_edge27_recon_once_wrapped", False):
        return

    def wrapped(self, *args, **kwargs):
        _record(started, source=f"core.recon_once_probe.{cls.__name__}.{method_name}", details=_safe_details((self, *args), dict(kwargs)))
        try:
            result = original(self, *args, **kwargs)
        except Exception as exc:
            _record(failed, source=f"core.recon_once_probe.{cls.__name__}.{method_name}", error=f"{type(exc).__name__}:{exc}")
            raise
        _record(completed, source=f"core.recon_once_probe.{cls.__name__}.{method_name}", details=_result_details(result))
        return result

    wrapped._edge27_recon_once_wrapped = True  # type: ignore[attr-defined]
    setattr(cls, method_name, wrapped)


def install_recon_once_probe(module: Any | None = None) -> None:
    global _PATCHED
    if _PATCHED:
        return
    if module is None:
        try:
            import core.order_reconciliation_daemon as module  # type: ignore[no-redef]
        except Exception:
            return

    daemon_cls = getattr(module, "OrderReconciliationDaemon", None)
    if daemon_cls is not None:
        _wrap_method(
            daemon_cls,
            "run_cycle_once",
            "RECON_ONCE_ENTERED",
            "RECON_ONCE_COMPLETED",
            "RECON_ONCE_FAILED",
        )
        _wrap_method(
            daemon_cls,
            "_resolve_broker_api",
            "RECON_ONCE_BROKER_RESOLVE_STARTED",
            "RECON_ONCE_BROKER_RESOLVE_COMPLETED",
            "RECON_ONCE_BROKER_RESOLVE_FAILED",
        )
        _wrap_method(
            daemon_cls,
            "_fetch_broker_orders",
            "RECON_ONCE_BROKER_ORDERS_FETCH_STARTED",
            "RECON_ONCE_BROKER_ORDERS_FETCH_COMPLETED",
            "RECON_ONCE_BROKER_ORDERS_FETCH_FAILED",
        )
        _wrap_method(
            daemon_cls,
            "_fetch_broker_positions",
            "RECON_ONCE_BROKER_POSITIONS_FETCH_STARTED",
            "RECON_ONCE_BROKER_POSITIONS_FETCH_COMPLETED",
            "RECON_ONCE_BROKER_POSITIONS_FETCH_FAILED",
        )
        _wrap_method(
            daemon_cls,
            "_write_log",
            "RECON_ONCE_WRITE_STARTED",
            "RECON_ONCE_WRITE_COMPLETED",
            "RECON_ONCE_WRITE_FAILED",
        )

    order_state_machine_cls = getattr(module, "OrderStateMachine", None)
    if order_state_machine_cls is not None:
        _wrap_method(
            order_state_machine_cls,
            "list_orders",
            "RECON_ONCE_LOCAL_STATE_LOAD_STARTED",
            "RECON_ONCE_LOCAL_STATE_LOAD_COMPLETED",
            "RECON_ONCE_LOCAL_STATE_LOAD_FAILED",
        )

    _PATCHED = True


__all__ = ["install_recon_once_probe"]
