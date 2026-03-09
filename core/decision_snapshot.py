"""Atomic snapshot contract for decision-time pricing context.

Feature-gated via cfg.USE_DECISION_SNAPSHOT.
This module is side-effect free and deterministic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _to_int_ms(value: Any) -> int | None:
    try:
        if value is None:
            return None
        out = int(float(value))
        return out
    except Exception:
        return None


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload or {}), sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    # Keep only canonical snapshot fields in digest source.
    out: dict[str, Any] = {
        "ts_ms": _to_int_ms(data.get("ts_ms")),
        "spread": _to_float(data.get("spread")),
        "depth": dict(data.get("depth") or {}) if isinstance(data.get("depth"), Mapping) else None,
        "meta": dict(data.get("meta") or {}) if isinstance(data.get("meta"), Mapping) else {},
    }
    index_quote = data.get("index_quote")
    option_quote = data.get("option_quote")
    if not isinstance(index_quote, Mapping):
        # Legacy shape fallback.
        ts_ms = _to_int_ms(data.get("ts_ms"))
        if ts_ms is None:
            legacy_ts = _to_float(data.get("timestamp"))
            if legacy_ts is not None:
                ts_ms = int(round(legacy_ts * 1000.0))
        index_quote = {
            "ltp": _to_float(data.get("index_price")),
            "bid": None,
            "ask": None,
            "ts_ms": ts_ms,
            "age_ms": _to_float(data.get("index_quote_age_ms")),
        }
    if not isinstance(option_quote, Mapping):
        ts_ms = _to_int_ms(data.get("ts_ms"))
        if ts_ms is None:
            legacy_ts = _to_float(data.get("timestamp"))
            if legacy_ts is not None:
                ts_ms = int(round(legacy_ts * 1000.0))
        option_quote = {
            "ltp": _to_float(data.get("option_ltp")),
            "bid": _to_float(data.get("option_bid")),
            "ask": _to_float(data.get("option_ask")),
            "ts_ms": ts_ms,
            "age_ms": _to_float(data.get("option_quote_age_ms")),
        }
    out["index_quote"] = {
        "ltp": _to_float(index_quote.get("ltp") if isinstance(index_quote, Mapping) else None),
        "bid": _to_float(index_quote.get("bid") if isinstance(index_quote, Mapping) else None),
        "ask": _to_float(index_quote.get("ask") if isinstance(index_quote, Mapping) else None),
        "ts_ms": _to_int_ms(index_quote.get("ts_ms") if isinstance(index_quote, Mapping) else None),
        "age_ms": _to_float(index_quote.get("age_ms") if isinstance(index_quote, Mapping) else None),
    }
    out["option_quote"] = {
        "ltp": _to_float(option_quote.get("ltp") if isinstance(option_quote, Mapping) else None),
        "bid": _to_float(option_quote.get("bid") if isinstance(option_quote, Mapping) else None),
        "ask": _to_float(option_quote.get("ask") if isinstance(option_quote, Mapping) else None),
        "ts_ms": _to_int_ms(option_quote.get("ts_ms") if isinstance(option_quote, Mapping) else None),
        "age_ms": _to_float(option_quote.get("age_ms") if isinstance(option_quote, Mapping) else None),
    }
    source = data.get("source")
    if source is None and isinstance(out["meta"], Mapping):
        source = out["meta"].get("source")
    if source is not None:
        meta = dict(out.get("meta") or {})
        meta["source"] = str(source).strip()
        out["meta"] = meta
    return out


def compute_snapshot_id(payload: Mapping[str, Any]) -> str:
    raw = _canonical_json(_hash_payload(payload))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Quote:
    ltp: float | None
    bid: float | None
    ask: float | None
    ts_ms: int | None
    age_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "Quote":
        data = dict(payload or {})
        return cls(
            ltp=_to_float(data.get("ltp")),
            bid=_to_float(data.get("bid")),
            ask=_to_float(data.get("ask")),
            ts_ms=_to_int_ms(data.get("ts_ms")),
            age_ms=_to_float(data.get("age_ms")),
        )


@dataclass(frozen=True)
class DecisionSnapshot:
    snapshot_id: str
    ts_ms: int
    index_quote: Quote
    option_quote: Quote
    spread: float | None
    depth: dict[str, Any] | None
    meta: dict[str, Any]

    # Compatibility aliases for existing call sites.
    @property
    def timestamp(self) -> float:
        return float(self.ts_ms) / 1000.0

    @property
    def index_price(self) -> float | None:
        return self.index_quote.ltp

    @property
    def option_bid(self) -> float | None:
        return self.option_quote.bid

    @property
    def option_ask(self) -> float | None:
        return self.option_quote.ask

    @property
    def option_ltp(self) -> float | None:
        return self.option_quote.ltp

    @property
    def index_quote_age_ms(self) -> float | None:
        return self.index_quote.age_ms

    @property
    def option_quote_age_ms(self) -> float | None:
        return self.option_quote.age_ms

    @property
    def source(self) -> str | None:
        value = self.meta.get("source") if isinstance(self.meta, Mapping) else None
        if value is None:
            return None
        return str(value).strip() or None

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "ts_ms": int(self.ts_ms),
            "index_quote": self.index_quote.to_dict(),
            "option_quote": self.option_quote.to_dict(),
            "spread": _to_float(self.spread),
            "depth": dict(self.depth or {}) if isinstance(self.depth, Mapping) else None,
            "meta": dict(self.meta or {}),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "snapshot_id": self.snapshot_id,
            **self._canonical_payload(),
        }
        # Backward-compatible keys (do not remove until downstream migration completes).
        payload.update(
            {
                "timestamp": self.timestamp,
                "index_price": self.index_price,
                "option_bid": self.option_bid,
                "option_ask": self.option_ask,
                "option_ltp": self.option_ltp,
                "index_quote_age_ms": self.index_quote_age_ms,
                "option_quote_age_ms": self.option_quote_age_ms,
                "source": self.source,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionSnapshot":
        data = dict(payload or {})
        canonical = _hash_payload(data)

        raw_ts_ms = _to_int_ms(data.get("ts_ms"))
        if raw_ts_ms is None:
            legacy_timestamp = _to_float(data.get("timestamp"))
            raw_ts_ms = int(round((legacy_timestamp or 0.0) * 1000.0))
        index_quote = Quote.from_dict(canonical.get("index_quote"))
        option_quote = Quote.from_dict(canonical.get("option_quote"))
        meta = dict(canonical.get("meta") or {})
        sid = str(data.get("snapshot_id") or "").strip()
        if not sid:
            sid = compute_snapshot_id(
                {
                    "ts_ms": raw_ts_ms,
                    "index_quote": index_quote.to_dict(),
                    "option_quote": option_quote.to_dict(),
                    "spread": canonical.get("spread"),
                    "depth": canonical.get("depth"),
                    "meta": meta,
                }
            )
        return cls(
            snapshot_id=sid,
            ts_ms=int(raw_ts_ms),
            index_quote=index_quote,
            option_quote=option_quote,
            spread=_to_float(canonical.get("spread")),
            depth=dict(canonical.get("depth") or {}) if isinstance(canonical.get("depth"), Mapping) else None,
            meta=meta,
        )

    @classmethod
    def build(
        cls,
        *,
        ts_ms: int | None = None,
        timestamp: float | None = None,
        index_quote: Quote | Mapping[str, Any] | None = None,
        option_quote: Quote | Mapping[str, Any] | None = None,
        index_price: float | None = None,
        option_bid: float | None = None,
        option_ask: float | None = None,
        option_ltp: float | None = None,
        spread: float | None = None,
        depth: Mapping[str, Any] | None = None,
        index_quote_age_ms: float | None = None,
        option_quote_age_ms: float | None = None,
        source: str | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> "DecisionSnapshot":
        out_ts_ms = _to_int_ms(ts_ms)
        if out_ts_ms is None:
            out_ts_ms = int(round((_to_float(timestamp) or 0.0) * 1000.0))
        if isinstance(index_quote, Quote):
            idx_quote = index_quote
        elif isinstance(index_quote, Mapping):
            idx_quote = Quote.from_dict(index_quote)
        else:
            idx_quote = Quote(
                ltp=_to_float(index_price),
                bid=None,
                ask=None,
                ts_ms=out_ts_ms,
                age_ms=_to_float(index_quote_age_ms),
            )

        if isinstance(option_quote, Quote):
            opt_quote = option_quote
        elif isinstance(option_quote, Mapping):
            opt_quote = Quote.from_dict(option_quote)
        else:
            opt_quote = Quote(
                ltp=_to_float(option_ltp),
                bid=_to_float(option_bid),
                ask=_to_float(option_ask),
                ts_ms=out_ts_ms,
                age_ms=_to_float(option_quote_age_ms),
            )

        meta_payload = dict(meta or {})
        if source is not None and str(source).strip():
            meta_payload.setdefault("source", str(source).strip())

        payload = {
            "ts_ms": out_ts_ms,
            "index_quote": idx_quote.to_dict(),
            "option_quote": opt_quote.to_dict(),
            "spread": _to_float(spread),
            "depth": dict(depth or {}) if isinstance(depth, Mapping) else None,
            "meta": meta_payload,
        }
        sid = compute_snapshot_id(payload)
        return cls(
            snapshot_id=sid,
            ts_ms=out_ts_ms,
            index_quote=idx_quote,
            option_quote=opt_quote,
            spread=_to_float(spread),
            depth=dict(depth or {}) if isinstance(depth, Mapping) else None,
            meta=meta_payload,
        )
