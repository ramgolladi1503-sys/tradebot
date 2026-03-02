from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _safe_to_datetime(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    except TypeError:
        return pd.to_datetime(series, errors="coerce", utc=True)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return set()
    cols = set()
    for row in rows:
        try:
            cols.add(str(row[1]))
        except Exception:
            continue
    return cols


def _epoch_to_datetime_utc(series: pd.Series) -> pd.Series:
    epoch = pd.to_numeric(series, errors="coerce")
    if epoch.empty:
        return pd.to_datetime(pd.Series(dtype="float64"), errors="coerce", utc=True)
    # Support both seconds and milliseconds in legacy rows.
    epoch_sec = epoch.where(epoch < 1_000_000_000_000, epoch / 1000.0)
    return pd.to_datetime(epoch_sec, unit="s", errors="coerce", utc=True)


def _parse_depth_payload(payload: str | dict | list | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"depth": payload}
    try:
        return json.loads(payload)
    except Exception:
        return None


def _extract_depth_features(depth_payload: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not depth_payload:
        return None, None

    imbalance = depth_payload.get("imbalance")
    depth = depth_payload.get("depth") or {}
    buy = depth.get("buy") or []
    sell = depth.get("sell") or []

    best_bid = buy[0].get("price") if buy else None
    best_ask = sell[0].get("price") if sell else None

    if best_bid is None or best_ask is None:
        return imbalance, None

    try:
        best_bid = float(best_bid)
        best_ask = float(best_ask)
    except Exception:
        return imbalance, None

    if best_bid <= 0 or best_ask <= 0:
        return imbalance, None

    mid = (best_bid + best_ask) / 2.0
    if mid <= 0:
        return imbalance, None

    spread_pct = (best_ask - best_bid) / mid
    return imbalance, spread_pct


def build_tick_dataset(
    db_path,
    horizon: int = 2,
    threshold: float = 0.001,
    out_path: str | Path | None = None,
    from_depth: bool = False,
    depth_tolerance_sec: int = 2,
) -> pd.DataFrame:
    """
    Build a tick-level training dataset from sqlite ticks and optional depth snapshots.

    This module is intentionally pure and side-effect free at import time.
    """
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    try:
        tick_cols = _table_columns(conn, "ticks")
        tick_select_cols = ["timestamp", "instrument_token", "last_price", "volume", "oi"]
        if "timestamp_epoch" in tick_cols:
            tick_select_cols.append("timestamp_epoch")
        if "timestamp_iso" in tick_cols:
            tick_select_cols.append("timestamp_iso")
        df_ticks = pd.read_sql_query(
            f"SELECT {', '.join(tick_select_cols)} FROM ticks",
            conn,
        )
        if df_ticks.empty:
            df_ticks = pd.DataFrame(
                columns=["timestamp", "instrument_token", "last_price", "volume", "oi"]
            )

        ts_text = pd.Series(pd.NaT, index=df_ticks.index, dtype="datetime64[ns, UTC]")
        if "timestamp_iso" in df_ticks.columns:
            ts_text = _safe_to_datetime(df_ticks["timestamp_iso"])
        elif "timestamp" in df_ticks.columns:
            ts_text = _safe_to_datetime(df_ticks["timestamp"])
        if "timestamp_epoch" in df_ticks.columns:
            ts_epoch = _epoch_to_datetime_utc(df_ticks["timestamp_epoch"])
            df_ticks["ts"] = ts_epoch.fillna(ts_text)
        else:
            df_ticks["ts"] = ts_text
        df_ticks["_row_id"] = np.arange(len(df_ticks), dtype=int)
        df_ticks = df_ticks.sort_values(["instrument_token", "ts", "_row_id"]).reset_index(drop=True)

        if "last_price" in df_ticks.columns:
            df_ticks["future_price"] = (
                df_ticks.groupby("instrument_token")["last_price"].shift(-horizon)
            )
            df_ticks["ret"] = (
                df_ticks["future_price"] - df_ticks["last_price"]
            ) / df_ticks["last_price"]
            df_ticks["target"] = (df_ticks["ret"] > float(threshold)).astype(int)

        if from_depth:
            df_depth = pd.read_sql_query(
                "SELECT timestamp, instrument_token, depth_json FROM depth_snapshots",
                conn,
            )
            if not df_depth.empty:
                df_depth["ts"] = _safe_to_datetime(df_depth["timestamp"])
                df_depth = df_depth.sort_values(["instrument_token", "ts"]).reset_index(drop=True)

                df_ticks_sorted = df_ticks.sort_values(["instrument_token", "ts"]).reset_index(drop=True)
                merged = pd.merge_asof(
                    df_ticks_sorted,
                    df_depth,
                    by="instrument_token",
                    left_on="ts",
                    right_on="ts",
                    tolerance=pd.Timedelta(seconds=float(depth_tolerance_sec)),
                    direction="nearest",
                )

                parsed = merged["depth_json"].apply(_parse_depth_payload)
                feats = parsed.apply(_extract_depth_features)
                merged["depth_imbalance"] = feats.apply(lambda x: x[0])
                merged["depth_spread_pct"] = feats.apply(lambda x: x[1])
                df_ticks = merged
            else:
                df_ticks["depth_imbalance"] = np.nan
                df_ticks["depth_spread_pct"] = np.nan

        if "_row_id" in df_ticks.columns:
            df_ticks = df_ticks.drop(columns=["_row_id"])

        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df_ticks.to_csv(out_path, index=False)

        return df_ticks
    finally:
        conn.close()


__all__ = ["build_tick_dataset"]
