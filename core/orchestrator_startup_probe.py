from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from typing import Any

_PROBE_INSTALLED = False
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


def _safe_init_details(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {
        "args_count": max(0, len(args) - 1),
        "kwargs": sorted(str(key) for key in kwargs.keys()),
    }
    if len(args) > 1:
        try:
            details["total_capital"] = float(args[1])
        except Exception:
            details["total_capital_present"] = True
    if len(args) > 2:
        try:
            details["poll_interval"] = float(args[2])
        except Exception:
            details["poll_interval_present"] = True
    if "total_capital" in kwargs:
        try:
            details["total_capital"] = float(kwargs.get("total_capital"))
        except Exception:
            details["total_capital_present"] = True
    if "poll_interval" in kwargs:
        try:
            details["poll_interval"] = float(kwargs.get("poll_interval"))
        except Exception:
            details["poll_interval_present"] = True
    return details


def _patch_orchestrator_module(module: Any) -> None:
    global _PATCHED
    if _PATCHED:
        return
    cls = getattr(module, "Orchestrator", None)
    if cls is None:
        return

    original_init = getattr(cls, "__init__", None)
    if original_init is None or getattr(original_init, "_edge20_probe_wrapped", False):
        _PATCHED = True
        return

    def wrapped_init(self, *args, **kwargs):
        _record(
            "ORCHESTRATOR_INIT_ENTERED",
            source="core.orchestrator_startup_probe.Orchestrator.__init__",
            details=_safe_init_details((self, *args), dict(kwargs)),
        )
        try:
            result = original_init(self, *args, **kwargs)
        except Exception as exc:
            _record(
                "ORCHESTRATOR_INIT_FAILED",
                source="core.orchestrator_startup_probe.Orchestrator.__init__",
                error=f"{type(exc).__name__}:{exc}",
            )
            raise
        _record(
            "ORCHESTRATOR_INIT_COMPLETED",
            source="core.orchestrator_startup_probe.Orchestrator.__init__",
            details={
                "predictor_ready": hasattr(self, "predictor"),
                "execution_engine_ready": hasattr(self, "execution_engine"),
                "execution_router_ready": hasattr(self, "execution_router"),
                "trade_builder_ready": hasattr(self, "trade_builder"),
                "risk_state_ready": hasattr(self, "risk_state"),
            },
        )
        return result

    wrapped_init._edge20_probe_wrapped = True  # type: ignore[attr-defined]
    cls.__init__ = wrapped_init

    original_live_monitoring = getattr(cls, "live_monitoring", None)
    if original_live_monitoring is not None and not getattr(original_live_monitoring, "_edge20_probe_wrapped", False):
        def wrapped_live_monitoring(self, *args, **kwargs):
            _record(
                "LIVE_MONITORING_CALLING",
                source="core.orchestrator_startup_probe.Orchestrator.live_monitoring",
                details={"args_count": len(args), "kwargs": sorted(str(key) for key in kwargs.keys())},
            )
            try:
                result = original_live_monitoring(self, *args, **kwargs)
            except Exception as exc:
                _record(
                    "LIVE_MONITORING_CALL_FAILED",
                    source="core.orchestrator_startup_probe.Orchestrator.live_monitoring",
                    error=f"{type(exc).__name__}:{exc}",
                )
                raise
            _record(
                "LIVE_MONITORING_RETURNED",
                source="core.orchestrator_startup_probe.Orchestrator.live_monitoring",
                details={"result": str(result)},
            )
            return result

        wrapped_live_monitoring._edge20_probe_wrapped = True  # type: ignore[attr-defined]
        cls.live_monitoring = wrapped_live_monitoring

    _PATCHED = True


class _ProbeLoader(importlib.abc.Loader):
    def __init__(self, wrapped_loader: importlib.abc.Loader) -> None:
        self._wrapped_loader = wrapped_loader

    def create_module(self, spec):
        create_module = getattr(self._wrapped_loader, "create_module", None)
        if create_module is None:
            return None
        return create_module(spec)

    def exec_module(self, module) -> None:
        self._wrapped_loader.exec_module(module)  # type: ignore[attr-defined]
        _patch_orchestrator_module(module)


class _ProbeFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "core.orchestrator":
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        if isinstance(spec.loader, _ProbeLoader):
            return spec
        spec.loader = _ProbeLoader(spec.loader)  # type: ignore[assignment]
        return spec


def install_orchestrator_startup_probe() -> None:
    global _PROBE_INSTALLED
    if _PROBE_INSTALLED:
        return
    if "core.orchestrator" in sys.modules:
        _patch_orchestrator_module(sys.modules["core.orchestrator"])
        _PROBE_INSTALLED = True
        return
    sys.meta_path.insert(0, _ProbeFinder())
    _PROBE_INSTALLED = True


__all__ = ["install_orchestrator_startup_probe"]
