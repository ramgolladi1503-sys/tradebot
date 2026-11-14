from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

from .contracts import CanonicalEvent, parse_timestamp
from .lineage import CandidateLineage


@dataclass(frozen=True, slots=True)
class Quote:
    instrument_key: str
    event_time: datetime
    available_time: datetime
    bid: float | None
    ask: float | None
    ltp: float | None
    mid: float | None
    event_id: str


@dataclass(frozen=True, slots=True)
class HorizonOutcome:
    candidate_id: str
    horizon_seconds: int
    decision_time: str
    label_available_time: str
    direction: str
    underlying_instrument: str
    selected_option_instrument: str
    underlying_entry: float | None
    underlying_exit: float | None
    signed_underlying_return: float | None
    underlying_mfe: float | None
    underlying_mae: float | None
    option_entry_ask: float | None
    option_entry_mid: float | None
    option_exit_bid: float | None
    option_exit_mid: float | None
    option_executable_pnl: float | None
    option_mid_pnl: float | None
    option_mfe: float | None
    option_mae: float | None
    delayed_entry_best_pnl: float | None
    classification: str
    evidence_event_ids: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OutcomeContractError(ValueError):
    pass


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _positive_ints(values: Any, *, field_name: str) -> tuple[int, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise OutcomeContractError(f"{field_name} must be a non-empty list")
    out: list[int] = []
    for raw in values:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise OutcomeContractError(f"{field_name} contains non-integer {raw!r}") from exc
        if value <= 0:
            raise OutcomeContractError(f"{field_name} must contain positive seconds")
        if value not in out:
            out.append(value)
    return tuple(sorted(out))


def _nonnegative_ints(values: Any, *, field_name: str) -> tuple[int, ...]:
    if values in (None, ""):
        return ()
    if not isinstance(values, (list, tuple)):
        raise OutcomeContractError(f"{field_name} must be a list")
    out: list[int] = []
    for raw in values:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise OutcomeContractError(f"{field_name} contains non-integer {raw!r}") from exc
        if value < 0:
            raise OutcomeContractError(f"{field_name} cannot contain negative seconds")
        if value not in out:
            out.append(value)
    return tuple(sorted(out))


def _direction_sign(direction: str) -> int:
    normalized = direction.strip().upper()
    if normalized in {"BUY_CALL", "CALL", "CE", "LONG", "UP"}:
        return 1
    if normalized in {"BUY_PUT", "PUT", "PE", "SHORT", "DOWN"}:
        return -1
    raise OutcomeContractError(f"unsupported direction {direction!r}")


class QuoteIndex:
    def __init__(self, events: Iterable[CanonicalEvent]) -> None:
        grouped: dict[str, list[Quote]] = defaultdict(list)
        for event in events:
            if event.event_type not in {"MARKET_QUOTE", "MARKET_SNAPSHOT"}:
                continue
            instrument = event.instrument_key or str(event.payload.get("instrument_key") or "").strip()
            if not instrument:
                continue
            bid = _number(event.payload.get("bid"))
            ask = _number(event.payload.get("ask"))
            ltp = _number(event.payload.get("ltp"))
            mid = _number(event.payload.get("mid"))
            if mid is None and bid is not None and ask is not None and ask >= bid:
                mid = (bid + ask) / 2.0
            grouped[instrument].append(
                Quote(
                    instrument_key=instrument,
                    event_time=event.event_time,
                    available_time=event.available_time,
                    bid=bid,
                    ask=ask,
                    ltp=ltp,
                    mid=mid,
                    event_id=event.event_id,
                )
            )
        self._quotes: dict[str, tuple[Quote, ...]] = {
            instrument: tuple(sorted(rows, key=lambda quote: (quote.available_time, quote.event_time, quote.event_id)))
            for instrument, rows in grouped.items()
        }
        self._times: dict[str, tuple[datetime, ...]] = {
            instrument: tuple(quote.available_time for quote in rows)
            for instrument, rows in self._quotes.items()
        }

    def first_at_or_after(self, instrument: str, when: datetime) -> Quote | None:
        rows = self._quotes.get(instrument, ())
        if not rows:
            return None
        idx = bisect_left(self._times[instrument], when)
        return rows[idx] if idx < len(rows) else None

    def last_at_or_before(self, instrument: str, when: datetime) -> Quote | None:
        rows = self._quotes.get(instrument, ())
        if not rows:
            return None
        idx = bisect_right(self._times[instrument], when) - 1
        return rows[idx] if idx >= 0 else None

    def all(self, instrument: str) -> tuple[Quote, ...]:
        return self._quotes.get(instrument, ())

    def instruments(self) -> tuple[str, ...]:
        return tuple(sorted(self._quotes))

    def window(self, instrument: str, start: datetime, end: datetime) -> tuple[Quote, ...]:
        rows = self._quotes.get(instrument, ())
        if not rows:
            return ()
        times = self._times[instrument]
        left = bisect_left(times, start)
        right = bisect_right(times, end)
        return rows[left:right]


def _quote_value(quote: Quote | None, fields: Sequence[str]) -> float | None:
    if quote is None:
        return None
    for field in fields:
        value = getattr(quote, field)
        if value is not None:
            return value
    return None


def _signed_return(entry: float | None, exit_: float | None, sign: int) -> float | None:
    if entry is None or exit_ is None or entry == 0:
        return None
    return sign * (exit_ - entry) / abs(entry)


def _signed_excursions(values: list[float], entry: float, sign: int) -> tuple[float | None, float | None]:
    if not values or entry == 0:
        return None, None
    signed = [sign * (value - entry) / abs(entry) for value in values]
    return max(signed), min(signed)


def _option_excursions(rows: Sequence[Quote], entry_ask: float | None) -> tuple[float | None, float | None]:
    if entry_ask is None:
        return None, None
    executable = [quote.bid - entry_ask for quote in rows if quote.bid is not None]
    return (max(executable), min(executable)) if executable else (None, None)


def _classification(
    *,
    underlying_return: float | None,
    option_mid_pnl: float | None,
    executable_pnl: float | None,
    delayed_entry_best_pnl: float | None,
) -> str:
    if underlying_return is None:
        return "OUTCOME_UNAVAILABLE"
    if underlying_return <= 0:
        return "UNDERLYING_WRONG"
    if option_mid_pnl is None:
        return "UNDERLYING_RIGHT_OPTION_UNAVAILABLE"
    if option_mid_pnl <= 0:
        return "UNDERLYING_RIGHT_OPTION_WRONG"
    if executable_pnl is None:
        return "UNDERLYING_RIGHT_EXECUTION_UNAVAILABLE"
    if executable_pnl > 0:
        return "FULL_TRADE_CORRECT"
    if delayed_entry_best_pnl is not None and delayed_entry_best_pnl > 0:
        return "UNDERLYING_RIGHT_ENTRY_WRONG"
    return "SIGNAL_RIGHT_EXECUTION_WRONG"


def _decision_event(lineage: CandidateLineage, by_id: Mapping[str, CanonicalEvent]) -> CanonicalEvent:
    for event_id in (lineage.candidate_event_id, lineage.signal_event_id, lineage.evaluation_event_id):
        event = by_id.get(event_id)
        if event is not None:
            return event
    raise OutcomeContractError(f"candidate {lineage.candidate_id} has no decision event")


def calculate_outcomes(
    events: Iterable[CanonicalEvent],
    lineage_rows: Iterable[CandidateLineage],
) -> tuple[HorizonOutcome, ...]:
    materialized = tuple(events)
    by_id = {event.event_id: event for event in materialized}
    quotes = QuoteIndex(materialized)
    outputs: list[HorizonOutcome] = []

    for lineage in lineage_rows:
        contract = dict(lineage.outcome_contract)
        if not contract:
            continue
        horizons = _positive_ints(contract.get("horizons_seconds"), field_name="horizons_seconds")
        delay_scenarios = _nonnegative_ints(
            contract.get("entry_delay_seconds", []),
            field_name="entry_delay_seconds",
        )
        decision = _decision_event(lineage, by_id)
        decision_time = max(decision.event_time, decision.available_time)
        sign = _direction_sign(lineage.direction)
        underlying_instrument = lineage.underlying_instrument or str(contract.get("underlying_instrument") or "")
        option_instrument = lineage.selected_option_instrument or str(contract.get("selected_option_instrument") or "")
        if not underlying_instrument:
            raise OutcomeContractError(f"candidate {lineage.candidate_id} lacks underlying instrument")
        if not option_instrument:
            raise OutcomeContractError(f"candidate {lineage.candidate_id} lacks selected option instrument")

        underlying_entry_quote = quotes.first_at_or_after(underlying_instrument, decision_time)
        option_entry_quote = quotes.first_at_or_after(option_instrument, decision_time)
        underlying_entry = _quote_value(underlying_entry_quote, ("ltp", "mid", "bid", "ask"))
        option_entry_ask = _quote_value(option_entry_quote, ("ask",))
        option_entry_mid = _quote_value(option_entry_quote, ("mid", "ltp"))

        for horizon in horizons:
            end_time = decision_time + timedelta(seconds=horizon)
            underlying_exit_quote = quotes.first_at_or_after(underlying_instrument, end_time)
            option_exit_quote = quotes.first_at_or_after(option_instrument, end_time)
            underlying_exit = _quote_value(underlying_exit_quote, ("ltp", "mid", "bid", "ask"))
            option_exit_bid = _quote_value(option_exit_quote, ("bid",))
            option_exit_mid = _quote_value(option_exit_quote, ("mid", "ltp"))
            underlying_return = _signed_return(underlying_entry, underlying_exit, sign)

            underlying_window = quotes.window(underlying_instrument, decision_time, end_time)
            underlying_values = [
                value
                for quote in underlying_window
                for value in [_quote_value(quote, ("ltp", "mid", "bid", "ask"))]
                if value is not None
            ]
            underlying_mfe, underlying_mae = (
                _signed_excursions(underlying_values, underlying_entry, sign)
                if underlying_entry is not None
                else (None, None)
            )
            option_window = quotes.window(option_instrument, decision_time, end_time)
            option_mfe, option_mae = _option_excursions(option_window, option_entry_ask)
            option_executable_pnl = (
                option_exit_bid - option_entry_ask
                if option_exit_bid is not None and option_entry_ask is not None
                else None
            )
            option_mid_pnl = (
                option_exit_mid - option_entry_mid
                if option_exit_mid is not None and option_entry_mid is not None
                else None
            )

            delayed_results: list[float] = []
            for delay in delay_scenarios:
                delayed_time = decision_time + timedelta(seconds=delay)
                if delayed_time >= end_time:
                    continue
                delayed_quote = quotes.first_at_or_after(option_instrument, delayed_time)
                delayed_ask = _quote_value(delayed_quote, ("ask",))
                if delayed_ask is not None and option_exit_bid is not None:
                    delayed_results.append(option_exit_bid - delayed_ask)
            delayed_entry_best_pnl = max(delayed_results) if delayed_results else None

            unavailable: list[str] = []
            required = {
                "UNDERLYING_ENTRY": underlying_entry,
                "UNDERLYING_EXIT": underlying_exit,
                "OPTION_ENTRY_ASK": option_entry_ask,
                "OPTION_ENTRY_MID": option_entry_mid,
                "OPTION_EXIT_BID": option_exit_bid,
                "OPTION_EXIT_MID": option_exit_mid,
            }
            unavailable.extend(key for key, value in required.items() if value is None)
            evidence_ids = tuple(
                dict.fromkeys(
                    event_id
                    for event_id in (
                        decision.event_id,
                        underlying_entry_quote.event_id if underlying_entry_quote else "",
                        underlying_exit_quote.event_id if underlying_exit_quote else "",
                        option_entry_quote.event_id if option_entry_quote else "",
                        option_exit_quote.event_id if option_exit_quote else "",
                    )
                    if event_id
                )
            )
            label_available_time = max(
                [end_time]
                + [
                    quote.available_time
                    for quote in (underlying_exit_quote, option_exit_quote)
                    if quote is not None
                ]
            )
            outputs.append(
                HorizonOutcome(
                    candidate_id=lineage.candidate_id,
                    horizon_seconds=horizon,
                    decision_time=decision_time.isoformat().replace("+00:00", "Z"),
                    label_available_time=label_available_time.isoformat().replace("+00:00", "Z"),
                    direction=lineage.direction,
                    underlying_instrument=underlying_instrument,
                    selected_option_instrument=option_instrument,
                    underlying_entry=underlying_entry,
                    underlying_exit=underlying_exit,
                    signed_underlying_return=underlying_return,
                    underlying_mfe=underlying_mfe,
                    underlying_mae=underlying_mae,
                    option_entry_ask=option_entry_ask,
                    option_entry_mid=option_entry_mid,
                    option_exit_bid=option_exit_bid,
                    option_exit_mid=option_exit_mid,
                    option_executable_pnl=option_executable_pnl,
                    option_mid_pnl=option_mid_pnl,
                    option_mfe=option_mfe,
                    option_mae=option_mae,
                    delayed_entry_best_pnl=delayed_entry_best_pnl,
                    classification=_classification(
                        underlying_return=underlying_return,
                        option_mid_pnl=option_mid_pnl,
                        executable_pnl=option_executable_pnl,
                        delayed_entry_best_pnl=delayed_entry_best_pnl,
                    ),
                    evidence_event_ids=evidence_ids,
                    unavailable_reasons=tuple(unavailable),
                )
            )
    return tuple(sorted(outputs, key=lambda row: (row.candidate_id, row.horizon_seconds)))
