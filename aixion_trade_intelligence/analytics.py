from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import median
from typing import Any, Iterable, Mapping

from .contracts import CanonicalEvent, parse_timestamp
from .lineage import CandidateLineage
from .outcomes import HorizonOutcome, Quote, QuoteIndex


AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
UNAVAILABLE = "UNAVAILABLE"
CALCULATION_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class MetricResult:
    metric_id: str
    status: str
    value: Mapping[str, Any]
    reason: str = ""
    evidence_event_ids: tuple[str, ...] = ()
    calculation_version: str = CALCULATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SessionAnalytics:
    metrics: tuple[MetricResult, ...]
    required_metrics: tuple[str, ...]
    missing_required_metrics: tuple[str, ...]
    contract: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": [row.to_dict() for row in self.metrics],
            "required_metrics": list(self.required_metrics),
            "missing_required_metrics": list(self.missing_required_metrics),
            "contract": dict(self.contract),
        }


class AnalyticsContractError(ValueError):
    pass


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _price(quote: Quote | None) -> float | None:
    if quote is None:
        return None
    for value in (quote.ltp, quote.mid, quote.bid, quote.ask):
        if value is not None:
            return value
    return None


def _session_contract(events: tuple[CanonicalEvent, ...]) -> dict[str, Any]:
    starts = [event for event in events if event.event_type == "SESSION_STARTED"]
    if len(starts) != 1:
        return {}
    raw = starts[0].payload.get("analytics_contract")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise AnalyticsContractError("analytics_contract must be an object")
    return dict(raw)


def _required_metrics(contract: Mapping[str, Any]) -> tuple[str, ...]:
    raw = contract.get("required_metrics", [])
    if raw in (None, ""):
        return ()
    if not isinstance(raw, (list, tuple)):
        raise AnalyticsContractError("required_metrics must be a list")
    out: list[str] = []
    for value in raw:
        text = str(value or "").strip()
        if not text:
            raise AnalyticsContractError("required_metrics contains an empty metric ID")
        if text not in out:
            out.append(text)
    return tuple(out)


def _derive_index_instrument(
    contract: Mapping[str, Any],
    lineage: tuple[CandidateLineage, ...],
) -> tuple[str, str]:
    explicit = str(contract.get("index_instrument") or "").strip()
    if explicit:
        return explicit, "analytics_contract"
    candidates = sorted({row.underlying_instrument for row in lineage if row.underlying_instrument})
    if len(candidates) == 1:
        return candidates[0], "candidate_lineage"
    if not candidates:
        return "", "no exact index/underlying instrument was declared or derived"
    return "", f"multiple underlying instruments require an explicit index_instrument: {candidates}"


def _index_path_metric(quotes: QuoteIndex, instrument: str, source: str) -> MetricResult:
    if not instrument:
        return MetricResult("index_path", UNAVAILABLE, {}, reason=source)
    rows = tuple(row for row in quotes.all(instrument) if _price(row) is not None)
    if len(rows) < 2:
        return MetricResult(
            "index_path",
            UNAVAILABLE,
            {"instrument_key": instrument, "identity_source": source},
            reason="fewer than two usable quotes",
            evidence_event_ids=tuple(row.event_id for row in rows),
        )
    values = [_price(row) for row in rows]
    numeric = [value for value in values if value is not None]
    first = numeric[0]
    last = numeric[-1]
    session_return = None if first == 0 else (last - first) / abs(first)
    return MetricResult(
        "index_path",
        AVAILABLE,
        {
            "instrument_key": instrument,
            "identity_source": source,
            "quote_count": len(rows),
            "start": first,
            "end": last,
            "absolute_change": last - first,
            "return": session_return,
            "low": min(numeric),
            "high": max(numeric),
            "range": max(numeric) - min(numeric),
            "event_time_start": rows[0].event_time.isoformat().replace("+00:00", "Z"),
            "event_time_end": rows[-1].event_time.isoformat().replace("+00:00", "Z"),
        },
        evidence_event_ids=(rows[0].event_id, rows[-1].event_id),
    )


def _futures_basis_metric(
    quotes: QuoteIndex,
    *,
    index_instrument: str,
    futures_instrument: str,
    max_pair_lag_seconds: float | None,
) -> MetricResult:
    if not index_instrument or not futures_instrument:
        return MetricResult(
            "futures_basis",
            UNAVAILABLE,
            {
                "index_instrument": index_instrument,
                "futures_instrument": futures_instrument,
            },
            reason="exact index and futures instruments are required",
        )
    if max_pair_lag_seconds is None or max_pair_lag_seconds < 0:
        return MetricResult(
            "futures_basis",
            UNAVAILABLE,
            {
                "index_instrument": index_instrument,
                "futures_instrument": futures_instrument,
            },
            reason="nonnegative max_pair_lag_seconds is required by the analytics contract",
        )
    pairs: list[tuple[Quote, Quote, float]] = []
    for future_quote in quotes.all(futures_instrument):
        future_price = _price(future_quote)
        if future_price is None:
            continue
        index_quote = quotes.last_at_or_before(index_instrument, future_quote.available_time)
        index_price = _price(index_quote)
        if index_quote is None or index_price is None:
            continue
        lag = (future_quote.available_time - index_quote.available_time).total_seconds()
        if lag <= max_pair_lag_seconds:
            pairs.append((future_quote, index_quote, future_price - index_price))
    if not pairs:
        return MetricResult(
            "futures_basis",
            UNAVAILABLE,
            {
                "index_instrument": index_instrument,
                "futures_instrument": futures_instrument,
                "max_pair_lag_seconds": max_pair_lag_seconds,
            },
            reason="no causal quote pairs satisfy the declared lag contract",
        )
    start = pairs[0]
    end = pairs[-1]
    return MetricResult(
        "futures_basis",
        AVAILABLE,
        {
            "index_instrument": index_instrument,
            "futures_instrument": futures_instrument,
            "max_pair_lag_seconds": max_pair_lag_seconds,
            "pair_count": len(pairs),
            "start_basis": start[2],
            "end_basis": end[2],
            "basis_change": end[2] - start[2],
            "start_pair_lag_seconds": (
                start[0].available_time - start[1].available_time
            ).total_seconds(),
            "end_pair_lag_seconds": (
                end[0].available_time - end[1].available_time
            ).total_seconds(),
        },
        evidence_event_ids=(start[0].event_id, start[1].event_id, end[0].event_id, end[1].event_id),
    )


def _validate_constituents(contract: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    raw = contract.get("constituents")
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list):
        raise AnalyticsContractError("constituents must be a list")
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AnalyticsContractError(f"constituents[{index}] must be an object")
        instrument = str(item.get("instrument_key") or "").strip()
        weight = _number(item.get("weight"))
        if not instrument or weight is None or weight <= 0:
            raise AnalyticsContractError(
                f"constituents[{index}] requires exact instrument_key and positive weight"
            )
        if instrument in seen:
            raise AnalyticsContractError(f"duplicate constituent instrument {instrument}")
        seen.add(instrument)
        out.append((instrument, weight))
    return tuple(out)


def _breadth_metric(quotes: QuoteIndex, contract: Mapping[str, Any]) -> MetricResult:
    constituents = _validate_constituents(contract)
    version = str(contract.get("constituent_weights_version") or "").strip()
    if not constituents:
        return MetricResult(
            "constituent_breadth",
            UNAVAILABLE,
            {},
            reason="point-in-time constituent instruments and weights were not supplied",
        )
    if not version:
        return MetricResult(
            "constituent_breadth",
            UNAVAILABLE,
            {"constituent_count": len(constituents)},
            reason="constituent_weights_version is required",
        )
    returns: list[tuple[str, float, float, str, str]] = []
    missing: list[str] = []
    for instrument, weight in constituents:
        rows = tuple(row for row in quotes.all(instrument) if _price(row) is not None)
        if len(rows) < 2:
            missing.append(instrument)
            continue
        start = _price(rows[0])
        end = _price(rows[-1])
        if start in (None, 0) or end is None:
            missing.append(instrument)
            continue
        returns.append((instrument, (end - start) / abs(start), weight, rows[0].event_id, rows[-1].event_id))
    if not returns:
        return MetricResult(
            "constituent_breadth",
            UNAVAILABLE,
            {
                "constituent_count": len(constituents),
                "missing_instruments": missing,
                "constituent_weights_version": version,
            },
            reason="no constituent has a complete start/end price path",
        )
    total_weight = sum(row[2] for row in returns)
    positive = [row for row in returns if row[1] > 0]
    negative = [row for row in returns if row[1] < 0]
    unchanged = [row for row in returns if row[1] == 0]
    weighted_positive = sum(row[2] for row in positive) / total_weight if total_weight else None
    weighted_return = sum(row[1] * row[2] for row in returns) / total_weight if total_weight else None
    absolute_contributions = [abs(row[1] * row[2]) for row in returns]
    total_absolute = sum(absolute_contributions)
    concentration_hhi = (
        sum((value / total_absolute) ** 2 for value in absolute_contributions)
        if total_absolute > 0
        else 0.0
    )
    status = AVAILABLE if not missing else PARTIAL
    return MetricResult(
        "constituent_breadth",
        status,
        {
            "constituent_weights_version": version,
            "declared_constituent_count": len(constituents),
            "observed_constituent_count": len(returns),
            "missing_instruments": missing,
            "positive_count": len(positive),
            "negative_count": len(negative),
            "unchanged_count": len(unchanged),
            "positive_fraction": len(positive) / len(returns),
            "weighted_positive_fraction": weighted_positive,
            "median_return": median(row[1] for row in returns),
            "equal_weight_mean_return": sum(row[1] for row in returns) / len(returns),
            "declared_weight_mean_return": weighted_return,
            "absolute_contribution_hhi": concentration_hhi,
        },
        reason=("some declared constituents lacked complete evidence" if missing else ""),
        evidence_event_ids=tuple(
            event_id for row in returns for event_id in (row[3], row[4])
        ),
    )


def _decision_event_by_candidate(
    events: tuple[CanonicalEvent, ...],
    lineage: CandidateLineage,
) -> CanonicalEvent | None:
    by_id = {event.event_id: event for event in events}
    for event_id in (lineage.candidate_event_id, lineage.signal_event_id, lineage.evaluation_event_id):
        if event_id and event_id in by_id:
            return by_id[event_id]
    return None


def _candidate_liquidity_metrics(
    events: tuple[CanonicalEvent, ...],
    quotes: QuoteIndex,
    lineage_rows: tuple[CandidateLineage, ...],
) -> tuple[MetricResult, ...]:
    out: list[MetricResult] = []
    for lineage in lineage_rows:
        decision = _decision_event_by_candidate(events, lineage)
        instrument = lineage.selected_option_instrument
        metric_id = f"candidate_liquidity:{lineage.candidate_id}"
        if decision is None or not instrument:
            out.append(
                MetricResult(
                    metric_id,
                    UNAVAILABLE,
                    {"candidate_id": lineage.candidate_id, "instrument_key": instrument},
                    reason="decision event and exact selected option are required",
                )
            )
            continue
        decision_time = max(decision.event_time, decision.available_time)
        quote = quotes.first_at_or_after(instrument, decision_time)
        if quote is None or quote.bid is None or quote.ask is None or quote.ask < quote.bid:
            out.append(
                MetricResult(
                    metric_id,
                    UNAVAILABLE,
                    {"candidate_id": lineage.candidate_id, "instrument_key": instrument},
                    reason="two-sided decision-time quote is unavailable",
                    evidence_event_ids=((quote.event_id,) if quote else ()),
                )
            )
            continue
        mid = (quote.bid + quote.ask) / 2.0
        spread = quote.ask - quote.bid
        out.append(
            MetricResult(
                metric_id,
                AVAILABLE,
                {
                    "candidate_id": lineage.candidate_id,
                    "instrument_key": instrument,
                    "decision_time": decision_time.isoformat().replace("+00:00", "Z"),
                    "quote_available_time": quote.available_time.isoformat().replace("+00:00", "Z"),
                    "quote_lag_seconds": (quote.available_time - decision_time).total_seconds(),
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "mid": mid,
                    "spread": spread,
                    "spread_pct_of_mid": None if mid == 0 else spread / abs(mid),
                },
                evidence_event_ids=(decision.event_id, quote.event_id),
            )
        )
    return tuple(out)


def _candidate_timing_metrics(
    events: tuple[CanonicalEvent, ...],
    lineage_rows: tuple[CandidateLineage, ...],
) -> tuple[MetricResult, ...]:
    by_candidate: dict[str, list[CanonicalEvent]] = {}
    for event in events:
        if event.candidate_id:
            by_candidate.setdefault(event.candidate_id, []).append(event)
    out: list[MetricResult] = []
    for lineage in lineage_rows:
        rows = sorted(by_candidate.get(lineage.candidate_id, []), key=lambda row: row.deterministic_sort_key)
        requested = next((row for row in rows if row.event_type == "APPROVAL_REQUESTED"), None)
        decided = next((row for row in rows if row.event_type == "APPROVAL_DECIDED"), None)
        order = next((row for row in rows if row.event_type == "ORDER_EVENT"), None)
        fill = next((row for row in rows if row.event_type == "FILL_EVENT"), None)
        values: dict[str, Any] = {"candidate_id": lineage.candidate_id}
        evidence: list[str] = []
        if requested and decided:
            values["approval_latency_seconds"] = (
                decided.available_time - requested.available_time
            ).total_seconds()
            evidence.extend((requested.event_id, decided.event_id))
        else:
            values["approval_latency_seconds"] = None
        if order and fill:
            values["order_to_fill_latency_seconds"] = (
                fill.available_time - order.available_time
            ).total_seconds()
            evidence.extend((order.event_id, fill.event_id))
        else:
            values["order_to_fill_latency_seconds"] = None
        available_count = sum(value is not None for key, value in values.items() if key != "candidate_id")
        out.append(
            MetricResult(
                f"candidate_timing:{lineage.candidate_id}",
                AVAILABLE if available_count else UNAVAILABLE,
                values,
                reason=("approval and order/fill pairs were not both observed" if not available_count else ""),
                evidence_event_ids=tuple(dict.fromkeys(evidence)),
            )
        )
    return tuple(out)


def build_session_analytics(
    events: Iterable[CanonicalEvent],
    lineage_rows: Iterable[CandidateLineage],
    outcomes: Iterable[HorizonOutcome],
) -> SessionAnalytics:
    del outcomes  # Reserved for later aggregate outcome metrics; outcomes remain separately reported.
    materialized = tuple(events)
    lineage = tuple(lineage_rows)
    contract = _session_contract(materialized)
    required = _required_metrics(contract)
    quotes = QuoteIndex(materialized)
    index_instrument, index_source = _derive_index_instrument(contract, lineage)

    futures_instrument = str(contract.get("futures_instrument") or "").strip()
    max_pair_lag = _number(contract.get("max_pair_lag_seconds"))
    metrics: list[MetricResult] = [
        _index_path_metric(quotes, index_instrument, index_source),
        _futures_basis_metric(
            quotes,
            index_instrument=index_instrument,
            futures_instrument=futures_instrument,
            max_pair_lag_seconds=max_pair_lag,
        ),
        _breadth_metric(quotes, contract),
    ]
    metrics.extend(_candidate_liquidity_metrics(materialized, quotes, lineage))
    metrics.extend(_candidate_timing_metrics(materialized, lineage))
    status_by_id = {row.metric_id: row.status for row in metrics}
    missing_required = tuple(
        metric_id
        for metric_id in required
        if status_by_id.get(metric_id) != AVAILABLE
    )
    return SessionAnalytics(
        metrics=tuple(metrics),
        required_metrics=required,
        missing_required_metrics=missing_required,
        contract=contract,
    )
