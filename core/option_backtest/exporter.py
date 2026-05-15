from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def _iter_instrument_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            out: list[dict[str, Any]] = []
            for value in payload.values():
                if isinstance(value, list):
                    out.extend(row for row in value if isinstance(row, dict))
            return out
        return []
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path).to_dict(orient="records")
    return []


def resolve_instrument_token(
    *,
    tradingsymbol: str,
    option_chain_path: Path | None = None,
    instruments_path: Path | None = None,
) -> dict[str, Any]:
    target = str(tradingsymbol or "").strip().upper()
    if not target:
        raise ValueError("tradingsymbol_required")

    candidate_paths = [path for path in [option_chain_path, instruments_path] if path is not None]
    for path in candidate_paths:
        rows = _iter_instrument_rows(path)
        for row in rows:
            ts = str(row.get("tradingsymbol") or "").strip().upper()
            if ts != target:
                continue
            token = _safe_int(row.get("instrument_token"))
            if token is None:
                continue
            return {
                "tradingsymbol": target,
                "instrument_token": token,
                "symbol": str(row.get("symbol") or row.get("name") or "").strip() or None,
                "expiry": row.get("expiry") or row.get("expiry_date"),
                "strike": _safe_float(row.get("strike")),
                "option_type": str(row.get("type") or row.get("option_type") or row.get("instrument_type") or "").strip() or None,
                "source": str(path),
            }
    raise ValueError(f"tradingsymbol_not_found:{target}")


def _load_ticks(
    conn: sqlite3.Connection,
    *,
    instrument_token: int,
    start_ts_epoch: float | None,
    end_ts_epoch: float | None,
) -> pd.DataFrame:
    clauses = ["instrument_token = ?", "timestamp_epoch IS NOT NULL", "last_price IS NOT NULL"]
    params: list[Any] = [int(instrument_token)]
    if start_ts_epoch is not None:
        clauses.append("timestamp_epoch >= ?")
        params.append(float(start_ts_epoch))
    if end_ts_epoch is not None:
        clauses.append("timestamp_epoch <= ?")
        params.append(float(end_ts_epoch))
    query = f"""
        SELECT timestamp_epoch, timestamp_iso, last_price, volume, oi
        FROM ticks
        WHERE {' AND '.join(clauses)}
        ORDER BY timestamp_epoch ASC
    """
    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp_epoch"], unit="s", utc=True)
    return df


def _load_depth(
    conn: sqlite3.Connection,
    *,
    instrument_token: int,
    start_ts_epoch: float | None,
    end_ts_epoch: float | None,
) -> pd.DataFrame:
    clauses = ["instrument_token = ?", "timestamp_epoch IS NOT NULL", "depth_json IS NOT NULL"]
    params: list[Any] = [int(instrument_token)]
    if start_ts_epoch is not None:
        clauses.append("timestamp_epoch >= ?")
        params.append(float(start_ts_epoch))
    if end_ts_epoch is not None:
        clauses.append("timestamp_epoch <= ?")
        params.append(float(end_ts_epoch))
    query = f"""
        SELECT timestamp_epoch, timestamp_iso, depth_json
        FROM depth_snapshots
        WHERE {' AND '.join(clauses)}
        ORDER BY timestamp_epoch ASC
    """
    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return df

    def _parse_side(payload: str, side: str) -> float | None:
        try:
            data = json.loads(payload)
            levels = (((data or {}).get("depth") or {}).get(side) or [])
            if not levels:
                return None
            return _safe_float(levels[0].get("price"))
        except Exception:
            return None

    df["bid"] = df["depth_json"].map(lambda payload: _parse_side(payload, "buy"))
    df["ask"] = df["depth_json"].map(lambda payload: _parse_side(payload, "sell"))
    df["timestamp"] = pd.to_datetime(df["timestamp_epoch"], unit="s", utc=True)
    return df[["timestamp", "bid", "ask"]]


def build_option_backtest_frame(
    *,
    db_path: Path,
    instrument_token: int,
    tradingsymbol: str,
    start_ts_epoch: float | None = None,
    end_ts_epoch: float | None = None,
) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as conn:
        ticks = _load_ticks(
            conn,
            instrument_token=instrument_token,
            start_ts_epoch=start_ts_epoch,
            end_ts_epoch=end_ts_epoch,
        )
        if ticks.empty:
            raise ValueError("no_ticks_for_token")
        depth = _load_depth(
            conn,
            instrument_token=instrument_token,
            start_ts_epoch=start_ts_epoch,
            end_ts_epoch=end_ts_epoch,
        )

    ticks["minute"] = ticks["timestamp"].dt.floor("min")
    bars = (
        ticks.groupby("minute", as_index=False)
        .agg(
            open=("last_price", "first"),
            high=("last_price", "max"),
            low=("last_price", "min"),
            close=("last_price", "last"),
            volume=("volume", "last"),
            oi=("oi", "last"),
        )
        .sort_values("minute")
        .reset_index(drop=True)
    )

    if not depth.empty:
        depth = depth.sort_values("timestamp").copy()
        depth["minute"] = depth["timestamp"].dt.floor("min")
        depth_last = (
            depth.groupby("minute", as_index=False)
            .agg(
                bid=("bid", "last"),
                ask=("ask", "last"),
            )
            .sort_values("minute")
        )
        bars = bars.merge(depth_last, how="left", on="minute")
    else:
        bars["bid"] = pd.NA
        bars["ask"] = pd.NA

    bars["symbol"] = str(tradingsymbol)
    bars["timestamp"] = bars["minute"].dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %H:%M:%S")
    return bars[["timestamp", "symbol", "open", "high", "low", "close", "volume", "oi", "bid", "ask"]]


def export_option_backtest_csv(
    *,
    db_path: Path,
    output_path: Path,
    tradingsymbol: str,
    instrument_token: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    start_ts_epoch = None
    end_ts_epoch = None
    if date_from:
        start_ts_epoch = pd.Timestamp(date_from, tz="Asia/Kolkata").timestamp()
    if date_to:
        end_ts_epoch = (
            pd.Timestamp(date_to, tz="Asia/Kolkata") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        ).timestamp()
    frame = build_option_backtest_frame(
        db_path=db_path,
        instrument_token=instrument_token,
        tradingsymbol=tradingsymbol,
        start_ts_epoch=start_ts_epoch,
        end_ts_epoch=end_ts_epoch,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return {
        "ok": True,
        "output_path": str(output_path),
        "rows": int(len(frame)),
        "tradingsymbol": str(tradingsymbol).upper(),
        "instrument_token": int(instrument_token),
    }
