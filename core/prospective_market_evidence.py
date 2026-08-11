"""Read-only prospective market evidence sidecar.

This module observes completed OHLC bars and writes research evidence only. It
has no broker, order, strategy, ranking, risk, approval, or execution authority.
Failures are intentionally contained by ``safe_finalize_live_session`` so this
sidecar cannot block or degrade the trading runtime.
"""
from __future__ import annotations

import hashlib
import hmac
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
ATTESTATION_SCHEMA = "tradebot-live-session-attestation-v1"
ATTESTATION_SOURCE = "tradebot_live_runtime_bridge"
SESSION_OPEN = time(9, 15)
SESSION_LAST_BAR = time(15, 29)
SESSION_MINUTES = 375
_REQUIRED_PROVENANCE_FIELDS = (
    "source_type",
    "live_feed_session_id",
    "provider",
    "token_domain",
    "symbol",
    "instrument_token",
)


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


def _attestation_unsigned(attestation: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(attestation)
    payload.pop("attestation_hmac_sha256", None)
    return payload


def sign_live_session_attestation(
    attestation: Mapping[str, Any], *, attestation_key: str
) -> dict[str, Any]:
    """Sign a separately-produced live-session attestation.

    The signing key is runtime-secret material and must not be persisted in the
    evidence artifact. This helper is deterministic so independent tooling can
    reproduce the signature contract without granting any trading authority.
    """
    key = str(attestation_key or "").encode("utf-8")
    if len(key) < 32:
        raise ValueError("LIVE_ATTESTATION_KEY_INVALID")
    unsigned = _attestation_unsigned(attestation)
    signed = dict(unsigned)
    signed["attestation_hmac_sha256"] = hmac.new(
        key, _canonical(unsigned), hashlib.sha256
    ).hexdigest()
    return signed


def _verify_live_attestation(
    *,
    live_attestation: Mapping[str, Any] | None,
    attestation_key: str | None,
    session_date: date,
    code_sha: str,
) -> dict[str, Any]:
    if not isinstance(live_attestation, Mapping):
        raise ValueError("LIVE_ATTESTATION_REQUIRED")
    key = str(attestation_key or "").encode("utf-8")
    if len(key) < 32:
        raise ValueError("LIVE_ATTESTATION_KEY_REQUIRED")

    att = dict(live_attestation)
    claimed = str(att.get("attestation_hmac_sha256") or "")
    expected = hmac.new(
        key, _canonical(_attestation_unsigned(att)), hashlib.sha256
    ).hexdigest()
    if not claimed or not hmac.compare_digest(claimed, expected):
        raise ValueError("LIVE_ATTESTATION_SIGNATURE_INVALID")

    if att.get("schema") != ATTESTATION_SCHEMA:
        raise ValueError("LIVE_ATTESTATION_SCHEMA_INVALID")
    if att.get("source") != ATTESTATION_SOURCE:
        raise ValueError("LIVE_ATTESTATION_SOURCE_INVALID")
    if att.get("status") != "VERIFIED_LIVE_SESSION":
        raise ValueError("LIVE_ATTESTATION_STATUS_INVALID")
    if str(att.get("session_date") or "") != session_date.isoformat():
        raise ValueError("LIVE_ATTESTATION_SESSION_MISMATCH")
    if str(att.get("code_sha") or "") != code_sha:
        raise ValueError("LIVE_ATTESTATION_CODE_SHA_MISMATCH")
    if str(att.get("provider") or "").lower() != "kite":
        raise ValueError("LIVE_ATTESTATION_PROVIDER_INVALID")
    if str(att.get("token_domain") or "") != "kite_instrument_token":
        raise ValueError("LIVE_ATTESTATION_TOKEN_DOMAIN_INVALID")
    if not str(att.get("live_feed_session_id") or "").strip():
        raise ValueError("LIVE_ATTESTATION_SESSION_ID_MISSING")

    try:
        attested_at = datetime.fromisoformat(str(att.get("attested_at_ist") or ""))
    except Exception as exc:
        raise ValueError("LIVE_ATTESTATION_TIMESTAMP_INVALID") from exc
    if attested_at.tzinfo is None:
        raise ValueError("LIVE_ATTESTATION_TIMESTAMP_INVALID")
    attested_at = attested_at.astimezone(IST)
    if attested_at.date() < session_date or attested_at.time() < time(15, 30):
        raise ValueError("LIVE_ATTESTATION_TIMESTAMP_INVALID")

    indices = att.get("indices")
    if not isinstance(indices, Mapping) or set(indices) != set(REQUIRED):
        raise ValueError("LIVE_ATTESTATION_INDEX_SET_INVALID")
    normalized_indices: dict[str, dict[str, Any]] = {}
    for symbol in REQUIRED:
        row = indices.get(symbol)
        if not isinstance(row, Mapping):
            raise ValueError(f"LIVE_ATTESTATION_INDEX_IDENTITY_INVALID:{symbol}")
        declared_symbol = str(row.get("symbol") or "").upper().strip()
        try:
            instrument_token = int(row.get("instrument_token"))
        except Exception as exc:
            raise ValueError(
                f"LIVE_ATTESTATION_INDEX_IDENTITY_INVALID:{symbol}"
            ) from exc
        if declared_symbol != symbol or instrument_token <= 0:
            raise ValueError(f"LIVE_ATTESTATION_INDEX_IDENTITY_INVALID:{symbol}")
        normalized_indices[symbol] = {
            "symbol": symbol,
            "instrument_token": instrument_token,
        }

    att["attested_at_ist"] = attested_at.isoformat(timespec="seconds")
    att["indices"] = normalized_indices
    return att


def _live_provenance(
    bar: Mapping[str, Any], *, symbol: str, attestation: Mapping[str, Any]
) -> Mapping[str, Any]:
    p = dict(bar.get("bar_provenance") or {})
    if (
        p.get("historical_seed")
        or p.get("replay_fixture")
        or p.get("non_live_fallback")
        or p.get("recovered_synthetic")
    ):
        raise ValueError(f"NON_LIVE_PROVENANCE:{symbol}")
    missing = [
        field
        for field in _REQUIRED_PROVENANCE_FIELDS
        if p.get(field) is None or str(p.get(field)).strip() == ""
    ]
    if missing:
        raise ValueError(f"LIVE_PROVENANCE_INCOMPLETE:{symbol}:{','.join(missing)}")
    if p.get("source_type") != "live_websocket":
        raise ValueError(f"LIVE_PROVENANCE_INCOMPLETE:{symbol}")

    expected = attestation["indices"][symbol]
    checks = {
        "live_feed_session_id": str(attestation["live_feed_session_id"]),
        "provider": str(attestation["provider"]),
        "token_domain": str(attestation["token_domain"]),
        "symbol": symbol,
        "instrument_token": str(expected["instrument_token"]),
    }
    actual = {
        "live_feed_session_id": str(p.get("live_feed_session_id")),
        "provider": str(p.get("provider")),
        "token_domain": str(p.get("token_domain")),
        "symbol": str(p.get("symbol")).upper().strip(),
        "instrument_token": str(p.get("instrument_token")),
    }
    for field, expected_value in checks.items():
        if actual[field] != expected_value:
            raise ValueError(f"SOURCE_IDENTITY_MISMATCH:{symbol}:{field}")
    return p


def _semantic_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    semantic = dict(payload)
    semantic.pop("semantic_sha256", None)
    return semantic


def _validate_existing_artifact(
    path: Path, expected_semantic: Mapping[str, Any]
) -> dict[str, Any]:
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
    live_attestation: Mapping[str, Any] | None = None,
    attestation_key: str | None = None,
) -> dict[str, Any]:
    """Validate and immutably seal one completed live Indian-index session."""
    if not isinstance(session_date, date):
        raise ValueError("SESSION_DATE_INVALID")
    if not isinstance(bars_by_symbol, Mapping):
        raise ValueError("BARS_BY_SYMBOL_INVALID")

    code_sha_value = str(code_sha or os.getenv("TRADEBOT_CODE_SHA") or "").strip()
    if not code_sha_value or code_sha_value.upper() == "UNKNOWN":
        raise ValueError("CODE_SHA_REQUIRED")

    now = datetime.now(IST)
    if session_date > now.date():
        raise ValueError("FUTURE_SESSION_DATE")
    if session_date == now.date() and now.time() < time(15, 30):
        raise ValueError("SESSION_NOT_COMPLETE_YET")

    attestation = _verify_live_attestation(
        live_attestation=live_attestation,
        attestation_key=attestation_key,
        session_date=session_date,
        code_sha=code_sha_value,
    )

    rows: dict[str, Any] = {}
    session_ids: set[str] = set()
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

        provenance = [
            _live_provenance(bar, symbol=symbol, attestation=attestation)
            for bar, _ in converted
        ]
        ids = {str(p.get("live_feed_session_id")) for p in provenance}
        if len(ids) != 1:
            raise ValueError(f"SESSION_ID_CONFLICT:{symbol}")
        session_ids |= ids

        stable_identity = {
            "provider": str(attestation["provider"]),
            "token_domain": str(attestation["token_domain"]),
            "instrument_token": int(attestation["indices"][symbol]["instrument_token"]),
            "symbol": symbol,
        }

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

    if len(session_ids) != 1 or next(iter(session_ids)) != str(
        attestation["live_feed_session_id"]
    ):
        raise ValueError("CROSS_SYMBOL_SESSION_ID_CONFLICT")

    payload = {
        "schema": SCHEMA,
        "session_date": session_date.isoformat(),
        "created_at_ist": attestation["attested_at_ist"],
        "claim": "READ_ONLY_LIVE_MARKET_EVIDENCE_NO_EDGE_CLAIM",
        "research_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "source": "existing_tradebot_completed_live_ohlc",
        "live_feed_session_id": str(attestation["live_feed_session_id"]),
        "provider": str(attestation["provider"]),
        "code_sha": code_sha_value,
        "live_attestation_sha256": _sha(_canonical(_attestation_unsigned(attestation))),
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


def _load_runtime_attestation(path_text: str) -> Mapping[str, Any]:
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        raise ValueError("LIVE_ATTESTATION_PATH_INVALID")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("LIVE_ATTESTATION_PATH_INVALID") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("LIVE_ATTESTATION_PATH_INVALID")
    return payload


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
        attestation_path = str(
            os.getenv("TRADEBOT_LIVE_SESSION_ATTESTATION_PATH") or ""
        ).strip()
        attestation_key = str(os.getenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY") or "")
        if not attestation_path:
            raise ValueError("LIVE_ATTESTATION_PATH_REQUIRED")
        live_attestation = _load_runtime_attestation(attestation_path)
        bars = {symbol: ohlc_buffer.get_bars(symbol) for symbol in REQUIRED}
        return finalize_session(
            session_date=d,
            bars_by_symbol=bars,
            output_root=root,
            code_sha=os.getenv("TRADEBOT_CODE_SHA"),
            live_attestation=live_attestation,
            attestation_key=attestation_key,
        )
    except Exception as exc:
        return {
            "status": "NOT_SEALED",
            "reason": f"{type(exc).__name__}:{exc}",
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }
