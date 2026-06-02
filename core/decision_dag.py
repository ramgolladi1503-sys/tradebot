# Migration note:
# Decision DAG now derives runtime mode from core.market_context and uses compute_age_sec helper.

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from config import config as cfg
from core.live_indicator_readiness import build_live_indicator_readiness_report
from core.market_context import coerce_segment_for_market_context, derive_market_context
from core.time_utils import compute_age_sec, now_utc_epoch

logger = logging.getLogger(__name__)

ReasonCode = str

REASON_MARKET_CLOSED = "MARKET_CLOSED"
REASON_FEED_STALE = "FEED_STALE"
REASON_WARMUP_INCOMPLETE = "WARMUP_INCOMPLETE"
REASON_INDICATORS_MISSING = "INDICATORS_MISSING"
REASON_QUOTE_INVALID = "QUOTE_INVALID"
REASON_INDEX_BIDASK_MISSING = "index_bidask_missing"
REASON_REGIME_UNKNOWN = "REGIME_UNKNOWN"
REASON_REGIME_UNSTABLE = "REGIME_UNSTABLE"
REASON_RISK_LIMIT = "RISK_LIMIT"
REASON_LOCK_ACTIVE = "LOCK_ACTIVE"
REASON_BROKER_DISABLED = "BROKER_DISABLED"
REASON_NO_STRATEGY_QUALIFIED = "NO_STRATEGY_QUALIFIED"
REASON_MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"

NODE_N1_MARKET_OPEN = "N1_MARKET_OPEN"
NODE_N2_FEED_FRESH = "N2_FEED_FRESH"
NODE_N3_WARMUP_DONE = "N3_WARMUP_DONE"
NODE_N4_QUOTE_OK = "N4_QUOTE_OK"
NODE_N5_REGIME_OK = "N5_REGIME_OK"
NODE_N6_RISK_OK = "N6_RISK_OK"
NODE_N7_GOVERNANCE_LOCKS_OK = "N7_GOVERNANCE_LOCKS_OK"
NODE_N8_STRATEGY_SELECT = "N8_STRATEGY_SELECT"
NODE_N9_STRATEGY_ELIGIBLE = "N9_STRATEGY_ELIGIBLE"
NODE_N10_DECISION_READY = "N10_DECISION_READY"
NODE_N11_FINAL_DECISION = "N11_FINAL_DECISION"
# Backward-compat export. Existing callsites/tests import NODE_N9_FINAL_DECISION.
NODE_N9_FINAL_DECISION = NODE_N11_FINAL_DECISION

_LINEAR_NODE_ORDER = (
    NODE_N1_MARKET_OPEN,
    NODE_N2_FEED_FRESH,
    NODE_N3_WARMUP_DONE,
    NODE_N4_QUOTE_OK,
    NODE_N5_REGIME_OK,
    NODE_N6_RISK_OK,
    NODE_N7_GOVERNANCE_LOCKS_OK,
    NODE_N8_STRATEGY_SELECT,
    NODE_N9_STRATEGY_ELIGIBLE,
    NODE_N10_DECISION_READY,
    NODE_N11_FINAL_DECISION,
)


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    sval = str(value).strip().lower()
    if sval in {"1", "true", "yes", "y", "on"}:
        return True
    if sval in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _normalized_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    return "LIVE" if mode == "LIVE" else "SIM"


def _is_index_symbol(symbol: str, instrument: str | None = None) -> bool:
    inst = str(instrument or "").upper()
    if inst == "INDEX":
        return True
    if inst:
        return False
    return str(symbol or "").upper() in {"NIFTY", "BANKNIFTY", "SENSEX"}


def _to_immutable_mapping(data: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        return MappingProxyType(copy.deepcopy(dict(data)))
    except Exception:
        return MappingProxyType(dict(data))


def _clean_reasons(reasons: Sequence[Any] | None) -> tuple[str, ...]:
    out: list[str] = []
    for raw in reasons or ():
        text = str(raw or "").strip()
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _synth_index_bid_ask(ltp: float) -> tuple[float, float]:
    spread = max(float(ltp) * 0.00005, 0.5)
    spread = min(spread, 5.0)
    half = spread / 2.0
    return round(float(ltp) - half, 4), round(float(ltp) + half, 4)


def _resolve_index_quote_from_snapshot(snapshot: "MarketSnapshot") -> dict:
    """
    Resolve index bid/ask using only snapshot fields.
    This keeps decision evaluation deterministic and snapshot-bound.
    """

    def _as_price(value: Any) -> float | None:
        try:
            p = float(value)
            if p > 0:
                return p
        except Exception:
            return None
        return None

    mode = str(snapshot.mode or "SIM").upper()
    ctx_payload = dict(snapshot.market_context or {})
    if "execution_mode" not in ctx_payload:
        ctx_payload["execution_mode"] = mode
    if "market_open" not in ctx_payload:
        ctx_payload["market_open"] = bool(snapshot.market_open)
    ctx = derive_market_context(ctx_payload)
    mode = str(ctx.mode or mode).upper()

    depth = dict(snapshot.depth or {})
    bid = _as_price(depth.get("bid"))
    ask = _as_price(depth.get("ask"))
    if bid is None:
        bid = _as_price(snapshot.bid)
    if ask is None:
        ask = _as_price(snapshot.ask)
    if bid is not None and ask is not None and ask >= bid:
        return {
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2.0,
            "quote_ok": True,
            "quote_source": "depth",
        }

    ltp = _as_price(snapshot.ltp)
    if ltp is None:
        return {
            "bid": None,
            "ask": None,
            "mid": None,
            "quote_ok": False,
            "quote_source": "missing_ltp" if bool(getattr(ctx, "require_live_quotes", False)) else "missing_depth",
        }

    max_ltp_age = float(
        getattr(
            cfg,
            "MAX_LTP_AGE_SEC" if mode == "LIVE" else "OFFHOURS_MAX_LTP_AGE_SEC",
            8.0 if mode == "LIVE" else 3600.0,
        )
    )
    ltp_age_sec = compute_age_sec(snapshot.ltp_ts_epoch, snapshot.ts_epoch)
    if ltp_age_sec is None:
        age_ok = not bool(getattr(ctx, "require_live_quotes", False))
    else:
        age_ok = float(max(0.0, ltp_age_sec)) <= max_ltp_age
    if not age_ok:
        return {
            "bid": None,
            "ask": None,
            "mid": None,
            "quote_ok": False,
            "quote_source": "stale_ltp",
        }

    depth_required = bool(mode == "LIVE" and bool(snapshot.market_open) and bool(getattr(cfg, "INDEX_REQUIRE_DEPTH_LIVE", False)))
    if depth_required:
        return {
            "bid": None,
            "ask": None,
            "mid": None,
            "quote_ok": False,
            "quote_source": "missing_depth",
        }

    synth_bid, synth_ask = _synth_index_bid_ask(ltp)
    return {
        "bid": synth_bid,
        "ask": synth_ask,
        "mid": (synth_bid + synth_ask) / 2.0 if synth_bid is not None and synth_ask is not None else None,
        "quote_ok": bool(synth_bid is not None and synth_ask is not None),
        "quote_source": "synthetic_index" if synth_bid is not None and synth_ask is not None else "missing_depth",
    }


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    ts_epoch: float
    mode: str
    market_open: bool
    offhours_mode: bool
    allow_stale_quotes: bool
    market_context: Mapping[str, Any]
    ltp: float | None
    ltp_ts_epoch: float | None
    ltp_source: str | None
    depth: Mapping[str, Any] | None
    depth_ts_epoch: float | None
    ohlc_bars_count: int
    last_bar_ts_epoch: float | None
    indicators_ok: bool
    indicators_age_sec: float
    indicator_last_update_epoch: float | None
    regime_probs: Mapping[str, float]
    regime_entropy: float | None
    regime_prob_max: float | None
    primary_regime: str | None
    unstable_reasons: tuple[str, ...]
    risk_ok: bool
    risk_reasons: tuple[str, ...]
    governance_lock_active: bool
    broker_enabled: bool
    manual_review_required: bool
    instrument: str
    bid: float | None
    ask: float | None
    quote_ok_input: bool | None
    quote_source_input: str | None
    feed_health: Mapping[str, Any]
    raw_data: Mapping[str, Any]


@dataclass(frozen=True)
class NodeResult:
    ok: bool
    value: Any = None
    reasons: tuple[str, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyCandidate:
    family: str | None = None
    allowed: bool = False
    reasons: tuple[str, ...] = ()
    candidate_summary: Mapping[str, Any] = field(default_factory=dict)
    risk_params: Mapping[str, Any] = field(default_factory=dict)
    manual_review_required: bool = False


@dataclass
class DecisionReport:
    symbol: str
    ts_epoch: float
    allowed: bool
    blockers: tuple[str, ...]
    primary_blocker: str | None
    stage: str
    selected_strategy: str | None
    risk_params: Mapping[str, Any]
    facts: Mapping[str, Any]
    explain: tuple[Mapping[str, Any], ...]


# Backward-compatible name for existing integrations.
Decision = DecisionReport


@dataclass(frozen=True)
class NodeSpec:
    name: str
    deps: tuple[str, ...]
    fn: Callable[[MarketSnapshot, Mapping[str, Any], Mapping[str, NodeResult]], NodeResult]


def _normalize_candidate(raw: Any) -> StrategyCandidate:
    if isinstance(raw, StrategyCandidate):
        return raw
    row = dict(raw or {})
    candidate_summary = row.get("candidate_summary") if isinstance(row.get("candidate_summary"), Mapping) else {}
    reasons = _clean_reasons(row.get("reasons") if isinstance(row.get("reasons"), Sequence) else ())
    manual_review_required = _to_bool(
        row.get("manual_review_required", candidate_summary.get("manual_review_required", False)),
        default=False,
    )
    risk_params = row.get("risk_params") if isinstance(row.get("risk_params"), Mapping) else {}
    family = row.get("family")
    family_str = str(family).strip().upper() if family is not None else None
    if not family_str:
        family_str = None
    allowed = _to_bool(row.get("allowed"), default=False)
    return StrategyCandidate(
        family=family_str,
        allowed=allowed,
        reasons=reasons,
        candidate_summary=dict(candidate_summary),
        risk_params=dict(risk_params),
        manual_review_required=manual_review_required,
    )


def _normalize_candidates(raw_candidates: Sequence[Any] | None) -> tuple[StrategyCandidate, ...]:
    out: list[StrategyCandidate] = []
    for raw in raw_candidates or ():
        out.append(_normalize_candidate(raw))
    return tuple(out)


def build_market_snapshot(
    market_data: Mapping[str, Any] | MarketSnapshot,
    *,
    now_epoch: float | None = None,
) -> MarketSnapshot:
    if isinstance(market_data, MarketSnapshot):
        return market_data
    data = dict(market_data or {})
    now_value = _to_float(now_epoch)
    if now_value is None:
        now_value = _to_float(data.get("timestamp"))
    if now_value is None:
        now_value = float(now_utc_epoch())

    symbol = str(data.get("symbol") or "").upper() or "UNKNOWN"
    instrument = str(data.get("instrument") or data.get("instrument_type") or "").upper() or "OPT"
    ctx_payload = dict(data.get("market_context") or {}) if isinstance(data.get("market_context"), Mapping) else {}
    if "execution_mode" not in ctx_payload:
        ctx_payload["execution_mode"] = data.get("execution_mode")
    if "market_open" not in ctx_payload and "market_open" in data:
        ctx_payload["market_open"] = data.get("market_open")
    if "segment" not in ctx_payload:
        ctx_payload["segment"] = data.get("segment")
    ctx_payload["segment"] = coerce_segment_for_market_context(
        ctx_payload.get("segment"),
        symbol=symbol,
        instrument=instrument,
    )
    if "symbol" not in ctx_payload:
        ctx_payload["symbol"] = symbol
    if "instrument" not in ctx_payload:
        ctx_payload["instrument"] = instrument
    if "state" not in ctx_payload:
        ctx_payload["state"] = data.get("state")
    market_ctx = derive_market_context(ctx_payload)
    mode = str(market_ctx.mode)
    market_open = bool(market_ctx.is_market_open)
    offhours_mode = bool(market_ctx.mode == "OFFHOURS")
    allow_stale_quotes = bool(market_ctx.allow_stale_quotes)

    ltp = _to_float(data.get("ltp"))
    ltp_ts_epoch = _to_float(data.get("ltp_ts_epoch"))
    if ltp_ts_epoch is None:
        ltp_ts_epoch = _to_float(data.get("tick_last_epoch"))
    if ltp_ts_epoch is None:
        for fallback_key in (
            "quote_ts_epoch",
            "latest_option_tick_ts",
            "last_tick_ts",
            "timestamp_epoch",
            "feed_timestamp_epoch",
            "ts_epoch",
        ):
            ltp_ts_epoch = _to_float(data.get(fallback_key))
            if ltp_ts_epoch is not None:
                break
    ltp_source = str(data.get("ltp_source") or "").strip() or None

    bid = _to_float(data.get("bid"))
    ask = _to_float(data.get("ask"))
    depth_raw = data.get("depth")
    depth: Mapping[str, Any] | None
    if isinstance(depth_raw, Mapping):
        depth = dict(depth_raw)
    else:
        d: dict[str, Any] = {}
        if bid is not None:
            d["bid"] = bid
        if ask is not None:
            d["ask"] = ask
        depth = d or None

    depth_ts_epoch = _to_float(data.get("depth_ts_epoch"))
    if depth_ts_epoch is None:
        depth_ts_epoch = _to_float(data.get("depth_last_epoch"))
    depth_age_from_row = _to_float(data.get("depth_age_sec"))
    if depth_ts_epoch is None and depth_age_from_row is not None:
        depth_ts_epoch = max(0.0, float(now_value) - float(depth_age_from_row))

    ohlc_bars_count_raw = data.get("ohlc_bars_count")
    try:
        ohlc_bars_count = int(ohlc_bars_count_raw) if ohlc_bars_count_raw is not None else 0
    except Exception:
        ohlc_bars_count = 0
    last_bar_ts_epoch = _to_float(data.get("last_bar_ts_epoch"))
    if last_bar_ts_epoch is None:
        last_bar_ts_epoch = _to_float(data.get("ohlc_last_bar_epoch"))

    indicator_last_update_epoch = _to_float(data.get("indicator_last_update_epoch"))
    indicators_ok = _to_bool(data.get("indicators_ok"), default=False)
    indicators_age_sec = _to_float(data.get("indicators_age_sec"))
    never_computed_age = float(getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9))
    if indicators_age_sec is None:
        if indicator_last_update_epoch is not None:
            indicators_age_sec = compute_age_sec(indicator_last_update_epoch, now_value) or 0.0
        else:
            indicators_age_sec = never_computed_age

    regime_probs_raw = data.get("regime_probs") if isinstance(data.get("regime_probs"), Mapping) else {}
    regime_probs: dict[str, float] = {}
    for key, value in regime_probs_raw.items():
        fv = _to_float(value)
        if fv is not None:
            regime_probs[str(key)] = fv
    regime_prob_max = _to_float(data.get("regime_prob_max"))
    if regime_prob_max is None:
        regime_prob_max = _to_float(data.get("regime_probs_max"))
    if regime_prob_max is None and regime_probs:
        regime_prob_max = max(regime_probs.values())
    regime_entropy = _to_float(data.get("regime_entropy"))
    primary_regime = str(data.get("primary_regime") or data.get("regime") or "").upper() or None
    unstable_reasons = _clean_reasons(data.get("unstable_reasons") if isinstance(data.get("unstable_reasons"), Sequence) else ())
    if _to_bool(data.get("unstable_regime_flag"), default=False) and "legacy_unstable_flag" not in unstable_reasons:
        unstable_reasons = tuple(list(unstable_reasons) + ["legacy_unstable_flag"])

    risk_ok_raw = data.get("risk_ok")
    if risk_ok_raw is None:
        risk_ok = not _to_bool(data.get("risk_limit"), default=False) and not _to_bool(data.get("risk_halt_active"), default=False)
    else:
        risk_ok = _to_bool(risk_ok_raw, default=True)
    risk_reasons = _clean_reasons(data.get("risk_reasons") if isinstance(data.get("risk_reasons"), Sequence) else ())
    if (not risk_ok) and (REASON_RISK_LIMIT not in risk_reasons):
        risk_reasons = tuple(list(risk_reasons) + [REASON_RISK_LIMIT])

    governance_lock_active = _to_bool(
        data.get("governance_lock_active", data.get("lock_active", data.get("wf_lock_active", False))),
        default=False,
    )
    if "wf_lock" in str(data.get("gate_reasons", "")).lower():
        governance_lock_active = True
    broker_enabled = _to_bool(data.get("broker_enabled"), default=True) and (not _to_bool(data.get("broker_disabled"), default=False))
    manual_review_required = _to_bool(data.get("manual_review_required", data.get("review_required", False)), default=False)

    quote_ok_input: bool | None
    if "quote_ok" in data:
        quote_ok_input = _to_bool(data.get("quote_ok"), default=False)
    else:
        quote_ok_input = None
    quote_source_input = str(data.get("quote_source") or "").strip() or None

    max_ltp_age = _to_float(
        getattr(
            cfg,
            "OFFHOURS_SLA_MAX_LTP_AGE_SEC" if offhours_mode else "SLA_MAX_LTP_AGE_SEC",
            None,
        )
    )
    if max_ltp_age is None:
        max_ltp_age = _to_float(
            getattr(
                cfg,
                "OFFHOURS_MAX_LTP_AGE_SEC" if offhours_mode else "MAX_LTP_AGE_SEC",
                900.0 if offhours_mode else 2.5,
            )
        )
    if max_ltp_age is None:
        max_ltp_age = 2.5

    max_depth_age = _to_float(
        getattr(
            cfg,
            "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC" if offhours_mode else "SLA_MAX_DEPTH_AGE_SEC",
            None,
        )
    )
    if max_depth_age is None:
        max_depth_age = _to_float(
            getattr(
                cfg,
                "OFFHOURS_MAX_DEPTH_AGE_SEC" if offhours_mode else "MAX_DEPTH_AGE_SEC",
                900.0 if offhours_mode else 6.0,
            )
        )
    if max_depth_age is None:
        max_depth_age = 6.0

    max_option_tick_age = _to_float(
        getattr(
            cfg,
            "OFFHOURS_MAX_OPTION_QUOTE_AGE_SEC" if offhours_mode else "MAX_OPTION_QUOTE_AGE_SEC",
            max_ltp_age,
        )
    )
    if max_option_tick_age is None:
        max_option_tick_age = max_ltp_age

    if ltp_ts_epoch is None:
        ltp_age_sec = float("inf")
    else:
        ltp_age_sec = compute_age_sec(ltp_ts_epoch, now_value)
        if ltp_age_sec is None:
            ltp_age_sec = float("inf")

    if depth_ts_epoch is None:
        depth_age_sec = depth_age_from_row
    else:
        depth_age_sec = compute_age_sec(depth_ts_epoch, now_value)

    raw_feed_health = data.get("feed_health") if isinstance(data.get("feed_health"), Mapping) else {}
    latest_option_tick_ts = _to_float(data.get("latest_option_tick_ts"))
    if latest_option_tick_ts is None:
        latest_option_tick_ts = _to_float(raw_feed_health.get("latest_option_tick_ts"))
    latest_option_tick_age_sec = _to_float(data.get("latest_option_tick_age_sec"))
    if latest_option_tick_age_sec is None:
        latest_option_tick_age_sec = _to_float(raw_feed_health.get("latest_option_tick_age_sec"))
    if latest_option_tick_age_sec is None and latest_option_tick_ts is not None:
        latest_option_tick_age_sec = compute_age_sec(latest_option_tick_ts, now_value)

    ws_connected = data.get("ws_connected")
    if ws_connected is None:
        ws_connected = raw_feed_health.get("ws_connected")
    subscribed_option_tokens_count = _to_float(data.get("subscribed_option_tokens_count"))
    if subscribed_option_tokens_count is None:
        subscribed_option_tokens_count = _to_float(raw_feed_health.get("subscribed_option_tokens_count"))

    option_feed_block_reason = str(data.get("option_feed_block_reason") or "").strip().upper()
    if not option_feed_block_reason:
        option_feed_block_reason = str(raw_feed_health.get("option_feed_block_reason") or "").strip().upper()

    ltp_fresh = bool(ltp is not None and ltp > 0 and ltp_age_sec <= float(max_ltp_age))
    option_tick_fresh = bool(
        latest_option_tick_age_sec is not None
        and float(latest_option_tick_age_sec) <= float(max_option_tick_age)
    )
    option_feed_ok = option_feed_block_reason in {"", "OK"}
    option_feed_fresh = bool(
        str(instrument or "").upper() == "OPT"
        and option_tick_fresh
        and option_feed_ok
    )

    is_fresh = bool(allow_stale_quotes or ltp_fresh or option_feed_fresh)
    stale_reasons: list[str] = []
    if not is_fresh:
        if ltp is None or float(ltp) <= 0.0:
            stale_reasons.append("ltp_missing")
        elif not ltp_fresh:
            stale_reasons.append("ltp_stale")
        if str(instrument or "").upper() == "OPT":
            if not option_feed_ok:
                stale_reasons.append(f"option_feed_block:{option_feed_block_reason}")
            elif not option_tick_fresh:
                stale_reasons.append("option_tick_stale")
            if ws_connected is False:
                stale_reasons.append("ws_disconnected")
            if subscribed_option_tokens_count is not None and int(subscribed_option_tokens_count) <= 0:
                stale_reasons.append("no_option_subscriptions")

    feed_health = {
        "ltp_age_sec": ltp_age_sec,
        "ltp_max_age_sec": float(max_ltp_age),
        "depth_age_sec": depth_age_sec,
        "depth_max_age_sec": float(max_depth_age),
        "latest_option_tick_ts": latest_option_tick_ts,
        "latest_option_tick_age_sec": latest_option_tick_age_sec,
        "latest_option_tick_max_age_sec": float(max_option_tick_age),
        "ws_connected": ws_connected,
        "subscribed_option_tokens_count": (
            int(subscribed_option_tokens_count) if subscribed_option_tokens_count is not None else None
        ),
        "option_feed_block_reason": option_feed_block_reason or None,
        "is_fresh": bool(is_fresh),
        "source": ltp_source or "unknown",
        "offhours_mode": bool(offhours_mode),
        "allow_stale_quotes": bool(allow_stale_quotes),
        "ts_epoch": float(now_value),
        "ltp": {
            "age_sec": ltp_age_sec,
            "max_age_sec": float(max_ltp_age),
        },
        "depth": {
            "age_sec": depth_age_sec,
            "max_age_sec": float(max_depth_age),
        },
        "reasons": list(stale_reasons),
    }

    return MarketSnapshot(
        symbol=symbol,
        ts_epoch=float(now_value),
        mode=mode,
        market_open=market_open,
        offhours_mode=bool(offhours_mode),
        allow_stale_quotes=bool(allow_stale_quotes),
        market_context=MappingProxyType(market_ctx.to_dict()),
        ltp=ltp,
        ltp_ts_epoch=ltp_ts_epoch,
        ltp_source=ltp_source,
        depth=depth,
        depth_ts_epoch=depth_ts_epoch,
        ohlc_bars_count=max(0, int(ohlc_bars_count)),
        last_bar_ts_epoch=last_bar_ts_epoch,
        indicators_ok=indicators_ok,
        indicators_age_sec=float(indicators_age_sec),
        indicator_last_update_epoch=indicator_last_update_epoch,
        regime_probs=MappingProxyType(regime_probs),
        regime_entropy=regime_entropy,
        regime_prob_max=regime_prob_max,
        primary_regime=primary_regime,
        unstable_reasons=unstable_reasons,
        risk_ok=risk_ok,
        risk_reasons=risk_reasons,
        governance_lock_active=governance_lock_active,
        broker_enabled=broker_enabled,
        manual_review_required=manual_review_required,
        instrument=instrument,
        bid=bid,
        ask=ask,
        quote_ok_input=quote_ok_input,
        quote_source_input=quote_source_input,
        feed_health=MappingProxyType(feed_health),
        raw_data=_to_immutable_mapping(data),
    )


def _node_market_open(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    facts = {
        "market_open": bool(snapshot.market_open),
        "allow_stale_quotes": bool(snapshot.allow_stale_quotes),
        "offhours_mode": bool(snapshot.offhours_mode),
        "mode": str(snapshot.mode or "SIM").upper(),
    }
    if snapshot.market_open:
        return NodeResult(ok=True, facts=facts)
    if snapshot.allow_stale_quotes and bool(getattr(cfg, "DECISION_DAG_ALLOW_NON_LIVE_MARKET_CLOSED", True)):
        facts["market_closed_degraded"] = True
        facts["market_closed_degraded_reason"] = "non_live_market_closed"
        return NodeResult(ok=True, facts=facts)
    return NodeResult(ok=False, reasons=(REASON_MARKET_CLOSED,), facts=facts)


def _node_feed_fresh(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    feed = dict(snapshot.feed_health or {})
    if snapshot.allow_stale_quotes:
        feed["offhours_mode"] = bool(snapshot.offhours_mode)
        feed["allow_stale_quotes"] = True
        return NodeResult(ok=True, facts=feed)
    if bool(feed.get("is_fresh")):
        return NodeResult(ok=True, facts=feed)
    if bool(getattr(cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True)):
        feed_ltp = feed.get("ltp") if isinstance(feed.get("ltp"), Mapping) else {}
        feed_depth = feed.get("depth") if isinstance(feed.get("depth"), Mapping) else {}
        raw = snapshot.raw_data if isinstance(snapshot.raw_data, Mapping) else {}
        logger.warning(
            "FEED_STALE_EVIDENCE symbol=%s source=decision_dag mode=%s market_open=%s allow_stale_quotes=%s feed_is_fresh=%s ltp_age_sec=%s ltp_max_age_sec=%s depth_age_sec=%s depth_max_age_sec=%s ltp_ts_epoch=%s depth_ts_epoch=%s timestamp_epoch=%s latest_option_tick_ts=%s latest_option_tick_age_sec=%s ws_connected=%s subscribed_option_tokens_count=%s reasons=%s",
            str(snapshot.symbol or ""),
            str(snapshot.mode or ""),
            bool(snapshot.market_open),
            bool(snapshot.allow_stale_quotes),
            bool(feed.get("is_fresh", False)),
            feed_ltp.get("age_sec", feed.get("ltp_age_sec")),
            feed_ltp.get("max_age_sec", feed.get("ltp_max_age_sec")),
            feed_depth.get("age_sec", feed.get("depth_age_sec")),
            feed_depth.get("max_age_sec", feed.get("depth_max_age_sec")),
            snapshot.ltp_ts_epoch,
            snapshot.depth_ts_epoch,
            raw.get("timestamp_epoch"),
            raw.get("latest_option_tick_ts"),
            raw.get("latest_option_tick_age_sec"),
            raw.get("ws_connected", feed.get("ws_connected")),
            raw.get("subscribed_option_tokens_count", feed.get("subscribed_option_tokens_count")),
            list(feed.get("reasons") or []),
        )
    return NodeResult(ok=False, reasons=(REASON_FEED_STALE,), facts=feed)


def _node_warmup_done(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    reasons: list[str] = []
    warmup_reasons = _clean_reasons(snapshot.raw_data.get("warmup_reasons") if isinstance(snapshot.raw_data.get("warmup_reasons"), Sequence) else ())
    system_state = str(snapshot.raw_data.get("system_state") or "READY").upper()
    min_bars_cfg = int(getattr(cfg, "WARMUP_MIN_BARS", 50))
    min_bars = int(snapshot.raw_data.get("warmup_min_bars") or min_bars_cfg)
    indicator_stale_sec = float(getattr(cfg, "INDICATOR_STALE_SEC", 120.0))
    never_computed_age = float(getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9))
    has_explicit_bar_contract = ("ohlc_bars_count" in snapshot.raw_data) or ("warmup_min_bars" in snapshot.raw_data)
    indicator_missing_inputs: list[str] = []
    indicator_readiness_blockers: list[str] = []
    indicator_readiness_ready: bool | None = None

    if system_state == "WARMUP":
        reasons.append(REASON_WARMUP_INCOMPLETE)
    if (system_state == "WARMUP") or has_explicit_bar_contract:
        if snapshot.ohlc_bars_count < min_bars:
            reasons.append(REASON_WARMUP_INCOMPLETE)

    # Strict indicator readiness gate (LIVE only):
    # In LIVE mode, missing technical context must block executability. To preserve backward
    # compatibility for legacy snapshots/tests that do not carry per-indicator values, we
    # only enforce the per-indicator presence check when those fields are actually present
    # in the snapshot payload; otherwise we fall back to the existing coarse flags.
    if snapshot.mode == "LIVE" and snapshot.market_open:
        raw = dict(snapshot.raw_data or {}) if isinstance(snapshot.raw_data, Mapping) else {}
        has_indicator_values = any(k in raw for k in ("vwap", "rsi", "ema", "atr"))
        if has_indicator_values:
            try:
                indicator_report = build_live_indicator_readiness_report(
                    [
                        {
                            "symbol": snapshot.symbol,
                            "ohlc_bars_count": snapshot.ohlc_bars_count,
                            "warmup_min_bars": min_bars,
                            "indicator_last_update_epoch": snapshot.indicator_last_update_epoch,
                            "compute_indicators_error": raw.get("compute_indicators_error", ""),
                            "ohlc_bars": raw.get("ohlc_bars"),
                            "vwap": raw.get("vwap"),
                            "rsi": raw.get("rsi"),
                            "ema": raw.get("ema"),
                            "atr": raw.get("atr"),
                        }
                    ],
                    now_epoch=float(snapshot.ts_epoch),
                    warmup_min_bars=max(0, int(min_bars)),
                    max_indicator_age_sec=float(indicator_stale_sec),
                    source="decision_dag_indicator_readiness_v1",
                )
                decision = indicator_report.get(snapshot.symbol)
                if decision is None or not decision.ready:
                    reasons.append(REASON_INDICATORS_MISSING)
                if decision is not None:
                    indicator_readiness_ready = bool(decision.ready)
                    indicator_missing_inputs = list(decision.indicator_missing_inputs or ())
                    indicator_readiness_blockers = list(decision.blockers or ())
            except Exception:
                reasons.append(REASON_INDICATORS_MISSING)

    # Backward-compat coarse flags (fail-closed).
    if indicator_readiness_ready is not True:
        if not snapshot.indicators_ok:
            if REASON_INDICATORS_MISSING not in reasons:
                reasons.append(REASON_INDICATORS_MISSING)
        elif snapshot.indicators_age_sec >= never_computed_age:
            if REASON_INDICATORS_MISSING not in reasons:
                reasons.append(REASON_INDICATORS_MISSING)
    if snapshot.indicators_age_sec > indicator_stale_sec:
        reasons.append(REASON_WARMUP_INCOMPLETE)

    reasons_tuple = _clean_reasons(reasons)
    facts = {
        "system_state": system_state,
        "warmup_reasons": list(warmup_reasons),
        "min_bars": min_bars,
        "ohlc_bars_count": snapshot.ohlc_bars_count,
        "indicator_last_update_epoch": snapshot.indicator_last_update_epoch,
        "indicator_stale_sec": indicator_stale_sec,
        "never_computed_age": never_computed_age,
        "indicators_age_sec": snapshot.indicators_age_sec,
        "indicators_ok": snapshot.indicators_ok,
        "indicator_readiness_ready": indicator_readiness_ready,
        "indicator_missing_inputs": indicator_missing_inputs,
        "indicator_readiness_blockers": indicator_readiness_blockers,
    }
    hist_fetch_failed_only = bool(warmup_reasons) and all(
        str(reason).upper() == "HIST_FETCH_FAILED" for reason in warmup_reasons
    )
    if snapshot.allow_stale_quotes and hist_fetch_failed_only:
        facts["warmup_degraded"] = True
        facts["warmup_degraded_reason"] = "HIST_FETCH_FAILED"
        return NodeResult(ok=True, reasons=(), facts=facts)
    return NodeResult(ok=not bool(reasons_tuple), reasons=reasons_tuple, facts=facts)


def _node_quote_ok(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    symbol = snapshot.symbol
    mode = snapshot.mode
    is_index = _is_index_symbol(symbol, snapshot.instrument)

    if is_index:
        resolved = _resolve_index_quote_from_snapshot(snapshot)
        facts = {
            "quote_ok": bool(resolved.get("quote_ok")),
            "quote_source": resolved.get("quote_source"),
            "bid": resolved.get("bid"),
            "ask": resolved.get("ask"),
            "mid": resolved.get("mid"),
            "mode": mode,
            "instrument": snapshot.instrument,
            "offhours_mode": bool(snapshot.offhours_mode),
        }
        if snapshot.allow_stale_quotes:
            return NodeResult(ok=True, value=resolved, facts=facts)
        if bool(resolved.get("quote_ok")):
            return NodeResult(ok=True, value=resolved, facts=facts)
        return NodeResult(ok=False, reasons=(REASON_INDEX_BIDASK_MISSING,), facts=facts)

    bid = snapshot.bid
    ask = snapshot.ask
    valid_depth_bidask = bool(
        bid is not None
        and ask is not None
        and bid > 0
        and ask > 0
        and ask >= bid
    )
    if snapshot.quote_ok_input is not None:
        if snapshot.mode == "LIVE":
            quote_ok = bool(snapshot.quote_ok_input and valid_depth_bidask)
        else:
            quote_ok = bool(snapshot.quote_ok_input)
    else:
        quote_ok = valid_depth_bidask
    quote_source = snapshot.quote_source_input or ("depth" if valid_depth_bidask else "missing_depth")
    facts = {
        "quote_ok": bool(quote_ok),
        "quote_source": quote_source,
        "bid": bid,
        "ask": ask,
        "mid": ((bid + ask) / 2.0 if valid_depth_bidask else None),
        "mode": mode,
        "instrument": snapshot.instrument,
    }
    if quote_ok:
        return NodeResult(ok=True, facts=facts)
    if (
        snapshot.allow_stale_quotes
        and bool(getattr(cfg, "DECISION_DAG_ALLOW_NON_LIVE_OPTION_QUOTE_MISSING", True))
        and snapshot.ltp is not None
        and float(snapshot.ltp) > 0
    ):
        facts["quote_degraded"] = True
        facts["quote_degraded_reason"] = "non_live_missing_option_quote"
        facts["quote_reference_ltp"] = float(snapshot.ltp)
        return NodeResult(ok=True, facts=facts)
    return NodeResult(ok=False, reasons=(REASON_QUOTE_INVALID,), facts=facts)


def _node_regime_ok(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    reasons: list[str] = []
    unstable_reasons = list(snapshot.unstable_reasons)
    primary_regime = str(snapshot.primary_regime or "UNKNOWN").upper()
    if primary_regime in {"", "NONE", "UNKNOWN", "NULL"}:
        reasons.append(REASON_REGIME_UNKNOWN)

    live_mode = snapshot.mode == "LIVE"
    regime_prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
    regime_entropy_max = float(getattr(cfg, "REGIME_ENTROPY_MAX", 1.3))
    if (not live_mode) and bool(getattr(cfg, "PAPER_RELAX_GATES", True)):
        regime_prob_min = float(getattr(cfg, "PAPER_REGIME_PROB_MIN", regime_prob_min))
        regime_entropy_max = float(getattr(cfg, "PAPER_REGIME_ENTROPY_MAX", regime_entropy_max))

    if snapshot.regime_prob_max is not None and float(snapshot.regime_prob_max) < regime_prob_min:
        unstable_reasons.append("prob_too_low")
    if snapshot.regime_entropy is not None and float(snapshot.regime_entropy) > regime_entropy_max:
        unstable_reasons.append("entropy_too_high")

    # Strongly deterministic regime with clean indicators should not be marked unstable.
    if (
        snapshot.regime_prob_max is not None
        and snapshot.regime_entropy is not None
        and float(snapshot.regime_prob_max) >= 0.99
        and float(snapshot.regime_entropy) <= 0.01
        and snapshot.indicators_ok
    ):
        unstable_reasons = [r for r in unstable_reasons if r not in {"prob_too_low", "entropy_too_high"}]

    unstable_reasons = list(_clean_reasons(unstable_reasons))
    debounce_default = int(
        getattr(
            cfg,
            "PAPER_REGIME_UNSTABLE_CONSECUTIVE_BLOCK",
            getattr(cfg, "REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 1),
        )
        if snapshot.allow_stale_quotes
        else getattr(
            cfg,
            "LIVE_REGIME_UNSTABLE_CONSECUTIVE_BLOCK",
            getattr(cfg, "REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 1),
        )
    )
    debounce_block_after = max(1, debounce_default)
    debounce_streak = 0
    try:
        debounce_block_after = max(
            1,
            int(snapshot.raw_data.get("regime_unstable_block_after") or debounce_default),
        )
    except Exception:
        debounce_block_after = max(1, debounce_default)
    try:
        debounce_streak = max(
            0,
            int(snapshot.raw_data.get("regime_unstable_streak") or 0),
        )
    except Exception:
        debounce_streak = 0
    debounced_unstable = bool(
        unstable_reasons
        and debounce_block_after > 1
        and debounce_streak > 0
        and debounce_streak < debounce_block_after
    )
    if unstable_reasons and (not debounced_unstable):
        reasons.append(REASON_REGIME_UNSTABLE)

    reasons_tuple = _clean_reasons(reasons)
    warmup_reasons = _clean_reasons(
        snapshot.raw_data.get("warmup_reasons")
        if isinstance(snapshot.raw_data.get("warmup_reasons"), Sequence)
        else ()
    )
    hist_fetch_failed_only = bool(warmup_reasons) and all(
        str(reason).upper() == "HIST_FETCH_FAILED" for reason in warmup_reasons
    )
    facts = {
        "primary_regime": primary_regime,
        "regime_prob_max": snapshot.regime_prob_max,
        "regime_entropy": snapshot.regime_entropy,
        "unstable_reasons": unstable_reasons,
        "regime_prob_min": regime_prob_min,
        "regime_entropy_max": regime_entropy_max,
        "regime_unstable_streak": debounce_streak,
        "regime_unstable_block_after": debounce_block_after,
        "regime_unstable_debounced": debounced_unstable,
    }
    if snapshot.allow_stale_quotes and hist_fetch_failed_only:
        facts["regime_degraded"] = True
        facts["regime_degraded_reason"] = "HIST_FETCH_FAILED"
        return NodeResult(ok=True, reasons=(), facts=facts)
    return NodeResult(ok=not bool(reasons_tuple), reasons=reasons_tuple, facts=facts)


def _node_risk_ok(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    if snapshot.risk_ok:
        return NodeResult(ok=True, facts={"risk_ok": True, "risk_reasons": list(snapshot.risk_reasons)})
    reasons = list(snapshot.risk_reasons) or [REASON_RISK_LIMIT]
    if REASON_RISK_LIMIT not in reasons:
        reasons.append(REASON_RISK_LIMIT)
    return NodeResult(
        ok=False,
        reasons=_clean_reasons(reasons),
        facts={"risk_ok": False, "risk_reasons": list(snapshot.risk_reasons)},
    )


def _node_governance_locks_ok(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    reasons: list[str] = []
    if snapshot.governance_lock_active:
        reasons.append(REASON_LOCK_ACTIVE)
    if not snapshot.broker_enabled:
        reasons.append(REASON_BROKER_DISABLED)
    reasons_tuple = _clean_reasons(reasons)
    return NodeResult(
        ok=not bool(reasons_tuple),
        reasons=reasons_tuple,
        facts={
            "governance_lock_active": snapshot.governance_lock_active,
            "broker_enabled": snapshot.broker_enabled,
        },
    )


def _pick_actionable_candidate(candidates: Sequence[StrategyCandidate]) -> StrategyCandidate | None:
    for candidate in candidates:
        if candidate.family or candidate.allowed:
            return candidate
    return None


def _candidate_summary(candidate: StrategyCandidate | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    summary = dict(candidate.candidate_summary or {})
    summary.setdefault("family", candidate.family)
    summary.setdefault("allowed", bool(candidate.allowed))
    summary.setdefault("reasons", list(candidate.reasons))
    return summary


def _collect_failed_deps(deps: Mapping[str, NodeResult], dep_order: Sequence[str]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    reasons: list[str] = []
    for dep_name in dep_order:
        dep_result = deps.get(dep_name)
        if dep_result is None or dep_result.ok:
            continue
        failures.append(dep_name)
        for reason in dep_result.reasons:
            if reason not in reasons:
                reasons.append(reason)
    return failures, reasons


def _derive_qual_fail_codes(candidate: StrategyCandidate | None, *, manual_review: bool) -> list[str]:
    """
    Produce stable, machine-friendly codes to explain NO_STRATEGY_QUALIFIED outcomes.
    We do not try to "interpret" all possible reasons; we bucket the common ones
    and also include normalized raw reasons.
    """
    codes: list[str] = []
    if manual_review:
        codes.append("manual_review_required")
    if candidate is None:
        codes.append("no_candidates")
        return codes

    if not candidate.allowed:
        codes.append("candidate_not_allowed")
    if not candidate.family:
        codes.append("candidate_family_missing")

    # Normalize raw reasons into stable tokens
    for r in candidate.reasons or ():
        s = str(r or "").strip().lower()
        if not s:
            continue
        # small canonical buckets (extend safely over time)
        if "liquid" in s or "liquidity" in s:
            code = "liquidity"
        elif "spread" in s:
            code = "spread"
        elif "iv" in s or "implied" in s:
            code = "iv"
        elif "vwap" in s:
            code = "vwap"
        elif "trend" in s:
            code = "trend"
        elif "time" in s or "window" in s:
            code = "time_window"
        elif "warmup" in s or "hist" in s:
            code = "warmup"
        elif "risk" in s:
            code = "risk"
        elif "manual" in s or "review" in s:
            code = "manual_review"
        else:
            code = "reason:" + s.replace(" ", "_")[:64]
        if code not in codes:
            codes.append(code)

    return codes


def _node_strategy_select(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    precondition_nodes = (
        NODE_N1_MARKET_OPEN,
        NODE_N2_FEED_FRESH,
        NODE_N3_WARMUP_DONE,
        NODE_N4_QUOTE_OK,
        NODE_N5_REGIME_OK,
        NODE_N6_RISK_OK,
        NODE_N7_GOVERNANCE_LOCKS_OK,
    )
    cached_results = ctx.get("cache") if isinstance(ctx, Mapping) else None
    if not isinstance(cached_results, Mapping):
        cached_results = deps
    precondition_failures, precondition_reasons = _collect_failed_deps(cached_results, precondition_nodes)

    candidates = tuple(ctx.get("strategy_candidates") or ())
    candidate = _pick_actionable_candidate(candidates)
    candidate_summary = _candidate_summary(candidate)

    # NEW: full candidates telemetry (bounded + deterministic)
    all_candidates_rows: list[dict[str, Any]] = []
    for c in candidates:
        try:
            all_candidates_rows.append(
                {
                    "family": c.family,
                    "allowed": bool(c.allowed),
                    "manual_review_required": bool(c.manual_review_required),
                    "reasons": list(c.reasons),
                    "candidate_summary": dict(c.candidate_summary or {}),
                }
            )
        except Exception:
            continue

    facts: dict[str, Any] = {
        "strategy_skipped_due_to_preconditions": bool(precondition_failures),
        "precondition_failures": list(precondition_failures),
        "precondition_reasons": list(precondition_reasons),
        "candidate_summary": candidate_summary if candidate_summary else {},
        "predicate_node": NODE_N8_STRATEGY_SELECT,
        "trade_builder_reached": False,
        "candidate_family_considered": (candidate.family if candidate else None),
        "no_candidate_constructed": candidate is None,
        "picked_candidate": {
            "family": (candidate.family if candidate else None),
            "allowed": (bool(candidate.allowed) if candidate else False),
            "manual_review_required": (bool(candidate.manual_review_required) if candidate else False),
            "reasons": (list(candidate.reasons) if candidate else []),
        },
        "all_candidates": all_candidates_rows,
    }

    if precondition_failures:
        # Strategy selection is intentionally skipped if preconditions fail.
        # Still emit candidate telemetry for observability.
        return NodeResult(ok=True, reasons=(), facts=facts)

    facts["trade_builder_reached"] = True
    if candidate is None:
        facts["strategy_reasons"] = []
        facts["qual_fail_codes"] = _derive_qual_fail_codes(None, manual_review=False)
        facts["qual_fail_reasons_raw"] = []
        facts["no_candidate_constructed"] = True
        facts["candidate_family_considered"] = None
        return NodeResult(ok=False, reasons=(REASON_NO_STRATEGY_QUALIFIED,), facts=facts)

    facts["strategy_reasons"] = list(candidate.reasons)

    manual_review = bool(snapshot.manual_review_required or candidate.manual_review_required)
    if manual_review:
        facts["qual_fail_codes"] = _derive_qual_fail_codes(candidate, manual_review=True)
        facts["qual_fail_reasons_raw"] = list(candidate.reasons)
        return NodeResult(ok=False, reasons=(REASON_MANUAL_REVIEW_REQUIRED,), facts=facts)

    if not candidate.allowed or not candidate.family:
        has_manual_reason = any("manual_review" in reason.lower() for reason in candidate.reasons)
        reason = REASON_MANUAL_REVIEW_REQUIRED if has_manual_reason else REASON_NO_STRATEGY_QUALIFIED

        if reason == REASON_NO_STRATEGY_QUALIFIED:
            facts["qual_fail_codes"] = _derive_qual_fail_codes(candidate, manual_review=False)
            facts["qual_fail_reasons_raw"] = list(candidate.reasons)
        else:
            facts["qual_fail_codes"] = _derive_qual_fail_codes(candidate, manual_review=True)
            facts["qual_fail_reasons_raw"] = list(candidate.reasons)

        return NodeResult(ok=False, reasons=(reason,), facts=facts)

    return NodeResult(
        ok=True,
        value={"selected_strategy": candidate.family, "risk_params": dict(candidate.risk_params)},
        reasons=(),
        facts=facts,
    )


def _node_strategy_eligible(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    n8 = deps.get(NODE_N8_STRATEGY_SELECT, NodeResult(ok=False, reasons=(REASON_NO_STRATEGY_QUALIFIED,), facts={}))
    facts = {"from_node": NODE_N8_STRATEGY_SELECT, "candidate_summary": (n8.facts or {}).get("candidate_summary", {})}
    # NEW: pass through telemetry if present
    for k in (
        "qual_fail_codes",
        "qual_fail_reasons_raw",
        "picked_candidate",
        "all_candidates",
        "precondition_failures",
        "precondition_reasons",
        "predicate_node",
        "trade_builder_reached",
        "candidate_family_considered",
        "no_candidate_constructed",
        "strategy_reasons",
    ):
        if k in (n8.facts or {}):
            facts[k] = (n8.facts or {}).get(k)
    if n8.ok:
        return NodeResult(ok=True, value=n8.value, facts=facts)
    return NodeResult(ok=False, reasons=n8.reasons, facts=facts)


def _node_decision_ready(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    n9 = deps.get(NODE_N9_STRATEGY_ELIGIBLE, NodeResult(ok=False, reasons=(REASON_NO_STRATEGY_QUALIFIED,), facts={}))
    facts = {"from_node": NODE_N9_STRATEGY_ELIGIBLE}
    # NEW: pass through telemetry if present
    for k in (
        "qual_fail_codes",
        "qual_fail_reasons_raw",
        "picked_candidate",
        "all_candidates",
        "precondition_failures",
        "precondition_reasons",
        "predicate_node",
        "trade_builder_reached",
        "candidate_family_considered",
        "no_candidate_constructed",
        "strategy_reasons",
    ):
        if k in (n9.facts or {}):
            facts[k] = (n9.facts or {}).get(k)
    if n9.ok:
        return NodeResult(ok=True, value=n9.value, facts=facts)
    return NodeResult(ok=False, reasons=n9.reasons, facts=facts)


def _node_final_decision(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    explain_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    first_failing_node: str | None = None
    cached_results = ctx.get("cache") if isinstance(ctx, Mapping) else None
    if not isinstance(cached_results, Mapping):
        cached_results = {}

    # NEW: capture strategy telemetry from N8/N9/N10 chain if present
    strategy_telemetry: dict[str, Any] = {}

    for node_name in _LINEAR_NODE_ORDER[:-1]:
        result = cached_results.get(node_name)
        if result is None:
            continue
        row = {
            "node": node_name,
            "ok": bool(result.ok),
            "reasons": list(result.reasons),
            "facts": dict(result.facts or {}),
        }
        explain_rows.append(row)
        if (not result.ok) and first_failing_node is None:
            first_failing_node = node_name
        if not result.ok:
            for reason in result.reasons:
                if reason not in blockers:
                    blockers.append(reason)

        if node_name in {NODE_N8_STRATEGY_SELECT, NODE_N9_STRATEGY_ELIGIBLE, NODE_N10_DECISION_READY}:
            f = dict(result.facts or {})
            # Only keep a safe subset (bounded)
            for k in (
                "qual_fail_codes",
                "qual_fail_reasons_raw",
                "picked_candidate",
                "all_candidates",
                "precondition_failures",
                "precondition_reasons",
                "strategy_reasons",
                "predicate_node",
                "trade_builder_reached",
                "candidate_family_considered",
                "no_candidate_constructed",
                "strategy_skipped_due_to_preconditions",
            ):
                if k in f:
                    strategy_telemetry[k] = f.get(k)

    decision_ready = cached_results.get(
        NODE_N10_DECISION_READY,
        NodeResult(ok=False, reasons=(REASON_NO_STRATEGY_QUALIFIED,), facts={}),
    )
    selected_strategy = None
    risk_params: dict[str, Any] = {}
    if isinstance(decision_ready.value, Mapping):
        selected_strategy = str(decision_ready.value.get("selected_strategy") or "").upper() or None
        risk_params_raw = decision_ready.value.get("risk_params")
        if isinstance(risk_params_raw, Mapping):
            risk_params = dict(risk_params_raw)

    allowed = (not blockers) and bool(selected_strategy)
    if (not allowed) and (not blockers):
        blockers = [REASON_NO_STRATEGY_QUALIFIED]
        first_failing_node = NODE_N8_STRATEGY_SELECT

    stage = first_failing_node or NODE_N11_FINAL_DECISION
    decision = DecisionReport(
        symbol=snapshot.symbol,
        ts_epoch=float(snapshot.ts_epoch),
        allowed=bool(allowed),
        blockers=tuple(blockers),
        primary_blocker=(blockers[0] if blockers else None),
        stage=stage,
        selected_strategy=selected_strategy,
        risk_params=risk_params,
        facts={"strategy_telemetry": strategy_telemetry} if strategy_telemetry else {},
        explain=tuple(explain_rows),
    )
    final_row = {
        "node": NODE_N11_FINAL_DECISION,
        "ok": bool(allowed),
        "reasons": list(blockers),
        "facts": {"stage": stage},
    }
    decision.explain = tuple(list(decision.explain) + [final_row])
    return NodeResult(
        ok=bool(allowed),
        value=decision,
        reasons=tuple(blockers),
        facts={"stage": stage, "strategy_telemetry": strategy_telemetry} if strategy_telemetry else {"stage": stage},
    )


class DecisionDAGEvaluator:
    def __init__(
        self,
        *,
        strategy_candidates: Sequence[StrategyCandidate | Mapping[str, Any]] | None = None,
        strategy_evaluator: Callable[[MarketSnapshot], Sequence[StrategyCandidate | Mapping[str, Any]]] | None = None,
    ) -> None:
        self._precomputed_candidates = _normalize_candidates(strategy_candidates)
        self._strategy_evaluator = strategy_evaluator
        self._nodes: dict[str, NodeSpec] = {
            NODE_N1_MARKET_OPEN: NodeSpec(NODE_N1_MARKET_OPEN, (), _node_market_open),
            NODE_N2_FEED_FRESH: NodeSpec(NODE_N2_FEED_FRESH, (NODE_N1_MARKET_OPEN,), _node_feed_fresh),
            NODE_N3_WARMUP_DONE: NodeSpec(NODE_N3_WARMUP_DONE, (NODE_N2_FEED_FRESH,), _node_warmup_done),
            NODE_N4_QUOTE_OK: NodeSpec(NODE_N4_QUOTE_OK, (NODE_N3_WARMUP_DONE,), _node_quote_ok),
            NODE_N5_REGIME_OK: NodeSpec(NODE_N5_REGIME_OK, (NODE_N4_QUOTE_OK,), _node_regime_ok),
            NODE_N6_RISK_OK: NodeSpec(NODE_N6_RISK_OK, (NODE_N5_REGIME_OK,), _node_risk_ok),
            NODE_N7_GOVERNANCE_LOCKS_OK: NodeSpec(NODE_N7_GOVERNANCE_LOCKS_OK, (NODE_N6_RISK_OK,), _node_governance_locks_ok),
            NODE_N8_STRATEGY_SELECT: NodeSpec(NODE_N8_STRATEGY_SELECT, (NODE_N7_GOVERNANCE_LOCKS_OK,), _node_strategy_select),
            NODE_N9_STRATEGY_ELIGIBLE: NodeSpec(NODE_N9_STRATEGY_ELIGIBLE, (NODE_N8_STRATEGY_SELECT,), _node_strategy_eligible),
            NODE_N10_DECISION_READY: NodeSpec(NODE_N10_DECISION_READY, (NODE_N9_STRATEGY_ELIGIBLE,), _node_decision_ready),
            NODE_N11_FINAL_DECISION: NodeSpec(NODE_N11_FINAL_DECISION, (NODE_N10_DECISION_READY,), _node_final_decision),
        }

    def _prepare_candidates(self, snapshot: MarketSnapshot) -> tuple[StrategyCandidate, ...]:
        if self._precomputed_candidates:
            return self._precomputed_candidates
        if self._strategy_evaluator is None:
            return ()
        raw = self._strategy_evaluator(snapshot)
        return _normalize_candidates(raw)

    def _eval_node(self, node_name: str, snapshot: MarketSnapshot, ctx: dict[str, Any]) -> NodeResult:
        cache: dict[str, NodeResult] = ctx["cache"]
        if node_name in cache:
            return cache[node_name]

        node = self._nodes[node_name]
        dep_results = {
            dep_name: self._eval_node(dep_name, snapshot, ctx)
            for dep_name in node.deps
        }
        ctx["node_call_counts"][node_name] = int(ctx["node_call_counts"].get(node_name, 0)) + 1
        result = node.fn(snapshot, ctx, dep_results)
        cache[node_name] = result
        return result

    def evaluate(self, snapshot: MarketSnapshot | Mapping[str, Any]) -> DecisionReport:
        snap = build_market_snapshot(snapshot)
        ctx: dict[str, Any] = {
            "cache": {},
            "node_call_counts": {},
            "strategy_candidates": self._prepare_candidates(snap),
        }
        final_result = self._eval_node(NODE_N11_FINAL_DECISION, snap, ctx)
        decision = final_result.value
        if not isinstance(decision, DecisionReport):
            blockers = tuple(final_result.reasons or ())
            stage = str((final_result.facts or {}).get("stage") or NODE_N11_FINAL_DECISION)
            decision = DecisionReport(
                symbol=snap.symbol,
                ts_epoch=float(snap.ts_epoch),
                allowed=False,
                blockers=blockers,
                primary_blocker=(blockers[0] if blockers else None),
                stage=stage,
                selected_strategy=None,
                risk_params={},
                facts={},
                explain=(),
            )
        decision.facts = {
            **dict(decision.facts or {}),
            "feed_health": dict(snap.feed_health or {}),
            "node_call_counts": dict(ctx.get("node_call_counts") or {}),
            "snapshot_mode": snap.mode,
        }
        return decision


def evaluate_decision(
    market_data: Mapping[str, Any] | MarketSnapshot,
    *,
    strategy_eval: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
    strategy_evaluator: Callable[[MarketSnapshot], Sequence[Mapping[str, Any]]] | None = None,
    strategy_candidates: Sequence[StrategyCandidate | Mapping[str, Any]] | None = None,
    now_epoch: float | None = None,
) -> DecisionReport:
    snapshot = build_market_snapshot(market_data, now_epoch=now_epoch)

    pure_strategy_evaluator = strategy_evaluator
    if pure_strategy_evaluator is None and strategy_eval is not None:
        # Backward-compatible shim: strategy_eval is used only outside DAG execution.
        def _wrapped(snap: MarketSnapshot):
            return strategy_eval(dict(snap.raw_data))

        pure_strategy_evaluator = _wrapped

    evaluator = DecisionDAGEvaluator(
        strategy_candidates=strategy_candidates,
        strategy_evaluator=pure_strategy_evaluator,
    )
    return evaluator.evaluate(snapshot)


__all__ = [
    "Decision",
    "DecisionReport",
    "DecisionDAGEvaluator",
    "MarketSnapshot",
    "NodeResult",
    "StrategyCandidate",
    "NODE_N1_MARKET_OPEN",
    "NODE_N2_FEED_FRESH",
    "NODE_N3_WARMUP_DONE",
    "NODE_N4_QUOTE_OK",
    "NODE_N5_REGIME_OK",
    "NODE_N6_RISK_OK",
    "NODE_N7_GOVERNANCE_LOCKS_OK",
    "NODE_N8_STRATEGY_SELECT",
    "NODE_N9_STRATEGY_ELIGIBLE",
    "NODE_N10_DECISION_READY",
    "NODE_N11_FINAL_DECISION",
    "NODE_N9_FINAL_DECISION",
    "_synth_index_bid_ask",
    "build_market_snapshot",
    "evaluate_decision",
]
