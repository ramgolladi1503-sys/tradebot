"""Pure live indicator readiness diagnostics for HOTFIX/EDGE-79A."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

LIVE_INDICATOR_READINESS_SCHEMA_VERSION = 1
LIVE_INDICATOR_READINESS_SOURCE = "live_indicator_readiness_diagnostics_v1"

INDICATOR_READY = "INDICATOR_READY"
INDICATOR_BLOCKED = "INDICATOR_BLOCKED"

INDICATOR_EMPTY_INPUT = "indicator_empty_input"
INDICATOR_SYMBOL_MISSING = "indicator_symbol_missing"
INDICATOR_INPUTS_MISSING = "indicator_inputs_missing"
INDICATOR_BARS_BELOW_WARMUP = "indicator_bars_below_warmup"
INDICATOR_LAST_UPDATE_MISSING = "indicator_last_update_missing"
INDICATOR_STALE = "indicator_stale"
INDICATOR_COMPUTE_ERROR = "indicator_compute_error"
INDICATOR_VALUE_MISSING = "indicator_value_missing"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_REQUIRED_INPUTS = ("ohlc_bars",)
_REQUIRED_INDICATORS = ("vwap", "rsi", "ema", "atr")


@dataclass(frozen=True)
class LiveIndicatorReadinessDecision:
    symbol: str
    status: str
    indicators_ok: bool
    indicator_inputs_ok: bool
    ohlc_bars_count: int
    warmup_min_bars: int
    indicator_last_update_epoch: float | None
    indicators_age_sec: float | None
    missing_inputs: tuple[str, ...]
    indicator_missing_inputs: tuple[str, ...]
    compute_indicators_error: str
    vwap_present: bool
    rsi_present: bool
    ema_present: bool
    atr_present: bool
    decision_gate_reason: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = LIVE_INDICATOR_READINESS_SOURCE

    @property
    def ready(self) -> bool:
        return self.status == INDICATOR_READY and self.indicators_ok and self.indicator_inputs_ok and not self.blockers

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "symbol": self.symbol,
            "status": self.status,
            "ready": self.ready,
            "indicators_ok": self.indicators_ok,
            "indicator_inputs_ok": self.indicator_inputs_ok,
            "ohlc_bars_count": self.ohlc_bars_count,
            "warmup_min_bars": self.warmup_min_bars,
            "indicator_last_update_epoch": self.indicator_last_update_epoch,
            "indicators_age_sec": self.indicators_age_sec,
            "missing_inputs": list(self.missing_inputs),
            "indicator_missing_inputs": list(self.indicator_missing_inputs),
            "compute_indicators_error": self.compute_indicators_error,
            "vwap_present": self.vwap_present,
            "rsi_present": self.rsi_present,
            "ema_present": self.ema_present,
            "atr_present": self.atr_present,
            "decision_gate_reason": self.decision_gate_reason,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class LiveIndicatorReadinessReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    decisions: tuple[LiveIndicatorReadinessDecision, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def ready_decisions(self) -> tuple[LiveIndicatorReadinessDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.ready)

    @property
    def blocked_decisions(self) -> tuple[LiveIndicatorReadinessDecision, ...]:
        return tuple(decision for decision in self.decisions if not decision.ready)

    @property
    def indicators_ready(self) -> bool:
        return not self.blockers and bool(self.ready_decisions) and not self.blocked_decisions

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def get(self, symbol: str) -> LiveIndicatorReadinessDecision | None:
        wanted = _symbol_key(symbol)
        return next((decision for decision in self.decisions if decision.symbol == wanted), None)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "indicators_ready": self.indicators_ready,
            "decision_count": len(self.decisions),
            "ready_count": len(self.ready_decisions),
            "blocked_count": len(self.blocked_decisions),
            "symbols": [decision.symbol for decision in self.decisions],
            "ready_symbols": [decision.symbol for decision in self.ready_decisions],
            "blocked_symbols": [decision.symbol for decision in self.blocked_decisions],
            "decisions": [decision.to_payload() for decision in self.decisions],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload


def build_live_indicator_readiness_report(
    symbol_snapshots: Iterable[Mapping[str, Any]],
    *,
    now_epoch: float | None = None,
    warmup_min_bars: int = 50,
    max_indicator_age_sec: float = 120.0,
    source: str = LIVE_INDICATOR_READINESS_SOURCE,
) -> LiveIndicatorReadinessReport:
    """Return per-symbol indicator readiness diagnostics without runtime side effects."""

    snapshots = tuple(symbol_snapshots or ())
    now_value = float(time.time() if now_epoch is None else now_epoch)
    if not snapshots:
        return LiveIndicatorReadinessReport(
            schema_version=LIVE_INDICATOR_READINESS_SCHEMA_VERSION,
            read_only=True,
            append=False,
            source=source,
            decisions=(),
            blockers=(INDICATOR_EMPTY_INPUT,),
            warnings=(),
            metadata=_metadata(warmup_min_bars=warmup_min_bars, max_indicator_age_sec=max_indicator_age_sec),
            generated_epoch=now_value,
        )

    decisions = tuple(
        _decision_for_snapshot(
            snapshot,
            now_epoch=now_value,
            warmup_min_bars=max(0, int(warmup_min_bars)),
            max_indicator_age_sec=float(max_indicator_age_sec),
            source=source,
        )
        for snapshot in snapshots
    )
    return LiveIndicatorReadinessReport(
        schema_version=LIVE_INDICATOR_READINESS_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        decisions=tuple(sorted(decisions, key=lambda item: item.symbol)),
        blockers=(),
        warnings=(),
        metadata=_metadata(warmup_min_bars=warmup_min_bars, max_indicator_age_sec=max_indicator_age_sec),
        generated_epoch=now_value,
    )


def _decision_for_snapshot(
    snapshot: Mapping[str, Any],
    *,
    now_epoch: float,
    warmup_min_bars: int,
    max_indicator_age_sec: float,
    source: str,
) -> LiveIndicatorReadinessDecision:
    symbol = _symbol_key(snapshot.get("symbol"))
    ohlc_bars_count = _count_bars(snapshot.get("ohlc_bars"), snapshot.get("ohlc_bars_count"))
    indicator_last_update_epoch = _finite_float_or_none(
        snapshot.get("indicator_last_update_epoch", snapshot.get("last_update_epoch"))
    )
    indicators_age_sec = None if indicator_last_update_epoch is None else max(0.0, now_epoch - indicator_last_update_epoch)
    compute_error = str(snapshot.get("compute_indicators_error") or "").strip()

    present = {
        "vwap": _present(snapshot.get("vwap")),
        "rsi": _present(snapshot.get("rsi")),
        "ema": _present(snapshot.get("ema")),
        "atr": _present(snapshot.get("atr")),
    }
    missing_inputs = _missing_inputs(snapshot)
    indicator_missing_inputs = tuple(name for name in _REQUIRED_INDICATORS if not present[name])

    blockers: list[str] = []
    if not symbol:
        blockers.append(INDICATOR_SYMBOL_MISSING)
    if missing_inputs:
        blockers.append(INDICATOR_INPUTS_MISSING)
    if ohlc_bars_count < warmup_min_bars:
        blockers.append(INDICATOR_BARS_BELOW_WARMUP)
    if indicator_last_update_epoch is None:
        blockers.append(INDICATOR_LAST_UPDATE_MISSING)
    elif indicators_age_sec is not None and indicators_age_sec > max_indicator_age_sec:
        blockers.append(INDICATOR_STALE)
    if compute_error:
        blockers.append(INDICATOR_COMPUTE_ERROR)
    if indicator_missing_inputs:
        blockers.append(INDICATOR_VALUE_MISSING)

    indicators_ok = not (indicator_missing_inputs or compute_error or INDICATOR_LAST_UPDATE_MISSING in blockers or INDICATOR_STALE in blockers)
    indicator_inputs_ok = not (missing_inputs or INDICATOR_BARS_BELOW_WARMUP in blockers)
    status = INDICATOR_READY if indicators_ok and indicator_inputs_ok and not blockers else INDICATOR_BLOCKED
    return LiveIndicatorReadinessDecision(
        symbol=symbol or "UNKNOWN",
        status=status,
        indicators_ok=indicators_ok,
        indicator_inputs_ok=indicator_inputs_ok,
        ohlc_bars_count=ohlc_bars_count,
        warmup_min_bars=warmup_min_bars,
        indicator_last_update_epoch=indicator_last_update_epoch,
        indicators_age_sec=indicators_age_sec,
        missing_inputs=missing_inputs,
        indicator_missing_inputs=indicator_missing_inputs,
        compute_indicators_error=compute_error,
        vwap_present=present["vwap"],
        rsi_present=present["rsi"],
        ema_present=present["ema"],
        atr_present=present["atr"],
        decision_gate_reason=_decision_gate_reason(blockers),
        blockers=_dedupe(blockers),
        metadata={
            "max_indicator_age_sec": max_indicator_age_sec,
            "does_not_compute_indicators": True,
            "does_not_touch_runtime": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
        },
        source=source,
    )


def _missing_inputs(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    missing: list[str] = []
    for name in _REQUIRED_INPUTS:
        value = snapshot.get(name)
        if value is None or value == () or value == []:
            if snapshot.get(f"{name}_count") in (None, 0, "0"):
                missing.append(name)
    return tuple(sorted(missing))


def _count_bars(raw_bars: Any, explicit_count: Any) -> int:
    explicit = _int_or_none(explicit_count)
    if explicit is not None:
        return max(0, explicit)
    if raw_bars is None:
        return 0
    if isinstance(raw_bars, (str, bytes)):
        return 0
    try:
        return max(0, len(raw_bars))
    except TypeError:
        return 0


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return _finite_float_or_none(value) is not None or not isinstance(value, (int, float, str))


def _finite_float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decision_gate_reason(blockers: list[str]) -> str:
    if not blockers:
        return "indicator_ready"
    return blockers[0]


def _symbol_key(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _metadata(*, warmup_min_bars: int, max_indicator_age_sec: float) -> dict[str, Any]:
    return {
        "model": LIVE_INDICATOR_READINESS_SOURCE,
        "scope": "pure_live_indicator_readiness_diagnostics_no_runtime_wiring",
        "warmup_min_bars": int(warmup_min_bars),
        "max_indicator_age_sec": float(max_indicator_age_sec),
        "required_indicators": list(_REQUIRED_INDICATORS),
        "does_not_compute_indicators": True,
        "does_not_touch_runtime": True,
        "does_not_rank_candidates": True,
        "does_not_score_edge": True,
    }


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ORDER_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "INDICATOR_BARS_BELOW_WARMUP",
    "INDICATOR_BLOCKED",
    "INDICATOR_COMPUTE_ERROR",
    "INDICATOR_EMPTY_INPUT",
    "INDICATOR_INPUTS_MISSING",
    "INDICATOR_LAST_UPDATE_MISSING",
    "INDICATOR_READY",
    "INDICATOR_STALE",
    "INDICATOR_SYMBOL_MISSING",
    "INDICATOR_VALUE_MISSING",
    "LIVE_INDICATOR_READINESS_SCHEMA_VERSION",
    "LIVE_INDICATOR_READINESS_SOURCE",
    "LiveIndicatorReadinessDecision",
    "LiveIndicatorReadinessReport",
    "build_live_indicator_readiness_report",
]
