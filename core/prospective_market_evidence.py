"""Read-only prospective market evidence sidecar.

This module observes completed OHLC bars and writes research evidence only. It
has no broker, order, strategy, ranking, risk, approval, or execution authority.
Failures are intentionally contained by ``safe_finalize_live_session`` so this
sidecar cannot block or degrade the trading runtime.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
REQUIRED = ("NIFTY", "BANKNIFTY", "SENSEX")
SCHEMA = "tradebot-prospective-market-evidence-v1"
SESSION_OPEN = time(9, 15)
SESSION_LAST_BAR = time(15, 29)
SESSION_MINUTES = 375


def _canonical(obj: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dt(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("BAR_TIMESTAMP_INVALID")
    if value.tzinfo is None:
        raise ValueError("BAR_TIMESTAMP_NAIVE")
    return value.astimezone(IST)


def _number(value: Any, *, field: str, symbol: str, ts: datetime) -> float:
    if isinstance(value, bool):
        raise ValueError(f"OHLC_INVALID:{symbol}:{field}:{ts.isoformat()}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"OHLC_INVALID:{symbol}:{field}:{ts.isoformat()}") from exc
    if not math.isfinite(result):
        raise ValueError(f"OHLC_INVALID:{symbol}:{field}:{ts.isoformat()}")
    return result


def _live_provenance(bar: Mapping[str, Any], *, symbol: str) -> Mapping[str, Any]:
    p = dict(bar.get("bar_provenance") or {})
    if (
        p.get("historical_seed")
        or p.get("replay_fixture")
        or p.get("non_live_fallback")
        or p.get("recovered_synthetic")
    ):
        raise ValueError(f"NON_LIVE_PROVENANCE:{symbol}")
    if p.get("source_type") != "live_websocket" or not p.get("live_feed_session_id"):
        raise ValueError(f"LIVE_PROVENANCE_INCOMPLETE:{symbol}")
    declared_symbol = str(p.get("symbol") or "").upper().strip()
    if declared_symbol and declared_symbol != symbol:
        raise ValueError(f"SOURCE_IDENTITY_MISMATCH:{symbol}:symbol:{declared_symbol}")
    return p


def _semantic_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    semantic = dict(payload)
    semantic.pop("created_at_ist", None)
    semantic.pop("semantic_sha256", None)
    return semantic


def _validate_existing_artifact(path: Path, expected_semantic: Mapping[str, Any]) -> dict[str, Any]:
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise FileExistsError(f"IMMUTABLE_EVIDENCE_CONFLICT:{path}") from exc
    if not isinstance(old, dict):
        raise FileExistsError(f"IMMUTABLE_EVIDENCE_CONFLICT:{path}")
    old_semantic = _semantic_payload(old)
    old_claimed_sha = old.get("semantic_sha256")
    old_recomputed_sha = _sha(_canonical(old_semantic))
    if old_claimed_sha != old_recomputed_sha:
        raise FileExistsError(f"IMMUTABLE_EVIDENCE_CONFLICT:{path}")
    if old_semantic != dict(expected_semantic):
        raise FileExistsError(f"IMMUTABLE_EVIDENCE_CONFLICT:{path}")
    return {
        "status": "IDEMPOTENT",
        "path": str(path),
        "sha256": _sha(path.read_bytes()),
        "semantic_sha256": old_recomputed_sha,
    }


def finalize_session(
    *,
    session_date: date,
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    output_root: Path,
    code_sha: str | None = None,
) -> dict[str, Any]:
    """Validate and immutably seal one completed live Indian-index session."""
    if not isinstance(session_date, date):
        raise ValueError("SESSION_DATE_INVALID")
    if not isinstance(bars_by_symbol, Mapping):
        raise ValueError("BARS_BY_SYMBOL_INVALID")

    now = datetime.now(IST)
    if session_date > now.date():
        raise ValueError("FUTURE_SESSION_DATE")
    if session_date == now.date() and now.time() < time(15, 30):
        raise ValueError("SESSION_NOT_COMPLETE_YET")

    rows: dict[str, Any] = {}
    session_ids: set[str] = set()
    cross_symbol_provider_ids: set[str] = set()

    session_start = datetime.combine(session_date, SESSION_OPEN, tzinfo=IST)
    session_end = datetime.combine(session_date, SESSION_LAST_BAR, tzinfo=IST)

    for symbol in REQUIRED:
        raw = list(bars_by_symbol.get(symbol) or [])
        converted: list[tuple[Mapping[str, Any], datetime]] = []
        for bar in raw:
            ts = _dt(bar.get("ts"))
            if ts.date() > session_date:
                raise ValueError(f"FUTURE_BAR_PRESENT:{symbol}:{ts.isoformat()}")
            if ts.date() == session_date:
                converted.append((bar, ts))

        if len(converted) != SESSION_MINUTES:
            raise ValueError(
                f"SESSION_INCOMPLETE:{symbol}:{len(converted)}:{SESSION_MINUTES}"
            )

        times = [ts for _, ts in converted]
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError(f"TIMESTAMP_ORDER_INVALID:{symbol}")
        if times[0] != session_start or times[-1] != session_end:
            raise ValueError(
                f"SESSION_BOUNDARY_INVALID:{symbol}:{times[0].isoformat()}:{times[-1].isoformat()}"
            )
        for expected_index, ts in enumerate(times):
            expected_ts = session_start + timedelta(minutes=expected_index)
            if ts != expected_ts:
                raise ValueError(
                    f"SESSION_GAP:{symbol}:{expected_ts.isoformat()}:{ts.isoformat()}"
                )

        provenance = [_live_provenance(bar, symbol=symbol) for bar, _ in converted]
        ids = {str(p.get("live_feed_session_id")) for p in provenance}
        if len(ids) != 1:
            raise ValueError(f"SESSION_ID_CONFLICT:{symbol}")
        session_ids |= ids

        # Preserve source identity without inventing fields the live feed does not provide.
        # Any identity field that is present must remain stable throughout the session.
        stable_identity: dict[str, Any] = {}
        for field in (
            "provider",
            "token_domain",
            "universe_hash",
            "instrument_token",
            "symbol",
        ):
            values = {
                str(p.get(field))
                for p in provenance
                if p.get(field) is not None and str(p.get(field)).strip() != ""
            }
            if len(values) > 1:
                raise ValueError(f"SOURCE_IDENTITY_MISMATCH:{symbol}:{field}")
            stable_identity[field] = next(iter(values)) if values else None
        provider_id = stable_identity.get("provider")
        if provider_id:
            cross_symbol_provider_ids.add(str(provider_id))

        vals: list[tuple[float, float, float, float]] = []
        for bar, ts in converted:
            o = _number(bar.get("open"), field="open", symbol=symbol, ts=ts)
            h = _number(bar.get("high"), field="high", symbol=symbol, ts=ts)
            l = _number(bar.get("low"), field="low", symbol=symbol, ts=ts)
            c = _number(bar.get("close"), field="close", symbol=symbol, ts=ts)
            if min(o, h, l, c) <= 0 or h < max(o, l, c) or l > min(o, h, c):
                raise ValueError(f"OHLC_INVALID:{symbol}:{ts.isoformat()}")
            vals.append((o, h, l, c))

        rows[symbol] = {
            "open": vals[0][0],
            "high": max(v[1] for v in vals),
            "low": min(v[2] for v in vals),
            "close": vals[-1][3],
            "minute_bars": len(vals),
            "volume": None,
            "volume_status": "MISSING_NOT_ZERO",
            "source_type": "live_websocket",
            "live_feed_session_id": next(iter(ids)),
            "source_identity": stable_identity,
        }

    if len(session_ids) != 1:
        raise ValueError("CROSS_SYMBOL_SESSION_ID_CONFLICT")
    if len(cross_symbol_provider_ids) > 1:
        raise ValueError("CROSS_SYMBOL_PROVIDER_CONFLICT")

    payload = {
        "schema": SCHEMA,
        "session_date": session_date.isoformat(),
        "created_at_ist": now.isoformat(timespec="seconds"),
        "claim": "READ_ONLY_LIVE_MARKET_EVIDENCE_NO_EDGE_CLAIM",
        "research_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "source": "existing_tradebot_completed_live_ohlc",
        "live_feed_session_id": next(iter(session_ids)),
        "provider": next(iter(cross_symbol_provider_ids)) if cross_symbol_provider_ids else None,
        "code_sha": str(code_sha or os.getenv("TRADEBOT_CODE_SHA") or "UNKNOWN"),
        "indices": rows,
    }
    semantic = _semantic_payload(payload)
    payload["semantic_sha256"] = _sha(_canonical(semantic))

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{session_date.isoformat()}.json"
    if path.exists():
        return _validate_existing_artifact(path, semantic)

    data = _canonical(payload)
    tmp = path.with_suffix(".json.tmp")
    if tmp.exists():
        tmp.unlink()
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {
        "status": "SEALED",
        "path": str(path),
        "sha256": _sha(data),
        "semantic_sha256": payload["semantic_sha256"],
    }


def safe_finalize_live_session(
    *, session_date: date | None = None, output_root: Path | None = None
) -> dict[str, Any]:
    """Best-effort runtime hook. Never raises into the trading runtime."""
    try:
        from core.ohlc_buffer import ohlc_buffer

        d = session_date or datetime.now(IST).date()
        root = output_root or Path(
            os.getenv(
                "TRADEBOT_PROSPECTIVE_EVIDENCE_DIR",
                ".runtime/research/prospective_market_evidence_v1",
            )
        )
        bars = {symbol: ohlc_buffer.get_bars(symbol) for symbol in REQUIRED}
        return finalize_session(session_date=d, bars_by_symbol=bars, output_root=root)
    except Exception as exc:
        return {
            "status": "NOT_SEALED",
            "reason": f"{type(exc).__name__}:{exc}",
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }
