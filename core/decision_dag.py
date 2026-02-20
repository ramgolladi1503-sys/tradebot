from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from config import config as cfg
from core.market_data import resolve_index_quote
from core.time_utils import now_utc_epoch

ReasonCode = str

REASON_MARKET_CLOSED = "MARKET_CLOSED"
REASON_FEED_STALE = "FEED_STALE"
REASON_WARMUP_INCOMPLETE = "WARMUP_INCOMPLETE"
REASON_INDICATORS_MISSING = "INDICATORS_MISSING"
REASON_QUOTE_INVALID = "QUOTE_INVALID"
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
    return str(raw_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()


def _is_index_symbol(symbol: str, instrument: str | None = None) -> bool:
    inst = str(instrument or "").upper()
    if inst == "INDEX":
        return True
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


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    ts_epoch: float
    mode: str
    market_open: bool
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
class Decision:
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
    mode = _normalized_mode(data.get("execution_mode"))
    market_open = _to_bool(data.get("market_open"), default=False)

    ltp = _to_float(data.get("ltp"))
    ltp_ts_epoch = _to_float(data.get("ltp_ts_epoch"))
    if ltp_ts_epoch is None:
        ltp_ts_epoch = _to_float(data.get("tick_last_epoch"))
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
            indicators_age_sec = max(0.0, float(now_value) - float(indicator_last_update_epoch))
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

    instrument = str(data.get("instrument") or data.get("instrument_type") or "").upper() or "OPT"
    quote_ok_input: bool | None
    if "quote_ok" in data:
        quote_ok_input = _to_bool(data.get("quote_ok"), default=False)
    else:
        quote_ok_input = None
    quote_source_input = str(data.get("quote_source") or "").strip() or None

    max_ltp_age = _to_float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", None))
    if max_ltp_age is None:
        max_ltp_age = _to_float(getattr(cfg, "MAX_LTP_AGE_SEC", 2.5))
    if max_ltp_age is None:
        max_ltp_age = 2.5
    if ltp_ts_epoch is None:
        ltp_age_sec = float("inf")
    else:
        ltp_age_sec = max(0.0, float(now_value) - float(ltp_ts_epoch))
    if depth_ts_epoch is None:
        depth_age_sec = depth_age_from_row
    else:
        depth_age_sec = max(0.0, float(now_value) - float(depth_ts_epoch))
    feed_health = {
        "ltp_age_sec": ltp_age_sec,
        "depth_age_sec": depth_age_sec,
        "is_fresh": bool(ltp is not None and ltp > 0 and ltp_age_sec <= float(max_ltp_age)),
        "source": ltp_source or "unknown",
        "ts_epoch": float(now_value),
    }

    return MarketSnapshot(
        symbol=symbol,
        ts_epoch=float(now_value),
        mode=mode,
        market_open=market_open,
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
    if snapshot.market_open:
        return NodeResult(ok=True, facts={"market_open": True})
    return NodeResult(ok=False, reasons=(REASON_MARKET_CLOSED,), facts={"market_open": False})


def _node_feed_fresh(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    feed = dict(snapshot.feed_health or {})
    if bool(feed.get("is_fresh")):
        return NodeResult(ok=True, facts=feed)
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

    if system_state == "WARMUP":
        reasons.append(REASON_WARMUP_INCOMPLETE)
    if (system_state == "WARMUP") or has_explicit_bar_contract:
        if snapshot.ohlc_bars_count < min_bars:
            reasons.append(REASON_WARMUP_INCOMPLETE)
    if not snapshot.indicators_ok:
        reasons.append(REASON_INDICATORS_MISSING)
    elif snapshot.indicators_age_sec >= never_computed_age:
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
    }
    return NodeResult(ok=not bool(reasons_tuple), reasons=reasons_tuple, facts=facts)


def _node_quote_ok(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    symbol = snapshot.symbol
    mode = snapshot.mode
    is_index = _is_index_symbol(symbol, snapshot.instrument)

    if is_index:
        resolved = resolve_index_quote(symbol=symbol, mode=mode, ltp=snapshot.ltp, depth=snapshot.depth)
        facts = {
            "quote_source": resolved.get("quote_source"),
            "bid": resolved.get("bid"),
            "ask": resolved.get("ask"),
            "mid": resolved.get("mid"),
            "mode": mode,
            "instrument": snapshot.instrument,
        }
        if bool(resolved.get("quote_ok")):
            return NodeResult(ok=True, value=resolved, facts=facts)
        return NodeResult(ok=False, reasons=(REASON_QUOTE_INVALID,), facts=facts)

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
        quote_ok = bool(snapshot.quote_ok_input and valid_depth_bidask)
    else:
        quote_ok = valid_depth_bidask
    quote_source = snapshot.quote_source_input or ("depth" if valid_depth_bidask else "missing_depth")
    facts = {
        "quote_source": quote_source,
        "bid": bid,
        "ask": ask,
        "mid": ((bid + ask) / 2.0 if valid_depth_bidask else None),
        "mode": mode,
        "instrument": snapshot.instrument,
    }
    if quote_ok:
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
    if unstable_reasons:
        reasons.append(REASON_REGIME_UNSTABLE)

    reasons_tuple = _clean_reasons(reasons)
    facts = {
        "primary_regime": primary_regime,
        "regime_prob_max": snapshot.regime_prob_max,
        "regime_entropy": snapshot.regime_entropy,
        "unstable_reasons": unstable_reasons,
        "regime_prob_min": regime_prob_min,
        "regime_entropy_max": regime_entropy_max,
    }
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
    facts: dict[str, Any] = {
        "strategy_skipped_due_to_preconditions": bool(precondition_failures),
        "precondition_failures": list(precondition_failures),
        "precondition_reasons": list(precondition_reasons),
        "candidate_summary": candidate_summary if candidate_summary else {},
    }

    if precondition_failures:
        return NodeResult(ok=True, reasons=(), facts=facts)

    if candidate is None:
        facts["strategy_reasons"] = []
        return NodeResult(ok=False, reasons=(REASON_NO_STRATEGY_QUALIFIED,), facts=facts)

    facts["strategy_reasons"] = list(candidate.reasons)
    if snapshot.manual_review_required or candidate.manual_review_required:
        return NodeResult(ok=False, reasons=(REASON_MANUAL_REVIEW_REQUIRED,), facts=facts)

    if not candidate.allowed or not candidate.family:
        has_manual_reason = any("manual_review" in reason.lower() for reason in candidate.reasons)
        reason = REASON_MANUAL_REVIEW_REQUIRED if has_manual_reason else REASON_NO_STRATEGY_QUALIFIED
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
    if n8.ok:
        return NodeResult(ok=True, value=n8.value, facts=facts)
    return NodeResult(ok=False, reasons=n8.reasons, facts=facts)


def _node_decision_ready(snapshot: MarketSnapshot, ctx: Mapping[str, Any], deps: Mapping[str, NodeResult]) -> NodeResult:
    n9 = deps.get(NODE_N9_STRATEGY_ELIGIBLE, NodeResult(ok=False, reasons=(REASON_NO_STRATEGY_QUALIFIED,), facts={}))
    facts = {"from_node": NODE_N9_STRATEGY_ELIGIBLE}
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
    decision = Decision(
        symbol=snapshot.symbol,
        ts_epoch=float(snapshot.ts_epoch),
        allowed=bool(allowed),
        blockers=tuple(blockers),
        primary_blocker=(blockers[0] if blockers else None),
        stage=stage,
        selected_strategy=selected_strategy,
        risk_params=risk_params,
        facts={},
        explain=tuple(explain_rows),
    )
    final_row = {
        "node": NODE_N11_FINAL_DECISION,
        "ok": bool(allowed),
        "reasons": list(blockers),
        "facts": {"stage": stage},
    }
    decision.explain = tuple(list(decision.explain) + [final_row])
    return NodeResult(ok=bool(allowed), value=decision, reasons=tuple(blockers), facts={"stage": stage})


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

    def evaluate(self, snapshot: MarketSnapshot | Mapping[str, Any]) -> Decision:
        snap = build_market_snapshot(snapshot)
        ctx: dict[str, Any] = {
            "cache": {},
            "node_call_counts": {},
            "strategy_candidates": self._prepare_candidates(snap),
        }
        final_result = self._eval_node(NODE_N11_FINAL_DECISION, snap, ctx)
        decision = final_result.value
        if not isinstance(decision, Decision):
            blockers = tuple(final_result.reasons or ())
            stage = str((final_result.facts or {}).get("stage") or NODE_N11_FINAL_DECISION)
            decision = Decision(
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
) -> Decision:
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
