from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any, Mapping

ALLOWED_EVENT_TYPES = {
    "candidate_created",
    "gate_rejected",
    "trade_accepted",
    "trade_exited",
    "sla_violation",
    "disk_critical",
}

_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "api_key",
    "apikey",
    "password",
    "access_key",
    "account",
    "credential",
)


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    ts_utc: str
    desk: str
    mode: str
    symbols: list[str]
    event_type: str
    gate_name: str | None = None
    reason_code: str | None = None
    confidence: float | None = None
    config_version: str = ""
    features_summary: dict[str, Any] | None = None
    data_source: str = "derived"
    latency_ms: float | None = None
    missing_fields: list[str] = field(default_factory=list)
    instruments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ---- NEW: structured decision diagnostics (optional) ----
    decision_stage: str | None = None
    decision_explain: str | None = None
    decision_blockers: list[str] = field(default_factory=list)
    strategy_telemetry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    ts_utc: str
    instrument: dict[str, Any]
    ltp: float | None
    bid: float | None
    ask: float | None
    spread_pct: float | None
    depth_summary: dict[str, Any]
    oi: float | None
    volume: float | None
    iv: float | None
    capture_reason: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def config_version_hash(config: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(config), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def build_effective_config_dict(config_module: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    items = vars(config_module)
    for key, value in items.items():
        if not str(key).isupper():
            continue
        if _looks_sensitive_key(str(key)):
            continue
        if callable(value):
            continue
        out[str(key)] = _normalize_json_value(value)
    return out


def build_config_version(config_module: Any) -> str:
    return config_version_hash(build_effective_config_dict(config_module))


def build_event_record(
    payload: Mapping[str, Any],
    *,
    config_version: str,
    features_max_bytes: int = 2048,
    features_max_keys: int = 96,
) -> EventRecord:
    event_type = str(payload.get("event_type") or "").strip().lower()
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"invalid_event_type:{event_type}")

    symbols = _normalize_symbols(payload.get("symbols"))
    instruments = _normalize_instruments(payload.get("instruments"), symbols)
    ts_utc = _normalize_ts_utc(payload.get("ts_utc"))

    features_summary = _cap_features_summary(
        payload.get("features_summary"),
        max_bytes=max(256, int(features_max_bytes)),
        max_keys=max(8, int(features_max_keys)),
    )

    confidence = _coerce_float(payload.get("confidence"))
    latency_ms = _coerce_float(payload.get("latency_ms"))

    # ---- NEW: structured decision diagnostics ----
    decision_stage = _clean_nullable_text(payload.get("decision_stage"), max_len=120)
    decision_explain = _clean_nullable_text(payload.get("decision_explain"), max_len=500)
    decision_blockers = _normalize_text_list(payload.get("decision_blockers"), max_items=64, max_len=120)

    strategy_telemetry: dict[str, Any] = {}
    raw_telem = payload.get("strategy_telemetry")
    if isinstance(raw_telem, Mapping):
        # sanitize + bound (avoid huge payloads)
        strategy_telemetry = _sanitize_mapping(raw_telem)
        qfr = strategy_telemetry.get("qual_fail_reasons_raw")
        if isinstance(qfr, list):
            strategy_telemetry["qual_fail_reasons_raw"] = list(qfr)[:10]
        ac = strategy_telemetry.get("all_candidates")
        if isinstance(ac, list):
            strategy_telemetry["all_candidates"] = list(ac)[:10]

    record = EventRecord(
        event_id=_normalize_uuid(payload.get("event_id")),
        ts_utc=ts_utc,
        desk=str(payload.get("desk") or "DEFAULT")[:64],
        mode=str(payload.get("mode") or "PAPER").upper()[:16],
        symbols=symbols,
        event_type=event_type,
        gate_name=_clean_nullable_text(payload.get("gate_name"), max_len=96),
        reason_code=_clean_nullable_text(payload.get("reason_code"), max_len=160),
        confidence=confidence,
        config_version=str(config_version or "")[:32],
        features_summary=features_summary,
        data_source=str(payload.get("data_source") or "derived")[:64],
        latency_ms=latency_ms,
        missing_fields=_normalize_text_list(payload.get("missing_fields"), max_items=32, max_len=96),
        instruments=instruments,
        metadata=_sanitize_mapping(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}),
        # ---- NEW ----
        decision_stage=decision_stage,
        decision_explain=decision_explain,
        decision_blockers=decision_blockers,
        strategy_telemetry=strategy_telemetry,
    )
    return record


def build_snapshot_record(payload: Mapping[str, Any]) -> SnapshotRecord:
    ts_utc = _normalize_ts_utc(payload.get("ts_utc"))
    instrument = _normalize_instrument(payload.get("instrument"))

    bid = _coerce_float(payload.get("bid"))
    ask = _coerce_float(payload.get("ask"))
    ltp = _coerce_float(payload.get("ltp"))
    spread_pct = _coerce_float(payload.get("spread_pct"))
    if spread_pct is None and bid is not None and ask is not None and ask >= bid:
        base = ((bid + ask) / 2.0) if (bid and ask) else (ltp or 0.0)
        if base and base > 0:
            spread_pct = (ask - bid) / base

    capture_reason = payload.get("capture_reason")
    if not isinstance(capture_reason, Mapping):
        raise ValueError("invalid_capture_reason")
    around_event = capture_reason.get("around_event")
    periodic = capture_reason.get("periodic")
    if around_event is None and periodic is None:
        raise ValueError("capture_reason_missing")

    depth_summary = payload.get("depth_summary")
    if not isinstance(depth_summary, Mapping):
        depth_summary = {}

    return SnapshotRecord(
        snapshot_id=_normalize_uuid(payload.get("snapshot_id")),
        ts_utc=ts_utc,
        instrument=instrument,
        ltp=ltp,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        depth_summary=_sanitize_mapping(depth_summary),
        oi=_coerce_float(payload.get("oi")),
        volume=_coerce_float(payload.get("volume")),
        iv=_coerce_float(payload.get("iv")),
        capture_reason={
            "around_event": str(around_event) if around_event is not None else None,
            "periodic": periodic,
        },
    )


def _normalize_uuid(value: Any) -> str:
    if value:
        text = str(value).strip()
        try:
            return str(uuid.UUID(text))
        except Exception:
            pass
    return str(uuid.uuid4())


def _normalize_ts_utc(value: Any) -> str:
    if value is None:
        return now_iso_utc()
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    text = str(value).strip()
    if not text:
        return now_iso_utc()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return now_iso_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_symbols(raw: Any) -> list[str]:
    if raw is None:
        return []
    values: list[str] = []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = [str(v) for v in raw]
    else:
        values = [str(raw)]
    out: list[str] = []
    seen = set()
    for val in values:
        sym = str(val or "").strip().upper()
        if not sym:
            continue
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym[:64])
    return out


def _normalize_instruments(raw: Any, symbols: list[str]) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        out = []
        for item in raw:
            try:
                out.append(_normalize_instrument(item))
            except Exception:
                continue
        if out:
            return out
    if symbols:
        return [{"symbol": sym} for sym in symbols]
    return []


def _normalize_instrument(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("invalid_instrument")
    symbol = str(raw.get("symbol") or raw.get("name") or "").strip().upper()
    if not symbol:
        raise ValueError("instrument_symbol_missing")
    out: dict[str, Any] = {"symbol": symbol[:64]}
    instrument_id = raw.get("instrument_id")
    if instrument_id is not None:
        out["instrument_id"] = str(instrument_id)[:128]
    instrument_token = raw.get("instrument_token")
    if instrument_token is not None:
        try:
            out["instrument_token"] = int(instrument_token)
        except Exception:
            pass
    tradingsymbol = raw.get("tradingsymbol")
    if tradingsymbol is not None:
        out["tradingsymbol"] = str(tradingsymbol)[:128]
    return out


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _clean_nullable_text(value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _normalize_text_list(value: Any, *, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        out.append(text[:max_len])
        if len(out) >= max_items:
            break
    return out


def _cap_features_summary(value: Any, *, max_bytes: int, max_keys: int) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    flattened = _flatten_mapping(_sanitize_mapping(value))
    if not flattened:
        return None

    out: dict[str, Any] = {}
    truncated = False
    for key in sorted(flattened.keys()):
        if len(out) >= max_keys:
            truncated = True
            break
        candidate = dict(out)
        candidate[str(key)[:120]] = _normalize_scalar_value(flattened[key])
        encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) > max_bytes:
            truncated = True
            continue
        out = candidate
    if not out:
        return None
    if truncated:
        marker = dict(out)
        marker["__truncated__"] = True
        encoded = json.dumps(marker, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) <= max_bytes:
            out = marker
    return out


def _flatten_mapping(mapping: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        key_text = str(key)
        if not key_text:
            continue
        full_key = f"{prefix}.{key_text}" if prefix else key_text
        if isinstance(value, Mapping):
            out.update(_flatten_mapping(value, prefix=full_key))
        else:
            out[full_key] = value
    return out


def _sanitize_mapping(mapping: Mapping[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(mapping, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        key_text = str(key)
        if _looks_sensitive_key(key_text):
            continue
        if isinstance(value, Mapping):
            out[key_text] = _sanitize_mapping(value)
        elif isinstance(value, (list, tuple, set)):
            out[key_text] = [_normalize_scalar_value(item) for item in value]
        else:
            out[key_text] = _normalize_scalar_value(value)
    return out


def _looks_sensitive_key(key: str) -> bool:
    lowered = str(key or "").lower()
    if not lowered:
        return False
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalize_json_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(v) for v in value]
    if isinstance(value, set):
        return sorted(_normalize_json_value(v) for v in value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return _normalize_ts_utc(value)
    return _normalize_scalar_value(value)


def _normalize_scalar_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, datetime):
        return _normalize_ts_utc(value)
    if isinstance(value, Path):
        return str(value)
    try:
        parsed = float(value)
        if math.isnan(parsed) or math.isinf(parsed):
            return None
        return parsed
    except Exception:
        return str(value)
