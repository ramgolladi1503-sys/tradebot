from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Mapping

SETUP_FINGERPRINT_SCHEMA_VERSION = 1
_UNKNOWN = "UNKNOWN"
_DEFAULT_SOURCE = "setup_fingerprint_contract"


@dataclass(frozen=True)
class SetupFingerprint:
    schema_version: int
    setup_id: str
    setup_family: str
    setup_variant: str
    strategy_family: str
    regime_bucket: str
    volatility_bucket: str
    volume_bucket: str
    spread_bucket: str
    time_of_day_bucket: str
    expiry_bucket: str
    direction_bucket: str
    index_bucket: str
    option_type_bucket: str
    source: str = _DEFAULT_SOURCE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any, *, default: str = _UNKNOWN) -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return text or default.lower()


def _bucket_text(value: Any, *, default: str = _UNKNOWN) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    return text or default


def _number(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    return number


def _coerce_epoch(value: Any) -> float | None:
    number = _number(value)
    if number is not None:
        return number
    text = _text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def _percentish_bucket(value: Any) -> str:
    number = _number(value)
    if number is None:
        return _UNKNOWN
    normalized = number / 100.0 if number > 1.0 and number <= 100.0 else number
    if normalized < 0.15:
        return "LOW"
    if normalized < 0.35:
        return "MEDIUM"
    if normalized < 0.7:
        return "HIGH"
    return "EXTREME"


def _volume_bucket(value: Any) -> str:
    number = _number(value)
    if number is None:
        return _UNKNOWN
    if number < 1000:
        return "LOW"
    if number < 10000:
        return "MEDIUM"
    if number < 100000:
        return "HIGH"
    return "EXTREME"


def _spread_bucket(row: Mapping[str, Any]) -> str:
    for key in ("spread_pct", "spread_percent", "spread_rate"):
        number = _number(row.get(key))
        if number is not None:
            normalized = number / 100.0 if number > 1.0 and number <= 100.0 else number
            if normalized < 0.001:
                return "TIGHT"
            if normalized < 0.0025:
                return "NORMAL"
            if normalized < 0.005:
                return "WIDE"
            return "VERY_WIDE"
    number = _number(row.get("spread"))
    if number is None:
        return _UNKNOWN
    if number < 0.5:
        return "TIGHT"
    if number < 1.0:
        return "NORMAL"
    if number < 2.0:
        return "WIDE"
    return "VERY_WIDE"


def _time_bucket(row: Mapping[str, Any]) -> str:
    epoch = None
    for key in ("signal_epoch", "signal_time_epoch", "entry_epoch", "created_at_epoch"):
        epoch = _coerce_epoch(row.get(key))
        if epoch is not None:
            break
    if epoch is None:
        return _UNKNOWN
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    hour_start = (dt.hour // 4) * 4
    hour_end = hour_start + 3
    return f"T{hour_start:02d}_{hour_end:02d}_UTC"


def _direction_bucket(row: Mapping[str, Any]) -> str:
    direction = _bucket_text(row.get("direction"))
    side = _bucket_text(row.get("side"))
    for candidate in (direction, side):
        if candidate in {"BUY", "LONG"}:
            return "BUY"
        if candidate in {"SELL", "SHORT"}:
            return "SELL"
    return _UNKNOWN


def build_setup_fingerprint(record: Any) -> SetupFingerprint:
    row = _mapping(record)
    strategy_family = _slug(row.get("strategy_family") or row.get("strategy"))
    regime_bucket = _bucket_text(row.get("regime") or row.get("regime_key"))
    volatility_bucket = _percentish_bucket(
        row.get("volatility")
        if row.get("volatility") is not None
        else row.get("realized_vol")
        if row.get("realized_vol") is not None
        else row.get("iv")
        if row.get("iv") is not None
        else row.get("ivp")
    )
    volume_bucket = _volume_bucket(
        row.get("volume")
        if row.get("volume") is not None
        else row.get("traded_volume")
        if row.get("traded_volume") is not None
        else row.get("avg_volume")
        if row.get("avg_volume") is not None
        else row.get("quantity")
    )
    spread_bucket = _spread_bucket(row)
    time_of_day_bucket = _time_bucket(row)
    expiry_bucket = _bucket_text(row.get("expiry_type") or row.get("expiry") or row.get("expiry_bucket"))
    direction_bucket = _direction_bucket(row)
    index_bucket = _bucket_text(row.get("index") or row.get("underlying_index") or row.get("symbol"))
    option_type_bucket = _bucket_text(row.get("option_type") or row.get("type"))
    setup_family = strategy_family
    setup_variant = "__".join(
        [
            regime_bucket,
            volatility_bucket,
            volume_bucket,
            spread_bucket,
            time_of_day_bucket,
            expiry_bucket,
            direction_bucket,
            index_bucket,
            option_type_bucket,
        ]
    )
    setup_id = "__".join([setup_family, setup_variant])
    if not setup_id.strip("_"):
        setup_id = sha1(
            repr(
                (
                    strategy_family,
                    regime_bucket,
                    volatility_bucket,
                    volume_bucket,
                    spread_bucket,
                    time_of_day_bucket,
                    expiry_bucket,
                    direction_bucket,
                    index_bucket,
                    option_type_bucket,
                )
            ).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:16]
    return SetupFingerprint(
        schema_version=SETUP_FINGERPRINT_SCHEMA_VERSION,
        setup_id=setup_id,
        setup_family=setup_family,
        setup_variant=setup_variant,
        strategy_family=strategy_family,
        regime_bucket=regime_bucket,
        volatility_bucket=volatility_bucket,
        volume_bucket=volume_bucket,
        spread_bucket=spread_bucket,
        time_of_day_bucket=time_of_day_bucket,
        expiry_bucket=expiry_bucket,
        direction_bucket=direction_bucket,
        index_bucket=index_bucket,
        option_type_bucket=option_type_bucket,
    )


def attach_setup_fingerprint(record: Any) -> dict[str, Any]:
    row = dict(_mapping(record))
    fingerprint = build_setup_fingerprint(row).to_dict()
    enriched = dict(row)
    for key, value in fingerprint.items():
        if key == "source":
            continue
        enriched[key] = value
    metadata = dict(enriched.get("metadata") or {})
    metadata["setup_fingerprint"] = fingerprint
    enriched["metadata"] = metadata
    return enriched


__all__ = [
    "SETUP_FINGERPRINT_SCHEMA_VERSION",
    "SetupFingerprint",
    "attach_setup_fingerprint",
    "build_setup_fingerprint",
]
