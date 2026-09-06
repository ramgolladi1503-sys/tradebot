from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import db_dir, reports_dir
from core.time_utils import now_utc_epoch

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
SCHEMA_VERSION = "1.0"


class SessionMemoryError(RuntimeError):
    pass


class SessionMemoryConflict(SessionMemoryError):
    pass


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        out = value
    elif isinstance(value, (int, float)):
        out = datetime.fromtimestamp(float(value), tz=IST)
    else:
        out = datetime.fromisoformat(str(value))
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST)
    return out.astimezone(IST)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256((_json(value) if not isinstance(value, str) else value).encode("utf-8")).hexdigest()


def _open(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), SESSION_OPEN, tzinfo=IST)


def _close(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), SESSION_CLOSE, tzinfo=IST)


def _num(value: Any) -> float:
    out = float(value)
    if out != out or out in (float("inf"), float("-inf")):
        raise ValueError("non_finite_number")
    return out


def _normalize(symbol: str, bar: dict[str, Any]) -> dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol_missing")
    ts = _dt(bar.get("ts") or bar.get("date")).replace(second=0, microsecond=0)
    o, h, l, c = (_num(bar.get(k)) for k in ("open", "high", "low", "close"))
    v = _num(bar.get("volume", 0) or 0)
    if min(o, h, l, c) <= 0:
        raise ValueError("non_positive_ohlc")
    if h < max(o, l, c):
        raise ValueError("high_invariant_failed")
    if l > min(o, h, c):
        raise ValueError("low_invariant_failed")
    row = {
        "schema_version": SCHEMA_VERSION,
        "session_date": ts.date().isoformat(),
        "symbol": sym,
        "timeframe": "1m",
        "ts_epoch": float(ts.timestamp()),
        "ts_ist": ts.isoformat(),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "provenance": dict(bar.get("bar_provenance") or {}),
    }
    row["row_hash"] = _sha(row)
    return row


class MarketSessionStore:
    """Canonical durable intraday memory. Completed 1m bars are immutable."""

    def __init__(self, db_path: str | Path | None = None, report_root: str | Path | None = None):
        configured = str(getattr(cfg, "MARKET_SESSION_MEMORY_DB_PATH", "") or "").strip()
        self.db_path = Path(db_path or configured or (db_dir() / "market_session_memory.sqlite"))
        self.report_root = Path(report_root or (reports_dir() / "market_session_memory"))
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._loaded: set[tuple[str, str]] = set()
        self._conflicts = 0
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS market_session_bars(
              session_date TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
              ts_epoch REAL NOT NULL, ts_ist TEXT NOT NULL, open REAL NOT NULL,
              high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,
              provenance_json TEXT NOT NULL, row_hash TEXT NOT NULL, persisted_at_epoch REAL NOT NULL,
              PRIMARY KEY(session_date,symbol,timeframe,ts_epoch));
            CREATE INDEX IF NOT EXISTS idx_market_session_bars_lookup
              ON market_session_bars(session_date,symbol,timeframe,ts_epoch);
            CREATE TABLE IF NOT EXISTS market_session_features(
              session_date TEXT NOT NULL, symbol TEXT NOT NULL, as_of_epoch REAL NOT NULL,
              as_of_ist TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
              PRIMARY KEY(session_date,symbol,as_of_epoch));
            CREATE TABLE IF NOT EXISTS market_session_seals(
              session_date TEXT PRIMARY KEY, sealed_at_epoch REAL NOT NULL,
              manifest_json TEXT NOT NULL, manifest_hash TEXT NOT NULL);
            """)

    def persist_completed_bar(self, symbol: str, bar: dict[str, Any]) -> dict[str, Any]:
        row = _normalize(symbol, bar)
        ts = _dt(row["ts_ist"])
        if ts.time() < SESSION_OPEN or ts.time() >= SESSION_CLOSE:
            return {"status": "SKIPPED_OUTSIDE_SESSION", "persisted": False, "row_hash": row["row_hash"]}
        key = (row["session_date"], row["symbol"])
        with self._lock, self._conn() as conn:
            old = conn.execute("SELECT row_hash FROM market_session_bars WHERE session_date=? AND symbol=? AND timeframe='1m' AND ts_epoch=?", (row["session_date"], row["symbol"], row["ts_epoch"])).fetchone()
            if old:
                if str(old["row_hash"]) != row["row_hash"]:
                    self._conflicts += 1
                    raise SessionMemoryConflict(f"immutable_bar_conflict:{row['session_date']}:{row['symbol']}:{row['ts_ist']}")
                return {"status": "EXISTS", "persisted": True, "row_hash": row["row_hash"]}
            conn.execute("INSERT INTO market_session_bars VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                row["session_date"], row["symbol"], "1m", row["ts_epoch"], row["ts_ist"],
                row["open"], row["high"], row["low"], row["close"], row["volume"],
                _json(row["provenance"]), row["row_hash"], float(now_utc_epoch())))
        if key in self._cache:
            cached = dict(row); cached["ts"] = ts; cached["bar_provenance"] = dict(row["provenance"])
            self._cache[key].append(cached); self._cache[key].sort(key=lambda r: r["ts_epoch"])
        return {"status": "INSERTED", "persisted": True, "row_hash": row["row_hash"]}

    def _load(self, day: str, symbol: str) -> list[dict[str, Any]]:
        key = (str(day), str(symbol).upper())
        with self._lock:
            if key in self._loaded:
                return [dict(r) for r in self._cache.get(key, [])]
            with self._conn() as conn:
                rows = conn.execute("SELECT * FROM market_session_bars WHERE session_date=? AND symbol=? AND timeframe='1m' ORDER BY ts_epoch", key).fetchall()
            out = []
            for r in rows:
                try: prov = json.loads(r["provenance_json"] or "{}")
                except Exception: prov = {}
                out.append({
                    "schema_version": SCHEMA_VERSION, "session_date": r["session_date"],
                    "symbol": r["symbol"], "timeframe": "1m", "ts_epoch": float(r["ts_epoch"]),
                    "ts_ist": r["ts_ist"], "ts": _dt(r["ts_ist"]), "open": float(r["open"]),
                    "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"]),
                    "volume": float(r["volume"]), "provenance": prov, "bar_provenance": prov,
                    "row_hash": r["row_hash"]})
            self._cache[key] = out; self._loaded.add(key)
            return [dict(r) for r in out]

    def _derive(self, bars: list[dict[str, Any]], timeframe: str, as_of: datetime) -> list[dict[str, Any]]:
        minutes = TIMEFRAMES.get(str(timeframe))
        if minutes is None:
            raise ValueError(f"unsupported_timeframe:{timeframe}")
        if minutes == 1:
            return [dict(r) for r in bars if float(r["ts_epoch"]) + 60 <= as_of.timestamp()]
        if not bars:
            return []
        anchor = _open(bars[0]["session_date"]); groups: dict[int, list[dict[str, Any]]] = {}
        for row in bars:
            offset = int((_dt(row["ts"]) - anchor).total_seconds() // 60)
            if offset >= 0: groups.setdefault(offset // minutes, []).append(row)
        out = []
        for bucket, group in sorted(groups.items()):
            group = sorted(group, key=lambda r: r["ts_epoch"])
            epochs = [int(float(r["ts_epoch"])) for r in group]
            contiguous = len(group) == minutes and all(epochs[i] - epochs[i-1] == 60 for i in range(1, len(epochs)))
            start = anchor + timedelta(minutes=bucket * minutes)
            if not contiguous or start + timedelta(minutes=minutes) > as_of:
                continue
            out.append({
                "schema_version": SCHEMA_VERSION, "session_date": bars[0]["session_date"],
                "symbol": group[0]["symbol"], "timeframe": str(timeframe), "ts": start,
                "ts_epoch": float(start.timestamp()), "ts_ist": start.isoformat(),
                "open": float(group[0]["open"]), "high": max(float(r["high"]) for r in group),
                "low": min(float(r["low"]) for r in group), "close": float(group[-1]["close"]),
                "volume": sum(float(r["volume"]) for r in group), "constituent_1m_bars": minutes})
        return out

    def get_bars(self, symbol: str, *, as_of: Any, timeframe: str = "1m", session_date: str | None = None) -> list[dict[str, Any]]:
        when = _dt(as_of); day = str(session_date or when.date().isoformat())
        return self._derive(self._load(day, str(symbol).strip().upper()), timeframe, when)

    def persist_feature_snapshot(self, symbol: str, *, as_of: Any, payload: dict[str, Any]) -> dict[str, Any]:
        when = _dt(as_of); sym = str(symbol or "").strip().upper()
        if not sym: raise ValueError("symbol_missing")
        compact = dict(payload or {}); compact.pop("option_chain", None)
        body = {"schema_version": SCHEMA_VERSION, "session_date": when.date().isoformat(), "symbol": sym,
                "as_of_epoch": float(when.timestamp()), "as_of_ist": when.isoformat(), "payload": compact}
        text = _json(body); digest = _sha(text)
        with self._lock, self._conn() as conn:
            existing = conn.execute("SELECT payload_hash FROM market_session_features WHERE session_date=? AND symbol=? AND as_of_epoch=?",
                                    (body["session_date"], sym, body["as_of_epoch"])).fetchone()
            if existing:
                if str(existing["payload_hash"]) != digest:
                    raise SessionMemoryConflict(f"immutable_feature_conflict:{body['session_date']}:{sym}:{body['as_of_ist']}")
                return {"status": "EXISTS", "payload_hash": digest}
            conn.execute("INSERT INTO market_session_features VALUES(?,?,?,?,?,?)",
                         (body["session_date"], sym, body["as_of_epoch"], body["as_of_ist"], text, digest))
        return {"status": "OK", "payload_hash": digest}

    def get_feature_snapshots(self, symbol: str, *, as_of: Any) -> list[dict[str, Any]]:
        when = _dt(as_of); day = when.date().isoformat(); sym = str(symbol).strip().upper()
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM market_session_features WHERE session_date=? AND symbol=? AND as_of_epoch<=? ORDER BY as_of_epoch", (day, sym, when.timestamp())).fetchall()
        out = []
        for r in rows:
            try: body = json.loads(r["payload_json"] or "{}")
            except Exception: body = {}
            out.append({"as_of_epoch": float(r["as_of_epoch"]), "as_of_ist": r["as_of_ist"], "payload": dict(body.get("payload") or {}), "payload_hash": r["payload_hash"]})
        return out

    def build_context(self, symbol: str, *, as_of: Any) -> dict[str, Any]:
        when = _dt(as_of); day = when.date().isoformat(); one = self.get_bars(symbol, as_of=when, timeframe="1m")
        counts = {tf: len(self.get_bars(symbol, as_of=when, timeframe=tf)) for tf in TIMEFRAMES}
        effective = min(when, _close(day)); expected = max(0, int((effective - _open(day)).total_seconds() // 60)) if effective > _open(day) else 0
        observed = {int(float(r["ts_epoch"])) for r in one}; missing = []
        for i in range(expected):
            stamp = _open(day) + timedelta(minutes=i)
            if int(stamp.timestamp()) not in observed: missing.append(stamp.isoformat())
        current = one[-1]["close"] if one else None; opening = one[0]["open"] if one else None
        def ret(minutes: int):
            if not one or current is None: return None
            cutoff = when - timedelta(minutes=minutes); prior = [r for r in one if _dt(r["ts"]) <= cutoff]
            if not prior or float(prior[-1]["close"]) == 0: return None
            return (float(current) / float(prior[-1]["close"]) - 1) * 100
        return {
            "schema_version": SCHEMA_VERSION, "symbol": str(symbol).strip().upper(), "session_date": day,
            "as_of_ist": when.isoformat(), "authoritative": True, "source": "market_session_memory",
            "bars": counts, "session_open": opening,
            "session_high": max((float(r["high"]) for r in one), default=None),
            "session_low": min((float(r["low"]) for r in one), default=None), "current_close": current,
            "return_since_open_pct": None if not opening or current is None else (float(current)/float(opening)-1)*100,
            "range_points": None if not one else max(float(r["high"]) for r in one)-min(float(r["low"]) for r in one),
            "return_15m_pct": ret(15), "return_30m_pct": ret(30), "return_60m_pct": ret(60),
            "expected_1m_bars": expected, "observed_1m_bars": len(one), "missing_1m_bars": len(missing),
            "missing_1m_sample": missing[:20], "coverage_pct": 100.0 if expected == 0 else round(len(one)/expected*100, 6),
            "authoritative_up_to_ist": one[-1]["ts_ist"] if one else None}

    def verify_integrity(self, session_date: str, symbols: Iterable[str] | None = None) -> dict[str, Any]:
        day = str(session_date); wanted = {str(s).strip().upper() for s in (symbols or []) if str(s).strip()}
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM market_session_bars WHERE session_date=? AND timeframe='1m' ORDER BY symbol,ts_epoch", (day,)).fetchall()
        failures = []; counts: Counter[str] = Counter(); last: dict[str, float] = {}
        for r in rows:
            sym = str(r["symbol"]).upper()
            if wanted and sym not in wanted: continue
            counts[sym] += 1
            if sym in last and float(r["ts_epoch"]) <= last[sym]: failures.append(f"non_monotonic:{sym}:{r['ts_ist']}")
            last[sym] = float(r["ts_epoch"])
            try:
                prov = json.loads(r["provenance_json"] or "{}")
                check = _normalize(sym, {"ts": r["ts_ist"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "volume": r["volume"], "bar_provenance": prov})
                if check["row_hash"] != r["row_hash"]: failures.append(f"hash_mismatch:{sym}:{r['ts_ist']}")
            except Exception as exc: failures.append(f"invalid_row:{sym}:{r['ts_ist']}:{type(exc).__name__}")
        return {"status": "PASS" if not failures else "FAIL", "session_date": day, "symbols": dict(sorted(counts.items())), "failures": failures, "conflicts_seen_this_process": self._conflicts}

    @staticmethod
    def summarize_decisions(session_date: str, trade_db_path: str | Path | None = None) -> dict[str, Any]:
        raw = str(trade_db_path or getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
        if not raw or not Path(raw).exists(): return {"available": False, "total": 0, "execution_allowed": 0, "blocked": 0, "first_blocking_gates": {}}
        try:
            with sqlite3.connect(raw) as conn:
                rows = conn.execute("SELECT execution_allowed,first_blocking_gate FROM candidate_decision_events WHERE trade_date=?", (str(session_date),)).fetchall()
        except Exception: return {"available": False, "total": 0, "execution_allowed": 0, "blocked": 0, "first_blocking_gates": {}}
        allowed = sum(bool(r[0]) for r in rows); gates = Counter(str(r[1] or "NONE") for r in rows if not bool(r[0]))
        return {"available": True, "total": len(rows), "execution_allowed": allowed, "blocked": len(rows)-allowed, "first_blocking_gates": dict(gates.most_common())}

    def seal_session(self, session_date: str, symbols: Iterable[str]) -> dict[str, Any]:
        day = str(session_date); syms = [str(s).strip().upper() for s in symbols if str(s).strip()]
        integrity = self.verify_integrity(day, syms); contexts = {s: self.build_context(s, as_of=_close(day)+timedelta(minutes=1)) for s in syms}
        threshold = float(getattr(cfg, "MARKET_SESSION_MEMORY_READY_COVERAGE_PCT", 99.5) or 99.5)
        issues = [f"coverage:{s}:{c['coverage_pct']:.3f}<{threshold:.3f}" for s,c in contexts.items() if float(c.get("coverage_pct") or 0) < threshold]
        if integrity["status"] != "PASS": issues.append("integrity_failed")
        manifest = {"schema_version": SCHEMA_VERSION, "session_date": day, "sealed_at_epoch": float(now_utc_epoch()),
                    "integrity": integrity, "contexts": contexts, "decision_summary": self.summarize_decisions(day),
                    "readiness": {"status": "READY" if not issues else "NOT_READY", "required_coverage_pct": threshold, "issues": issues}}
        text = _json(manifest); digest = _sha(text); out = self.report_root/day; out.mkdir(parents=True, exist_ok=True)
        manifest_path = out/"session_manifest.json"; manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str)+"\n", encoding="utf-8")
        bars_path = out/"bars_1m.jsonl"
        with bars_path.open("w", encoding="utf-8") as handle:
            for sym in syms:
                for row in self._load(day, sym):
                    serial = dict(row); serial["ts"] = serial["ts_ist"]; handle.write(_json(serial)+"\n")
        hashes = {"session_manifest.json": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "bars_1m.jsonl": hashlib.sha256(bars_path.read_bytes()).hexdigest(), "manifest_payload_sha256": digest}
        hashes_path = out/"SHA256SUMS.json"; hashes_path.write_text(json.dumps(hashes, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        with self._lock, self._conn() as conn:
            existing = conn.execute("SELECT manifest_hash FROM market_session_seals WHERE session_date=?", (day,)).fetchone()
            if existing:
                if str(existing["manifest_hash"]) != digest:
                    raise SessionMemoryConflict(f"immutable_seal_conflict:{day}")
            else:
                conn.execute("INSERT INTO market_session_seals VALUES(?,?,?,?)", (day, manifest["sealed_at_epoch"], text, digest))
        return {"status": "PASS" if integrity["status"] == "PASS" else "FAIL", "session_date": day, "readiness": manifest["readiness"], "manifest_path": str(manifest_path), "bars_path": str(bars_path), "hashes_path": str(hashes_path), "manifest_payload_sha256": digest, "integrity": integrity}

    def verify_seal(self, session_date: str) -> dict[str, Any]:
        day = str(session_date)
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT manifest_json,manifest_hash FROM market_session_seals WHERE session_date=?", (day,)).fetchone()
        if not row: return {"status": "FAIL", "reason": "seal_missing", "session_date": day}
        actual = _sha(str(row["manifest_json"])); expected = str(row["manifest_hash"])
        return {"status": "PASS" if actual == expected else "FAIL", "reason": None if actual == expected else "manifest_hash_mismatch", "session_date": day, "manifest_payload_sha256": expected}


def _default_store() -> MarketSessionStore | None:
    if not bool(getattr(cfg, "MARKET_SESSION_MEMORY_ENABLE", True)): return None
    if str(os.getenv("MARKET_SESSION_MEMORY_DISABLE", "")).strip().lower() in {"1", "true", "yes"}: return None
    return MarketSessionStore()


market_session_store = _default_store()
