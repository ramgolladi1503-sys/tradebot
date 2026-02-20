from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from config import config as cfg
from core import risk_halt
from core.time_utils import is_market_open_ist, now_utc_epoch

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX"}

NODE_N1_MARKET_OPEN = "N1_MARKET_OPEN"
NODE_N2_FEED_FRESH = "N2_FEED_FRESH"
NODE_N3_WARMUP_DONE = "N3_WARMUP_DONE"
NODE_N4_QUOTE_OK = "N4_QUOTE_OK"
NODE_N5_REGIME_OK = "N5_REGIME_OK"
NODE_N6_RISK_OK = "N6_RISK_OK"
NODE_N7_GOVERNANCE_LOCKS_OK = "N7_GOVERNANCE_LOCKS_OK"
NODE_N8_STRATEGY_SELECT = "N8_STRATEGY_SELECT"
NODE_N9_FINAL_DECISION = "N9_FINAL_DECISION"


@dataclass(frozen=True)
class FeedHealthSnapshot:
    ltp_age_sec: Optional[float]
    depth_age_sec: Optional[float]
    is_fresh: bool
    ts_epoch: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ltp_age_sec": self.ltp_age_sec,
            "depth_age_sec": self.depth_age_sec,
            "is_fresh": self.is_fresh,
            "ts_epoch": self.ts_epoch,
            "source": self.source,
        }


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    instrument: str
    execution_mode: str
    ts_epoch: float
    market_open: bool
    ltp: Optional[float]
    ltp_source: str
    ltp_ts_epoch: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    quote_ok: bool
    quote_source: str
    indicators_ok: bool
    indicators_age_sec: float
    indicator_stale_sec: float
    system_state: str
    warmup_reasons: Tuple[str, ...]
    primary_regime: str
    regime_probs_max: Optional[float]
    regime_entropy: Optional[float]
    unstable_reasons: Tuple[str, ...]
    risk_halted: bool
    feed_health: FeedHealthSnapshot
    raw_data: Mapping[str, Any]


@dataclass(frozen=True)
class NodeResult:
    ok: bool
    value: Any = None
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    facts: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self, node: str) -> Dict[str, Any]:
        return {
            "node": node,
            "ok": self.ok,
            "value": self.value,
            "reasons": list(self.reasons),
            "facts": dict(self.facts or {}),
        }


@dataclass(frozen=True)
class Decision:
    symbol: str
    ts_epoch: float
    allowed: bool
    primary_blocker: Optional[str]
    blockers: Tuple[str, ...]
    stage: str
    selected_strategy: Optional[str]
    risk_params: Mapping[str, Any]
    facts: Mapping[str, Any]
    explain: Tuple[Dict[str, Any], ...]


@dataclass(frozen=True)
class StrategyCandidate:
    family: Optional[str]
    allowed: bool
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    candidate_summary: Mapping[str, Any] = field(default_factory=dict)

    def to_summary(self) -> Dict[str, Any]:
        summary = dict(self.candidate_summary or {})
        summary.setdefault("family", self.family)
        summary.setdefault("allowed", bool(self.allowed))
        summary.setdefault("reasons", list(self.reasons))
        return summary

    @property
    def actionable(self) -> bool:
        return bool(self.allowed or self.family)


@dataclass(frozen=True)
class _NodeDef:
    name: str
    deps: Tuple[str, ...]
    fn: Callable[[MarketSnapshot, Mapping[str, Any]], NodeResult]


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _as_positive_float(value: Any) -> Optional[float]:
    out = _to_float(value)
    if out is None or out <= 0:
        return None
    return out


def _uniq(values: Iterable[str]) -> Tuple[str, ...]:
    out: list[str] = []
    seen = set()
    for raw in values:
        val = str(raw or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return tuple(out)


def _as_strategy_candidate(raw: Any) -> Optional[StrategyCandidate]:
    if isinstance(raw, StrategyCandidate):
        return raw
    if raw is None:
        return None
    family = None
    allowed = False
    reasons: Sequence[str] = ()
    candidate_summary: Mapping[str, Any] = {}
    if isinstance(raw, Mapping):
        family = raw.get("family")
        allowed = bool(raw.get("allowed", False))
        reasons = raw.get("reasons") or ()
        candidate_summary = raw.get("candidate_summary") or {}
    else:
        family = getattr(raw, "family", None)
        allowed = bool(getattr(raw, "allowed", False))
        reasons = getattr(raw, "reasons", ()) or ()
        candidate_summary = getattr(raw, "candidate_summary", {}) or {}
    return StrategyCandidate(
        family=str(family) if family is not None else None,
        allowed=bool(allowed),
        reasons=_uniq(reasons),
        candidate_summary=MappingProxyType(dict(candidate_summary) if isinstance(candidate_summary, Mapping) else {}),
    )


def _normalize_strategy_candidates(raw_candidates: Sequence[Any] | None) -> Tuple[StrategyCandidate, ...]:
    out: list[StrategyCandidate] = []
    for item in (raw_candidates or ()):
        cand = _as_strategy_candidate(item)
        if cand is None:
            continue
        out.append(cand)
    return tuple(out)


def _max_regime_prob(raw: Mapping[str, Any]) -> Optional[float]:
    direct = _to_float(raw.get("regime_prob_max"))
    if direct is not None:
        return direct
    probs = raw.get("regime_probs") or {}
    if not isinstance(probs, Mapping):
        return None
    vals = [_to_float(v) for v in probs.values()]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _compute_feed_health(raw: Mapping[str, Any], now_epoch: float, market_open: bool) -> FeedHealthSnapshot:
    max_ltp_age = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    ltp_ts_epoch = _to_float(raw.get("ltp_ts_epoch"))
    ltp_age_sec = None if ltp_ts_epoch is None else max(0.0, now_epoch - ltp_ts_epoch)
    depth_age_sec = _to_float(raw.get("depth_age_sec"))
    if depth_age_sec is None:
        feed = raw.get("feed_health") or {}
        if isinstance(feed, Mapping):
            depth_age_sec = _to_float(feed.get("depth_age_sec"))
    # FEED_FRESH is strictly time-based.
    is_fresh = (not market_open) or (ltp_age_sec is not None and ltp_age_sec <= max_ltp_age)
    return FeedHealthSnapshot(
        ltp_age_sec=ltp_age_sec,
        depth_age_sec=depth_age_sec,
        is_fresh=bool(is_fresh),
        ts_epoch=now_epoch,
        source=str(raw.get("ltp_source") or "unknown"),
    )


def build_market_snapshot(market_data: Mapping[str, Any], now_epoch: Optional[float] = None) -> MarketSnapshot:
    raw = dict(market_data or {})
    symbol = str(raw.get("symbol") or "").upper()
    execution_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    ts_epoch = _to_float(now_epoch if now_epoch is not None else raw.get("timestamp")) or now_utc_epoch()
    market_open = bool(raw.get("market_open")) if "market_open" in raw else bool(is_market_open_ist())
    instrument = str(raw.get("instrument") or "").upper()
    if not instrument:
        instrument = "INDEX" if symbol in INDEX_SYMBOLS else "OPT"

    indicator_stale_sec = float(getattr(cfg, "INDICATOR_STALE_SEC", 120))
    indicators_age = _to_float(raw.get("indicators_age_sec"))
    if indicators_age is None:
        last_upd = _to_float(raw.get("indicator_last_update_epoch"))
        if last_upd is not None:
            indicators_age = max(0.0, ts_epoch - last_upd)
        else:
            indicators_age = float(getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9))

    warmup_reasons = _uniq(raw.get("warmup_reasons") or [])
    feed_health = _compute_feed_health(raw=raw, now_epoch=ts_epoch, market_open=market_open)

    return MarketSnapshot(
        symbol=symbol,
        instrument=instrument,
        execution_mode=execution_mode,
        ts_epoch=ts_epoch,
        market_open=market_open,
        ltp=_to_float(raw.get("ltp")),
        ltp_source=str(raw.get("ltp_source") or "none"),
        ltp_ts_epoch=_to_float(raw.get("ltp_ts_epoch")),
        bid=_as_positive_float(raw.get("bid")),
        ask=_as_positive_float(raw.get("ask")),
        quote_ok=bool(raw.get("quote_ok", False)),
        quote_source=str(raw.get("quote_source") or "none"),
        indicators_ok=bool(raw.get("indicators_ok", False)),
        indicators_age_sec=float(indicators_age),
        indicator_stale_sec=indicator_stale_sec,
        system_state=str(raw.get("system_state") or "READY").upper(),
        warmup_reasons=tuple(warmup_reasons),
        primary_regime=str(raw.get("primary_regime") or raw.get("regime") or "UNKNOWN").upper(),
        regime_probs_max=_max_regime_prob(raw),
        regime_entropy=_to_float(raw.get("regime_entropy")),
        unstable_reasons=_uniq(raw.get("unstable_reasons") or []),
        risk_halted=bool(risk_halt.is_halted()),
        feed_health=feed_health,
        raw_data=MappingProxyType(raw),
    )


def _has_bid_ask(snapshot: MarketSnapshot) -> bool:
    return snapshot.bid is not None and snapshot.ask is not None and snapshot.ask >= snapshot.bid


def _synth_index_bid_ask(ltp: float) -> Tuple[float, float]:
    spread = max(ltp * 0.00005, 0.5)
    half = spread / 2.0
    return round(ltp - half, 4), round(ltp + half, 4)


def _node_n1_market_open(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    if snapshot.market_open:
        return NodeResult(ok=True, value=True, reasons=(), facts=MappingProxyType({"market_open": True}))
    return NodeResult(ok=False, value=False, reasons=("MARKET_CLOSED",), facts=MappingProxyType({"market_open": False}))


def _node_n2_feed_fresh(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    # FEED_STALE is exclusively based on snapshot.feed_health.is_fresh.
    if not snapshot.market_open:
        return NodeResult(ok=True, value=True, reasons=(), facts=MappingProxyType(snapshot.feed_health.to_dict()))
    if snapshot.feed_health.is_fresh:
        return NodeResult(ok=True, value=True, reasons=(), facts=MappingProxyType(snapshot.feed_health.to_dict()))
    return NodeResult(
        ok=False,
        value=False,
        reasons=("FEED_STALE",),
        facts=MappingProxyType(snapshot.feed_health.to_dict()),
    )


def _node_n3_warmup_done(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    reasons: list[str] = []
    if snapshot.system_state == "WARMUP":
        reasons.append("WARMUP_INCOMPLETE")
    if (not snapshot.indicators_ok) or (snapshot.indicators_age_sec > snapshot.indicator_stale_sec):
        reasons.append("INDICATORS_MISSING")
    return NodeResult(
        ok=len(_uniq(reasons)) == 0,
        reasons=_uniq(reasons),
        facts=MappingProxyType(
            {
                "system_state": snapshot.system_state,
                "warmup_reasons": list(snapshot.warmup_reasons),
                "indicators_ok": snapshot.indicators_ok,
                "indicators_age_sec": snapshot.indicators_age_sec,
                "indicator_stale_sec": snapshot.indicator_stale_sec,
            }
        ),
    )


def _node_n4_quote_ok(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    if not snapshot.market_open:
        return NodeResult(
            ok=True,
            value={"quote_ok": True, "quote_source": "offhours"},
            reasons=(),
            facts=MappingProxyType({"instrument": snapshot.instrument, "quote_source": "offhours"}),
        )

    is_index = snapshot.instrument == "INDEX"
    if is_index:
        if _has_bid_ask(snapshot):
            bid = float(snapshot.bid)
            ask = float(snapshot.ask)
            return NodeResult(
                ok=True,
                value={"bid": bid, "ask": ask, "mid": (bid + ask) / 2.0, "quote_source": "depth"},
                reasons=(),
                facts=MappingProxyType({"instrument": "INDEX", "quote_source": "depth"}),
            )
        if snapshot.ltp is not None and snapshot.ltp > 0:
            mid = float(snapshot.ltp)
            if snapshot.execution_mode in {"SIM", "PAPER"}:
                bid, ask = _synth_index_bid_ask(mid)
                return NodeResult(
                    ok=True,
                    value={"bid": bid, "ask": ask, "mid": mid, "quote_source": "synthetic_index"},
                    reasons=(),
                    facts=MappingProxyType({"instrument": "INDEX", "quote_source": "synthetic_index"}),
                )
            # LIVE: no depth requirement for indices, use ltp mid.
            return NodeResult(
                ok=True,
                value={"bid": None, "ask": None, "mid": mid, "quote_source": "ltp_mid"},
                reasons=(),
                facts=MappingProxyType({"instrument": "INDEX", "quote_source": "ltp_mid"}),
            )
        return NodeResult(
            ok=False,
            value={"quote_source": "missing_depth_or_ltp"},
            reasons=("QUOTE_INVALID",),
            facts=MappingProxyType({"instrument": "INDEX", "quote_source": "missing_depth_or_ltp"}),
        )

    # OPTIONS: LIVE requires bid+ask. Never synthesize option bid/ask.
    if snapshot.instrument == "OPT" and snapshot.execution_mode == "LIVE":
        if _has_bid_ask(snapshot):
            bid = float(snapshot.bid)
            ask = float(snapshot.ask)
            return NodeResult(
                ok=True,
                value={"bid": bid, "ask": ask, "mid": (bid + ask) / 2.0, "quote_source": snapshot.quote_source},
                reasons=(),
                facts=MappingProxyType({"instrument": "OPT", "quote_source": snapshot.quote_source}),
            )
        return NodeResult(
            ok=False,
            value={"quote_source": snapshot.quote_source or "missing_depth"},
            reasons=("QUOTE_INVALID",),
            facts=MappingProxyType({"instrument": "OPT", "quote_source": snapshot.quote_source or "missing_depth"}),
        )

    # Non-LIVE options still require quote_ok but no synthetic option quotes are ever generated here.
    if snapshot.quote_ok:
        return NodeResult(
            ok=True,
            value={"bid": snapshot.bid, "ask": snapshot.ask, "quote_source": snapshot.quote_source},
            reasons=(),
            facts=MappingProxyType({"instrument": snapshot.instrument, "quote_source": snapshot.quote_source}),
        )
    return NodeResult(
        ok=False,
        value={"quote_source": snapshot.quote_source or "none"},
        reasons=("QUOTE_INVALID",),
        facts=MappingProxyType({"instrument": snapshot.instrument, "quote_source": snapshot.quote_source or "none"}),
    )


def _node_n5_regime_ok(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    reasons: list[str] = []
    if snapshot.primary_regime in {"", "NONE", "UNKNOWN"}:
        reasons.append("REGIME_UNKNOWN")
    if snapshot.unstable_reasons:
        reasons.append("REGIME_UNSTABLE")
    return NodeResult(
        ok=len(_uniq(reasons)) == 0,
        reasons=_uniq(reasons),
        facts=MappingProxyType(
            {
                "primary_regime": snapshot.primary_regime,
                "regime_probs_max": snapshot.regime_probs_max,
                "regime_entropy": snapshot.regime_entropy,
                "unstable_reasons": list(snapshot.unstable_reasons),
            }
        ),
    )


def _node_n6_risk_ok(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    raw = snapshot.raw_data
    risk_ok = bool(raw.get("risk_ok", True))
    risk_limit_hit = bool(raw.get("risk_limit_hit", False))
    risk_mode = str(raw.get("risk_state_mode") or raw.get("risk_mode") or "").upper()
    blocked = (not risk_ok) or risk_limit_hit or (risk_mode == "HARD_HALT")
    return NodeResult(
        ok=not blocked,
        reasons=("RISK_LIMIT",) if blocked else (),
        facts=MappingProxyType(
            {
                "risk_ok": risk_ok,
                "risk_limit_hit": risk_limit_hit,
                "risk_state_mode": risk_mode,
            }
        ),
    )


def _node_n7_governance_locks_ok(snapshot: MarketSnapshot, _ctx: Mapping[str, Any]) -> NodeResult:
    raw = snapshot.raw_data
    reasons: list[str] = []
    lock_active = bool(
        snapshot.risk_halted
        or raw.get("lock_active", False)
        or raw.get("wf_lock_active", False)
        or raw.get("governance_lock_active", False)
    )
    if lock_active:
        reasons.append("LOCK_ACTIVE")

    broker_enabled_raw = raw.get("broker_enabled")
    if broker_enabled_raw is None:
        broker_enabled = bool(raw.get("kite_use_api", getattr(cfg, "KITE_USE_API", True)))
    else:
        broker_enabled = bool(broker_enabled_raw)
    if snapshot.execution_mode == "LIVE" and not broker_enabled:
        reasons.append("BROKER_DISABLED")

    return NodeResult(
        ok=len(_uniq(reasons)) == 0,
        reasons=_uniq(reasons),
        facts=MappingProxyType({"lock_active": lock_active, "broker_enabled": broker_enabled}),
    )


def _node_n8_strategy_select(snapshot: MarketSnapshot, ctx: Mapping[str, Any]) -> NodeResult:
    deps = ctx["deps"]
    all_node_results = ctx.get("all_node_results") or {}
    strategy_candidates = tuple(ctx.get("strategy_candidates") or ())

    precondition_nodes = (
        NODE_N1_MARKET_OPEN,
        NODE_N2_FEED_FRESH,
        NODE_N3_WARMUP_DONE,
        NODE_N4_QUOTE_OK,
        NODE_N5_REGIME_OK,
        NODE_N6_RISK_OK,
        NODE_N7_GOVERNANCE_LOCKS_OK,
    )
    precondition_failures: list[str] = []
    for name in precondition_nodes:
        dep = all_node_results.get(name) or deps.get(name)
        if dep is None or not dep.ok:
            precondition_failures.append(name)
    if precondition_failures:
        precondition_reasons: list[str] = []
        for name in precondition_failures:
            dep = all_node_results.get(name) or deps.get(name)
            if dep is None:
                continue
            precondition_reasons.extend(list(dep.reasons))
        precondition_reasons = list(_uniq(precondition_reasons))
        candidate_summary: Dict[str, Any] = {}
        actionable_candidates = [cand for cand in strategy_candidates if cand.actionable]
        if actionable_candidates:
            candidate_summary = actionable_candidates[0].to_summary()
        return NodeResult(
            ok=True,
            value={"selected_strategy": None},
            reasons=(),
            facts=MappingProxyType(
                {
                    "strategy_skipped_due_to_preconditions": True,
                    "precondition_failures": precondition_failures,
                    "precondition_reasons": precondition_reasons,
                    "candidate_summary": candidate_summary,
                }
            ),
        )

    if not strategy_candidates:
        return NodeResult(
            ok=False,
            reasons=("NO_STRATEGY_QUALIFIED",),
            facts=MappingProxyType({"strategy_candidates_missing": True}),
        )

    chosen = next((cand for cand in strategy_candidates if cand.allowed), None)
    if chosen is not None:
        return NodeResult(
            ok=True,
            value={"selected_strategy": chosen.family},
            reasons=(),
            facts=MappingProxyType(
                {
                    "gate_family": chosen.family,
                    "gate_reasons": list(chosen.reasons),
                    "candidate_summary": chosen.to_summary(),
                }
            ),
        )

    gate_reasons: list[str] = []
    for cand in strategy_candidates:
        gate_reasons.extend(list(cand.reasons))
    gate_reasons = list(_uniq(gate_reasons))
    manual_review = bool(snapshot.raw_data.get("manual_review_required", False)) or any("manual_review" in r.lower() for r in gate_reasons)
    reason = "MANUAL_REVIEW_REQUIRED" if manual_review else "NO_STRATEGY_QUALIFIED"
    return NodeResult(
        ok=False,
        value={"selected_strategy": None},
        reasons=(reason,),
        facts=MappingProxyType(
            {
                "gate_family": None,
                "gate_reasons": gate_reasons,
                "candidate_count": len(strategy_candidates),
            }
        ),
    )


def _node_n9_final_decision(snapshot: MarketSnapshot, ctx: Mapping[str, Any]) -> NodeResult:
    deps = ctx["deps"]
    all_node_results = ctx.get("all_node_results") or {}
    blockers: list[str] = []
    for name in (
        NODE_N1_MARKET_OPEN,
        NODE_N2_FEED_FRESH,
        NODE_N3_WARMUP_DONE,
        NODE_N4_QUOTE_OK,
        NODE_N5_REGIME_OK,
        NODE_N6_RISK_OK,
        NODE_N7_GOVERNANCE_LOCKS_OK,
        NODE_N8_STRATEGY_SELECT,
    ):
        dep = all_node_results.get(name) or deps.get(name)
        if dep is None:
            continue
        blockers.extend(list(dep.reasons))
    blockers_tuple = _uniq(blockers)
    selected_strategy = None
    n8_val = deps[NODE_N8_STRATEGY_SELECT].value
    if isinstance(n8_val, Mapping):
        selected_strategy = n8_val.get("selected_strategy")

    stage = NODE_N9_FINAL_DECISION
    primary_blocker = None
    for name in (
        NODE_N1_MARKET_OPEN,
        NODE_N2_FEED_FRESH,
        NODE_N3_WARMUP_DONE,
        NODE_N4_QUOTE_OK,
        NODE_N5_REGIME_OK,
        NODE_N6_RISK_OK,
        NODE_N7_GOVERNANCE_LOCKS_OK,
        NODE_N8_STRATEGY_SELECT,
    ):
        dep = all_node_results.get(name) or deps.get(name)
        if dep is not None and not dep.ok:
            stage = name
            primary_blocker = dep.reasons[0] if dep.reasons else name
            break

    risk_params = {
        "size_mult": snapshot.raw_data.get("size_mult"),
        "risk_multiplier": snapshot.raw_data.get("risk_multiplier"),
    }

    return NodeResult(
        ok=(len(blockers_tuple) == 0),
        value={
            "symbol": snapshot.symbol,
            "ts_epoch": snapshot.ts_epoch,
            "allowed": len(blockers_tuple) == 0,
            "primary_blocker": primary_blocker,
            "blockers": list(blockers_tuple),
            "stage": stage,
            "selected_strategy": selected_strategy,
            "risk_params": risk_params,
        },
        reasons=blockers_tuple,
        facts=MappingProxyType(
            {
                "stage": stage,
                "primary_blocker": primary_blocker,
                "blockers": list(blockers_tuple),
            }
        ),
    )


class DecisionDAGEvaluator:
    NODE_ORDER = (
        NODE_N1_MARKET_OPEN,
        NODE_N2_FEED_FRESH,
        NODE_N3_WARMUP_DONE,
        NODE_N4_QUOTE_OK,
        NODE_N5_REGIME_OK,
        NODE_N6_RISK_OK,
        NODE_N7_GOVERNANCE_LOCKS_OK,
        NODE_N8_STRATEGY_SELECT,
        NODE_N9_FINAL_DECISION,
    )

    def __init__(self, strategy_candidates: Sequence[StrategyCandidate] | None = None):
        self._strategy_candidates = _normalize_strategy_candidates(strategy_candidates)
        self._nodes: Dict[str, _NodeDef] = {
            NODE_N1_MARKET_OPEN: _NodeDef(NODE_N1_MARKET_OPEN, (), _node_n1_market_open),
            NODE_N2_FEED_FRESH: _NodeDef(NODE_N2_FEED_FRESH, (NODE_N1_MARKET_OPEN,), _node_n2_feed_fresh),
            NODE_N3_WARMUP_DONE: _NodeDef(NODE_N3_WARMUP_DONE, (NODE_N2_FEED_FRESH,), _node_n3_warmup_done),
            NODE_N4_QUOTE_OK: _NodeDef(NODE_N4_QUOTE_OK, (NODE_N3_WARMUP_DONE,), _node_n4_quote_ok),
            NODE_N5_REGIME_OK: _NodeDef(NODE_N5_REGIME_OK, (NODE_N4_QUOTE_OK,), _node_n5_regime_ok),
            NODE_N6_RISK_OK: _NodeDef(NODE_N6_RISK_OK, (NODE_N5_REGIME_OK,), _node_n6_risk_ok),
            NODE_N7_GOVERNANCE_LOCKS_OK: _NodeDef(NODE_N7_GOVERNANCE_LOCKS_OK, (NODE_N6_RISK_OK,), _node_n7_governance_locks_ok),
            NODE_N8_STRATEGY_SELECT: _NodeDef(
                NODE_N8_STRATEGY_SELECT,
                (NODE_N7_GOVERNANCE_LOCKS_OK,),
                _node_n8_strategy_select,
            ),
            NODE_N9_FINAL_DECISION: _NodeDef(
                NODE_N9_FINAL_DECISION,
                (NODE_N8_STRATEGY_SELECT,),
                _node_n9_final_decision,
            ),
        }

    def evaluate(self, snapshot: MarketSnapshot) -> Decision:
        cache: Dict[str, NodeResult] = {}
        call_counts: Dict[str, int] = {}

        def run(name: str) -> NodeResult:
            if name in cache:
                return cache[name]
            node = self._nodes[name]
            deps = {dep: run(dep) for dep in node.deps}
            ctx = {"deps": deps, "all_node_results": cache, "strategy_candidates": self._strategy_candidates}
            call_counts[name] = call_counts.get(name, 0) + 1
            out = node.fn(snapshot, ctx)
            cache[name] = out
            return out

        final = run(NODE_N9_FINAL_DECISION)
        final_payload = dict(final.value or {})
        explain = tuple(cache[name].to_dict(name) for name in self.NODE_ORDER if name in cache)
        facts = {
            "feed_health": snapshot.feed_health.to_dict(),
            "node_call_counts": dict(call_counts),
            "instrument": snapshot.instrument,
            "execution_mode": snapshot.execution_mode,
            "ltp_source": snapshot.ltp_source,
            "quote_source": snapshot.quote_source,
        }

        return Decision(
            symbol=snapshot.symbol,
            ts_epoch=snapshot.ts_epoch,
            allowed=bool(final_payload.get("allowed", False)),
            primary_blocker=final_payload.get("primary_blocker"),
            blockers=tuple(final_payload.get("blockers") or []),
            stage=str(final_payload.get("stage") or NODE_N9_FINAL_DECISION),
            selected_strategy=final_payload.get("selected_strategy"),
            risk_params=MappingProxyType(dict(final_payload.get("risk_params") or {})),
            facts=MappingProxyType(facts),
            explain=explain,
        )


def evaluate_decision(
    market_data: Mapping[str, Any],
    strategy_eval: Callable[..., Any] | None = None,
    now_epoch: Optional[float] = None,
    strategy_candidates: Sequence[Any] | None = None,
    strategy_evaluator: Callable[[MarketSnapshot], Sequence[Any] | Any] | None = None,
) -> Decision:
    snapshot = build_market_snapshot(market_data, now_epoch=now_epoch)
    candidates: Tuple[StrategyCandidate, ...] = ()
    if strategy_candidates is not None:
        candidates = _normalize_strategy_candidates(strategy_candidates)
    elif strategy_evaluator is not None:
        evaluated = strategy_evaluator(snapshot)
        if isinstance(evaluated, Sequence) and not isinstance(evaluated, (str, bytes, bytearray)):
            candidates = _normalize_strategy_candidates(evaluated)
        else:
            one = _as_strategy_candidate(evaluated)
            candidates = (one,) if one is not None else ()
    elif strategy_eval is not None:
        # Backward-compatible shim: call with snapshot only.
        try:
            legacy = strategy_eval(snapshot, mode="MAIN")
        except TypeError:
            legacy = strategy_eval(snapshot)
        one = _as_strategy_candidate(legacy)
        candidates = (one,) if one is not None else ()

    evaluator = DecisionDAGEvaluator(strategy_candidates=candidates)
    return evaluator.evaluate(snapshot)
