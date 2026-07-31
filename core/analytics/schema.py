from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence, TypedDict

from core.trade_identity import compute_trade_key


IntentType = Literal["accepted", "rejected", "advisory"]
OutcomeType = Literal["hit_target", "hit_sl", "no_hit"]


class GateDecisionTD(TypedDict, total=False):
    gate_name: str
    passed: bool
    reason: str | None
    metrics_snapshot: dict[str, Any]


class TradeIntentEventTD(TypedDict, total=False):
    trade_key: str
    event_id: str
    intent: IntentType
    ts_epoch_ms: int
    symbol: str
    expiry: str | None
    strike: float | None
    option_type: str | None
    side: str | None
    source: str
    reject_reason: str | None
    gate_decisions: list[GateDecisionTD]
    metrics_snapshot: dict[str, Any]
    feed_group: str | None
    feed_state: str | None
    feed_metrics: dict[str, Any] | None


class TradeOutcomeTD(TypedDict, total=False):
    trade_key: str
    event_id: str
    outcome: OutcomeType
    ts_epoch_ms: int
    symbol: str
    mfe_points: float | None
    mae_points: float | None
    exec_feasible: bool
    exec_feasible_flags: dict[str, Any]
    source: str
    reject_reason: str | None
    reject_reasons: list[str]
    primary_reject_reason: str | None


GATE_DECISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["gate_name", "passed"],
    "properties": {
        "gate_name": {"type": "string"},
        "passed": {"type": "boolean"},
        "reason": {"type": ["string", "null"]},
        "metrics_snapshot": {"type": "object"},
    },
}

TRADE_INTENT_EVENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["trade_key", "event_id", "intent", "ts_epoch_ms", "symbol", "source"],
    "properties": {
        "trade_key": {"type": "string"},
        "event_id": {"type": "string"},
        "intent": {"type": "string", "enum": ["accepted", "rejected", "advisory"]},
        "ts_epoch_ms": {"type": "integer"},
        "symbol": {"type": "string"},
        "expiry": {"type": ["string", "null"]},
        "strike": {"type": ["number", "null"]},
        "option_type": {"type": ["string", "null"]},
        "side": {"type": ["string", "null"]},
        "source": {"type": "string"},
        "reject_reason": {"type": ["string", "null"]},
        "gate_decisions": {"type": "array", "items": GATE_DECISION_JSON_SCHEMA},
        "metrics_snapshot": {"type": "object"},
        "feed_group": {"type": ["string", "null"]},
        "feed_state": {"type": ["string", "null"]},
        "feed_metrics": {"type": ["object", "null"]},
    },
}

TRADE_OUTCOME_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "trade_key",
        "event_id",
        "outcome",
        "ts_epoch_ms",
        "symbol",
        "exec_feasible",
        "source",
    ],
    "properties": {
        "trade_key": {"type": "string"},
        "event_id": {"type": "string"},
        "outcome": {"type": "string", "enum": ["hit_target", "hit_sl", "no_hit"]},
        "ts_epoch_ms": {"type": "integer"},
        "symbol": {"type": "string"},
        "mfe_points": {"type": ["number", "null"]},
        "mae_points": {"type": ["number", "null"]},
        "exec_feasible": {"type": "boolean"},
        "exec_feasible_flags": {"type": "object"},
        "source": {"type": "string"},
        "reject_reason": {"type": ["string", "null"]},
        "reject_reasons": {"type": "array", "items": {"type": "string"}},
        "primary_reject_reason": {"type": ["string", "null"]},
    },
}


def build_trade_key(
    *,
    symbol: Any,
    expiry: Any = None,
    strike: Any = None,
    option_type: Any = None,
    side: Any = None,
    strategy_id: Any = None,
) -> str:
    return compute_trade_key(symbol, expiry, strike, option_type, side, strategy_id)


def build_event_id(
    *,
    trade_key: str,
    event_kind: str,
    ts_epoch_ms: int | float | str,
    source: str = "",
    discriminator: str = "",
) -> str:
    try:
        ts_int = int(float(ts_epoch_ms))
    except Exception:
        ts_int = 0
    payload = f"{trade_key}|{str(event_kind)}|{ts_int}|{str(source)}|{str(discriminator)}"
    return "evt_" + hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:24]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except Exception:
        return None


def _normalize_intent(value: Any) -> IntentType:
    text = str(value or "").strip().lower()
    if text in {"accepted", "rejected", "advisory"}:
        return text  # type: ignore[return-value]
    raise ValueError(f"invalid_intent:{value}")


def _normalize_outcome(value: Any) -> OutcomeType:
    text = str(value or "").strip().lower()
    mapping = {
        "hit_target": "hit_target",
        "target_hit": "hit_target",
        "hit_sl": "hit_sl",
        "stop_hit": "hit_sl",
        "sl_hit": "hit_sl",
        "no_hit": "no_hit",
        "timeout": "no_hit",
    }
    if text in mapping:
        return mapping[text]  # type: ignore[return-value]
    raise ValueError(f"invalid_outcome:{value}")


def _expected_type_names(spec: Any) -> tuple[str, ...]:
    if isinstance(spec, list):
        return tuple(str(item) for item in spec)
    return (str(spec),)


def _json_type_ok(value: Any, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "null":
        return value is None
    return True


def validate_json_schema(payload: Any, schema: Mapping[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    def _validate(value: Any, spec: Mapping[str, Any], path: str) -> None:
        expected = _expected_type_names(spec.get("type", "object"))
        if expected and not any(_json_type_ok(value, t) for t in expected):
            errors.append(f"{path}:expected_type={expected}:actual={type(value).__name__}")
            return
        enum_vals = spec.get("enum")
        if isinstance(enum_vals, list) and value is not None and value not in enum_vals:
            errors.append(f"{path}:not_in_enum={enum_vals}")
            return
        if isinstance(value, dict):
            required = spec.get("required", [])
            if isinstance(required, list):
                for key in required:
                    if key not in value:
                        errors.append(f"{path}:missing_required:{key}")
            props = spec.get("properties", {})
            if isinstance(props, dict):
                for key, key_spec in props.items():
                    if key not in value:
                        continue
                    if isinstance(key_spec, dict):
                        _validate(value.get(key), key_spec, f"{path}.{key}")
        elif isinstance(value, list):
            item_spec = spec.get("items")
            if isinstance(item_spec, dict):
                for idx, item in enumerate(value):
                    _validate(item, item_spec, f"{path}[{idx}]")

    _validate(payload, schema, "$")
    return len(errors) == 0, errors


def validate_gate_decision_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    return validate_json_schema(dict(payload or {}), GATE_DECISION_JSON_SCHEMA)


def validate_trade_intent_event_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    return validate_json_schema(dict(payload or {}), TRADE_INTENT_EVENT_JSON_SCHEMA)


def validate_trade_outcome_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    return validate_json_schema(dict(payload or {}), TRADE_OUTCOME_JSON_SCHEMA)


@dataclass(frozen=True)
class GateDecision:
    gate_name: str
    passed: bool
    reason: str | None = None
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> GateDecisionTD:
        return {
            "gate_name": str(self.gate_name),
            "passed": bool(self.passed),
            "reason": (str(self.reason) if self.reason is not None else None),
            "metrics_snapshot": dict(self.metrics_snapshot or {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GateDecision":
        data = dict(payload or {})
        ok, errors = validate_gate_decision_payload(data)
        if not ok:
            raise ValueError(f"invalid_gate_decision:{';'.join(errors)}")
        return cls(
            gate_name=str(data.get("gate_name") or "").strip(),
            passed=bool(data.get("passed")),
            reason=(str(data.get("reason")) if data.get("reason") is not None else None),
            metrics_snapshot=dict(data.get("metrics_snapshot") or {}),
        )


@dataclass(frozen=True)
class TradeIntentEvent:
    trade_key: str
    event_id: str
    intent: IntentType
    ts_epoch_ms: int
    symbol: str
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None
    side: str | None = None
    source: str = ""
    reject_reason: str | None = None
    gate_decisions: tuple[GateDecision, ...] = ()
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
    feed_group: str | None = None
    feed_state: str | None = None
    feed_metrics: dict[str, Any] | None = None

    def to_dict(self) -> TradeIntentEventTD:
        return {
            "trade_key": str(self.trade_key),
            "event_id": str(self.event_id),
            "intent": self.intent,
            "ts_epoch_ms": int(self.ts_epoch_ms),
            "symbol": str(self.symbol),
            "expiry": (str(self.expiry) if self.expiry is not None else None),
            "strike": _safe_float(self.strike),
            "option_type": (str(self.option_type) if self.option_type is not None else None),
            "side": (str(self.side) if self.side is not None else None),
            "source": str(self.source),
            "reject_reason": (str(self.reject_reason) if self.reject_reason is not None else None),
            "gate_decisions": [gd.to_dict() for gd in self.gate_decisions],
            "metrics_snapshot": dict(self.metrics_snapshot or {}),
            "feed_group": (str(self.feed_group) if self.feed_group is not None else None),
            "feed_state": (str(self.feed_state) if self.feed_state is not None else None),
            "feed_metrics": (dict(self.feed_metrics) if isinstance(self.feed_metrics, Mapping) else None),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TradeIntentEvent":
        data = dict(payload or {})
        trade_key = str(data.get("trade_key") or "").strip()
        if not trade_key:
            trade_key = build_trade_key(
                symbol=data.get("symbol"),
                expiry=data.get("expiry"),
                strike=data.get("strike"),
                option_type=data.get("option_type"),
                side=data.get("side"),
                strategy_id=data.get("strategy_id"),
            )
            data["trade_key"] = trade_key
        ts_epoch_ms = _safe_int(data.get("ts_epoch_ms"))
        if ts_epoch_ms is None:
            raise ValueError("invalid_trade_intent:missing_ts_epoch_ms")
        event_id = str(data.get("event_id") or "").strip()
        if not event_id:
            event_id = build_event_id(
                trade_key=trade_key,
                event_kind=str(data.get("intent") or "unknown"),
                ts_epoch_ms=ts_epoch_ms,
                source=str(data.get("source") or ""),
                discriminator=str(data.get("reject_reason") or ""),
            )
            data["event_id"] = event_id
        data["intent"] = _normalize_intent(data.get("intent"))
        gate_decisions_raw = data.get("gate_decisions") or []
        if not isinstance(gate_decisions_raw, list):
            gate_decisions_raw = []
        gate_decisions = tuple(
            GateDecision.from_dict(item)
            for item in gate_decisions_raw
            if isinstance(item, Mapping)
        )
        data["gate_decisions"] = [g.to_dict() for g in gate_decisions]
        ok, errors = validate_trade_intent_event_payload(data)
        if not ok:
            raise ValueError(f"invalid_trade_intent:{';'.join(errors)}")
        return cls(
            trade_key=trade_key,
            event_id=event_id,
            intent=data["intent"],
            ts_epoch_ms=ts_epoch_ms,
            symbol=str(data.get("symbol") or "").strip().upper(),
            expiry=(str(data.get("expiry")) if data.get("expiry") is not None else None),
            strike=_safe_float(data.get("strike")),
            option_type=(str(data.get("option_type")) if data.get("option_type") is not None else None),
            side=(str(data.get("side")) if data.get("side") is not None else None),
            source=str(data.get("source") or ""),
            reject_reason=(str(data.get("reject_reason")) if data.get("reject_reason") is not None else None),
            gate_decisions=gate_decisions,
            metrics_snapshot=dict(data.get("metrics_snapshot") or {}),
            feed_group=(str(data.get("feed_group")) if data.get("feed_group") is not None else None),
            feed_state=(str(data.get("feed_state")) if data.get("feed_state") is not None else None),
            feed_metrics=(dict(data.get("feed_metrics")) if isinstance(data.get("feed_metrics"), Mapping) else None),
        )


@dataclass(frozen=True)
class TradeOutcome:
    trade_key: str
    event_id: str
    outcome: OutcomeType
    ts_epoch_ms: int
    symbol: str
    mfe_points: float | None = None
    mae_points: float | None = None
    exec_feasible: bool = True
    exec_feasible_flags: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    reject_reason: str | None = None
    reject_reasons: tuple[str, ...] = field(default_factory=tuple)
    primary_reject_reason: str | None = None

    def to_dict(self) -> TradeOutcomeTD:
        normalized_reasons = [str(item).strip() for item in (self.reject_reasons or ()) if str(item).strip()]
        primary = str(self.primary_reject_reason).strip() if self.primary_reject_reason is not None else ""
        if not primary:
            primary = (str(self.reject_reason).strip() if self.reject_reason is not None else "") or (
                normalized_reasons[0] if normalized_reasons else ""
            )
        if primary and primary not in normalized_reasons:
            normalized_reasons = [primary] + normalized_reasons
        return {
            "trade_key": str(self.trade_key),
            "event_id": str(self.event_id),
            "outcome": self.outcome,
            "ts_epoch_ms": int(self.ts_epoch_ms),
            "symbol": str(self.symbol),
            "mfe_points": _safe_float(self.mfe_points),
            "mae_points": _safe_float(self.mae_points),
            "exec_feasible": bool(self.exec_feasible),
            "exec_feasible_flags": {str(k): v for k, v in (self.exec_feasible_flags or {}).items()},
            "source": str(self.source),
            "reject_reason": (primary or None),
            "reject_reasons": normalized_reasons,
            "primary_reject_reason": (primary or None),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TradeOutcome":
        data = dict(payload or {})
        trade_key = str(data.get("trade_key") or "").strip()
        if not trade_key:
            trade_key = build_trade_key(
                symbol=data.get("symbol"),
                expiry=data.get("expiry"),
                strike=data.get("strike"),
                option_type=data.get("option_type"),
                side=data.get("side"),
                strategy_id=data.get("strategy_id"),
            )
            data["trade_key"] = trade_key
        ts_epoch_ms = _safe_int(data.get("ts_epoch_ms"))
        if ts_epoch_ms is None:
            raise ValueError("invalid_trade_outcome:missing_ts_epoch_ms")
        outcome = _normalize_outcome(data.get("outcome"))
        data["outcome"] = outcome
        event_id = str(data.get("event_id") or "").strip()
        if not event_id:
            event_id = build_event_id(
                trade_key=trade_key,
                event_kind="outcome",
                ts_epoch_ms=ts_epoch_ms,
                source=str(data.get("source") or ""),
                discriminator=outcome,
            )
            data["event_id"] = event_id
        ok, errors = validate_trade_outcome_payload(data)
        if not ok:
            raise ValueError(f"invalid_trade_outcome:{';'.join(errors)}")
        flags = data.get("exec_feasible_flags")
        if not isinstance(flags, dict):
            flags = {}
        normalized_flags = {str(k): v for k, v in flags.items()}
        raw_reasons = data.get("reject_reasons")
        normalized_reasons: list[str] = []
        if isinstance(raw_reasons, (list, tuple)):
            for item in raw_reasons:
                text = str(item or "").strip()
                if text and text not in normalized_reasons:
                    normalized_reasons.append(text)
        fallback_reject_reason = str(data.get("reject_reason") or "").strip()
        primary_reject_reason = str(data.get("primary_reject_reason") or "").strip()
        if not primary_reject_reason and fallback_reject_reason:
            primary_reject_reason = fallback_reject_reason
        if primary_reject_reason and primary_reject_reason not in normalized_reasons:
            normalized_reasons = [primary_reject_reason] + normalized_reasons
        if not primary_reject_reason and normalized_reasons:
            primary_reject_reason = normalized_reasons[0]
        return cls(
            trade_key=trade_key,
            event_id=event_id,
            outcome=outcome,
            ts_epoch_ms=ts_epoch_ms,
            symbol=str(data.get("symbol") or "").strip().upper(),
            mfe_points=_safe_float(data.get("mfe_points")),
            mae_points=_safe_float(data.get("mae_points")),
            exec_feasible=bool(data.get("exec_feasible")),
            exec_feasible_flags=normalized_flags,
            source=str(data.get("source") or ""),
            reject_reason=(primary_reject_reason or None),
            reject_reasons=tuple(normalized_reasons),
            primary_reject_reason=(primary_reject_reason or None),
        )


def to_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload or {}), ensure_ascii=True, sort_keys=True)


def from_json(text: str) -> dict[str, Any]:
    decoded = json.loads(text)
    if not isinstance(decoded, dict):
        raise ValueError("json_payload_must_be_object")
    return decoded


def normalize_gate_decisions(raw: Sequence[Mapping[str, Any]] | None) -> tuple[GateDecision, ...]:
    out: list[GateDecision] = []
    for item in list(raw or []):
        try:
            out.append(GateDecision.from_dict(item))
        except Exception:
            continue
    return tuple(out)
