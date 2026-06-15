from __future__ import annotations

from core.paths import data_root, logs_dir
from datetime import datetime, timezone
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from config import config as cfg

from .events import _append_gzip_jsonl_atomic
from .guard import DiskGuard
from .schema import build_snapshot_record, now_iso_utc


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if out != out:  # NaN
        return None
    return out


def _coerce_epoch(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _best_price(levels: Any) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None
    row = levels[0] or {}
    if not isinstance(row, Mapping):
        return None
    return _safe_float(row.get("price"))


def _best_qty(levels: Any) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None
    row = levels[0] or {}
    if not isinstance(row, Mapping):
        return None
    return _safe_float(row.get("quantity"))


def _depth_summary(depth: Any) -> dict[str, Any]:
    if not isinstance(depth, Mapping):
        return {}
    buy = depth.get("buy") if isinstance(depth.get("buy"), list) else []
    sell = depth.get("sell") if isinstance(depth.get("sell"), list) else []
    top_bid = _best_price(buy)
    top_ask = _best_price(sell)
    bid_qty = _best_qty(buy)
    ask_qty = _best_qty(sell)
    out = {
        "best_bid": top_bid,
        "best_ask": top_ask,
        "best_bid_qty": bid_qty,
        "best_ask_qty": ask_qty,
        "levels_buy": min(len(buy), 5),
        "levels_sell": min(len(sell), 5),
    }
    if bid_qty is not None and ask_qty is not None and (bid_qty + ask_qty) > 0:
        out["imbalance"] = (bid_qty - ask_qty) / (bid_qty + ask_qty)
    return out


def _sqlite_conn() -> sqlite3.Connection:
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))


def _load_tick_rows_before(token: int, ts_epoch: float, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    try:
        with _sqlite_conn() as conn:
            rows = conn.execute(
                """
                SELECT timestamp_epoch, timestamp_iso, last_price, volume, oi
                FROM ticks
                WHERE instrument_token=? AND timestamp_epoch<=?
                ORDER BY timestamp_epoch DESC
                LIMIT ?
                """,
                (int(token), float(ts_epoch), int(limit)),
            ).fetchall()
    except Exception:
        return []
    out = []
    for row in reversed(rows):
        out.append(
            {
                "timestamp_epoch": _safe_float(row[0]),
                "timestamp_iso": str(row[1]) if row[1] is not None else None,
                "last_price": _safe_float(row[2]),
                "volume": _safe_float(row[3]),
                "oi": _safe_float(row[4]),
            }
        )
    return out


def _latest_tick_row(token: int) -> dict[str, Any] | None:
    try:
        with _sqlite_conn() as conn:
            row = conn.execute(
                """
                SELECT timestamp_epoch, timestamp_iso, last_price, volume, oi
                FROM ticks
                WHERE instrument_token=?
                ORDER BY timestamp_epoch DESC
                LIMIT 1
                """,
                (int(token),),
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {
        "timestamp_epoch": _safe_float(row[0]),
        "timestamp_iso": str(row[1]) if row[1] is not None else None,
        "last_price": _safe_float(row[2]),
        "volume": _safe_float(row[3]),
        "oi": _safe_float(row[4]),
    }


def _default_fetch_snapshot(instrument: Mapping[str, Any]) -> dict[str, Any] | None:
    symbol = str(instrument.get("symbol") or "").upper()
    token = instrument.get("instrument_token")
    tradingsymbol = instrument.get("tradingsymbol")

    ltp = None
    bid = None
    ask = None
    volume = None
    oi = None
    ts_iso = None
    ts_epoch = None
    depth_sum: dict[str, Any] = {}

    token_int = None
    if token is not None:
        try:
            token_int = int(token)
        except Exception:
            token_int = None

    if token_int is not None:
        try:
            from core.tick_store import get_last_tick

            tick = get_last_tick(token_int, allow_db=True, decision_path=True)
            if isinstance(tick, Mapping):
                ltp = _safe_float(tick.get("ltp"))
                ts_epoch = _safe_float(tick.get("ts_epoch"))
        except Exception:
            pass
        tick_row = _latest_tick_row(token_int)
        if tick_row:
            volume = tick_row.get("volume")
            oi = tick_row.get("oi")
            if ts_epoch is None:
                ts_epoch = tick_row.get("timestamp_epoch")
            ts_iso = tick_row.get("timestamp_iso")
        try:
            from core.depth_store import depth_store

            depth_entry = depth_store.get(token_int) or {}
            depth = depth_entry.get("depth") if isinstance(depth_entry, Mapping) else None
            if isinstance(depth, Mapping):
                depth_sum = _depth_summary(depth)
                bid = depth_sum.get("best_bid")
                ask = depth_sum.get("best_ask")
        except Exception:
            pass

    if (bid is None or ask is None) and symbol:
        try:
            from core.market_data import get_index_quote_snapshot

            idx_quote = get_index_quote_snapshot(symbol) or {}
            if isinstance(idx_quote, Mapping):
                if bid is None:
                    bid = _safe_float(idx_quote.get("bid"))
                if ask is None:
                    ask = _safe_float(idx_quote.get("ask"))
                if ltp is None:
                    ltp = _safe_float(idx_quote.get("last_price") or idx_quote.get("mid"))
                if ts_epoch is None:
                    ts_epoch = _safe_float(idx_quote.get("ts_epoch"))
        except Exception:
            pass

    if (ltp is None and bid is None and ask is None) and tradingsymbol:
        try:
            from core.kite_client import kite_client

            quote_key = str(tradingsymbol)
            if ":" not in quote_key:
                exchange = "BFO" if symbol == "SENSEX" else "NFO"
                quote_key = f"{exchange}:{quote_key}"
            resp = kite_client.quote([quote_key]) or {}
            qrow = resp.get(quote_key) or {}
            if isinstance(qrow, Mapping):
                ltp = _safe_float(qrow.get("last_price"))
                depth = qrow.get("depth") if isinstance(qrow.get("depth"), Mapping) else None
                if depth:
                    depth_sum = _depth_summary(depth)
                    bid = depth_sum.get("best_bid")
                    ask = depth_sum.get("best_ask")
                if ts_epoch is None:
                    ts_epoch = time.time()
        except Exception:
            pass

    if ltp is None and bid is None and ask is None:
        return None

    ts_iso_final = ts_iso
    if not ts_iso_final:
        ts_val = ts_epoch if ts_epoch is not None else time.time()
        ts_iso_final = datetime.fromtimestamp(ts_val, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    spread_pct = None
    if bid is not None and ask is not None and ask >= bid:
        base = ((bid + ask) / 2.0) if (bid and ask) else (ltp or 0.0)
        if base and base > 0:
            spread_pct = (ask - bid) / base

    return {
        "ts_utc": ts_iso_final,
        "instrument": {
            "symbol": symbol,
            "instrument_id": instrument.get("instrument_id"),
            "instrument_token": token_int,
            "tradingsymbol": tradingsymbol,
        },
        "ltp": ltp,
        "bid": bid,
        "ask": ask,
        "spread_pct": spread_pct,
        "depth_summary": depth_sum,
        "oi": oi,
        "volume": volume,
        "iv": _safe_float(instrument.get("iv")),
    }


class SnapshotStore:
    def __init__(
        self,
        base_dir: str | Path,
        *,
        guard: DiskGuard | None = None,
        fetch_snapshot_fn: Callable[[Mapping[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.snapshots_dir = self.base_dir / "snapshots"
        self.guard = guard or DiskGuard(
            self.base_dir,
            min_free_pct=float(getattr(cfg, "STORAGE_MIN_FREE_PCT", 10.0)),
            critical_free_pct=float(getattr(cfg, "STORAGE_CRITICAL_FREE_PCT", 5.0)),
        )
        self.fetch_snapshot_fn = fetch_snapshot_fn or _default_fetch_snapshot
        self._snapshots_written_by_day: dict[str, int] = {}

    def _daily_path(self, ts_utc: str | None = None) -> Path:
        if ts_utc:
            try:
                dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
                day = dt.date().isoformat()
            except Exception:
                day = datetime.now(timezone.utc).date().isoformat()
        else:
            day = datetime.now(timezone.utc).date().isoformat()
        return self.snapshots_dir / f"snapshots_{day}.jsonl.gz"

    def _bump_counter(self, ts_utc: str) -> None:
        day = ts_utc[:10]
        self._snapshots_written_by_day[day] = int(self._snapshots_written_by_day.get(day, 0)) + 1

    def snapshots_written_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return int(self._snapshots_written_by_day.get(today, 0))

    def store_snapshot(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        if not self.guard.allow_snapshots():
            return None
        try:
            record = build_snapshot_record(payload)
        except Exception:
            return None
        data = record.to_dict()
        try:
            _append_gzip_jsonl_atomic(self._daily_path(record.ts_utc), data)
            self._bump_counter(record.ts_utc)
            return data
        except Exception:
            return None

    def capture_around_event(self, event: Mapping[str, Any]) -> int:
        if not self.guard.allow_snapshots():
            return 0
        event_type = str(event.get("event_type") or "").strip().lower()
        if not self._should_capture_event_type(event_type):
            return 0

        instruments = event.get("instruments")
        normalized: list[dict[str, Any]] = []
        if isinstance(instruments, list):
            for item in instruments:
                if isinstance(item, Mapping):
                    symbol = str(item.get("symbol") or "").upper().strip()
                    if not symbol:
                        continue
                    normalized.append(
                        {
                            "symbol": symbol,
                            "instrument_id": item.get("instrument_id"),
                            "instrument_token": item.get("instrument_token"),
                            "tradingsymbol": item.get("tradingsymbol"),
                        }
                    )
        if not normalized:
            for symbol in event.get("symbols") or []:
                sym = str(symbol or "").strip().upper()
                if sym:
                    normalized.append({"symbol": sym})
        if not normalized:
            return 0

        event_id = str(event.get("event_id") or "")
        event_ts_epoch = _coerce_epoch(event.get("ts_utc")) or time.time()
        n_before = int(getattr(cfg, "STORAGE_SNAPSHOT_N_BEFORE", 2))
        n_after = int(getattr(cfg, "STORAGE_SNAPSHOT_N_AFTER", 0))  # Default 0 to prevent synchronous thread blocking
        interval_ms = int(getattr(cfg, "STORAGE_SNAPSHOT_INTERVAL_MS", 500))
        captured = 0

        for instrument in normalized:
            token = instrument.get("instrument_token")
            token_int = None
            if token is not None:
                try:
                    token_int = int(token)
                except Exception:
                    token_int = None

            if token_int is not None and n_before > 0:
                rows = _load_tick_rows_before(token_int, event_ts_epoch, n_before)
                for row in rows:
                    snapshot_payload = {
                        "ts_utc": row.get("timestamp_iso") or now_iso_utc(),
                        "instrument": {
                            "symbol": instrument.get("symbol"),
                            "instrument_id": instrument.get("instrument_id"),
                            "instrument_token": token_int,
                            "tradingsymbol": instrument.get("tradingsymbol"),
                        },
                        "ltp": row.get("last_price"),
                        "bid": None,
                        "ask": None,
                        "spread_pct": None,
                        "depth_summary": {},
                        "oi": row.get("oi"),
                        "volume": row.get("volume"),
                        "iv": _safe_float(instrument.get("iv")),
                        "capture_reason": {"around_event": event_id, "periodic": None},
                    }
                    if self.store_snapshot(snapshot_payload) is not None:
                        captured += 1

            for idx in range(max(0, n_after)):
                if idx > 0 and interval_ms > 0:
                    time.sleep(interval_ms / 1000.0)
                snap = None
                try:
                    snap = self.fetch_snapshot_fn(instrument)
                except Exception:
                    snap = None
                if not isinstance(snap, Mapping):
                    continue
                payload = dict(snap)
                payload.setdefault("instrument", dict(instrument))
                payload["capture_reason"] = {"around_event": event_id, "periodic": None}
                payload.setdefault("ts_utc", now_iso_utc())
                if self.store_snapshot(payload) is not None:
                    captured += 1

        if captured > 0:
            print(
                f"[Storage] stored snapshots count={captured} event_type={event_type} total_today={self.snapshots_written_today()}"
            )
        return captured

    def _should_capture_event_type(self, event_type: str) -> bool:
        if event_type in {"gate_rejected", "trade_accepted", "trade_exited"}:
            return True
        if event_type == "candidate_created":
            return bool(getattr(cfg, "STORAGE_SNAPSHOTS_FOR_CANDIDATE_CREATED", False))
        return False

    def metrics(self) -> dict[str, Any]:
        state = self.guard.refresh()
        return {
            "snapshots_written_today": self.snapshots_written_today(),
            "disk_free_pct": float(state.free_pct),
            "storage_mode": str(state.mode),
        }
