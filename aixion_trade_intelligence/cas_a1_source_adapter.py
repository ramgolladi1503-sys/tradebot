from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo
import math

from .cas_a1 import EXPECTED_CONSTITUENT_COUNT, FROZEN_SPEC_PAYLOAD, FROZEN_SPEC_SHA256
from .contracts import parse_timestamp


IST = ZoneInfo("Asia/Kolkata")


class CasA1SourceAdapterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CompletedMinuteBar:
    instrument_key: str
    minute: str
    close: float
    available_time: datetime
    source_event_id: str
    source_provider: str
    bar_complete: bool


@dataclass(frozen=True, slots=True)
class PointMark:
    instrument_key: str
    label: str
    price: float
    available_time: datetime
    source_event_id: str
    source_provider: str


def _finite_positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CasA1SourceAdapterError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise CasA1SourceAdapterError(f"{field} must be finite and positive")
    return number


def _dt(value: Any, field: str) -> datetime:
    if value in (None, ""):
        raise CasA1SourceAdapterError(f"{field} is required")
    return parse_timestamp(value, field_name=field)


def _date_ist(value: datetime) -> str:
    return value.astimezone(IST).date().isoformat()


def _parse_bar(row: Mapping[str, Any]) -> CompletedMinuteBar:
    instrument = str(row.get("instrument_key") or "").strip()
    minute = str(row.get("minute") or "").strip()
    event_id = str(row.get("source_event_id") or "").strip()
    provider = str(row.get("source_provider") or "").strip()
    if not instrument or not minute or not event_id or not provider:
        raise CasA1SourceAdapterError("bar requires instrument_key, minute, source_event_id, source_provider")
    if row.get("bar_complete") is not True:
        raise CasA1SourceAdapterError(f"incomplete minute bar rejected: {instrument} {minute}")
    return CompletedMinuteBar(
        instrument_key=instrument,
        minute=minute,
        close=_finite_positive(row.get("close"), f"{instrument}.{minute}.close"),
        available_time=_dt(row.get("available_time"), f"{instrument}.{minute}.available_time"),
        source_event_id=event_id,
        source_provider=provider,
        bar_complete=True,
    )


def _parse_mark(row: Mapping[str, Any]) -> PointMark:
    instrument = str(row.get("instrument_key") or "").strip()
    label = str(row.get("label") or "").strip()
    event_id = str(row.get("source_event_id") or "").strip()
    provider = str(row.get("source_provider") or "").strip()
    if not instrument or not label or not event_id or not provider:
        raise CasA1SourceAdapterError("point mark requires instrument_key, label, source_event_id, source_provider")
    return PointMark(
        instrument_key=instrument,
        label=label,
        price=_finite_positive(row.get("price"), f"{instrument}.{label}.price"),
        available_time=_dt(row.get("available_time"), f"{instrument}.{label}.available_time"),
        source_event_id=event_id,
        source_provider=provider,
    )


def _unique_by_key(rows: Sequence[Any], key_fn, description: str) -> dict[Any, Any]:
    out: dict[Any, Any] = {}
    for row in rows:
        key = key_fn(row)
        if key in out:
            raise CasA1SourceAdapterError(f"duplicate {description}: {key}")
        out[key] = row
    return out


def build_cas_a1_observation_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Convert exact completed-minute/post-close evidence into the frozen CAS-A1 input contract.

    This adapter intentionally does not infer minute closes from arbitrary ticks, forward-fill missing
    observations, substitute instruments, or shift timestamps. Missing/ambiguous evidence fails closed.
    """
    session_id = str(bundle.get("session_id") or "").strip()
    session_date = str(bundle.get("session_date") or "").strip()
    index_instrument = str(bundle.get("index_instrument") or "").strip()
    futures_instrument = str(bundle.get("futures_instrument") or "").strip()
    if not session_id or not session_date or not index_instrument or not futures_instrument:
        raise CasA1SourceAdapterError("session_id, session_date, index_instrument and futures_instrument are required")

    contract = bundle.get("analytics_contract")
    if not isinstance(contract, Mapping):
        raise CasA1SourceAdapterError("analytics_contract is required")
    cas_contract = contract.get("cas_a1")
    if not isinstance(cas_contract, Mapping):
        raise CasA1SourceAdapterError("analytics_contract.cas_a1 is required")
    frozen = cas_contract.get("frozen_constituents")
    if not isinstance(frozen, list) or len(frozen) != EXPECTED_CONSTITUENT_COUNT:
        raise CasA1SourceAdapterError(f"exactly {EXPECTED_CONSTITUENT_COUNT} frozen constituents are required")
    frozen_constituents = tuple(str(value or "").strip() for value in frozen)
    if any(not value for value in frozen_constituents) or len(set(frozen_constituents)) != len(frozen_constituents):
        raise CasA1SourceAdapterError("frozen constituents must be unique non-empty instrument keys")

    bars_raw = bundle.get("completed_minute_bars")
    marks_raw = bundle.get("point_marks")
    if not isinstance(bars_raw, list) or not isinstance(marks_raw, list):
        raise CasA1SourceAdapterError("completed_minute_bars and point_marks must be lists")
    bars = tuple(_parse_bar(row) for row in bars_raw if isinstance(row, Mapping))
    marks = tuple(_parse_mark(row) for row in marks_raw if isinstance(row, Mapping))
    bar_map = _unique_by_key(bars, lambda row: (row.instrument_key, row.minute), "completed minute bar")
    mark_map = _unique_by_key(marks, lambda row: (row.instrument_key, row.label), "point mark")

    required_bar_keys = [(instrument, minute) for instrument in frozen_constituents for minute in ("15:10", "15:14")]
    required_bar_keys.append((index_instrument, "15:14"))
    missing_bars = [key for key in required_bar_keys if key not in bar_map]
    if missing_bars:
        raise CasA1SourceAdapterError(f"missing exact completed-minute evidence: {missing_bars}")

    required_mark_keys = [
        (index_instrument, "FINAL_CAS"),
        (futures_instrument, "15:29"),
        (futures_instrument, "15:39"),
    ]
    missing_marks = [key for key in required_mark_keys if key not in mark_map]
    if missing_marks:
        raise CasA1SourceAdapterError(f"missing exact point evidence: {missing_marks}")

    selected_bars = [bar_map[key] for key in required_bar_keys]
    selected_marks = [mark_map[key] for key in required_mark_keys]
    providers = {row.source_provider for row in selected_bars + selected_marks}
    if len(providers) != 1:
        raise CasA1SourceAdapterError(f"mixed source providers rejected: {sorted(providers)}")
    source_provider = next(iter(providers))

    for row in selected_bars + selected_marks:
        if _date_ist(row.available_time) != session_date:
            raise CasA1SourceAdapterError(
                f"cross-session evidence rejected: {row.instrument_key} available on {_date_ist(row.available_time)}"
            )

    constituent_marks = []
    source_event_ids: list[str] = []
    for instrument in frozen_constituents:
        bar_1510 = bar_map[(instrument, "15:10")]
        bar_1514 = bar_map[(instrument, "15:14")]
        constituent_marks.append(
            {
                "instrument_key": instrument,
                "price_1510": bar_1510.close,
                "price_1514": bar_1514.close,
                "source_event_ids": [bar_1510.source_event_id, bar_1514.source_event_id],
            }
        )
        source_event_ids.extend((bar_1510.source_event_id, bar_1514.source_event_id))

    nifty = bar_map[(index_instrument, "15:14")]
    final_cas = mark_map[(index_instrument, "FINAL_CAS")]
    future_1529 = mark_map[(futures_instrument, "15:29")]
    future_1539 = mark_map[(futures_instrument, "15:39")]
    source_event_ids.extend(
        (nifty.source_event_id, final_cas.source_event_id, future_1529.source_event_id, future_1539.source_event_id)
    )

    return {
        "session_id": session_id,
        "session_date": session_date,
        "index_instrument": index_instrument,
        "futures_instrument": futures_instrument,
        "source_provider": source_provider,
        "analytics_contract": dict(contract),
        "constituent_marks": constituent_marks,
        "nifty_1514": nifty.close,
        "nifty_1514_available_time": nifty.available_time.isoformat().replace("+00:00", "Z"),
        "final_cas_index": final_cas.price,
        "final_cas_available_time": final_cas.available_time.isoformat().replace("+00:00", "Z"),
        "future_1529": future_1529.price,
        "future_1529_available_time": future_1529.available_time.isoformat().replace("+00:00", "Z"),
        "future_1539": future_1539.price,
        "future_1539_available_time": future_1539.available_time.isoformat().replace("+00:00", "Z"),
        "source_event_ids": list(dict.fromkeys(source_event_ids)),
        "adapter_contract": {
            "completed_minute_close_semantics": True,
            "tick_to_minute_inference_authorized": False,
            "forward_fill_authorized": False,
            "instrument_substitution_authorized": False,
            "timestamp_shift_authorized": False,
            "frozen_spec_sha256": FROZEN_SPEC_SHA256,
            "frozen_target_start": FROZEN_SPEC_PAYLOAD["target_start"],
            "frozen_target_end": FROZEN_SPEC_PAYLOAD["target_end"],
        },
    }
