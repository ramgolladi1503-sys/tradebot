from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from core.atr_contract import APPROVED_ATR_CONTRACT, AtrContractSpec
from core.session_bar_history import CompletedBarSnapshot, SessionBarHistoryState
from core.time_utils import IST_TZ


TIMEFRAME_SECONDS = 60
STATUS_AVAILABLE = "AVAILABLE"
STATUS_CONTIGUOUS = "CONTIGUOUS"
STATUS_WARMING_UP = "WARMING_UP"
STATUS_CONTIGUITY_REWARMING = "CONTIGUITY_REWARMING"
STATUS_INVALID_SOURCE = "INVALID_SOURCE"


@dataclass(frozen=True)
class SessionAtrResult:
    contract_version: str
    symbol: str
    session_date: str
    timeframe: str
    latest_completed_bar_timestamp: str | None
    completed_bar_count: int
    current_contiguous_bar_count: int
    short_lookback: int
    long_lookback: int
    atr_short: float | None
    atr_long: float | None
    short_available: bool
    long_available: bool
    continuity_status: str
    gap_count: int
    latest_gap_timestamp: str | None
    source_history_hash: str
    calculation_hash: str
    warnings: tuple[str, ...] = ()
    short_status: str = STATUS_WARMING_UP
    long_status: str = STATUS_WARMING_UP

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload

    def provenance_payload(
        self,
        *,
        source_component: str,
        receipt_timestamp: str | None = None,
    ) -> dict[str, Any]:
        payload = self.to_dict()
        payload.update(
            {
                "source_component": str(source_component or "").strip() or "core.session_atr.calculate_session_atr_state",
                "source_field": "atr_short_long_v1",
                "source_event_timestamp": self.latest_completed_bar_timestamp,
                "receipt_timestamp": receipt_timestamp or self.latest_completed_bar_timestamp,
                "scope": "session_atr",
                "complete": bool(self.short_available and self.long_available),
                "timeframe": self.timeframe,
                "symbol": self.symbol,
                "session_date": self.session_date,
            }
        )
        return payload


def _bar_value(bar: Any, key: str) -> Any:
    if isinstance(bar, Mapping):
        return bar.get(key)
    return getattr(bar, key, None)


def _coerce_float(value: Any, *, field_name: str) -> float:
    try:
        out = float(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"invalid_float:{field_name}") from exc
    if not math.isfinite(out):
        raise ValueError(f"invalid_float:{field_name}")
    return float(out)


def _coerce_timestamp(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        out = value
    else:
        try:
            out = datetime.fromisoformat(str(value))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid_timestamp:{field_name}") from exc
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST_TZ)
    return out


def _normalize_history(
    history: SessionBarHistoryState | Iterable[CompletedBarSnapshot | Mapping[str, Any]] | None,
    *,
    contract: AtrContractSpec,
    symbol: str | None,
    session_date: str | None,
    timeframe: str | None,
    source_history_hash: str | None,
) -> tuple[list[dict[str, Any]], str, str, str, str]:
    if isinstance(history, SessionBarHistoryState):
        bars = list(history.completed_bar_history)
        resolved_symbol = history.symbol
        resolved_session_date = history.session_date
        resolved_timeframe = history.timeframe
        resolved_source_hash = history.history_hash
    else:
        bars = list(history or [])
        resolved_symbol = str(symbol or "").strip().upper() or "UNKNOWN"
        resolved_session_date = str(session_date or "").strip()
        resolved_timeframe = str(timeframe or contract.timeframe).strip() or contract.timeframe
        resolved_source_hash = str(source_history_hash or "").strip()

    normalized: list[dict[str, Any]] = []
    for bar in bars:
        bar_symbol = str(_bar_value(bar, "symbol") or resolved_symbol).strip().upper() or resolved_symbol
        bar_session_date = str(_bar_value(bar, "session_date") or resolved_session_date).strip() or resolved_session_date
        bar_timeframe = str(_bar_value(bar, "timeframe") or resolved_timeframe).strip() or resolved_timeframe
        bar_start_raw = _bar_value(bar, "bar_start_timestamp") or _bar_value(bar, "ts")
        bar_end_raw = _bar_value(bar, "bar_end_timestamp") or bar_start_raw
        if bar_start_raw is None or bar_end_raw is None:
            raise ValueError("missing_bar_timestamp")
        bar_start = _coerce_timestamp(bar_start_raw, field_name="bar_start_timestamp")
        bar_end = _coerce_timestamp(bar_end_raw, field_name="bar_end_timestamp")
        normalized.append(
            {
                "symbol": bar_symbol,
                "session_date": bar_session_date,
                "timeframe": bar_timeframe,
                "bar_start_timestamp": bar_start.replace(microsecond=0).isoformat(),
                "bar_end_timestamp": bar_end.replace(microsecond=0).isoformat(),
                "open": _coerce_float(_bar_value(bar, "open"), field_name="open"),
                "high": _coerce_float(_bar_value(bar, "high"), field_name="high"),
                "low": _coerce_float(_bar_value(bar, "low"), field_name="low"),
                "close": _coerce_float(_bar_value(bar, "close"), field_name="close"),
                "volume": _bar_value(bar, "volume"),
            }
        )

    if not resolved_source_hash:
        resolved_source_hash = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()

    return normalized, resolved_symbol, resolved_session_date, resolved_timeframe, resolved_source_hash


def _build_status_result(
    *,
    contract: AtrContractSpec,
    symbol: str,
    session_date: str,
    timeframe: str,
    source_history_hash: str,
    warnings: list[str],
    continuity_status: str,
    short_status: str,
    long_status: str,
    short_available: bool,
    long_available: bool,
    atr_short: float | None,
    atr_long: float | None,
    completed_bar_count: int,
    current_contiguous_bar_count: int,
    gap_count: int,
    latest_completed_bar_timestamp: str | None,
    latest_gap_timestamp: str | None,
    include_invalid_marker: bool,
) -> SessionAtrResult:
    payload = {
        "contract_version": contract.version,
        "symbol": str(symbol or "").strip().upper() or "UNKNOWN",
        "session_date": str(session_date or "").strip() or "UNKNOWN",
        "timeframe": str(timeframe or contract.timeframe).strip() or contract.timeframe,
        "latest_completed_bar_timestamp": latest_completed_bar_timestamp,
        "completed_bar_count": completed_bar_count,
        "current_contiguous_bar_count": current_contiguous_bar_count,
        "short_lookback": contract.short_lookback,
        "long_lookback": contract.long_lookback,
        "atr_short": atr_short,
        "atr_long": atr_long,
        "short_available": short_available,
        "long_available": long_available,
        "continuity_status": continuity_status,
        "gap_count": gap_count,
        "latest_gap_timestamp": latest_gap_timestamp,
        "source_history_hash": source_history_hash,
        "warnings": tuple(
            sorted(dict.fromkeys(warnings + ([STATUS_INVALID_SOURCE] if include_invalid_marker else [])))
        ),
        "short_status": short_status,
        "long_status": long_status,
    }
    calculation_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    payload["calculation_hash"] = calculation_hash
    return SessionAtrResult(**payload)


def calculate_session_atr_state(
    history: SessionBarHistoryState | Iterable[CompletedBarSnapshot | Mapping[str, Any]] | None,
    *,
    contract: AtrContractSpec = APPROVED_ATR_CONTRACT,
    symbol: str | None = None,
    session_date: str | None = None,
    timeframe: str | None = None,
    source_history_hash: str | None = None,
) -> SessionAtrResult:
    normalized, resolved_symbol, resolved_session_date, resolved_timeframe, resolved_source_hash = _normalize_history(
        history,
        contract=contract,
        symbol=symbol,
        session_date=session_date,
        timeframe=timeframe,
        source_history_hash=source_history_hash,
    )

    if not normalized:
        warnings = ["atr_short_warming_up", "atr_long_warming_up"]
        return _build_status_result(
            contract=contract,
            symbol=resolved_symbol,
            session_date=resolved_session_date or "",
            timeframe=resolved_timeframe,
            source_history_hash=resolved_source_hash,
            warnings=warnings,
            continuity_status=STATUS_WARMING_UP,
            short_status=STATUS_WARMING_UP,
            long_status=STATUS_WARMING_UP,
            short_available=False,
            long_available=False,
            atr_short=None,
            atr_long=None,
            completed_bar_count=0,
            current_contiguous_bar_count=0,
            gap_count=0,
            latest_completed_bar_timestamp=None,
            latest_gap_timestamp=None,
            include_invalid_marker=False,
        )

    if resolved_timeframe != contract.timeframe:
        return _build_status_result(
            contract=contract,
            symbol=resolved_symbol,
            session_date=resolved_session_date or "",
            timeframe=resolved_timeframe,
            source_history_hash=resolved_source_hash,
            warnings=[f"unsupported_timeframe:{resolved_timeframe}"],
            continuity_status=STATUS_INVALID_SOURCE,
            short_status=STATUS_INVALID_SOURCE,
            long_status=STATUS_INVALID_SOURCE,
            short_available=False,
            long_available=False,
            atr_short=None,
            atr_long=None,
            completed_bar_count=0,
            current_contiguous_bar_count=0,
            gap_count=0,
            latest_completed_bar_timestamp=None,
            latest_gap_timestamp=None,
            include_invalid_marker=True,
        )

    trs: list[float] = []
    current_run_trs: list[float] = []
    current_contiguous_bar_count = 0
    gap_count = 0
    latest_gap_timestamp = None
    latest_completed_bar_timestamp = None
    prev_end: datetime | None = None
    prev_close: float | None = None
    warnings: list[str] = []
    short_status = STATUS_WARMING_UP
    long_status = STATUS_WARMING_UP
    atr_short: float | None = None
    atr_long: float | None = None

    for idx, bar in enumerate(normalized):
        bar_end = _coerce_timestamp(bar["bar_end_timestamp"], field_name="bar_end_timestamp")
        if prev_end is not None:
            delta_sec = int((bar_end - prev_end).total_seconds())
            if delta_sec <= 0:
                return _build_status_result(
                    contract=contract,
                    symbol=resolved_symbol,
                    session_date=resolved_session_date or bar["session_date"],
                    timeframe=resolved_timeframe,
                    source_history_hash=resolved_source_hash,
                    warnings=[f"invalid_bar_sequence:{bar_end.isoformat()}"],
                    continuity_status=STATUS_INVALID_SOURCE,
                    short_status=STATUS_INVALID_SOURCE,
                    long_status=STATUS_INVALID_SOURCE,
                    short_available=False,
                    long_available=False,
                    atr_short=None,
                    atr_long=None,
                    completed_bar_count=len(normalized),
                    current_contiguous_bar_count=current_contiguous_bar_count,
                    gap_count=gap_count,
                    latest_completed_bar_timestamp=latest_completed_bar_timestamp,
                    latest_gap_timestamp=latest_gap_timestamp,
                    include_invalid_marker=True,
                )
            if delta_sec > TIMEFRAME_SECONDS:
                gap_count += 1
                latest_gap_timestamp = bar_end.isoformat()
                current_run_trs = []
                current_contiguous_bar_count = 0
                prev_close = None

        if prev_close is None:
            tr = bar["high"] - bar["low"]
        else:
            tr = max(
                bar["high"] - bar["low"],
                abs(bar["high"] - prev_close),
                abs(bar["low"] - prev_close),
            )

        trs.append(tr)
        current_run_trs.append(tr)
        current_contiguous_bar_count += 1
        if len(current_run_trs) > contract.long_lookback:
            current_run_trs = current_run_trs[-contract.long_lookback :]

        short_available = current_contiguous_bar_count >= contract.short_lookback
        long_available = current_contiguous_bar_count >= contract.long_lookback
        if short_available:
            atr_short = sum(current_run_trs[-contract.short_lookback :]) / contract.short_lookback
            short_status = STATUS_AVAILABLE
        else:
            short_status = STATUS_CONTIGUITY_REWARMING if gap_count > 0 else STATUS_WARMING_UP
            atr_short = None
        if long_available:
            atr_long = sum(current_run_trs[-contract.long_lookback :]) / contract.long_lookback
            long_status = STATUS_AVAILABLE
        else:
            long_status = STATUS_CONTIGUITY_REWARMING if gap_count > 0 else STATUS_WARMING_UP
            atr_long = None

        latest_completed_bar_timestamp = bar_end.isoformat()
        prev_end = bar_end
        prev_close = bar["close"]

    if not (short_available and long_available):
        warnings.extend(
            [
                f"short_status:{short_status}",
                f"long_status:{long_status}",
            ]
        )

    if gap_count > 0 and current_contiguous_bar_count >= contract.long_lookback:
        continuity_status = STATUS_AVAILABLE
    elif gap_count > 0:
        continuity_status = STATUS_CONTIGUITY_REWARMING
    elif short_available and long_available:
        continuity_status = STATUS_AVAILABLE
    elif short_available:
        continuity_status = STATUS_WARMING_UP
    else:
        continuity_status = STATUS_WARMING_UP

    payload = {
        "contract_version": contract.version,
        "symbol": resolved_symbol,
        "session_date": resolved_session_date or normalized[0]["session_date"],
        "timeframe": resolved_timeframe,
        "latest_completed_bar_timestamp": latest_completed_bar_timestamp,
        "completed_bar_count": len(normalized),
        "current_contiguous_bar_count": current_contiguous_bar_count,
        "short_lookback": contract.short_lookback,
        "long_lookback": contract.long_lookback,
        "atr_short": atr_short,
        "atr_long": atr_long,
        "short_available": short_available,
        "long_available": long_available,
        "continuity_status": continuity_status,
        "gap_count": gap_count,
        "latest_gap_timestamp": latest_gap_timestamp,
        "source_history_hash": resolved_source_hash,
        "warnings": tuple(sorted(dict.fromkeys(warnings))),
        "short_status": short_status,
        "long_status": long_status,
    }
    calculation_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    payload["calculation_hash"] = calculation_hash
    return SessionAtrResult(**payload)


__all__ = [
    "STATUS_AVAILABLE",
    "STATUS_CONTIGUOUS",
    "STATUS_CONTIGUITY_REWARMING",
    "STATUS_INVALID_SOURCE",
    "STATUS_WARMING_UP",
    "SessionAtrResult",
    "calculate_session_atr_state",
]
