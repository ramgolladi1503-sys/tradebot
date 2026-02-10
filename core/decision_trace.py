from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config import config as cfg
from core.time_utils import now_utc_epoch


def _to_reason_code(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "UNKNOWN_REASON"
    return text.replace(" ", "_").replace(":", "_").replace("|", "_").upper()


def normalize_reason_codes(reasons: list[Any] | None) -> list[str]:
    out: list[str] = []
    for reason in reasons or []:
        code = _to_reason_code(reason)
        if code and code not in out:
            out.append(code)
    return out


def decision_config_snapshot() -> dict[str, Any]:
    keys = [
        "EXECUTION_MODE",
        "DEFAULT_SEGMENT",
        "REQUIRE_LIVE_QUOTES",
        "MAX_OPTION_QUOTE_AGE_SEC",
        "MAX_QUOTE_AGE_SEC",
        "MAX_SPREAD_PCT",
        "ML_MIN_PROBA",
        "MAX_DAILY_LOSS_PCT",
        "MAX_DRAWDOWN_PCT",
        "MAX_RISK_PER_TRADE_PCT",
        "RISK_PROFILE",
        "LIVE_PILOT_MODE",
    ]
    snap: dict[str, Any] = {}
    for key in keys:
        snap[key] = getattr(cfg, key, None)
    return snap


@dataclass
class DecisionTrace:
    run_id: str
    symbol: str
    ts: float
    inputs_snapshot: dict[str, Any] = field(default_factory=dict)
    features_snapshot: dict[str, Any] = field(default_factory=dict)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    gate_results: dict[str, Any] = field(default_factory=dict)
    final_decision: str = "BLOCKED"
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.final_decision not in {"ALLOWED", "BLOCKED"}:
            self.final_decision = "BLOCKED"
        self.reasons = normalize_reason_codes(self.reasons)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_trade_decision_trace(
    market_data: dict[str, Any],
    trade: Any,
    reject_ctx: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> DecisionTrace:
    symbol = str(market_data.get("symbol") or getattr(trade, "symbol", "") or "UNKNOWN")
    ts_epoch = float(now_utc_epoch())
    trace_run_id = run_id or str(market_data.get("run_id") or f"{symbol}-{int(ts_epoch)}")
    reasons: list[Any] = []
    gate_results: dict[str, Any] = {}
    score_breakdown: dict[str, Any] = {}
    features_snapshot: dict[str, Any] = {}
    if trade is None:
        if isinstance(reject_ctx, dict):
            if reject_ctx.get("reason"):
                reasons.append(reject_ctx.get("reason"))
            for key in ("detail", "feature_contract_failed"):
                if reject_ctx.get(key):
                    gate_results[key] = reject_ctx.get(key)
        final_decision = "BLOCKED"
    else:
        reasons.extend(list(getattr(trade, "tradable_reasons_blocking", []) or []))
        source_flags = dict(getattr(trade, "source_flags", {}) or {})
        gate_results.update(source_flags)
        gate_results["quote_ok"] = bool(getattr(trade, "quote_ok", source_flags.get("quote_ok", False)))
        gate_results["chain_source"] = source_flags.get("chain_source")
        gate_results["risk_guard_passed"] = source_flags.get("risk_guard_passed")
        score_breakdown = dict(getattr(trade, "trade_score_detail", {}) or {})
        score_breakdown["confidence"] = getattr(trade, "confidence", None)
        score_breakdown["trade_score"] = getattr(trade, "trade_score", None)
        features_snapshot = {
            "opt_ltp": getattr(trade, "opt_ltp", None),
            "opt_bid": getattr(trade, "opt_bid", None),
            "opt_ask": getattr(trade, "opt_ask", None),
            "model_type": getattr(trade, "model_type", None),
            "model_version": getattr(trade, "model_version", None),
            "alpha_confidence": getattr(trade, "alpha_confidence", None),
            "alpha_uncertainty": getattr(trade, "alpha_uncertainty", None),
        }
        final_decision = "ALLOWED" if bool(getattr(trade, "tradable", False)) else "BLOCKED"
        if final_decision == "BLOCKED" and not reasons:
            reasons.append("non_tradable")

    inputs_snapshot = {
        "symbol": symbol,
        "ltp": market_data.get("ltp"),
        "ltp_source": market_data.get("ltp_source"),
        "vwap": market_data.get("vwap"),
        "atr": market_data.get("atr"),
        "regime": market_data.get("regime"),
        "day_type": market_data.get("day_type"),
        "chain_source": market_data.get("chain_source"),
        "quote_ok": market_data.get("quote_ok"),
        "quote_age_sec": market_data.get("quote_age_sec"),
        "market_open": market_data.get("market_open"),
    }
    return DecisionTrace(
        run_id=trace_run_id,
        symbol=symbol,
        ts=ts_epoch,
        inputs_snapshot=inputs_snapshot,
        features_snapshot=features_snapshot,
        score_breakdown=score_breakdown,
        gate_results=gate_results,
        final_decision=final_decision,
        reasons=normalize_reason_codes(reasons),
    )
