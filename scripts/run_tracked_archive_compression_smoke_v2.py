#!/usr/bin/env python3
from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any

import pandas as pd

import run_tracked_archive_compression_smoke as smoke_v1


smoke_v1._OPTION_RE = re.compile(
    r"(?P<underlying>BANKNIFTY|NIFTY|SENSEX)"
    r"[ _-]+(?P<strike>\d{4,6}(?:\.\d+)?)"
    r"[ _-]+(?P<option_type>CE|PE)"
    r"[ _-]+(?P<expiry>\d{1,2}[ _-]+[A-Z]{3}[ _-]+\d{2})$",
    re.IGNORECASE,
)


def _select_underlying_member(members: list[str]) -> str:
    preferred = (
        "upstox_candidate_replay/20260709/underlying/"
        "NSE_INDEX|Nifty 50_20260709.parquet",
        "upstox_candidate_replay/20260709/underlying/NIFTY 50.parquet",
    )
    for member in preferred:
        if member in members:
            return member

    candidates: list[str] = []
    for member in members:
        path = PurePosixPath(member)
        stem = path.stem.upper()
        if smoke_v1.SESSION_DIRECTORY not in path.parts:
            continue
        if path.suffix.lower() != ".parquet":
            continue
        if "NIFTY" not in stem or "BANKNIFTY" in stem:
            continue
        if re.search(r"(?:^|[ _-])(CE|PE)(?:$|[ _-])", stem):
            continue
        if "NSE_INDEX" in stem or stem in {"NIFTY 50", "NIFTY"}:
            candidates.append(member)

    if len(candidates) != 1:
        raise ValueError(
            f"underlying_member_not_unique:{len(candidates)}:{candidates[:10]}"
        )
    return candidates[0]


def _empty_option_bars(contract_symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns, Asia/Kolkata]"),
            "open": pd.Series(dtype=float),
            "high": pd.Series(dtype=float),
            "low": pd.Series(dtype=float),
            "close": pd.Series(dtype=float),
            "volume": pd.Series(dtype=float),
            "contract_symbol": pd.Series(dtype=str),
        }
    )


def _normalise_tick_volume(series: pd.Series) -> pd.Series:
    cumulative = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    increment = cumulative.diff()
    increment = increment.where(increment >= 0.0, cumulative)
    return increment.fillna(0.0).clip(lower=0.0)


def _normalize_ohlcv(
    frame: pd.DataFrame,
    *,
    symbol: str,
    contract_symbol: str | None = None,
) -> pd.DataFrame:
    lowered = {str(column).strip().lower() for column in frame.columns}
    if {"open", "high", "low", "close"}.issubset(lowered):
        return smoke_v1_original_normalize(
            frame,
            symbol=symbol,
            contract_symbol=contract_symbol,
        )

    if contract_symbol is None:
        raise ValueError(f"tick_schema_not_valid_for_underlying:{symbol}")

    timestamp_column = smoke_v1._first_column(
        frame, ("timestamp", "date", "datetime", "ts", "time")
    )
    ltp_column = smoke_v1._first_column(frame, ("ltp", "last_price", "close"))
    volume_column = smoke_v1._first_column(frame, ("vol", "volume", "v"))
    if timestamp_column is None:
        raise ValueError(f"missing_tick_timestamp_column:{symbol}")
    if ltp_column is None:
        raise ValueError(f"missing_tick_ltp_column:{symbol}")

    ticks = pd.DataFrame()
    ticks["timestamp"] = smoke_v1._timestamps(frame[timestamp_column])
    ticks["ltp"] = pd.to_numeric(frame[ltp_column], errors="coerce")
    ticks["volume_increment"] = (
        _normalise_tick_volume(frame[volume_column])
        if volume_column is not None
        else 0.0
    )
    ticks = ticks.loc[
        ticks["timestamp"].notna()
        & ticks["ltp"].notna()
        & (ticks["ltp"] > 0.0)
    ].copy()
    if ticks.empty:
        return _empty_option_bars(contract_symbol)

    ticks = ticks.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    ticks["minute"] = ticks["timestamp"].dt.floor("min")
    grouped = ticks.groupby("minute", sort=True, observed=True)
    bars = grouped["ltp"].agg(
        open="first",
        high="max",
        low="min",
        close="last",
    )
    bars["volume"] = grouped["volume_increment"].sum()
    bars = bars.reset_index().rename(columns={"minute": "timestamp"})
    bars["contract_symbol"] = contract_symbol
    return bars[
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "contract_symbol",
        ]
    ].reset_index(drop=True)


def _quote_coverage(frame: pd.DataFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for source, name in (
        ("ltp", "positive_ltp"),
        ("bid", "positive_bid"),
        ("ask", "positive_ask"),
    ):
        if source in frame.columns:
            values = pd.to_numeric(frame[source], errors="coerce")
            payload[f"{name}_rows"] = int((values > 0.0).sum())
            payload[f"{name}_coverage"] = (
                float((values > 0.0).mean()) if len(values) else 0.0
            )
    if "bid" in frame.columns and "ask" in frame.columns:
        bid = pd.to_numeric(frame["bid"], errors="coerce")
        ask = pd.to_numeric(frame["ask"], errors="coerce")
        joint = (bid > 0.0) & (ask > 0.0) & (ask >= bid)
        payload["valid_joint_bid_ask_rows"] = int(joint.sum())
        payload["valid_joint_bid_ask_coverage"] = (
            float(joint.mean()) if len(joint) else 0.0
        )
    return payload


def _read_parquet_member(
    archive: Any,
    member: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    frame, metadata = smoke_v1_original_read_member(archive, member)
    return frame, {**metadata, **_quote_coverage(frame)}


def _run_smoke(path: Any) -> dict[str, object]:
    result = smoke_v1_original_run_smoke(path)
    option_members = list(result.get("option_members") or [])
    positive_ltp_rows = sum(
        int(item.get("positive_ltp_rows") or 0)
        for item in option_members
        if isinstance(item, dict)
    )
    valid_joint_bid_ask_rows = sum(
        int(item.get("valid_joint_bid_ask_rows") or 0)
        for item in option_members
        if isinstance(item, dict)
    )
    result["positive_option_ltp_rows"] = positive_ltp_rows
    result["valid_joint_bid_ask_rows"] = valid_joint_bid_ask_rows
    result["option_price_authority"] = (
        "ZERO_USABLE_OPTION_PRICES"
        if positive_ltp_rows == 0
        else "LTP_TICK_PRICE_PATH_AVAILABLE"
    )
    result["option_candle_backtest_authorized"] = positive_ltp_rows > 0
    result["bid_ask_execution_certified"] = False
    if positive_ltp_rows == 0:
        result["status"] = "ARCHIVE_SCHEMA_ONLY_ZERO_USABLE_OPTION_PRICES"
        result["coverage_verdict"] = "ONE_SESSION_SCHEMA_ONLY_NO_OPTION_ECONOMICS"
    return result


smoke_v1_original_normalize = smoke_v1._normalize_ohlcv
smoke_v1_original_read_member = smoke_v1._read_parquet_member
smoke_v1_original_run_smoke = smoke_v1.run_smoke
smoke_v1._select_underlying_member = _select_underlying_member
smoke_v1._normalize_ohlcv = _normalize_ohlcv
smoke_v1._read_parquet_member = _read_parquet_member
smoke_v1.run_smoke = _run_smoke


if __name__ == "__main__":
    raise SystemExit(smoke_v1.main())
