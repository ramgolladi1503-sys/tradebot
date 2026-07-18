from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from research.strategy_outcomes.contract import OutcomeBar, OutcomeCandidate


def candidate_from_orb_ledger_row(row: dict[str, Any]) -> OutcomeCandidate:
    semantic_payload = dict(row.get("semantic_payload") or {})
    symbol = str(row.get("symbol") or semantic_payload.get("symbol") or "")
    session_date = str(row.get("session_date") or "")
    proposal_ready_at = str(
        row.get("proposal_ready_at")
        or row.get("proposal_ready_at_iso")
        or semantic_payload.get("proposal_ready_at_iso")
        or row.get("signal_timestamp")
        or ""
    )
    setup_id = str(row.get("setup_id") or semantic_payload.get("setup_id") or "")
    return OutcomeCandidate(
        candidate_id=str(row.get("candidate_hash") or row.get("signal_identity") or row.get("candidate_id") or setup_id),
        session_key=str(row.get("session_key") or f"{session_date}:{symbol}"),
        symbol=symbol,
        direction=str(row.get("direction") or semantic_payload.get("direction") or ""),
        proposal_ready_at=proposal_ready_at,
        source_hash=str(row.get("source_universe_hash") or row.get("source_hash") or row.get("history_hash") or ""),
        candidate_hash=str(row.get("candidate_hash") or setup_id),
        metadata={
            "strategy_id": "opening_range_retest_v1",
            "session_date": session_date,
            "history_hash": str(row.get("history_hash") or ""),
            "raw_score": row.get("raw_score"),
        },
    )


def bars_from_ohlcv_rows(rows: Iterable[dict[str, Any]], *, session_key: str) -> list[OutcomeBar]:
    bars: list[OutcomeBar] = []
    for row in rows:
        bars.append(
            OutcomeBar(
                timestamp=_canonical_bar_timestamp(row.get("timestamp")),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                session_key=session_key,
            )
        )
    return sorted(bars, key=lambda bar: bar.timestamp)


def canonical_outcome_record_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "artifact_path"}


def canonical_outcome_records_hash(records: Iterable[dict[str, Any]]) -> str:
    from research.strategy_outcomes.contract import canonical_json_hash

    payload = [canonical_outcome_record_payload(dict(record)) for record in records]
    payload.sort(key=lambda item: str(item.get("candidate_id") or ""))
    return canonical_json_hash(payload)


def _canonical_bar_timestamp(value: Any) -> str:
    text = str(value)
    if "T" in text and ("+" in text or text.endswith("Z")):
        return text
    return f"{text.replace(' ', 'T').split('.')[0]}+05:30"
