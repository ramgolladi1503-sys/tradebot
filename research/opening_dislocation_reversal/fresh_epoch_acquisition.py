from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any


SAFETY_FLAGS = {
    "read_only": True,
    "append": False,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "execution_eligibility": False,
}

FORBIDDEN_ACQUISITION_FIELDS = {
    "dislocation_threshold",
    "retest_threshold",
    "reference_choice",
    "candidate_horizon",
    "direction_filter",
    "hypothesis_parameters",
}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_artifact(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(data)
    digest = sha256_bytes(data.rstrip(b"\n"))
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_text_artifact(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    digest = sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def month_chunks(start: date, end: date) -> list[dict[str, str]]:
    if end < start:
        raise ValueError("end_before_start")
    chunks: list[dict[str, str]] = []
    cursor = start
    while cursor <= end:
        last_day = monthrange(cursor.year, cursor.month)[1]
        chunk_end = min(date(cursor.year, cursor.month, last_day), end)
        chunks.append({"start": cursor.isoformat(), "end": chunk_end.isoformat(), "state": "PLANNED"})
        cursor = chunk_end.replace(day=1)
        if chunk_end.month == 12:
            cursor = date(chunk_end.year + 1, 1, 1)
        else:
            cursor = date(chunk_end.year, chunk_end.month + 1, 1)
    return chunks


def split_70_30(sessions: list[str]) -> tuple[list[str], list[str]]:
    split_index = (len(sessions) * 70) // 100
    return sessions[:split_index], sessions[split_index:]


def strengthened_session_gates(total: int, development: int, holdout: int, holdout_span_days: int | None) -> dict[str, bool]:
    return {
        "total_sessions": total >= 1800,
        "development_sessions": development >= 1200,
        "holdout_sessions": holdout >= 500,
        "holdout_calendar_span": holdout_span_days is not None and holdout_span_days >= 365,
    }


def validate_acquisition_contract(payload: dict[str, Any]) -> None:
    forbidden = sorted(FORBIDDEN_ACQUISITION_FIELDS & set(payload))
    if forbidden:
        raise ValueError(f"strategy_parameter_fields_forbidden:{','.join(forbidden)}")
    if payload.get("option_data_allowed") is not False:
        raise ValueError("option_data_must_be_forbidden")
    if payload.get("broker_trading_api_allowed") is not False:
        raise ValueError("broker_trading_api_must_be_forbidden")
    if payload.get("candidate_counts_allowed") is not False:
        raise ValueError("candidate_counts_must_be_forbidden")
    if payload.get("strategy_outcomes_allowed") is not False:
        raise ValueError("strategy_outcomes_must_be_forbidden")


def classify_prior_use(session_date: str, prior_dates: set[str]) -> str:
    normalized = session_date.replace("-", "")
    return "PRIOR_OUTCOME_USED" if normalized in prior_dates else "ELIGIBLE_FOR_DATA_VALIDATION"


def resolve_unique_nifty_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [
        row
        for row in rows
        if row.get("instrument_key") == "NSE_INDEX|Nifty 50"
        and str(row.get("instrument_type") or "").upper() == "INDEX"
        and str(row.get("name") or "") == "Nifty 50"
    ]
    if len(matches) != 1:
        raise ValueError(f"instrument_resolution_not_unique:{len(matches)}")
    row = dict(matches[0])
    row["resolution_status"] = "UNIQUE_EXACT_INDEX_MATCH"
    return row


def token_presence_audit(token: str | None) -> dict[str, Any]:
    return {
        "token_present": bool(token),
        "token_printed": False,
        "token_logged": False,
        "token_serialized": False,
        "token_hashed": False,
        "token_length_reported": False,
        "token_prefix_suffix_reported": False,
    }


def classify_historical_access(status_code: int, payload: dict[str, Any] | None) -> str:
    if status_code == 200 and payload and payload.get("status") == "success":
        return "TOKEN_VALID_HISTORICAL_ACCESS_CONFIRMED"
    if status_code in {401, 403}:
        return "TOKEN_INVALID_OR_EXPIRED" if status_code == 401 else "TOKEN_VALID_BUT_HISTORICAL_ACCESS_DENIED"
    if status_code in {400, 404, 405, 422}:
        return "ENDPOINT_CONTRACT_MISMATCH"
    return "PROVIDER_SERVICE_FAILURE"


def redacted_error(status_code: int, payload: dict[str, Any] | None) -> dict[str, Any]:
    code = None
    message_class = "NO_PROVIDER_ERROR_BODY"
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                code = first.get("errorCode") or first.get("code")
                message_class = "PROVIDER_ERROR_REDACTED"
        elif payload.get("code"):
            code = payload.get("code")
            message_class = "PROVIDER_ERROR_REDACTED"
    return {"status_code": status_code, "provider_error_code": code, "message_class": message_class}


def classify_chunk_state(chunk: dict[str, str], supported_start: date, supported_end: date) -> str:
    chunk_start = date.fromisoformat(chunk["start"])
    chunk_end = date.fromisoformat(chunk["end"])
    if chunk_end < supported_start or chunk_start > supported_end:
        return "UNSUPPORTED_BY_PROVIDER"
    return "PLANNED"


def partial_epoch_gate(total_sessions: int) -> dict[str, Any]:
    return {
        "partial_provider_epoch": total_sessions > 0,
        "development_assigned": False,
        "holdout_assigned": False,
        "full_session_floor": total_sessions >= 1800,
        "strategy_authorized": False,
    }
