from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .contracts import CanonicalEvent


CANDIDATE_EVENT_TYPES = {
    "STRATEGY_EVALUATED",
    "SIGNAL_GENERATED",
    "CANDIDATE_CREATED",
    "CANDIDATE_BLOCKED",
    "CANDIDATE_RANKED",
    "APPROVAL_REQUESTED",
    "APPROVAL_DECIDED",
    "ORDER_EVENT",
    "FILL_EVENT",
    "POSITION_EVENT",
    "RISK_STATE_CHANGED",
}


@dataclass(frozen=True, slots=True)
class CandidateLineage:
    session_id: str
    candidate_id: str
    strategy_id: str
    strategy_version: str
    direction: str
    underlying_instrument: str
    selected_option_instrument: str
    evaluation_event_id: str = ""
    signal_event_id: str = ""
    candidate_event_id: str = ""
    event_ids: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    approval_decision: str = ""
    approval_reason: str = ""
    order_ids: tuple[str, ...] = ()
    fill_count: int = 0
    filled_quantity: float = 0.0
    average_fill_price: float | None = None
    outcome_contract: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LineageError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def build_candidate_lineage(events: Iterable[CanonicalEvent]) -> tuple[CandidateLineage, ...]:
    grouped: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for event in events:
        if event.event_type not in CANDIDATE_EVENT_TYPES:
            continue
        candidate_id = event.candidate_id or _text(event.payload.get("candidate_id"))
        if not candidate_id:
            continue
        grouped[candidate_id].append(event)

    out: list[CandidateLineage] = []
    for candidate_id, candidate_events in grouped.items():
        ordered = sorted(candidate_events, key=lambda event: event.deterministic_sort_key)
        sessions = {event.session_id for event in ordered}
        if len(sessions) != 1:
            raise LineageError(f"candidate {candidate_id} spans multiple sessions")

        strategy_ids = {
            value
            for event in ordered
            for value in (event.strategy_id, _text(event.payload.get("strategy_id")))
            if value
        }
        strategy_versions = {
            value
            for event in ordered
            for value in (event.strategy_version, _text(event.payload.get("strategy_version")))
            if value
        }
        if len(strategy_ids) > 1:
            raise LineageError(f"candidate {candidate_id} has conflicting strategy identities: {sorted(strategy_ids)}")
        if len(strategy_versions) > 1:
            raise LineageError(
                f"candidate {candidate_id} has conflicting strategy versions: {sorted(strategy_versions)}"
            )

        evaluation = next((event for event in ordered if event.event_type == "STRATEGY_EVALUATED"), None)
        signal = next((event for event in ordered if event.event_type == "SIGNAL_GENERATED"), None)
        created = next((event for event in ordered if event.event_type == "CANDIDATE_CREATED"), None)

        payloads = [dict(event.payload) for event in ordered]
        direction = next((_text(payload.get("direction")) for payload in payloads if _text(payload.get("direction"))), "")
        underlying = next(
            (
                _text(payload.get("underlying_instrument") or payload.get("underlying"))
                for payload in payloads
                if _text(payload.get("underlying_instrument") or payload.get("underlying"))
            ),
            next((event.underlying for event in ordered if event.underlying), ""),
        )
        selected_option = next(
            (
                _text(payload.get("selected_option_instrument") or payload.get("option_instrument"))
                for payload in payloads
                if _text(payload.get("selected_option_instrument") or payload.get("option_instrument"))
            ),
            next((event.instrument_key for event in ordered if event.event_type == "CANDIDATE_CREATED" and event.instrument_key), ""),
        )
        outcome_contract = next(
            (
                dict(payload.get("outcome_contract"))
                for payload in payloads
                if isinstance(payload.get("outcome_contract"), Mapping)
            ),
            {},
        )

        statuses: list[str] = []
        blockers: list[str] = []
        approval_decision = ""
        approval_reason = ""
        order_ids: list[str] = []
        fill_notional = 0.0
        filled_quantity = 0.0
        fill_count = 0
        for event in ordered:
            status = _text(event.payload.get("status") or event.payload.get("stage_status"))
            if status and status not in statuses:
                statuses.append(status)
            if event.event_type == "CANDIDATE_BLOCKED":
                reasons = event.payload.get("blockers") or event.payload.get("reasons") or [event.payload.get("reason")]
                if not isinstance(reasons, (list, tuple)):
                    reasons = [reasons]
                for reason in reasons:
                    text = _text(reason)
                    if text and text not in blockers:
                        blockers.append(text)
            if event.event_type == "APPROVAL_DECIDED":
                approval_decision = _text(event.payload.get("decision"))
                approval_reason = _text(event.payload.get("reason"))
            if event.order_id and event.order_id not in order_ids:
                order_ids.append(event.order_id)
            if event.event_type == "FILL_EVENT":
                quantity = _float(event.payload.get("filled_quantity") or event.payload.get("quantity"))
                price = _float(event.payload.get("fill_price") or event.payload.get("price"))
                if quantity is not None and quantity > 0 and price is not None and price >= 0:
                    fill_count += 1
                    filled_quantity += quantity
                    fill_notional += quantity * price

        average_fill_price = fill_notional / filled_quantity if filled_quantity > 0 else None
        metadata = {
            "first_event_time": ordered[0].event_time.isoformat(),
            "last_event_time": ordered[-1].event_time.isoformat(),
            "data_quality_states": sorted({event.data_quality_state for event in ordered}),
            "authority_classes": sorted({event.authority_class for event in ordered}),
        }
        out.append(
            CandidateLineage(
                session_id=ordered[0].session_id,
                candidate_id=candidate_id,
                strategy_id=next(iter(strategy_ids), ""),
                strategy_version=next(iter(strategy_versions), ""),
                direction=direction,
                underlying_instrument=underlying,
                selected_option_instrument=selected_option,
                evaluation_event_id=evaluation.event_id if evaluation else "",
                signal_event_id=signal.event_id if signal else "",
                candidate_event_id=created.event_id if created else "",
                event_ids=tuple(event.event_id for event in ordered),
                statuses=tuple(statuses),
                blockers=tuple(blockers),
                approval_decision=approval_decision,
                approval_reason=approval_reason,
                order_ids=tuple(order_ids),
                fill_count=fill_count,
                filled_quantity=filled_quantity,
                average_fill_price=average_fill_price,
                outcome_contract=outcome_contract,
                metadata=metadata,
            )
        )
    return tuple(sorted(out, key=lambda row: row.candidate_id))
