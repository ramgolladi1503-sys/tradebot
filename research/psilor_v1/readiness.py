from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


_REQUIRED_EVENT = {
    "timestamp",
    "source_max_timestamp",
    "shock_direction",
    "participation_shock_z",
    "index_underreaction_z",
    "participation_persistence_z",
    "participation_collapse_z",
    "index_catchup_z",
    "index_reversal_z",
}
_REQUIRED_FUTURES = {
    "ts",
    "instrument_key",
    "bid_price",
    "ask_price",
    "bid_quantity",
    "ask_quantity",
    "volume",
}
_REQUIRED_OPTIONS = {
    "ts",
    "instrument_key",
    "bid_price",
    "ask_price",
    "bid_quantity",
    "ask_quantity",
    "volume",
    "delta",
    "theta",
    "gamma",
    "vega",
    "iv",
}
_REQUIRED_MASTER = {
    "instrument_key",
    "tradingsymbol",
    "name",
    "expiry",
    "strike",
    "instrument_type",
    "segment",
    "exchange",
    "lot_size",
}


def _columns(frame_or_columns: pd.DataFrame | Iterable[str] | None) -> set[str]:
    if frame_or_columns is None:
        return set()
    if isinstance(frame_or_columns, pd.DataFrame):
        return set(frame_or_columns.columns)
    return {str(item) for item in frame_or_columns}


def _sessions(frame: pd.DataFrame | None, column: str) -> set[str]:
    if frame is None or frame.empty or column not in frame:
        return set()
    ts = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return set(ts.dropna().dt.date.astype(str))


def audit_psilor_data_readiness(
    *,
    event_rows: pd.DataFrame | Iterable[str] | None,
    futures_ticks: pd.DataFrame | Iterable[str] | None,
    option_ticks: pd.DataFrame | Iterable[str] | None,
    instrument_master: pd.DataFrame | Iterable[str] | None,
    minimum_sessions: int = 30,
) -> dict[str, Any]:
    blockers: list[str] = []
    inputs = (
        ("EVENT", event_rows, _REQUIRED_EVENT),
        ("FUTURES", futures_ticks, _REQUIRED_FUTURES),
        ("OPTION", option_ticks, _REQUIRED_OPTIONS),
        ("INSTRUMENT_MASTER", instrument_master, _REQUIRED_MASTER),
    )
    for name, frame, required in inputs:
        if frame is None:
            blockers.append(f"MISSING_{name}_DATASET")
        missing = sorted(required - _columns(frame))
        if missing:
            blockers.append(f"{name}_FIELDS_MISSING:" + ",".join(missing))

    overlapping_sessions = 0
    if (
        isinstance(event_rows, pd.DataFrame)
        and isinstance(futures_ticks, pd.DataFrame)
        and isinstance(option_ticks, pd.DataFrame)
    ):
        overlap = (
            _sessions(event_rows, "timestamp")
            & _sessions(futures_ticks, "ts")
            & _sessions(option_ticks, "ts")
        )
        overlapping_sessions = len(overlap)
        if overlapping_sessions < int(minimum_sessions):
            blockers.append(
                f"INSUFFICIENT_OVERLAPPING_SESSIONS:{overlapping_sessions}"
            )

    blockers = sorted(set(blockers))
    return {
        "ready": not blockers,
        "verdict": (
            "DATA_READY_FOR_FROZEN_REPLAY"
            if not blockers
            else "NOT_EVALUATED_DATA_BLOCKED"
        ),
        "blockers": blockers,
        "overlapping_sessions": overlapping_sessions,
        "minimum_sessions": int(minimum_sessions),
        "required_columns": {
            "event_rows": sorted(_REQUIRED_EVENT),
            "futures_ticks": sorted(_REQUIRED_FUTURES),
            "option_ticks": sorted(_REQUIRED_OPTIONS),
            "instrument_master": sorted(_REQUIRED_MASTER),
        },
        "read_only": True,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }


def current_drive_option_schema_assessment() -> dict[str, Any]:
    observed = {
        "ts",
        "instrument_key",
        "ltp",
        "bid_price",
        "ask_price",
        "delta",
        "theta",
        "gamma",
        "vega",
        "iv",
        "volume",
        "oi",
    }
    return audit_psilor_data_readiness(
        event_rows=None,
        futures_ticks=None,
        option_ticks=observed,
        instrument_master=None,
    )
