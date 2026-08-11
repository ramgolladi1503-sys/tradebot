"""Read-only prospective market evidence sidecar.

This module may observe completed OHLC bars and write research evidence. It has
no broker, order, strategy, ranking, risk, approval, or execution authority.
Failures are intentionally contained by ``safe_finalize_live_session``.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
REQUIRED = ("NIFTY", "BANKNIFTY", "SENSEX")
SCHEMA = "tradebot-prospective-market-evidence-v1"


def _canonical(obj: Mapping[str, Any]) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dt(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("BAR_TIMESTAMP_INVALID")
    if value.tzinfo is None:
        raise ValueError("BAR_TIMESTAMP_NAIVE")
    return value.astimezone(IST)


def _live_provenance(bar: Mapping[str, Any]) -> Mapping[str, Any]:
    p = dict(bar.get("bar_provenance") or {})
    if p.get("historical_seed") or p.get("replay_fixture") or p.get("non_live_fallback") or p.get("recovered_synthetic"):
        raise ValueError("NON_LIVE_PROVENANCE")
    if p.get("source_type") != "live_websocket" or not p.get("live_feed_session_id"):
        raise ValueError("LIVE_PROVENANCE_INCOMPLETE")
    return p


def finalize_session(*, session_date: date, bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]], output_root: Path, expected_minutes: int = 375) -> dict[str, Any]:
    """Validate and immutably seal one completed live Indian-index session."""
    if expected_minutes <= 0:
        raise ValueError("EXPECTED_MINUTES_INVALID")
    rows: dict[str, Any] = {}
    session_ids: set[str] = set()
    for symbol in REQUIRED:
        raw = list(bars_by_symbol.get(symbol) or [])
        bars = [b for b in raw if _dt(b.get("ts")).date() == session_date]
        if len(bars) != expected_minutes:
            raise ValueError(f"SESSION_INCOMPLETE:{symbol}:{len(bars)}:{expected_minutes}")
        times = [_dt(b.get("ts")) for b in bars]
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError(f"TIMESTAMP_ORDER_INVALID:{symbol}")
        if times[0].time() != time(9, 15) or times[-1].time() != time(15, 29):
            raise ValueError(f"SESSION_BOUNDARY_INVALID:{symbol}:{times[0].time()}:{times[-1].time()}")
        expected = [times[0].replace(hour=9, minute=15, second=0, microsecond=0)]
        for _ in range(1, expected_minutes):
            expected.append(expected[-1].replace(timestamp=0) if False else expected[-1])
        # Strict one-minute continuity without importing market-calendar behavior.
        for prev, cur in zip(times, times[1:]):
            if (cur - prev).total_seconds() != 60:
                raise ValueError(f"SESSION_GAP:{symbol}:{prev.isoformat()}:{cur.isoformat()}")
        prov = [_live_provenance(b) for b in bars]
        ids = {str(p.get("live_feed_session_id")) for p in prov}
        if len(ids) != 1:
            raise ValueError(f"SESSION_ID_CONFLICT:{symbol}")
        session_ids |= ids
        vals = []
        for b in bars:
            o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
            if min(o, h, l, c) <= 0 or h < max(o, l, c) or l > min(o, h, c):
                raise ValueError(f"OHLC_INVALID:{symbol}:{_dt(b['ts']).isoformat()}")
            vals.append((o, h, l, c))
        rows[symbol] = {
            "open": vals[0][0], "high": max(v[1] for v in vals),
            "low": min(v[2] for v in vals), "close": vals[-1][3],
            "minute_bars": len(vals), "volume": None,
            "volume_status": "MISSING_NOT_ZERO",
            "source_type": "live_websocket", "live_feed_session_id": next(iter(ids)),
        }
    if len(session_ids) != 1:
        raise ValueError("CROSS_SYMBOL_SESSION_ID_CONFLICT")
    payload = {
        "schema": SCHEMA, "session_date": session_date.isoformat(),
        "created_at_ist": datetime.now(IST).isoformat(timespec="seconds"),
        "claim": "READ_ONLY_LIVE_MARKET_EVIDENCE_NO_EDGE_CLAIM",
        "research_only": True, "broker_write_authority": False,
        "order_authority": False, "paper_authorized": False, "live_authorized": False,
        "source": "existing_tradebot_completed_live_ohlc",
        "live_feed_session_id": next(iter(session_ids)), "indices": rows,
    }
    semantic = dict(payload); semantic.pop("created_at_ist")
    payload["semantic_sha256"] = _sha(_canonical(semantic))
    root = Path(output_root); root.mkdir(parents=True, exist_ok=True)
    path = root / f"{session_date.isoformat()}.json"
    data = _canonical(payload)
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("semantic_sha256") == payload["semantic_sha256"]:
            return {"status": "IDEMPOTENT", "path": str(path), "sha256": _sha(path.read_bytes())}
        raise FileExistsError(f"IMMUTABLE_EVIDENCE_CONFLICT:{path}")
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(data); os.replace(tmp, path)
    return {"status": "SEALED", "path": str(path), "sha256": _sha(data), "semantic_sha256": payload["semantic_sha256"]}


def safe_finalize_live_session(*, session_date: date | None = None, output_root: Path | None = None) -> dict[str, Any]:
    """Best-effort runtime hook. Never raises into the trading runtime."""
    try:
        from core.ohlc_buffer import ohlc_buffer
        d = session_date or datetime.now(IST).date()
        root = output_root or Path(os.getenv("TRADEBOT_PROSPECTIVE_EVIDENCE_DIR", ".runtime/research/prospective_market_evidence_v1"))
        bars = {s: ohlc_buffer.get_bars(s) for s in REQUIRED}
        return finalize_session(session_date=d, bars_by_symbol=bars, output_root=root)
    except Exception as exc:
        return {"status": "NOT_SEALED", "reason": f"{type(exc).__name__}:{exc}"}
