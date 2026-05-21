from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from typing import Any, Callable

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


def _wrap_callable(
    *,
    module: Any,
    attr_name: str,
    started_event: str,
    completed_event: str,
    failed_event: str,
) -> None:
    original = getattr(module, attr_name, None)
    if original is None or getattr(original, "_edge23_stage_probe_wrapped", False):
        return

    def wrapped(*args, **kwargs):
        _record(
            started_event,
            source=f"core.orchestrator_startup_probe.{attr_name}",
            details={"args_count": len(args), "kwargs": sorted(str(key) for key in kwargs.keys())},
        )
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            _record(
                failed_event,
                source=f"core.orchestrator_startup_probe.{attr_name}",
                error=f"{type(exc).__name__}:{exc}",
            )
            raise
        _record(completed_event, source=f"core.orchestrator_startup_probe.{attr_name}")
        return result

    wrapped._edge23_stage_probe_wrapped = True  # type: ignore[attr-defined]
    setattr(module, attr_name, wrapped)


def _wrap_class_constructor(
    *,
    module: Any,
    attr_name: str,
    started_event: str,
    completed_event: str,
    failed_event: str,
) -> None:
    original_cls = getattr(module, attr_name, None)
    if original_cls is None or getattr(original_cls, "_edge23_stage_probe_wrapped", False):
        return

    class StageProbeWrapper(original_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            _record(
                started_event,
                source=f"core.orchestrator_startup_probe.{attr_name}.__init__",
                details={"args_count": len(args), "kwargs": sorted(str(key) for key in kwargs.keys())},
            )
            try:
                super().__init__(*args, **kwargs)
            except Exception as exc:
                _record(
                    failed_event,
                    source=f"core.orchestrator_startup_probe.{attr_name}.__init__",
                    error=f"{type(exc).__name__}:{exc}",
                )
                raise
            _record(completed_event, source=f"core.orchestrator_startup_probe.{attr_name}.__init__")

    StageProbeWrapper.__name__ = getattr(original_cls, "__name__", attr_name)
    StageProbeWrapper.__qualname__ = getattr(original_cls, "__qualname__", attr_name)
    StageProbeWrapper.__module__ = getattr(original_cls, "__module__", "core.orchestrator")
    StageProbeWrapper._edge23_stage_probe_wrapped = True  # type: ignore[attr-defined]
    setattr(module, attr_name, StageProbeWrapper)


def _wrap_orchestrator_method(
    *,
    cls: Any,
    method_name: str,
    started_event: str,
    completed_event: str,
    failed_event: str,
) -> None:
    original = getattr(cls, method_name, None)
    if original is None or getattr(original, "_edge23_stage_probe_wrapped", False):
        return

    def wrapped(self, *args, **kwargs):
        _record(
            started_event,
            source=f"core.orchestrator_startup_probe.Orchestrator.{method_name}",
            details={"args_count": len(args), "kwargs": sorted(str(key) for key in kwargs.keys())},
        )
        try:
            result = original(self, *args, **kwargs)
        except Exception as exc:
            _record(
                failed_event,
                source=f"core.orchestrator_startup_probe.Orchestrator.{method_name}",
                error=f"{type(exc).__name__}:{exc}",
            )
            raise
        _record(completed_event, source=f"core.orchestrator_startup_probe.Orchestrator.{method_name}")
        return result

    wrapped._edge23_stage_probe_wrapped = True  # type: ignore[attr-defined]
    setattr(cls, method_name, wrapped)


def _patch_orchestrator_stages(module: Any, cls: Any) -> None:
    _wrap_callable(
        module=module,
        attr_name="auto_clear_risk_halt_if_safe",
        started_event="ORCHESTRATOR_SESSION_GUARD_STARTED",
        completed_event="ORCHESTRATOR_SESSION_GUARD_COMPLETED",
        failed_event="ORCHESTRATOR_SESSION_GUARD_FAILED",
    )
    _wrap_callable(
        module=module,
        attr_name="ensure_trade_log_exists",
        started_event="ORCHESTRATOR_TRADE_LOG_READY_STARTED",
        completed_event="ORCHESTRATOR_TRADE_LOG_READY_COMPLETED",
        failed_event="ORCHESTRATOR_TRADE_LOG_READY_FAILED",
    )
    _wrap_callable(
        module=module,
        attr_name="validate_and_repair_event_log",
        started_event="ORCHESTRATOR_EVENT_LOG_REPAIR_STARTED",
        completed_event="ORCHESTRATOR_EVENT_LOG_REPAIR_COMPLETED",
        failed_event="ORCHESTRATOR_EVENT_LOG_REPAIR_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="RiskState",
        started_event="ORCHESTRATOR_RISK_STATE_INIT_STARTED",
        completed_event="ORCHESTRATOR_RISK_STATE_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_RISK_STATE_INIT_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="TradePredictor",
        started_event="ORCHESTRATOR_PREDICTOR_INIT_STARTED",
        completed_event="ORCHESTRATOR_PREDICTOR_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_PREDICTOR_INIT_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="ExecutionEngine",
        started_event="ORCHESTRATOR_EXECUTION_ENGINE_INIT_STARTED",
        completed_event="ORCHESTRATOR_EXECUTION_ENGINE_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_EXECUTION_ENGINE_INIT_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="ExecutionRouter",
        started_event="ORCHESTRATOR_EXECUTION_ROUTER_INIT_STARTED",
        completed_event="ORCHESTRATOR_EXECUTION_ROUTER_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_EXECUTION_ROUTER_INIT_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="StrategyGatekeeper",
        started_event="ORCHESTRATOR_GATEKEEPER_INIT_STARTED",
        completed_event="ORCHESTRATOR_GATEKEEPER_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_GATEKEEPER_INIT_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="StrategyTracker",
        started_event="ORCHESTRATOR_STRATEGY_TRACKER_INIT_STARTED",
        completed_event="ORCHESTRATOR_STRATEGY_TRACKER_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_STRATEGY_TRACKER_INIT_FAILED",
    )
    _wrap_class_constructor(
        module=module,
        attr_name="TradeBuilder",
        started_event="ORCHESTRATOR_TRADE_BUILDER_INIT_STARTED",
        completed_event="ORCHESTRATOR_TRADE_BUILDER_INIT_COMPLETED",
        failed_event="ORCHESTRATOR_TRADE_BUILDER_INIT_FAILED",
    )
    _wrap_orchestrator_method(
        cls=cls,
        method_name="_run_preopen_auth_warm_check",
        started_event="ORCHESTRATOR_AUTH_WARM_CHECK_STARTED",
        completed_event="ORCHESTRATOR_AUTH_WARM_CHECK_COMPLETED",
        failed_event="ORCHESTRATOR_AUTH_WARM_CHECK_FAILED",
    )
    _wrap_orchestrator_method(
        cls=cls,
        method_name="_run_startup_warmup_bootstrap",
        started_event="ORCHESTRATOR_WARMUP_STARTED",
        completed_event="ORCHESTRATOR_WARMUP_COMPLETED",
        failed_event="ORCHESTRATOR_WARMUP_FAILED",
    )
    _wrap_orchestrator_method(
        cls=cls,
        method_name="_start_depth_ws_or_raise",
        started_event="FEED_START_REQUEST_BOUNDARY_REACHED",
        completed_event="ORCHESTRATOR_DEPTH_START_BOUNDARY_COMPLETED",
        failed_event="ORCHESTRATOR_DEPTH_START_BOUNDARY_FAILED",
    )


def _patch_orchestrator_module(module: Any) -> None:
    global _PATCHED
    if _PATCHED:
        return
    cls = getattr(module, "Orchestrator", None)
    if cls is None:
        return

    _patch_orchestrator_stages(module, cls)

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
