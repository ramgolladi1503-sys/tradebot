from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo
import math


IST = ZoneInfo("Asia/Kolkata")


class CasA1FinalizationReplayError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReplayTick:
    ts: datetime
    instrument_key: str
    ltp: float
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True, slots=True)
class FinalizationReplayResult:
    session_date: str
    index_instrument_key: str
    index_tick_count: int
    pre_jump_ts: str
    pre_jump_ltp: float
    jump_ts: str
    jump_ltp: float
    jump_points: float
    jump_bps: float
    final_observed_index: float
    first_final_value_ts: str
    candidate_final_cas_ts: str
    candidate_semantics: str
    official_final_cas_semantics_verified: bool
    target_start_causal: bool | None
    first_future_tick_after_candidate_ts: str | None
    first_future_price_after_candidate: float | None
    ce_first_quote_after_candidate_ts: str | None
    ce_first_ask_after_candidate: float | None
    pe_first_quote_after_candidate_ts: str | None
    pe_first_ask_after_candidate: float | None
    earlier_window_largest_jump_points: float | None
    finalization_to_earlier_jump_ratio: float | None
    broker_write_authority: bool = False
    order_authority: bool = False
    paper_authorized: bool = False
    live_authorized: bool = False
    prospective_supported: bool = False
    execution_viable: bool = False
    structural_edge_certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, field: str, *, positive: bool = False) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise CasA1FinalizationReplayError(f"{field} must be numeric") from exc
    if not math.isfinite(out) or (positive and out <= 0):
        raise CasA1FinalizationReplayError(f"{field} must be finite{' and positive' if positive else ''}")
    return out


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (float, int)):
        dt = datetime.fromtimestamp(float(value), tz=ZoneInfo("UTC"))
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            raise CasA1FinalizationReplayError("timestamp missing")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise CasA1FinalizationReplayError(f"invalid timestamp {value!r}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise CasA1FinalizationReplayError("timestamp timezone is required")
    return dt.astimezone(IST)


def normalize_ticks(rows: Sequence[Mapping[str, Any]]) -> tuple[ReplayTick, ...]:
    ticks: list[ReplayTick] = []
    for raw in rows:
        key = str(raw.get("instrument_key") or raw.get("key") or "").strip()
        if not key:
            continue
        price = raw.get("ltp", raw.get("last_price"))
        if price in (None, ""):
            continue
        bid_raw = raw.get("bid_price", raw.get("bid"))
        ask_raw = raw.get("ask_price", raw.get("ask"))
        ticks.append(
            ReplayTick(
                ts=_ts(raw.get("ts", raw.get("timestamp"))),
                instrument_key=key,
                ltp=_number(price, "ltp", positive=True),
                bid=None if bid_raw in (None, "") else _number(bid_raw, "bid", positive=True),
                ask=None if ask_raw in (None, "") else _number(ask_raw, "ask", positive=True),
            )
        )
    ticks.sort(key=lambda row: (row.ts, row.instrument_key))
    return tuple(ticks)


def _inside(dt: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    minute = dt.hour * 60 + dt.minute
    return start[0] * 60 + start[1] <= minute <= end[0] * 60 + end[1]


def _largest_adjacent_jump(rows: Sequence[ReplayTick]) -> tuple[ReplayTick, ReplayTick, float]:
    if len(rows) < 2:
        raise CasA1FinalizationReplayError("not enough index ticks for adjacent-jump audit")
    best = None
    for left, right in zip(rows, rows[1:]):
        delta = right.ltp - left.ltp
        candidate = (abs(delta), left, right, delta)
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    return best[1], best[2], best[3]


def _first_after(rows: Sequence[ReplayTick], ts: datetime) -> ReplayTick | None:
    return next((row for row in rows if row.ts >= ts), None)


def analyze_finalization_replay(
    rows: Sequence[Mapping[str, Any]],
    *,
    session_date: str,
    index_instrument_key: str = "NSE_INDEX|Nifty 50",
    futures_instrument_key: str | None = None,
    ce_instrument_key: str | None = None,
    pe_instrument_key: str | None = None,
) -> FinalizationReplayResult:
    """Audit sub-minute ordering around CAS finalization from replay ticks.

    The inferred event is deliberately labelled REPLAY_PROXY_FROM_INDEX_DISCONTINUITY.
    It must never be represented as an exchange-certified FINAL_CAS publication.
    """
    ticks = normalize_ticks(rows)
    ticks = tuple(row for row in ticks if row.ts.date().isoformat() == session_date)
    index = tuple(row for row in ticks if row.instrument_key == index_instrument_key)
    final_window = tuple(row for row in index if _inside(row.ts, (15, 27), (15, 30)))
    if len(final_window) < 2:
        raise CasA1FinalizationReplayError("insufficient exact index ticks in 15:27-15:30 finalization window")

    pre, jump, delta = _largest_adjacent_jump(final_window)
    final_value = final_window[-1].ltp
    first_final = next((row for row in final_window if row.ltp == final_value), final_window[-1])

    # Candidate publication proxy is the first tick at the largest discontinuity's post-jump value.
    # If the later final observed value differs, conservatively require that later value instead.
    candidate = jump if jump.ltp == final_value else first_final

    earlier = tuple(row for row in index if _inside(row.ts, (14, 45), (15, 26)))
    earlier_jump = None
    if len(earlier) >= 2:
        _, _, earlier_delta = _largest_adjacent_jump(earlier)
        earlier_jump = abs(earlier_delta)
    ratio = None if earlier_jump in (None, 0.0) else abs(delta) / earlier_jump

    future_rows = tuple(row for row in ticks if futures_instrument_key and row.instrument_key == futures_instrument_key)
    future_after = _first_after(future_rows, candidate.ts) if future_rows else None
    target_start = candidate.ts.replace(hour=15, minute=29, second=0, microsecond=0)
    target_start_causal: bool | None = None
    if futures_instrument_key:
        target_candidates = [row for row in future_rows if row.ts >= target_start and row.ts < target_start.replace(minute=30)]
        if target_candidates:
            target_start_causal = target_candidates[0].ts >= candidate.ts

    ce_rows = tuple(row for row in ticks if ce_instrument_key and row.instrument_key == ce_instrument_key)
    pe_rows = tuple(row for row in ticks if pe_instrument_key and row.instrument_key == pe_instrument_key)
    ce_after = _first_after(ce_rows, candidate.ts) if ce_rows else None
    pe_after = _first_after(pe_rows, candidate.ts) if pe_rows else None

    return FinalizationReplayResult(
        session_date=session_date,
        index_instrument_key=index_instrument_key,
        index_tick_count=len(index),
        pre_jump_ts=pre.ts.isoformat(),
        pre_jump_ltp=pre.ltp,
        jump_ts=jump.ts.isoformat(),
        jump_ltp=jump.ltp,
        jump_points=delta,
        jump_bps=(delta / pre.ltp) * 10000.0,
        final_observed_index=final_value,
        first_final_value_ts=first_final.ts.isoformat(),
        candidate_final_cas_ts=candidate.ts.isoformat(),
        candidate_semantics="REPLAY_PROXY_FROM_INDEX_DISCONTINUITY",
        official_final_cas_semantics_verified=False,
        target_start_causal=target_start_causal,
        first_future_tick_after_candidate_ts=None if future_after is None else future_after.ts.isoformat(),
        first_future_price_after_candidate=None if future_after is None else future_after.ltp,
        ce_first_quote_after_candidate_ts=None if ce_after is None else ce_after.ts.isoformat(),
        ce_first_ask_after_candidate=None if ce_after is None else ce_after.ask,
        pe_first_quote_after_candidate_ts=None if pe_after is None else pe_after.ts.isoformat(),
        pe_first_ask_after_candidate=None if pe_after is None else pe_after.ask,
        earlier_window_largest_jump_points=earlier_jump,
        finalization_to_earlier_jump_ratio=ratio,
    )
