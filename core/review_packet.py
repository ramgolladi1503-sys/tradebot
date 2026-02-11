from __future__ import annotations

from typing import Any


def _get(trade_candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(trade_candidate, dict):
        return trade_candidate.get(key, default)
    return getattr(trade_candidate, key, default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _top_reasons(trade_candidate: Any) -> list[str]:
    reasons: list[str] = []
    entry_reason = str(_get(trade_candidate, "entry_reason", "") or "").strip()
    if entry_reason:
        reasons.append(entry_reason)
    pattern_flags = list(_get(trade_candidate, "pattern_flags", []) or [])
    for flag in pattern_flags:
        text = str(flag).strip()
        if text:
            reasons.append(text)
    score_detail = _get(trade_candidate, "trade_score_detail", None)
    if isinstance(score_detail, dict):
        for key in sorted(score_detail.keys()):
            val = score_detail.get(key)
            reasons.append(f"{key}:{val}")
    for reason in list(_get(trade_candidate, "reason_codes", []) or []):
        text = str(reason).strip()
        if text:
            reasons.append(text)
    unique: list[str] = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return unique[:3]


def build_review_packet(
    trade_candidate: Any,
    market_data: dict[str, Any] | None = None,
    risk_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market_data = market_data or {}
    risk_policy = risk_policy or {}

    symbol = str(_get(trade_candidate, "symbol", market_data.get("symbol", "")) or "")
    strategy = str(_get(trade_candidate, "strategy", "") or "")
    direction = str(_get(trade_candidate, "side", "") or "").upper()
    entry_method = str(
        _get(
            trade_candidate,
            "entry_type",
            _get(trade_candidate, "order_type", _get(trade_candidate, "entry_condition", "LIMIT")),
        )
        or "LIMIT"
    ).upper()
    expected_holding_sec = _as_int(_get(trade_candidate, "max_hold_sec", 0), 0)
    if expected_holding_sec <= 0:
        expected_holding_sec = _as_int(_get(trade_candidate, "validity_sec", 0), 0)

    entry_price = _as_float(_get(trade_candidate, "entry_price", 0.0), 0.0)
    stop_loss = _as_float(_get(trade_candidate, "stop_loss", 0.0), 0.0)
    target = _as_float(_get(trade_candidate, "target", 0.0), 0.0)
    qty_units = _as_int(_get(trade_candidate, "qty_units", _get(trade_candidate, "qty", 0)), 0)
    qty_lots = _as_int(_get(trade_candidate, "qty_lots", 0), 0)

    max_loss = _as_float(_get(trade_candidate, "max_loss", 0.0), 0.0)
    if max_loss <= 0 and entry_price > 0 and stop_loss > 0 and qty_units > 0:
        max_loss = abs(entry_price - stop_loss) * qty_units

    notional = _as_float(_get(trade_candidate, "notional_estimate", 0.0), 0.0)
    if notional <= 0 and entry_price > 0 and qty_units > 0:
        notional = entry_price * qty_units
    margin_est = _as_float(_get(trade_candidate, "margin_estimate", 0.0), 0.0)
    if margin_est <= 0:
        margin_est = _as_float(risk_policy.get("margin_estimate"), notional)

    bid = _as_float(_get(trade_candidate, "opt_bid", market_data.get("bid")), 0.0)
    ask = _as_float(_get(trade_candidate, "opt_ask", market_data.get("ask")), 0.0)
    spread_abs = _as_float(market_data.get("spread"), 0.0)
    if spread_abs <= 0 and bid > 0 and ask > 0 and ask >= bid:
        spread_abs = ask - bid
    spread_pct = _as_float(market_data.get("spread_pct"), 0.0)
    if spread_pct <= 0 and spread_abs > 0 and entry_price > 0:
        spread_pct = spread_abs / entry_price

    liquidity = {
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "bid": bid,
        "ask": ask,
        "volume": _as_float(_get(trade_candidate, "volume", market_data.get("volume")), 0.0),
        "oi": _as_float(_get(trade_candidate, "open_interest", market_data.get("oi")), 0.0),
        "quote_ok": bool(_get(trade_candidate, "quote_ok", market_data.get("quote_ok", False))),
    }

    regime = str(
        market_data.get("regime")
        or market_data.get("primary_regime")
        or _get(trade_candidate, "regime", "")
        or ""
    )
    key_feature_names = [
        "trend_state",
        "regime",
        "vol_state",
        "depth_imbalance",
        "vwap",
        "shock_score",
        "spread_pct",
        "iv",
        "ivp",
    ]
    key_features: dict[str, Any] = {}
    for name in key_feature_names:
        if name in market_data and market_data.get(name) is not None:
            key_features[name] = market_data.get(name)

    review_packet = {
        "summary": {
            "strategy_name": strategy,
            "symbol": symbol,
            "direction": direction,
            "entry_method": entry_method,
            "expected_holding_sec": expected_holding_sec,
        },
        "risk": {
            "max_loss": max_loss,
            "notional_estimate": notional,
            "margin_estimate": margin_est,
            "stop": stop_loss,
            "target": target,
            "invalidation_condition": f"{direction}_invalid_if_stop_hit",
        },
        "liquidity": liquidity,
        "context": {
            "regime_tag": regime,
            "key_features_used": key_features,
            "top_reasons": _top_reasons(trade_candidate),
        },
        "guardrails": {
            "position_sizing_cap": _as_float(
                risk_policy.get("position_sizing_cap", _get(trade_candidate, "qty_cap", qty_units)),
                0.0,
            ),
            "time_window_validity_sec": _as_int(
                risk_policy.get("time_window_validity_sec", _get(trade_candidate, "validity_sec", 0)),
                0,
            ),
            "risk_policy_allow_reason": str(
                risk_policy.get("allow_reason", _get(trade_candidate, "risk_policy_reason", "risk_checks_passed"))
            ),
        },
    }
    return review_packet


def format_review_packet(packet: dict[str, Any]) -> str:
    summary = packet.get("summary", {}) or {}
    risk = packet.get("risk", {}) or {}
    liquidity = packet.get("liquidity", {}) or {}
    context = packet.get("context", {}) or {}
    guardrails = packet.get("guardrails", {}) or {}
    top_reasons = list(context.get("top_reasons", []) or [])
    reason_lines = "\n".join(f"- {reason}" for reason in top_reasons) if top_reasons else "- none"
    return (
        "APPROVAL REVIEW PACKET\n"
        f"Summary: strategy={summary.get('strategy_name')} symbol={summary.get('symbol')} "
        f"direction={summary.get('direction')} entry={summary.get('entry_method')} "
        f"hold_sec={summary.get('expected_holding_sec')}\n"
        f"Risk: max_loss={risk.get('max_loss')} notional={risk.get('notional_estimate')} "
        f"margin={risk.get('margin_estimate')} stop={risk.get('stop')} target={risk.get('target')} "
        f"invalidation={risk.get('invalidation_condition')}\n"
        f"Liquidity: spread_abs={liquidity.get('spread_abs')} spread_pct={liquidity.get('spread_pct')} "
        f"bid={liquidity.get('bid')} ask={liquidity.get('ask')} volume={liquidity.get('volume')} "
        f"oi={liquidity.get('oi')} quote_ok={liquidity.get('quote_ok')}\n"
        f"Context: regime={context.get('regime_tag')} key_features={context.get('key_features_used')}\n"
        f"Top reasons:\n{reason_lines}\n"
        f"Guardrails: size_cap={guardrails.get('position_sizing_cap')} "
        f"validity_sec={guardrails.get('time_window_validity_sec')} "
        f"allow_reason={guardrails.get('risk_policy_allow_reason')}"
    )
