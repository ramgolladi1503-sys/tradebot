from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from config import config as cfg


_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _get_value(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _update_candidate(candidate: Any, updates: dict[str, Any]) -> Any:
    if isinstance(candidate, dict):
        out = dict(candidate)
        out.update(updates)
        return out
    return replace(candidate, **updates)


def _source_flags(candidate: Any) -> dict[str, Any]:
    raw = _get_value(candidate, "source_flags", {}) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _trade_id(candidate: Any) -> str:
    return str(
        _get_value(candidate, "trade_id")
        or _get_value(candidate, "trade_key")
        or _get_value(candidate, "instrument_id")
        or "unknown"
    ).strip()


def _symbol(candidate: Any) -> str:
    return str(_get_value(candidate, "symbol") or _get_value(candidate, "underlying") or "UNKNOWN").strip().upper() or "UNKNOWN"


def _asset_family(candidate: Any) -> str:
    symbol = _symbol(candidate)
    if symbol in _INDEX_SYMBOLS:
        return "index"
    return symbol.lower()


def _setup_family(candidate: Any) -> str:
    flags = _source_flags(candidate)
    origin = flags.get("candidate_origin") if isinstance(flags.get("candidate_origin"), dict) else {}
    value = (
        origin.get("setup_family")
        or flags.get("setup_family")
        or _get_value(candidate, "setup_family")
        or _get_value(candidate, "strategy")
        or "unknown"
    )
    return str(value).strip().lower() or "unknown"


def _direction_bucket(candidate: Any) -> str:
    side = str(_get_value(candidate, "side") or "").strip().upper()
    right = str(_get_value(candidate, "right") or _get_value(candidate, "option_type") or "").strip().upper()
    if right in {"CE", "CALL"}:
        return "long_ce" if side != "SELL" else "short_ce"
    if right in {"PE", "PUT"}:
        return "long_pe" if side != "SELL" else "short_pe"
    if side == "BUY":
        return "long"
    if side == "SELL":
        return "short"
    return "unknown"


def _position_direction_bucket(candidate: Any) -> str:
    direction = str(_get_value(candidate, "direction") or "").strip().upper()
    side = str(_get_value(candidate, "side") or "").strip().upper()
    if direction in {"BUY", "LONG", "BUY_CALL", "BUY_PUT"}:
        return "long"
    if direction in {"SELL", "SHORT", "SELL_CALL", "SELL_PUT"}:
        return "short"
    if side == "BUY":
        return "long"
    if side == "SELL":
        return "short"
    return "unknown"


def _correlation_group(candidate: Any) -> str:
    return "|".join((_asset_family(candidate), _direction_bucket(candidate), _setup_family(candidate)))


def _allocation_selected(candidate: Any) -> bool:
    selected = _get_value(candidate, "selected_for_execution")
    if selected is not None:
        return bool(selected)
    return bool(_get_value(candidate, "allocation_reason") == "allocated")


def _base_score(candidate: Any) -> float:
    return float(
        _safe_float(_get_value(candidate, "opportunity_score"))
        or _safe_float(_get_value(candidate, "allocation_score"))
        or _safe_float(_get_value(candidate, "gating_final_confidence"))
        or _safe_float(_get_value(candidate, "permission_confidence"))
        or _safe_float(_get_value(candidate, "builder_confidence"))
        or _safe_float(_get_value(candidate, "confidence"))
        or 0.0
    )


def _capital_required(candidate: Any) -> float:
    assigned = _safe_float(_get_value(candidate, "capital_assigned"))
    if assigned is not None and assigned > 0:
        return float(assigned)
    risk = _safe_float(_get_value(candidate, "capital_at_risk"))
    if risk is not None and risk > 0:
        return float(risk)
    entry = _safe_float(_get_value(candidate, "entry_price")) or _safe_float(_get_value(candidate, "display_entry")) or 0.0
    qty = _safe_float(_get_value(candidate, "qty_units"))
    if qty is None or qty <= 0:
        qty = _safe_float(_get_value(candidate, "qty")) or 1.0
    return max(0.0, float(entry) * float(qty))


def _existing_group_counts(current_portfolio_exposure: Any) -> dict[str, int]:
    if not current_portfolio_exposure:
        return {}
    if isinstance(current_portfolio_exposure, dict):
        explicit = current_portfolio_exposure.get("correlation_group_counts") or current_portfolio_exposure.get("exposure_by_group")
        if isinstance(explicit, dict):
            return {
                str(key): max(0, int(_safe_float(value) or 0))
                for key, value in explicit.items()
                if str(key).strip()
            }
        trades = current_portfolio_exposure.get("trades") or current_portfolio_exposure.get("open_trades") or []
        return _existing_group_counts(trades)
    counts: dict[str, int] = {}
    if isinstance(current_portfolio_exposure, list):
        for row in current_portfolio_exposure:
            if not isinstance(row, (dict, object)):
                continue
            group = _correlation_group(row)
            counts[group] = counts.get(group, 0) + 1
    return counts


def _existing_symbol_counts(current_portfolio_exposure: Any) -> dict[str, int]:
    if not current_portfolio_exposure:
        return {}
    if isinstance(current_portfolio_exposure, dict):
        explicit = current_portfolio_exposure.get("symbol_counts") or current_portfolio_exposure.get("exposure_by_symbol")
        if isinstance(explicit, dict):
            return {
                str(key).strip().upper(): max(0, int(_safe_float(value) or 0))
                for key, value in explicit.items()
                if str(key).strip()
            }
        trades = current_portfolio_exposure.get("trades") or current_portfolio_exposure.get("open_trades") or []
        return _existing_symbol_counts(trades)
    counts: dict[str, int] = {}
    if isinstance(current_portfolio_exposure, list):
        for row in current_portfolio_exposure:
            symbol = _symbol(row)
            counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def _existing_direction_counts(current_portfolio_exposure: Any) -> dict[str, int]:
    if not current_portfolio_exposure:
        return {}
    if isinstance(current_portfolio_exposure, dict):
        explicit = current_portfolio_exposure.get("direction_counts") or current_portfolio_exposure.get("exposure_by_direction")
        if isinstance(explicit, dict):
            return {
                str(key).strip().lower(): max(0, int(_safe_float(value) or 0))
                for key, value in explicit.items()
                if str(key).strip()
            }
        trades = current_portfolio_exposure.get("trades") or current_portfolio_exposure.get("open_trades") or []
        return _existing_direction_counts(trades)
    counts: dict[str, int] = {}
    if isinstance(current_portfolio_exposure, list):
        for row in current_portfolio_exposure:
            direction = _position_direction_bucket(row)
            counts[direction] = counts.get(direction, 0) + 1
    return counts


def _annotate_candidate(
    candidate: Any,
    *,
    selected: bool,
    decision_reason: str,
    effective_score: float,
    penalty_total: float,
    penalty_reason: str | None,
    group: str,
) -> Any:
    flags = _source_flags(candidate)
    flags["portfolio_optimization"] = {
        "selected": bool(selected),
        "reason": str(decision_reason),
        "effective_score": round(float(effective_score), 6),
        "penalty": round(float(penalty_total), 6),
        "penalty_reason": penalty_reason,
        "symbol": _symbol(candidate),
        "direction_bucket": _position_direction_bucket(candidate),
        "correlation_group": group,
    }
    return _update_candidate(
        candidate,
        {
            "portfolio_optimization_selected": bool(selected),
            "portfolio_optimization_reason": str(decision_reason),
            "portfolio_optimization_score": round(float(effective_score), 6),
            "portfolio_optimization_penalty": round(float(penalty_total), 6),
            "portfolio_optimization_penalty_reason": penalty_reason,
            "source_flags": flags,
        },
    )


def optimize_portfolio_selection(
    candidates: Iterable[Any],
    *,
    current_portfolio_exposure: Any = None,
    max_group_exposure: int | None = None,
    max_per_symbol: int | None = None,
    max_per_direction: int | None = None,
    max_correlated_exposure: int | None = None,
    correlation_penalty: float | None = None,
    existing_exposure_penalty: float | None = None,
    diversification_bonus: float | None = None,
    capital_efficiency_weight: float | None = None,
) -> list[Any]:
    candidate_list = list(candidates or [])
    if not candidate_list:
        return []

    max_correlated = max(
        1,
        int(
            max_correlated_exposure
            if max_correlated_exposure is not None
            else (
                max_group_exposure
                if max_group_exposure is not None
                else getattr(
                    cfg,
                    "PORTFOLIO_OPTIMIZER_MAX_CORRELATED_EXPOSURE",
                    getattr(cfg, "PORTFOLIO_OPTIMIZER_MAX_GROUP_EXPOSURE", 1),
                )
            )
        ),
    )
    max_symbol = max(
        0,
        int(
            max_per_symbol
            if max_per_symbol is not None
            else getattr(cfg, "PORTFOLIO_OPTIMIZER_MAX_PER_SYMBOL", 0)
        ),
    )
    max_direction = max(
        0,
        int(
            max_per_direction
            if max_per_direction is not None
            else getattr(cfg, "PORTFOLIO_OPTIMIZER_MAX_PER_DIRECTION", 0)
        ),
    )
    correlation_penalty_value = max(
        0.0,
        float(
            correlation_penalty
            if correlation_penalty is not None
            else getattr(cfg, "PORTFOLIO_OPTIMIZER_CORRELATION_PENALTY", 0.08)
        ),
    )
    existing_penalty_value = max(
        0.0,
        float(
            existing_exposure_penalty
            if existing_exposure_penalty is not None
            else getattr(cfg, "PORTFOLIO_OPTIMIZER_EXISTING_EXPOSURE_PENALTY", 0.05)
        ),
    )
    diversification_bonus_value = max(
        0.0,
        float(
            diversification_bonus
            if diversification_bonus is not None
            else getattr(cfg, "PORTFOLIO_OPTIMIZER_DIVERSIFICATION_BONUS", 0.035)
        ),
    )
    capital_efficiency_weight_value = max(
        0.0,
        float(
            capital_efficiency_weight
            if capital_efficiency_weight is not None
            else getattr(cfg, "PORTFOLIO_OPTIMIZER_CAPITAL_EFFICIENCY_WEIGHT", 0.025)
        ),
    )

    existing_counts = _existing_group_counts(current_portfolio_exposure)
    existing_symbol_counts = _existing_symbol_counts(current_portfolio_exposure)
    existing_direction_counts = _existing_direction_counts(current_portfolio_exposure)
    candidate_states: list[dict[str, Any]] = []
    max_capital = max(
        (_capital_required(candidate) for candidate in candidate_list if _allocation_selected(candidate)),
        default=0.0,
    )

    for index, candidate in enumerate(candidate_list):
        group = _correlation_group(candidate)
        symbol = _symbol(candidate)
        direction_bucket = _position_direction_bucket(candidate)
        base_score = _base_score(candidate)
        capital = _capital_required(candidate)
        allocated = _allocation_selected(candidate)
        prior_group_count = int(existing_counts.get(group, 0))
        penalty_total = float(prior_group_count) * existing_penalty_value
        penalty_reasons: list[str] = []
        if prior_group_count > 0:
            penalty_reasons.append(f"existing_group_exposure:{prior_group_count}")
        bonus_total = 0.0
        if prior_group_count == 0:
            bonus_total += diversification_bonus_value
        if max_capital > 0 and capital > 0:
            bonus_total += capital_efficiency_weight_value * max(0.0, 1.0 - (capital / max_capital))
        effective_score = base_score - penalty_total + bonus_total
        candidate_states.append(
            {
                "index": int(index),
                "candidate": candidate,
                "group": group,
                "symbol": symbol,
                "direction_bucket": direction_bucket,
                "trade_id": _trade_id(candidate),
                "base_score": float(base_score),
                "effective_score": float(effective_score),
                "penalty_total": float(penalty_total),
                "penalty_reasons": penalty_reasons,
                "allocated": bool(allocated),
                "capital": float(capital),
                "rank_global": int(_safe_float(_get_value(candidate, "rank_global")) or 0),
            }
        )

    ranked_allocated = sorted(
        (state for state in candidate_states if state["allocated"]),
        key=lambda state: (
            -float(state["effective_score"]),
            -float(state["base_score"]),
            -float(state["capital"] and (1.0 / max(state["capital"], 1e-6)) or 0.0),
            int(state["rank_global"]),
            str(state["trade_id"]),
        ),
    )

    active_counts = dict(existing_counts)
    active_symbol_counts = dict(existing_symbol_counts)
    active_direction_counts = dict(existing_direction_counts)
    selected_indexes: set[int] = set()
    decision_reasons: dict[int, str] = {}
    penalty_reasons_by_index: dict[int, list[str]] = {
        state["index"]: list(state["penalty_reasons"]) for state in candidate_states
    }
    penalty_totals_by_index: dict[int, float] = {
        state["index"]: float(state["penalty_total"]) for state in candidate_states
    }

    for state in ranked_allocated:
        group = str(state["group"])
        symbol = str(state["symbol"])
        direction_bucket = str(state["direction_bucket"])
        if max_symbol > 0 and int(active_symbol_counts.get(symbol, 0)) >= max_symbol:
            penalty_totals_by_index[state["index"]] = penalty_totals_by_index.get(state["index"], 0.0) + correlation_penalty_value
            penalty_reasons_by_index[state["index"]].append("same_symbol_stacking")
            decision_reasons[state["index"]] = "rejected_symbol_concentration"
            continue
        if max_direction > 0 and direction_bucket != "unknown" and int(active_direction_counts.get(direction_bucket, 0)) >= max_direction:
            penalty_totals_by_index[state["index"]] = penalty_totals_by_index.get(state["index"], 0.0) + correlation_penalty_value
            penalty_reasons_by_index[state["index"]].append("same_direction_stacking")
            decision_reasons[state["index"]] = "rejected_direction_concentration"
            continue
        if int(active_counts.get(group, 0)) >= max_correlated:
            penalty_totals_by_index[state["index"]] = penalty_totals_by_index.get(state["index"], 0.0) + correlation_penalty_value
            penalty_reasons_by_index[state["index"]].append("same_theme_stacking")
            decision_reasons[state["index"]] = "rejected_correlated_concentration"
            continue
        selected_indexes.add(int(state["index"]))
        active_counts[group] = int(active_counts.get(group, 0)) + 1
        active_symbol_counts[symbol] = int(active_symbol_counts.get(symbol, 0)) + 1
        if direction_bucket != "unknown":
            active_direction_counts[direction_bucket] = int(active_direction_counts.get(direction_bucket, 0)) + 1
        if int(existing_counts.get(group, 0)) == 0:
            decision_reasons[state["index"]] = "selected_diversified"
        else:
            decision_reasons[state["index"]] = "selected_best_effective_score"

    optimized: list[Any] = []
    for state in candidate_states:
        index = int(state["index"])
        allocated = bool(state["allocated"])
        penalty_reasons = penalty_reasons_by_index.get(index) or []
        penalty_reason_text = ",".join(penalty_reasons) if penalty_reasons else None
        if index in selected_indexes:
            optimized.append(
                _annotate_candidate(
                    state["candidate"],
                    selected=True,
                    decision_reason=decision_reasons.get(index) or "selected_best_effective_score",
                    effective_score=float(state["effective_score"]),
                    penalty_total=float(penalty_totals_by_index.get(index, state["penalty_total"])),
                    penalty_reason=penalty_reason_text,
                    group=str(state["group"]),
                )
            )
            continue
        if not allocated:
            decision_reason = str(_get_value(state["candidate"], "allocation_reason") or "allocator_not_selected")
        else:
            decision_reason = decision_reasons.get(index) or "rejected_correlated_concentration"
        optimized.append(
            _annotate_candidate(
                state["candidate"],
                selected=False,
                decision_reason=decision_reason,
                effective_score=float(state["effective_score"]),
                penalty_total=float(penalty_totals_by_index.get(index, state["penalty_total"])),
                penalty_reason=penalty_reason_text,
                group=str(state["group"]),
            )
        )
    return optimized
