from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

"""
Canonical blocker lifecycle ownership.

This module is the single owner of current-state blocker lifecycle for the
runtime paths that need blocker transitions instead of sticky string lists.

Lifecycle summary:

| Code                | Owner                         | Scope              | Kind      | Clear condition                                  | TTL  |
|---------------------|-------------------------------|--------------------|-----------|--------------------------------------------------|------|
| NO_LIVE_OPTION_FEED | feed_health_evaluator         | feed/advisory      | edge_ttl  | feed connected + recent tick + within SLA        | 15s  |
| STALE_OPTION_LTP    | quote_freshness_evaluator     | feed/advisory      | level     | quote/tick age back within threshold             | 2x   |
| NO_TOKEN            | instrument_resolution_eval... | advisory_contract  | edge_ttl  | token resolution succeeds for current owner key  | 30s  |
| PRICE_MISMATCH      | price_coherence_evaluator     | advisory_contract  | level     | prices reconcile or owner changes                | 15s  |

Rules:
- blockers are keyed by owner identity, not just blocker code
- recovered healthy state clears active blockers immediately
- expired or invalid-owner blockers are pruned and must not leak forward
"""

TARGET_BLOCKER_CODES = {
    "NO_LIVE_OPTION_FEED",
    "STALE_OPTION_LTP",
    "PRICE_MISMATCH",
    "NO_TOKEN",
}
_TARGET_BLOCKER_PRIORITY = {
    "NO_TOKEN": 0,
    "NO_LIVE_OPTION_FEED": 1,
    "STALE_OPTION_LTP": 2,
    "PRICE_MISMATCH": 3,
}


@dataclass(frozen=True)
class BlockerSpec:
    code: str
    owner: str
    scope: str
    kind: str
    severity: str
    expiry_ttl_sec: float | None
    set_condition: str
    clear_condition: str
    evidence_fields: tuple[str, ...]


BLOCKER_SPECS: dict[str, BlockerSpec] = {
    "NO_LIVE_OPTION_FEED": BlockerSpec(
        code="NO_LIVE_OPTION_FEED",
        owner="feed_health_evaluator",
        scope="feed/advisory",
        kind="edge_ttl",
        severity="error",
        expiry_ttl_sec=15.0,
        set_condition="feed disconnected, expected subscriptions missing, or no fresh option tick within threshold",
        clear_condition="feed connected and fresh option tick/tick age within threshold for current owner",
        evidence_fields=("ws_connected", "expected_option_count", "subscribed_option_count", "latest_option_tick_ts", "latest_option_tick_age_sec"),
    ),
    "STALE_OPTION_LTP": BlockerSpec(
        code="STALE_OPTION_LTP",
        owner="quote_freshness_evaluator",
        scope="feed/advisory",
        kind="level",
        severity="error",
        expiry_ttl_sec=None,
        set_condition="quote or tick age exceeds stale threshold",
        clear_condition="quote or tick age returns within threshold for current owner",
        evidence_fields=("quote_age_sec", "stale_threshold_sec", "latest_option_tick_age_sec", "feed_freshness_sec"),
    ),
    "NO_TOKEN": BlockerSpec(
        code="NO_TOKEN",
        owner="instrument_resolution_evaluator",
        scope="advisory_contract",
        kind="edge_ttl",
        severity="error",
        expiry_ttl_sec=30.0,
        set_condition="selected contract lacks broker token and tradingsymbol identity",
        clear_condition="instrument token resolution succeeds for current owner key",
        evidence_fields=("symbol", "expiry", "strike", "right", "tradingsymbol", "advisory_generation"),
    ),
    "PRICE_MISMATCH": BlockerSpec(
        code="PRICE_MISMATCH",
        owner="price_coherence_evaluator",
        scope="advisory_contract",
        kind="level",
        severity="error",
        expiry_ttl_sec=15.0,
        set_condition="live and reference prices differ beyond absolute and percentage tolerances",
        clear_condition="prices reconcile, quote invalidates, or owner changes",
        evidence_fields=("live_price", "reference_price", "quote_age_sec", "abs_tol", "pct_tol"),
    ),
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def build_feed_owner_key(symbol: str) -> str:
    return f"feed|{_norm_text(symbol).upper()}"


def build_contract_owner_key(
    *,
    symbol: str | None,
    expiry: Any = None,
    strike: Any = None,
    right: str | None = None,
    generation: str | None = None,
) -> str:
    parts = [
        "contract",
        _norm_text(symbol).upper() or "UNKNOWN",
        _norm_text(expiry) or "UNKNOWN",
        _norm_text(strike) or "UNKNOWN",
        _norm_text(right).upper() or "UNKNOWN",
    ]
    if _norm_text(generation):
        parts.append(_norm_text(generation))
    return "|".join(parts)


@dataclass
class BlockerRecord:
    code: str
    owner: str
    scope: str
    owner_key: str
    kind: str
    severity: str
    active: bool
    reason: str | None
    evidence: dict[str, Any]
    source_ts: float | None
    last_eval_ts: float | None
    last_set_ts: float | None
    last_refresh_ts: float | None
    last_clear_ts: float | None
    expiry_ttl_sec: float | None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class BlockerRegistry:
    def __init__(self, name: str):
        self.name = str(name)
        self._records: dict[tuple[str, str, str], BlockerRecord] = {}

    def _log_transition(self, event: str, record: BlockerRecord) -> None:
        try:
            logger.info(
                json.dumps(
                    {
                        "event": str(event),
                        "registry": self.name,
                        "code": record.code,
                        "owner": record.owner,
                        "scope": record.scope,
                        "owner_key": record.owner_key,
                        "reason": record.reason,
                        "evidence": record.evidence,
                    },
                    sort_keys=True,
                    default=str,
                )
            )
        except Exception:
            return

    def evaluate(
        self,
        *,
        code: str,
        owner: str,
        scope: str,
        owner_key: str,
        kind: str,
        severity: str = "error",
        is_active: bool,
        now_ts: float,
        reason: str | None = None,
        evidence: dict[str, Any] | None = None,
        source_ts: float | None = None,
        expiry_ttl_sec: float | None = None,
    ) -> BlockerRecord | None:
        key = (str(scope), str(owner_key), str(code))
        existing = self._records.get(key)
        if bool(is_active):
            if existing is None:
                record = BlockerRecord(
                    code=str(code),
                    owner=str(owner),
                    scope=str(scope),
                    owner_key=str(owner_key),
                    kind=str(kind),
                    severity=str(severity),
                    active=True,
                    reason=str(reason) if reason else None,
                    evidence=dict(evidence or {}),
                    source_ts=_safe_float(source_ts),
                    last_eval_ts=float(now_ts),
                    last_set_ts=float(now_ts),
                    last_refresh_ts=float(now_ts),
                    last_clear_ts=None,
                    expiry_ttl_sec=_safe_float(expiry_ttl_sec),
                )
                self._records[key] = record
                self._log_transition("BLOCKER_SET", record)
                return record
            existing.active = True
            existing.reason = str(reason) if reason else None
            existing.evidence = dict(evidence or {})
            existing.source_ts = _safe_float(source_ts)
            existing.last_eval_ts = float(now_ts)
            existing.last_refresh_ts = float(now_ts)
            existing.expiry_ttl_sec = _safe_float(expiry_ttl_sec)
            self._log_transition("BLOCKER_REFRESH", existing)
            return existing
        if existing is None:
            return None
        existing.last_eval_ts = float(now_ts)
        if existing.active:
            existing.active = False
            existing.reason = str(reason) if reason else existing.reason
            existing.evidence = dict(evidence or existing.evidence or {})
            existing.last_clear_ts = float(now_ts)
            self._log_transition("BLOCKER_CLEAR", existing)
        return existing

    def expire_stale(self, now_ts: float, *, scope: str | None = None) -> None:
        for record in list(self._records.values()):
            if scope and record.scope != scope:
                continue
            ttl = _safe_float(record.expiry_ttl_sec)
            if not record.active or ttl is None or ttl <= 0:
                continue
            anchor = _safe_float(record.last_refresh_ts) or _safe_float(record.last_eval_ts) or _safe_float(record.last_set_ts)
            if anchor is None:
                continue
            if (float(now_ts) - float(anchor)) <= float(ttl):
                continue
            record.active = False
            record.last_clear_ts = float(now_ts)
            record.reason = record.reason or "expired"
            self._log_transition("BLOCKER_EXPIRE", record)

    def prune_invalid_owners(self, *, now_ts: float, scope: str, valid_owner_keys: set[str]) -> None:
        for record in list(self._records.values()):
            if record.scope != str(scope):
                continue
            if record.owner_key in valid_owner_keys:
                continue
            if not record.active:
                continue
            record.active = False
            record.last_clear_ts = float(now_ts)
            record.reason = "owner_invalid"
            self._log_transition("BLOCKER_CLEAR", record)

    def get_active(self, *, scope: str | None = None, owner_key: str | None = None) -> list[BlockerRecord]:
        out: list[BlockerRecord] = []
        for record in self._records.values():
            if not record.active:
                continue
            if scope and record.scope != scope:
                continue
            if owner_key and record.owner_key != owner_key:
                continue
            out.append(record)
        out.sort(key=lambda item: (_TARGET_BLOCKER_PRIORITY.get(item.code, 99), item.code, item.owner_key))
        return out


_REGISTRIES: dict[str, BlockerRegistry] = {}


def get_blocker_registry(name: str) -> BlockerRegistry:
    key = str(name or "default")
    registry = _REGISTRIES.get(key)
    if registry is None:
        registry = BlockerRegistry(key)
        _REGISTRIES[key] = registry
    return registry


def reset_blocker_registries() -> None:
    _REGISTRIES.clear()


def top_active_code(records: list[BlockerRecord]) -> str | None:
    if not records:
        return None
    return str(sorted(records, key=lambda item: (_TARGET_BLOCKER_PRIORITY.get(item.code, 99), item.code))[0].code)


def blocker_spec(code: str) -> BlockerSpec:
    return BLOCKER_SPECS[str(code)]


def evaluate_feed_symbol_blockers(
    registry: BlockerRegistry,
    *,
    now_ts: float,
    symbol: str,
    ws_connected: bool | None,
    expected_option_count: int,
    subscribed_option_count: int,
    option_ticks_received_count: int = 0,
    latest_option_tick_ts: float | None,
    latest_option_tick_age_sec: float | None,
    feed_freshness_sec: float,
    min_required_count: int = 0,
) -> list[BlockerRecord]:
    owner_key = build_feed_owner_key(symbol)
    expected_count = max(0, int(expected_option_count or 0))
    subscribed_count = max(0, int(subscribed_option_count or 0))
    min_required = max(0, int(min_required_count or 0))
    ticks_received_count = max(0, int(option_ticks_received_count or 0))
    age_sec = _safe_float(latest_option_tick_age_sec)
    feed_limit = max(0.1, float(feed_freshness_sec))
    fresh_tick_recovered = bool(
        latest_option_tick_ts is not None
        and age_sec is not None
        and age_sec <= feed_limit
        and ticks_received_count > 0
    )

    no_live_fault = False
    no_live_reason = "feed_ok"
    if fresh_tick_recovered:
        no_live_fault = False
        no_live_reason = "fresh_option_tick_recovered"
    elif ws_connected is False:
        no_live_fault = True
        no_live_reason = "ws_disconnected"
    elif max(expected_count, min_required) > subscribed_count:
        no_live_fault = True
        no_live_reason = "option_subscriptions_missing"
    elif subscribed_count > 0 and latest_option_tick_ts is None:
        no_live_fault = True
        no_live_reason = "no_option_ticks"
    elif subscribed_count > 0 and latest_option_tick_ts is None:
        no_live_fault = True
        no_live_reason = "option_tick_age_exceeded_critical"
    registry.evaluate(
        code="NO_LIVE_OPTION_FEED",
        owner="feed_health_evaluator",
        scope="feed_symbol",
        owner_key=owner_key,
        kind="edge_ttl",
        is_active=no_live_fault,
        now_ts=float(now_ts),
        reason=no_live_reason,
        evidence={
            "symbol": str(symbol).upper(),
            "ws_connected": ws_connected,
            "expected_option_count": expected_count,
            "subscribed_option_count": subscribed_count,
            "option_ticks_received_count": ticks_received_count,
            "latest_option_tick_ts": _safe_float(latest_option_tick_ts),
            "latest_option_tick_age_sec": age_sec,
            "feed_freshness_sec": feed_limit,
        },
        source_ts=_safe_float(latest_option_tick_ts),
        expiry_ttl_sec=15.0,
    )

    stale_fault = bool(subscribed_count > 0 and latest_option_tick_ts is not None and age_sec is not None and age_sec > max(60.0, float(feed_limit) * 10.0))
    registry.evaluate(
        code="STALE_OPTION_LTP",
        owner="quote_freshness_evaluator",
        scope="feed_symbol",
        owner_key=owner_key,
        kind="level",
        is_active=stale_fault,
        now_ts=float(now_ts),
        reason="latest_option_tick_age_exceeded" if stale_fault else "quote_fresh",
        evidence={
            "symbol": str(symbol).upper(),
            "latest_option_tick_ts": _safe_float(latest_option_tick_ts),
            "latest_option_tick_age_sec": age_sec,
            "feed_freshness_sec": feed_limit,
        },
        source_ts=_safe_float(latest_option_tick_ts),
        expiry_ttl_sec=max(10.0, float(feed_limit) * 2.0),
    )

    registry.expire_stale(float(now_ts), scope="feed_symbol")
    return registry.get_active(scope="feed_symbol", owner_key=owner_key)


def evaluate_advisory_contract_blockers(
    registry: BlockerRegistry,
    *,
    now_ts: float,
    symbol: str | None,
    expiry: Any = None,
    strike: Any = None,
    right: str | None = None,
    advisory_generation: str | None = None,
    instrument_token: Any = None,
    tradingsymbol: str | None = None,
    live_price: float | None = None,
    reference_price: float | None = None,
    quote_age_sec: float | None = None,
    stale_threshold_sec: float,
    abs_tol: float,
    pct_tol: float,
    subscription_failed: bool = False,
) -> list[BlockerRecord]:
    owner_key = build_contract_owner_key(
        symbol=symbol,
        expiry=expiry,
        strike=strike,
        right=right,
        generation=advisory_generation,
    )
    live_val = _safe_float(live_price)
    ref_val = _safe_float(reference_price)
    age_sec = _safe_float(quote_age_sec)
    threshold = max(0.1, float(stale_threshold_sec))

    tradingsymbol_text = _norm_text(tradingsymbol)
    no_token = instrument_token in (None, "", "None") and not tradingsymbol_text
    registry.evaluate(
        code="NO_TOKEN",
        owner="instrument_resolution_evaluator",
        scope="advisory_contract",
        owner_key=owner_key,
        kind="edge_ttl",
        is_active=no_token,
        now_ts=float(now_ts),
        reason="instrument_token_missing" if no_token else "token_present",
        evidence={
            "symbol": _norm_text(symbol).upper(),
            "expiry": _norm_text(expiry),
            "strike": _norm_text(strike),
            "right": _norm_text(right).upper(),
            "tradingsymbol": tradingsymbol_text,
            "advisory_generation": _norm_text(advisory_generation),
        },
        expiry_ttl_sec=30.0,
    )

    no_live = bool(not no_token and (subscription_failed or live_val is None or age_sec is None or age_sec > threshold))
    no_live_reason = "quote_present"
    if subscription_failed:
        no_live_reason = "subscription_failed"
    elif live_val is None:
        no_live_reason = "live_price_missing"
    elif age_sec is None:
        no_live_reason = "quote_age_missing"
    elif age_sec > threshold:
        no_live_reason = "quote_age_exceeded"
    registry.evaluate(
        code="NO_LIVE_OPTION_FEED",
        owner="feed_health_evaluator",
        scope="advisory_contract",
        owner_key=owner_key,
        kind="edge_ttl",
        is_active=no_live,
        now_ts=float(now_ts),
        reason=no_live_reason,
        evidence={
            "symbol": _norm_text(symbol).upper(),
            "expiry": _norm_text(expiry),
            "strike": _norm_text(strike),
            "right": _norm_text(right).upper(),
            "advisory_generation": _norm_text(advisory_generation),
            "subscription_failed": bool(subscription_failed),
            "live_price": live_val,
            "quote_age_sec": age_sec,
            "stale_threshold_sec": threshold,
        },
        expiry_ttl_sec=15.0,
    )

    stale = bool(not no_token and live_val is not None and age_sec is not None and age_sec > threshold)
    registry.evaluate(
        code="STALE_OPTION_LTP",
        owner="quote_freshness_evaluator",
        scope="advisory_contract",
        owner_key=owner_key,
        kind="level",
        is_active=stale,
        now_ts=float(now_ts),
        reason="quote_age_exceeded" if stale else "quote_fresh",
        evidence={
            "symbol": _norm_text(symbol).upper(),
            "expiry": _norm_text(expiry),
            "strike": _norm_text(strike),
            "right": _norm_text(right).upper(),
            "advisory_generation": _norm_text(advisory_generation),
            "quote_age_sec": age_sec,
            "stale_threshold_sec": threshold,
        },
        expiry_ttl_sec=max(10.0, threshold * 2.0),
    )

    mismatch = False
    mismatch_reason = "prices_reconciled"
    if live_val is not None and ref_val is not None and age_sec is not None and age_sec <= threshold:
        diff = abs(live_val - ref_val)
        pct = diff / max(abs(ref_val), 1e-9)
        mismatch = bool(diff > float(abs_tol) and pct > float(pct_tol))
        mismatch_reason = "price_out_of_tolerance" if mismatch else "prices_reconciled"
    registry.evaluate(
        code="PRICE_MISMATCH",
        owner="price_coherence_evaluator",
        scope="advisory_contract",
        owner_key=owner_key,
        kind="level",
        is_active=mismatch,
        now_ts=float(now_ts),
        reason=mismatch_reason,
        evidence={
            "symbol": _norm_text(symbol).upper(),
            "expiry": _norm_text(expiry),
            "strike": _norm_text(strike),
            "right": _norm_text(right).upper(),
            "advisory_generation": _norm_text(advisory_generation),
            "live_price": live_val,
            "reference_price": ref_val,
            "quote_age_sec": age_sec,
            "abs_tol": float(abs_tol),
            "pct_tol": float(pct_tol),
        },
        expiry_ttl_sec=15.0,
    )

    registry.expire_stale(float(now_ts), scope="advisory_contract")
    return registry.get_active(scope="advisory_contract", owner_key=owner_key)
