"""Paper intent contract builder.

This module bridges a selected ranked candidate to a paper-intent contract. It is
read-only: it does not create paper orders, reserve risk, submit broker payloads,
mutate selection reports, or touch dashboard/runtime wiring.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

from core.selection_policy import SELECTED_FOR_PAPER

PAPER_INTENT_SCHEMA_VERSION = 1
PAPER_INTENT_READY = "PAPER_INTENT_READY"
PAPER_INTENT_BLOCKED = "PAPER_INTENT_BLOCKED"


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _selected_records(selection_report: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    selections = selection_report.get("selections")
    if not isinstance(selections, (list, tuple)):
        return ()
    return tuple(
        row
        for row in selections
        if isinstance(row, Mapping)
        and _bool(row.get("selected"), default=False)
        and str(row.get("decision") or "") == SELECTED_FOR_PAPER
    )


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _contract_blockers(contract_resolution: Mapping[str, Any] | None) -> tuple[str, ...]:
    if contract_resolution is None:
        return ("CONTRACT_RESOLUTION_MISSING",)
    blockers: list[str] = []
    if contract_resolution.get("instrument_token") in (None, "", "None"):
        blockers.append("CONTRACT_TOKEN_MISSING")
    if not _first_text(contract_resolution.get("tradingsymbol")):
        blockers.append("CONTRACT_TRADINGSYMBOL_MISSING")
    if str(contract_resolution.get("resolution_path") or "") != "exact_contract_match":
        blockers.append("CONTRACT_NOT_EXACT_MATCH")
    if _bool(contract_resolution.get("fallback_candidate"), default=False):
        blockers.append("CONTRACT_FALLBACK_CANDIDATE")
    if _bool(contract_resolution.get("advisory_only"), default=False):
        blockers.append("CONTRACT_ADVISORY_ONLY")
    if not _bool(contract_resolution.get("execution_grade"), default=False):
        blockers.append("CONTRACT_NOT_EXECUTION_GRADE")
    return _dedupe(blockers)


def _feed_blockers(feed_gate_decision: Mapping[str, Any] | None) -> tuple[str, ...]:
    if feed_gate_decision is None:
        return ("FEED_GATE_DECISION_MISSING",)
    blockers = list(_list_of_strings(feed_gate_decision.get("blockers")))
    if not _bool(feed_gate_decision.get("allowed_for_paper_execution"), default=False):
        blockers.append("FEED_NOT_ALLOWED_FOR_PAPER_EXECUTION")
    if _bool(feed_gate_decision.get("advisory_only"), default=False):
        blockers.append("FEED_GATE_ADVISORY_ONLY")
    if str(feed_gate_decision.get("gate_state") or "") not in {"FRESH", "OK"}:
        blockers.append("FEED_GATE_NOT_FRESH")
    return _dedupe(blockers)


def _quote_blockers(quote_snapshot: Mapping[str, Any] | None) -> tuple[str, ...]:
    if quote_snapshot is None:
        return ("QUOTE_SNAPSHOT_MISSING",)
    bid = _as_float(quote_snapshot.get("bid"))
    ask = _as_float(quote_snapshot.get("ask"))
    ltp = _as_float(quote_snapshot.get("ltp") or quote_snapshot.get("last_price"))
    blockers: list[str] = []
    if bid is None or bid <= 0.0:
        blockers.append("QUOTE_BID_MISSING")
    if ask is None or ask <= 0.0:
        blockers.append("QUOTE_ASK_MISSING")
    if ltp is None or ltp <= 0.0:
        blockers.append("QUOTE_LTP_MISSING")
    if bid is not None and ask is not None and bid > 0.0 and ask > 0.0 and ask < bid:
        blockers.append("QUOTE_ASK_BELOW_BID")
    return _dedupe(blockers)


def _evidence_blockers(evidence_ref: Mapping[str, Any] | None) -> tuple[str, ...]:
    if evidence_ref is None:
        return ("RANKED_PIPELINE_EVIDENCE_MISSING",)
    evidence_hash = _first_text(evidence_ref.get("evidence_hash"), evidence_ref.get("ranked_pipeline_evidence_hash"))
    if evidence_hash is None:
        return ("RANKED_PIPELINE_EVIDENCE_HASH_MISSING",)
    return ()


def _intent_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


@dataclass(frozen=True)
class PaperIntentContract:
    schema_version: int
    state: str
    read_only: bool
    is_order_action: bool
    append: bool
    paper_intent_id: str | None
    ready_for_risk_review: bool
    allowed_for_paper_order: bool
    allowed_for_live_execution: bool
    selected_strategy_id: str | None
    rank: int | None
    symbol: str | None
    direction: str | None
    final_score: float | None
    instrument_token: int | None
    tradingsymbol: str | None
    exchange: str | None
    segment: str | None
    bid: float | None
    ask: float | None
    ltp: float | None
    quote_source: str | None
    feed_gate_state: str | None
    ranked_pipeline_evidence_hash: str | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_paper_intent_contract(
    selection_report: Any,
    *,
    contract_resolution: Any = None,
    quote_snapshot: Any = None,
    feed_gate_decision: Any = None,
    ranked_pipeline_evidence: Any = None,
) -> PaperIntentContract:
    """Build a paper-intent contract from one selected candidate.

    The returned contract is not an order. It is the immutable input boundary for
    later risk-decision and paper-decision orchestration PRs.
    """

    selection = _to_mapping(selection_report)
    contract = _to_mapping(contract_resolution)
    quote = _to_mapping(quote_snapshot)
    feed = _to_mapping(feed_gate_decision)
    evidence = _to_mapping(ranked_pipeline_evidence)

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []
    selected: Mapping[str, Any] | None = None

    if selection is None:
        blockers.append("SELECTION_REPORT_MISSING")
        reasons.append("selection_report_required")
    else:
        if not _bool(selection.get("read_only"), default=False):
            blockers.append("SELECTION_REPORT_NOT_READ_ONLY")
        if _bool(selection.get("is_order_action"), default=False):
            blockers.append("SELECTION_REPORT_CONTAINS_ORDER_ACTION")
        if _bool(selection.get("append"), default=False):
            blockers.append("SELECTION_REPORT_APPEND_TRUE")
        if str(selection.get("state") or "") != SELECTED_FOR_PAPER:
            blockers.append("SELECTION_NOT_SELECTED_FOR_PAPER")
        selected_records = _selected_records(selection)
        if len(selected_records) != 1:
            blockers.append("SELECTED_RECORD_COUNT_NOT_ONE")
        else:
            selected = selected_records[0]

    blockers.extend(_contract_blockers(contract))
    blockers.extend(_quote_blockers(quote))
    blockers.extend(_feed_blockers(feed))
    blockers.extend(_evidence_blockers(evidence))

    if feed is not None:
        warnings.extend(_list_of_strings(feed.get("warnings")))
    if selected is not None:
        warnings.extend(_list_of_strings(selected.get("warnings")))

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    ready = not normalized_blockers

    strategy_id = _first_text(selected.get("strategy_id") if selected else None)
    symbol = _first_text(selected.get("symbol") if selected else None)
    direction = _first_text(selected.get("direction") if selected else None)
    final_score = _as_float(selected.get("final_score") if selected else None)
    rank = _as_int(selected.get("rank") if selected else None)

    bid = _as_float(quote.get("bid") if quote else None)
    ask = _as_float(quote.get("ask") if quote else None)
    ltp = _as_float((quote.get("ltp") or quote.get("last_price")) if quote else None)
    evidence_hash = _first_text(
        evidence.get("evidence_hash") if evidence else None,
        evidence.get("ranked_pipeline_evidence_hash") if evidence else None,
    )
    instrument_token = _as_int(contract.get("instrument_token") if contract else None)
    tradingsymbol = _first_text(contract.get("tradingsymbol") if contract else None)
    exchange = _first_text(contract.get("exchange") if contract else None)
    segment = _first_text(contract.get("segment") if contract else None)
    quote_source = _first_text(quote.get("quote_source") if quote else None, quote.get("source") if quote else None)
    feed_gate_state = _first_text(feed.get("gate_state") if feed else None)

    intent_basis = {
        "strategy_id": strategy_id,
        "rank": rank,
        "symbol": symbol,
        "direction": direction,
        "instrument_token": instrument_token,
        "tradingsymbol": tradingsymbol,
        "evidence_hash": evidence_hash,
    }
    paper_intent_id = _intent_id(intent_basis) if ready else None

    if ready:
        state = PAPER_INTENT_READY
        reasons.append("selected_candidate_promoted_to_paper_intent_contract")
    else:
        state = PAPER_INTENT_BLOCKED
        reasons.append("paper_intent_contract_preconditions_failed")

    return PaperIntentContract(
        schema_version=PAPER_INTENT_SCHEMA_VERSION,
        state=state,
        read_only=True,
        is_order_action=False,
        append=False,
        paper_intent_id=paper_intent_id,
        ready_for_risk_review=ready,
        allowed_for_paper_order=False,
        allowed_for_live_execution=False,
        selected_strategy_id=strategy_id,
        rank=rank,
        symbol=symbol,
        direction=direction,
        final_score=round(final_score, 6) if final_score is not None else None,
        instrument_token=instrument_token,
        tradingsymbol=tradingsymbol,
        exchange=exchange,
        segment=segment,
        bid=bid,
        ask=ask,
        ltp=ltp,
        quote_source=quote_source,
        feed_gate_state=feed_gate_state,
        ranked_pipeline_evidence_hash=evidence_hash,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        metadata={
            "contract": "paper_intent_contract_v1",
            "scope": "read_only_no_order_creation_no_broker_calls",
            "requires_selection_policy": True,
            "requires_exact_contract": True,
            "requires_fresh_feed_gate": True,
            "requires_ranked_pipeline_evidence": True,
        },
    )


__all__ = [
    "PAPER_INTENT_BLOCKED",
    "PAPER_INTENT_READY",
    "PAPER_INTENT_SCHEMA_VERSION",
    "PaperIntentContract",
    "build_paper_intent_contract",
]
