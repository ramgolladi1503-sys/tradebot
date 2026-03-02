from __future__ import annotations
from core.paths import data_root

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
from typing import Any

import pandas as pd

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.kite_client import kite_client


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_output_path(symbol: str, interval: str) -> Path:
    clean_symbol = str(symbol).strip().upper() or "NIFTY"
    clean_interval = str(interval).strip().lower().replace(" ", "_")
    return data_root() / f"{clean_symbol}_{clean_interval}_walk_forward.csv"


def _resolve_index_token(symbol: str) -> int:
    resolved = kite_client.resolve_index_token(symbol)
    try:
        if resolved is not None and int(resolved) > 0:
            return int(resolved)
    except Exception:
        pass
    token_map = getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}
    fallback = token_map.get(str(symbol).upper())
    try:
        if fallback is not None and int(fallback) > 0:
            return int(fallback)
    except Exception:
        pass
    raise RuntimeError(f"Unable to resolve index token for symbol={symbol}")


def _normalize_candles(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows or [])
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    if "date" in frame.columns and "timestamp" not in frame.columns:
        frame["timestamp"] = frame["date"]
    needed = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in frame.columns:
            frame[col] = None
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
    frame["volume"] = frame["volume"].fillna(0.0)
    frame = frame.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return frame[needed].reset_index(drop=True)


def fetch_kite_candles(
    *,
    instrument_token: int,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    chunk_days: int = 60,
) -> list[dict[str, Any]]:
    if end_dt <= start_dt:
        raise ValueError("end_dt must be greater than start_dt")
    if chunk_days <= 0:
        raise ValueError("chunk_days must be positive")

    rows: list[dict[str, Any]] = []
    cursor = start_dt
    while cursor < end_dt:
        chunk_end = min(cursor + timedelta(days=chunk_days), end_dt)
        payload = kite_client.historical_data(instrument_token, cursor, chunk_end, interval=interval) or []
        if isinstance(payload, dict) and "candles" in payload:
            payload = payload.get("candles") or []
        for row in payload:
            if not isinstance(row, dict):
                continue
            rows.append(row)
        # Advance by one second to avoid repeating same bar boundaries.
        cursor = chunk_end + timedelta(seconds=1)
    return rows


def build_walk_forward_input(
    *,
    symbol: str,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    output_path: Path,
    chunk_days: int = 60,
) -> dict[str, Any]:
    token = _resolve_index_token(symbol)
    rows = fetch_kite_candles(
        instrument_token=token,
        interval=interval,
        start_dt=start_dt,
        end_dt=end_dt,
        chunk_days=chunk_days,
    )
    frame = _normalize_candles(rows)
    if frame.empty:
        raise RuntimeError(
            f"No candles returned for symbol={symbol} token={token} interval={interval} "
            f"start={start_dt.isoformat()} end={end_dt.isoformat()}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return {
        "symbol": str(symbol).upper(),
        "interval": interval,
        "instrument_token": int(token),
        "output_path": str(output_path),
        "rows": int(len(frame)),
        "start_utc": frame["timestamp"].min().isoformat(),
        "end_utc": frame["timestamp"].max().isoformat(),
    }


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Build walk-forward input CSV by fetching historical candles from Kite."
    )
    parser.add_argument("--symbol", default="NIFTY", help="Underlying symbol (e.g., NIFTY/BANKNIFTY/SENSEX)")
    parser.add_argument("--interval", default="5minute", help="Kite interval (e.g., minute, 5minute, 15minute)")
    parser.add_argument("--lookback-days", type=int, default=180, help="Lookback window in days when --start is omitted")
    parser.add_argument("--chunk-days", type=int, default=60, help="Days per historical API chunk")
    parser.add_argument("--start", default="", help="UTC/ISO start timestamp (optional)")
    parser.add_argument("--end", default="", help="UTC/ISO end timestamp (optional)")
    parser.add_argument("--output", default="", help="Output CSV path (default: data/<symbol>_<interval>_walk_forward.csv)")
    args = parser.parse_args(argv)

    now_utc = datetime.now(timezone.utc)
    end_dt = _parse_dt(args.end) if str(args.end).strip() else now_utc
    start_dt = _parse_dt(args.start) if str(args.start).strip() else (end_dt - timedelta(days=max(1, int(args.lookback_days))))
    output = Path(str(args.output).strip()) if str(args.output).strip() else _default_output_path(args.symbol, args.interval)

    report = build_walk_forward_input(
        symbol=str(args.symbol).upper(),
        interval=str(args.interval),
        start_dt=start_dt,
        end_dt=end_dt,
        output_path=output,
        chunk_days=max(1, int(args.chunk_days)),
    )
    print(
        f"[WF_INPUT] symbol={report['symbol']} token={report['instrument_token']} interval={report['interval']} "
        f"rows={report['rows']} output={report['output_path']}"
    )
    print(f"[WF_INPUT] range_utc={report['start_utc']} -> {report['end_utc']}")
    return report


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[WF_INPUT][ERROR] {type(exc).__name__}: {exc}")
        raise SystemExit(1)
