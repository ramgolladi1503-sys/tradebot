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
    details: dict[str, Any] = {"args_count": len(args), "kwargs": sorted(str(key) for key in kwargs.keys())}
    if args and isinstance(args[0], str):
        details["symbol"] = str(args[0]).upper()
    if "symbol" in kwargs:
        details["symbol"] = str(kwargs.get("symbol") or "").upper()
    if "symbols" in kwargs:
        symbols = kwargs.get("symbols")
        if isinstance(symbols, (list, tuple, set)):
            details["symbol_count"] = len(symbols)
            details["symbols_sample"] = [str(item).upper() for item in list(symbols)[:10] if str(item).strip()]
    for key in ("interval", "startup_phase", "market_mode", "force"):
        if key in kwargs:
            details[key] = kwargs.get(key)
    return details


def _result_details(result: Any) -> dict[str, Any]:
    try:
        if isinstance(result, (list, tuple, set, dict)):
            return {"result_count": len(result)}
        if result is not None:
            return {"result_type": type(result).__name__}
    except Exception:
        pass
    return {}


def _wrap(module: Any, attr_name: str, started: str, completed: str, failed: str) -> None:
    original = getattr(module, attr_name, None)
    if original is None or getattr(original, "_edge25_warmup_wrapped", False):
        return

    def wrapped(*args, **kwargs):
        _record(started, source=f"core.market_data_warmup_probe.{attr_name}", details=_safe_details(tuple(args), dict(kwargs)))
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            _record(failed, source=f"core.market_data_warmup_probe.{attr_name}", error=f"{type(exc).__name__}:{exc}")
            raise
        _record(completed, source=f"core.market_data_warmup_probe.{attr_name}", details=_result_details(result))
        return result

    wrapped._edge25_warmup_wrapped = True  # type: ignore[attr-defined]
    setattr(module, attr_name, wrapped)


def install_market_data_warmup_probe(module: Any | None = None) -> None:
    global _PATCHED
    if _PATCHED:
        return
    if module is None:
        try:
            import core.market_data as module  # type: ignore[no-redef]
        except Exception:
            return
    _wrap(module, "ensure_startup_warmup_bootstrap", "MARKET_DATA_WARMUP_ENTERED", "MARKET_DATA_WARMUP_COMPLETED", "MARKET_DATA_WARMUP_FAILED")
    _wrap(module, "_startup_warmup_symbols", "MARKET_DATA_WARMUP_SYMBOLS_RESOLVE_STARTED", "MARKET_DATA_WARMUP_SYMBOLS_RESOLVE_COMPLETED", "MARKET_DATA_WARMUP_SYMBOLS_RESOLVE_FAILED")
    _wrap(module, "seed_ohlc_buffers_on_startup", "MARKET_DATA_WARMUP_SEED_STARTED", "MARKET_DATA_WARMUP_SEED_COMPLETED", "MARKET_DATA_WARMUP_SEED_FAILED")
    _wrap(module, "_warm_seed_ohlc_from_history", "MARKET_DATA_WARMUP_SYMBOL_SEED_STARTED", "MARKET_DATA_WARMUP_SYMBOL_SEED_COMPLETED", "MARKET_DATA_WARMUP_SYMBOL_SEED_FAILED")
    _wrap(module, "compute_indicators", "MARKET_DATA_WARMUP_INDICATORS_STARTED", "MARKET_DATA_WARMUP_INDICATORS_COMPLETED", "MARKET_DATA_WARMUP_INDICATORS_FAILED")
    _PATCHED = True


__all__ = ["install_market_data_warmup_probe"]
