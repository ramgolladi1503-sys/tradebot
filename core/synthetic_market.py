from __future__ import annotations

import csv
import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional


IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class SyntheticSessionConfig:
    symbol: str
    date: str
    regime: str = "RANGE"
    start_price: float = 25000.0
    bars: int = 360
    bar_sec: int = 60
    seed: int = 1
    base_vol: float = 0.001
    drift: float = 0.0001
    shock_prob: float = 0.02
    shock_sigma: float = 0.02
    gap_prob: float = 0.01
    gap_sigma: float = 0.01


def _ist_start_epoch(date_str: str) -> float:
    day = datetime.fromisoformat(date_str).date()
    start = datetime(day.year, day.month, day.day, 9, 0, 0, tzinfo=IST)
    return start.timestamp()


def _resolve_instrument_token(symbol: str) -> Optional[int]:
    path = Path("data/kite_instruments.csv")
    if not path.exists():
        return None
    sym = symbol.upper()
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").upper()
            ts = (row.get("tradingsymbol") or "").upper()
            if name == sym or ts.startswith(sym):
                try:
                    return int(row.get("instrument_token"))
                except Exception:
                    return None
    return None


def generate_ohlcv_session(cfg: SyntheticSessionConfig) -> List[dict]:
    rng = random.Random(cfg.seed)
    regime = cfg.regime.upper()
    start_epoch = _ist_start_epoch(cfg.date)
    price = cfg.start_price
    mean_price = cfg.start_price
    bars = []

    for i in range(cfg.bars):
        if regime == "TREND":
            drift = cfg.drift
            vol = cfg.base_vol
        elif regime == "EVENT":
            drift = 0.0
            vol = cfg.base_vol * 2.0
        else:
            drift = -0.15 * (price - mean_price) / max(mean_price, 1.0)
            drift *= cfg.base_vol
            vol = cfg.base_vol * 0.8

        ret = drift + rng.gauss(0.0, vol)
        if regime == "EVENT" and rng.random() < cfg.shock_prob:
            ret += rng.gauss(0.0, cfg.shock_sigma)
        if rng.random() < cfg.gap_prob:
            price *= max(0.2, 1.0 + rng.gauss(0.0, cfg.gap_sigma))

        open_px = price
        close_px = max(0.01, price * (1.0 + ret))
        high_px = max(open_px, close_px) * (1.0 + abs(rng.gauss(0.0, vol * 0.5)))
        low_px = min(open_px, close_px) * (1.0 - abs(rng.gauss(0.0, vol * 0.5)))
        volume = int(1000 + abs(ret) * 1_000_000)

        ts_epoch = start_epoch + i * cfg.bar_sec
        ts_iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        bars.append({
            "timestamp_epoch": ts_epoch,
            "timestamp_iso": ts_iso,
            "open": float(open_px),
            "high": float(high_px),
            "low": float(low_px),
            "close": float(close_px),
            "volume": int(volume),
        })
        price = close_px
        mean_price = (mean_price * 0.95) + (price * 0.05)
    return bars


def write_ohlcv_csv(out_path: Path, bars: List[dict]) -> None:
    out_path.parent.mkdir(exist_ok=True)
    fields = ["timestamp_epoch", "timestamp_iso", "open", "high", "low", "close", "volume"]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in bars:
            writer.writerow({k: row.get(k) for k in fields})


def _depth_json_for_price(price: float, spread_bps: float = 5.0) -> str:
    spread = price * (spread_bps / 10000.0)
    bid = max(0.01, price - spread / 2.0)
    ask = price + spread / 2.0
    depth = {
        "depth": {
            "buy": [{"quantity": 100, "price": bid, "orders": 1}] * 5,
            "sell": [{"quantity": 100, "price": ask, "orders": 1}] * 5,
        },
        "imbalance": 0.0,
    }
    return json.dumps(depth)


def write_sqlite_session(db_path: Path, symbol: str, bars: List[dict]) -> None:
    db_path.parent.mkdir(exist_ok=True)
    token = _resolve_instrument_token(symbol)
    if token is None:
        raise RuntimeError(f"instrument_token not found for {symbol}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS ticks ("
        "timestamp_epoch REAL, timestamp TEXT, instrument_token INTEGER, "
        "last_price REAL, volume INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS depth_snapshots ("
        "timestamp_epoch REAL, timestamp TEXT, instrument_token INTEGER, depth_json TEXT)"
    )
    for row in bars:
        cur.execute(
            "INSERT INTO ticks (timestamp_epoch, timestamp, instrument_token, last_price, volume) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                row["timestamp_epoch"],
                row["timestamp_iso"],
                token,
                row["close"],
                row["volume"],
            ),
        )
        cur.execute(
            "INSERT INTO depth_snapshots (timestamp_epoch, timestamp, instrument_token, depth_json) "
            "VALUES (?, ?, ?, ?)",
            (
                row["timestamp_epoch"],
                row["timestamp_iso"],
                token,
                _depth_json_for_price(row["close"]),
            ),
        )
    conn.commit()
    conn.close()
