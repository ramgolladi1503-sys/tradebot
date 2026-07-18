from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from research.strategy_outcomes.adapters.opening_range_retest import candidate_from_orb_ledger_row
from research.strategy_outcomes.contract import HORIZONS_MINUTES, OutcomeCandidate, canonical_json_hash

IST = ZoneInfo("Asia/Kolkata")
CONTRACT_VERSION = "orb_underlying_outcome_v2"
BAR_TIMESTAMP_CONVENTION = "start_labelled_1minute"
ALLOWED_PATH_EVENTS = {"TARGET_FIRST", "STOP_FIRST", "AMBIGUOUS_SAME_BAR", "NEITHER", "INSUFFICIENT_FUTURE_DATA"}
REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")


class OutcomeEngineError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedSource:
    session_key: str
    logical_path: str
    absolute_path: str
    sha256: str
    byte_size: int
    row_count: int
    symbol: str
    session_date: str
    frame: pd.DataFrame


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise OutcomeEngineError(f"naive_timestamp:{value}")
    return dt.astimezone(IST)


def parse_source_timestamp(value: Any) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def canonical_timestamp(dt: datetime) -> str:
    return dt.astimezone(IST).replace(microsecond=0).isoformat()


def source_prefix_hash(frame: pd.DataFrame, proposal_ready_at: datetime) -> str:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        ts = parse_source_timestamp(row["timestamp"])
        if ts <= proposal_ready_at:
            rows.append(
                {
                    "timestamp": canonical_timestamp(ts),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )
    return canonical_json_hash(rows)


def resolve_source_path(project_root: Path, source: dict[str, Any]) -> Path:
    logical = project_root / str(source["logical_path"])
    if logical.exists():
        return logical
    absolute = Path(str(source["absolute_path"]))
    allowed_roots = (
        project_root / "runtime" / "upstox_candidate_replay",
        Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay"),
    )
    try:
        resolved = absolute.resolve()
    except FileNotFoundError:
        return absolute
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots if root.exists()):
        raise OutcomeEngineError(f"source_outside_allowed_root:{absolute}")
    return absolute


def verify_source_record(project_root: Path, source: dict[str, Any]) -> VerifiedSource:
    path = resolve_source_path(project_root, source)
    if not path.exists():
        raise OutcomeEngineError("MISSING_SOURCE_SESSION")
    raw = path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != str(source.get("sha256")):
        raise OutcomeEngineError("SOURCE_HASH_MISMATCH")
    if len(raw) != int(source.get("byte_size") or -1):
        raise OutcomeEngineError("SOURCE_SIZE_MISMATCH")
    frame = pd.read_parquet(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise OutcomeEngineError(f"INVALID_SOURCE_SCHEMA:{','.join(missing)}")
    if len(frame) != int(source.get("row_count") or -1):
        raise OutcomeEngineError("SOURCE_ROW_COUNT_MISMATCH")
    _validate_source_frame(frame, source)
    session_key = f"{source.get('session_date')}:{str(source.get('symbol') or '').upper()}"
    return VerifiedSource(
        session_key=session_key,
        logical_path=str(source["logical_path"]),
        absolute_path=str(path),
        sha256=actual_sha,
        byte_size=len(raw),
        row_count=len(frame),
        symbol=str(source.get("symbol") or "").upper(),
        session_date=str(source.get("session_date") or ""),
        frame=frame.sort_values("timestamp").reset_index(drop=True),
    )


def _validate_source_frame(frame: pd.DataFrame, source: dict[str, Any]) -> None:
    timestamps = [parse_source_timestamp(value) for value in frame["timestamp"]]
    if len(timestamps) != len(set(timestamps)):
        raise OutcomeEngineError("INVALID_SOURCE_HISTORY:duplicate_timestamp")
    if any(curr <= prev for prev, curr in zip(timestamps, timestamps[1:])):
        raise OutcomeEngineError("INVALID_SOURCE_HISTORY:non_monotonic_timestamp")
    declared = str(source.get("session_date") or "")
    if any(ts.date().isoformat() != declared for ts in timestamps):
        raise OutcomeEngineError("INVALID_SOURCE_HISTORY:wrong_declared_session")
    for column in ("open", "high", "low", "close"):
        if (frame[column].astype(float) <= 0).any():
            raise OutcomeEngineError(f"INVALID_SOURCE_HISTORY:invalid_price:{column}")
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    open_ = frame["open"].astype(float)
    close = frame["close"].astype(float)
    if (high < pd.concat([open_, low, close], axis=1).max(axis=1)).any():
        raise OutcomeEngineError("INVALID_SOURCE_HISTORY:invalid_ohlc_high")
    if (low > pd.concat([open_, high, close], axis=1).min(axis=1)).any():
        raise OutcomeEngineError("INVALID_SOURCE_HISTORY:invalid_ohlc_low")
    if "symbol" in frame.columns:
        expected = str(source.get("symbol") or "").upper()
        actual = {_normalize_source_symbol(value) for value in frame["symbol"].dropna().unique()}
        if actual and actual != {expected}:
            raise OutcomeEngineError("INVALID_SOURCE_HISTORY:symbol_mismatch")


def _normalize_source_symbol(value: Any) -> str:
    text = str(value).upper()
    if "NIFTY 50" in text:
        return "NIFTY"
    if "NIFTY BANK" in text or "BANKNIFTY" in text:
        return "BANKNIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    return text


def load_verified_sources(project_root: Path, source_manifest: dict[str, Any]) -> dict[str, VerifiedSource]:
    sources: dict[str, VerifiedSource] = {}
    for source in source_manifest.get("records") or []:
        verified = verify_source_record(project_root, source)
        sources[verified.session_key] = verified
    return sources


def legal_entry_index(frame: pd.DataFrame, proposal_ready_at: datetime) -> int | None:
    for index, value in enumerate(frame["timestamp"]):
        if parse_source_timestamp(value) > proposal_ready_at:
            return index
    return None


def horizon_terminal_index(frame: pd.DataFrame, entry_index: int, horizon: int) -> tuple[datetime, int | None]:
    entry_ts = parse_source_timestamp(frame.iloc[entry_index]["timestamp"])
    expected = entry_ts + timedelta(minutes=int(horizon) - 1)
    for index in range(entry_index, len(frame)):
        ts = parse_source_timestamp(frame.iloc[index]["timestamp"])
        if ts == expected:
            return expected, index
        if ts > expected:
            return expected, None
    return expected, None


def measure_candidate(
    candidate: OutcomeCandidate,
    *,
    source: VerifiedSource | None,
    stop_return: float,
    target_return: float,
) -> dict[str, Any]:
    proposal = parse_timestamp(candidate.proposal_ready_at)
    base = {
        "contract_version": CONTRACT_VERSION,
        "candidate_id": candidate.candidate_id,
        "candidate_hash": candidate.candidate_hash,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "session_key": candidate.session_key,
        "proposal_ready_at": canonical_timestamp(proposal),
        "bar_timestamp_convention": BAR_TIMESTAMP_CONVENTION,
        "candidate_status": "MISSING_SOURCE_SESSION",
        "status_reason": "source_session_symbol_missing",
        "legal_entry_timestamp": None,
        "entry_reference_price": None,
        "session_close_return": None,
        "maximum_legal_horizon": 0,
        "horizons": {},
        "overlap_count": 0,
        "same_direction_overlap_count": 0,
        "opposite_direction_overlap_count": 0,
        "exact_duplicate_directional_exposure": False,
        "overlap_candidate_ids_hash": canonical_json_hash([]),
        "source_logical_path": None,
        "verified_source_sha256": None,
        "source_byte_size": None,
        "source_row_count": None,
        "source_prefix_hash": None,
    }
    if source is None:
        base["horizons"] = _empty_horizons("INVALID_SOURCE_HISTORY")
        return base
    base.update(
        {
            "source_logical_path": source.logical_path,
            "verified_source_sha256": source.sha256,
            "source_byte_size": source.byte_size,
            "source_row_count": source.row_count,
            "source_prefix_hash": source_prefix_hash(source.frame, proposal),
        }
    )
    entry_index = legal_entry_index(source.frame, proposal)
    if entry_index is None:
        base["candidate_status"] = "NO_LEGAL_ENTRY"
        base["status_reason"] = "no_bar_strictly_after_proposal_ready_at"
        base["horizons"] = _empty_horizons("INSUFFICIENT_HORIZON")
        return base
    entry_row = source.frame.iloc[entry_index]
    entry_ts = parse_source_timestamp(entry_row["timestamp"])
    entry_price = float(entry_row["open"])
    base["candidate_status"] = "MEASURED"
    base["status_reason"] = "ok"
    base["legal_entry_timestamp"] = canonical_timestamp(entry_ts)
    base["entry_reference_price"] = entry_price
    close_row = source.frame.iloc[-1]
    base["session_close_return"] = _directional_return(candidate.direction, entry_price, float(close_row["close"]))
    horizons: dict[str, Any] = {}
    max_horizon = 0
    for horizon in HORIZONS_MINUTES:
        expected, terminal_index = horizon_terminal_index(source.frame, entry_index, horizon)
        if terminal_index is None:
            horizons[str(horizon)] = _insufficient_horizon(expected)
            continue
        max_horizon = int(horizon)
        terminal_row = source.frame.iloc[terminal_index]
        window = source.frame.iloc[entry_index : terminal_index + 1]
        horizons[str(horizon)] = _measure_horizon(
            candidate=candidate,
            entry_ts=entry_ts,
            entry_price=entry_price,
            expected_terminal=expected,
            terminal_row=terminal_row,
            window=window,
            stop_return=stop_return,
            target_return=target_return,
        )
    base["maximum_legal_horizon"] = max_horizon
    base["horizons"] = horizons
    return base


def _empty_horizons(status: str) -> dict[str, Any]:
    return {str(h): _null_horizon(status) for h in HORIZONS_MINUTES}


def _null_horizon(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "expected_terminal_timestamp": None,
        "actual_terminal_timestamp": None,
        "forward_return": None,
        "mfe": None,
        "mae": None,
        "elapsed_minutes_to_mfe": None,
        "elapsed_minutes_to_mae": None,
        "path_event": "INSUFFICIENT_FUTURE_DATA",
        "ambiguity_flag": False,
    }


def _insufficient_horizon(expected: datetime) -> dict[str, Any]:
    item = _null_horizon("INSUFFICIENT_HORIZON")
    item["expected_terminal_timestamp"] = canonical_timestamp(expected)
    return item


def _measure_horizon(
    *,
    candidate: OutcomeCandidate,
    entry_ts: datetime,
    entry_price: float,
    expected_terminal: datetime,
    terminal_row: pd.Series,
    window: pd.DataFrame,
    stop_return: float,
    target_return: float,
) -> dict[str, Any]:
    mfe, mfe_ts, mae, mae_ts = _mfe_mae(candidate.direction, entry_price, window)
    event = _path_event(candidate.direction, entry_price, window, stop_return=stop_return, target_return=target_return)
    terminal_ts = parse_source_timestamp(terminal_row["timestamp"])
    return {
        "status": "MEASURED",
        "expected_terminal_timestamp": canonical_timestamp(expected_terminal),
        "actual_terminal_timestamp": canonical_timestamp(terminal_ts),
        "forward_return": _directional_return(candidate.direction, entry_price, float(terminal_row["close"])),
        "mfe": mfe,
        "mae": mae,
        "elapsed_minutes_to_mfe": int((mfe_ts - entry_ts).total_seconds() // 60),
        "elapsed_minutes_to_mae": int((mae_ts - entry_ts).total_seconds() // 60),
        "path_event": event,
        "ambiguity_flag": event == "AMBIGUOUS_SAME_BAR",
    }


def _directional_return(direction: str, entry: float, price: float) -> float:
    raw = (float(price) - float(entry)) / float(entry)
    return raw if direction == "BUY_CALL" else -raw


def _mfe_mae(direction: str, entry: float, window: pd.DataFrame) -> tuple[float, datetime, float, datetime]:
    best_value: float | None = None
    worst_value: float | None = None
    best_ts: datetime | None = None
    worst_ts: datetime | None = None
    for row in window.to_dict(orient="records"):
        ts = parse_source_timestamp(row["timestamp"])
        favorable_price = float(row["high"]) if direction == "BUY_CALL" else float(row["low"])
        adverse_price = float(row["low"]) if direction == "BUY_CALL" else float(row["high"])
        favorable = _directional_return(direction, entry, favorable_price)
        adverse = _directional_return(direction, entry, adverse_price)
        if best_value is None or favorable > best_value:
            best_value = favorable
            best_ts = ts
        if worst_value is None or adverse < worst_value:
            worst_value = adverse
            worst_ts = ts
    assert best_value is not None and worst_value is not None and best_ts is not None and worst_ts is not None
    return best_value, best_ts, worst_value, worst_ts


def _path_event(direction: str, entry: float, window: pd.DataFrame, *, stop_return: float, target_return: float) -> str:
    for row in window.to_dict(orient="records"):
        favorable_price = float(row["high"]) if direction == "BUY_CALL" else float(row["low"])
        adverse_price = float(row["low"]) if direction == "BUY_CALL" else float(row["high"])
        hit_target = _directional_return(direction, entry, favorable_price) >= target_return
        hit_stop = _directional_return(direction, entry, adverse_price) <= -abs(stop_return)
        if hit_target and hit_stop:
            return "AMBIGUOUS_SAME_BAR"
        if hit_target:
            return "TARGET_FIRST"
        if hit_stop:
            return "STOP_FIRST"
    return "NEITHER"


def apply_overlap(records: list[dict[str, Any]]) -> dict[str, Any]:
    intervals: list[tuple[int, str, str, str, datetime, datetime]] = []
    for index, record in enumerate(records):
        if record.get("candidate_status") != "MEASURED":
            continue
        start = parse_timestamp(record["legal_entry_timestamp"])
        max_horizon = int(record.get("maximum_legal_horizon") or 0)
        if max_horizon <= 0:
            continue
        end = start + timedelta(minutes=min(30, max_horizon))
        intervals.append((index, str(record["session_key"]), str(record["symbol"]), str(record["direction"]), start, end))
    same_pairs = 0
    opposite_pairs = 0
    duplicate_groups: dict[str, list[int]] = {}
    overlaps: dict[int, list[int]] = {i: [] for i, *_ in intervals}
    same_by_index: dict[int, int] = {i: 0 for i, *_ in intervals}
    opposite_by_index: dict[int, int] = {i: 0 for i, *_ in intervals}
    for pos, left in enumerate(intervals):
        i, session, symbol, direction, start, end = left
        duplicate_key = f"{session}:{symbol}:{direction}:{records[i]['legal_entry_timestamp']}"
        duplicate_groups.setdefault(duplicate_key, []).append(i)
        for right in intervals[pos + 1 :]:
            j, other_session, other_symbol, other_direction, other_start, other_end = right
            if session != other_session or symbol != other_symbol:
                continue
            if not (start < other_end and other_start < end):
                continue
            overlaps[i].append(j)
            overlaps[j].append(i)
            if direction == other_direction:
                same_pairs += 1
                same_by_index[i] += 1
                same_by_index[j] += 1
            else:
                opposite_pairs += 1
                opposite_by_index[i] += 1
                opposite_by_index[j] += 1
    exact_groups = [members for members in duplicate_groups.values() if len(members) > 1]
    for index, record in enumerate(records):
        ids = sorted(str(records[j]["candidate_id"]) for j in overlaps.get(index, []))
        record["overlap_count"] = len(ids)
        record["same_direction_overlap_count"] = same_by_index.get(index, 0)
        record["opposite_direction_overlap_count"] = opposite_by_index.get(index, 0)
        record["overlap_candidate_ids_hash"] = canonical_json_hash(ids)
    for group in exact_groups:
        for index in group:
            records[index]["exact_duplicate_directional_exposure"] = True
    return {
        "candidates_with_any_overlap": sum(1 for record in records if int(record.get("overlap_count") or 0) > 0),
        "same_direction_overlapping_pairs": same_pairs,
        "opposite_direction_overlapping_pairs": opposite_pairs,
        "exact_duplicate_exposure_groups": len(exact_groups),
        "maximum_simultaneous_same_symbol_candidates": _max_simultaneous(intervals),
    }


def _max_simultaneous(intervals: list[tuple[int, str, str, str, datetime, datetime]]) -> int:
    by_key: dict[tuple[str, str], list[tuple[datetime, int]]] = {}
    for _, session, symbol, _, start, end in intervals:
        by_key.setdefault((session, symbol), []).append((start, 1))
        by_key.setdefault((session, symbol), []).append((end, -1))
    maximum = 0
    for events in by_key.values():
        active = 0
        for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
            active += delta
            maximum = max(maximum, active)
    return maximum


def outcome_records_hash(records: list[dict[str, Any]]) -> str:
    payload = sorted(records, key=lambda item: str(item.get("candidate_id") or ""))
    return canonical_json_hash(payload)


def load_candidates(ledger: dict[str, Any]) -> list[OutcomeCandidate]:
    return [candidate_from_orb_ledger_row(row) for row in ledger.get("records") or []]
