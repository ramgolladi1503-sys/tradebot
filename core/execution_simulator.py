from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import logging
import random
from typing import Any

from config import config as cfg
from core.execution_quality import evaluate_pretrade_execution_quality
from core.fill_model import FillModel
from core.market_context import derive_market_context
from core.option_entry import get_option_ltp_sla_sec
from core.sim_outcomes import build_sim_outcome_record, summarize_sim_outcome


logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _snapshot_value(snapshot: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = snapshot.get(name)
        if value not in (None, "", "None"):
            return value
    return None


def _merge_candidate_snapshot(candidate: Any, snapshot: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(snapshot or {})
    if "symbol" not in base:
        base["symbol"] = _candidate_get(candidate, "symbol")
    if "side" not in base:
        base["side"] = _candidate_get(candidate, "side", "BUY")
    if "qty" not in base:
        base["qty"] = _candidate_get(candidate, "qty", _candidate_get(candidate, "qty_units", 1))
    if "bid" not in base:
        base["bid"] = _candidate_get(candidate, "best_bid", _candidate_get(candidate, "opt_bid"))
    if "ask" not in base:
        base["ask"] = _candidate_get(candidate, "best_ask", _candidate_get(candidate, "opt_ask"))
    if "quote_age_sec" not in base:
        base["quote_age_sec"] = _candidate_get(candidate, "quote_age_sec")
    if "volume" not in base:
        base["volume"] = _candidate_get(candidate, "volume", _candidate_get(candidate, "current_volume"))
    if "oi" not in base:
        base["oi"] = _candidate_get(candidate, "oi")
    if "vol_z" not in base:
        base["vol_z"] = _candidate_get(candidate, "vol_z")
    return base


def _spread_pct(snapshot: dict[str, Any]) -> float | None:
    explicit = _safe_float(snapshot.get("spread_pct"))
    if explicit is not None:
        return explicit
    bid = _safe_float(_snapshot_value(snapshot, "bid", "best_bid", "opt_bid"))
    ask = _safe_float(_snapshot_value(snapshot, "ask", "best_ask", "opt_ask"))
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return max(0.0, ask - bid) / mid


def _rr(entry_price: float | None, stop_loss: float | None, target: float | None, side: str) -> float | None:
    if entry_price in (None, 0.0) or stop_loss is None or target is None:
        return None
    if str(side or "BUY").strip().upper() == "SELL":
        reward = float(entry_price) - float(target)
        risk = float(stop_loss) - float(entry_price)
    else:
        reward = float(target) - float(entry_price)
        risk = float(entry_price) - float(stop_loss)
    if risk <= 0:
        return None
    return max(0.0, reward / risk)


def _seeded_rng(seed: int, *parts: Any) -> random.Random:
    material = "|".join(str(part) for part in (seed, *parts))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


@dataclass(frozen=True)
class ExecutionSimulationResult:
    status: str
    reason: str
    fill_status: str | None = None
    fill_qty: int | None = None
    requested_qty: int | None = None
    residual_qty: int | None = None
    fill_price: float | None = None
    repriced_limit_price: float | None = None
    simulated_delay_sec: float = 0.0
    latency_jitter_sec: float = 0.0
    initial_quote_age_sec: float | None = None
    revalidated_quote_age_sec: float | None = None
    initial_spread_pct: float | None = None
    revalidated_spread_pct: float | None = None
    execution_score: float | None = None
    broker_status: str | None = None
    slippage_noise_bps: float = 0.0
    book_deterioration_pct: float = 0.0
    mfe: float | None = None
    mae: float | None = None
    simulated_pnl: float | None = None
    exit_reason: str | None = None
    would_have_worked: bool | None = None
    rejection_saved_loss: bool | None = None
    rejection_missed_win: bool | None = None
    realized_r_multiple: float | None = None
    stop_hit_before_target: bool | None = None
    risk_plan_respected: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def simulate_execution(
    candidate: Any,
    *,
    market_snapshot: dict[str, Any],
    revalidated_snapshot: dict[str, Any] | None = None,
    simulated_delay_sec: float | None = None,
    capital_context: dict[str, Any] | None = None,
    execution_mode: str | None = None,
    broker_behavior: str | None = None,
    run_id: str | None = None,
    random_seed: int | None = None,
    randomness_enabled: bool | None = None,
    allow_partial_fill: bool | None = None,
    future_prices: list[float] | tuple[float, ...] | None = None,
) -> ExecutionSimulationResult:
    if not bool(getattr(cfg, "OFFLINE_EXECUTION_SIM_ENABLE", True)):
        return ExecutionSimulationResult(
            status="SIM_CANCELLED",
            reason="simulation_disabled",
            details={"capital_context": dict(capital_context or {})},
        )

    initial_snapshot = _merge_candidate_snapshot(candidate, market_snapshot)
    delay_sec = max(
        0.0,
        float(
            simulated_delay_sec
            if simulated_delay_sec is not None
            else getattr(cfg, "OFFLINE_EXECUTION_SIM_DEFAULT_DELAY_SEC", 2.0)
        ),
    )
    revalidated = _merge_candidate_snapshot(candidate, revalidated_snapshot or initial_snapshot)
    if _safe_float(revalidated.get("quote_age_sec")) is None and _safe_float(initial_snapshot.get("quote_age_sec")) is not None:
        revalidated["quote_age_sec"] = float(initial_snapshot["quote_age_sec"]) + delay_sec
    side = str(_candidate_get(candidate, "side") or "BUY").strip().upper()
    requested_qty = int(max(_safe_float(_candidate_get(candidate, "qty")) or _safe_float(_candidate_get(candidate, "qty_units")) or 1, 1))
    limit_price = _safe_float(_candidate_get(candidate, "execution_entry"))
    if limit_price is None:
        limit_price = _safe_float(_candidate_get(candidate, "entry_price"))
    if limit_price is None:
        limit_price = _safe_float(revalidated.get("ask") if side == "BUY" else revalidated.get("bid"))

    stochastic_enabled = bool(
        randomness_enabled
        if randomness_enabled is not None
        else (random_seed is not None or bool(getattr(cfg, "OFFLINE_EXECUTION_SIM_RANDOMNESS_ENABLE", False)))
    )
    latency_jitter_sec = 0.0
    slippage_noise_bps = 0.0
    book_deterioration_pct = 0.0
    if stochastic_enabled:
        seed_value = int(
            random_seed
            if random_seed is not None
            else int(getattr(cfg, "FILL_REALISM_SEED", 20260227))
        )
        rng = _seeded_rng(
            seed_value,
            run_id or str(_candidate_get(candidate, "trade_id") or "offline-sim"),
            _candidate_get(candidate, "symbol"),
            side,
        )
        latency_jitter_sec = max(
            0.0,
            float(rng.uniform(0.0, float(getattr(cfg, "OFFLINE_EXECUTION_SIM_JITTER_MAX_SEC", 0.75) or 0.75))),
        )
        delay_sec += latency_jitter_sec
        existing_quote_age = _safe_float(revalidated.get("quote_age_sec"))
        if existing_quote_age is None:
            existing_quote_age = _safe_float(initial_snapshot.get("quote_age_sec"))
        if existing_quote_age is not None:
            revalidated["quote_age_sec"] = float(existing_quote_age) + float(latency_jitter_sec)
        bid_val = _safe_float(_snapshot_value(revalidated, "bid", "best_bid", "opt_bid"))
        ask_val = _safe_float(_snapshot_value(revalidated, "ask", "best_ask", "opt_ask"))
        if bid_val is not None and ask_val is not None and ask_val > bid_val:
            max_deterioration = max(
                0.0,
                float(getattr(cfg, "OFFLINE_EXECUTION_SIM_BOOK_DETERIORATION_PCT", 0.20) or 0.20),
            )
            book_deterioration_pct = max(0.0, float(rng.triangular(0.0, max_deterioration, max_deterioration * 0.4)))
            mid_val = (bid_val + ask_val) / 2.0
            spread_val = max(ask_val - bid_val, max(mid_val * 0.0005, 1e-6))
            extra_spread = spread_val * book_deterioration_pct
            noisy_bid = max(0.0, bid_val - (extra_spread * 0.5))
            noisy_ask = max(noisy_bid + 1e-6, ask_val + (extra_spread * 0.5))
            revalidated["bid"] = round(float(noisy_bid), 6)
            revalidated["ask"] = round(float(noisy_ask), 6)
            for qty_field in ("bid_qty", "ask_qty"):
                qty_val = _safe_float(revalidated.get(qty_field))
                if qty_val is not None:
                    revalidated[qty_field] = max(1.0, float(qty_val) * max(0.1, 1.0 - book_deterioration_pct))
        slippage_noise_bps = float(
            rng.triangular(
                -float(getattr(cfg, "OFFLINE_EXECUTION_SIM_SLIPPAGE_NOISE_BPS", 4.0) or 4.0),
                float(getattr(cfg, "OFFLINE_EXECUTION_SIM_SLIPPAGE_NOISE_BPS", 4.0) or 4.0),
                0.0,
            )
        )

    mode = str(
        execution_mode
        or _candidate_get(candidate, "market_mode")
        or _candidate_get(candidate, "execution_mode")
        or getattr(cfg, "EXECUTION_MODE", "SIM")
    ).strip().upper()
    max_age_sec = get_option_ltp_sla_sec(
        "LIVE",
        float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0)),
        allow_stale_quotes=False,
        market_open=True,
        expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
    )

    initial_quote_age = _safe_float(initial_snapshot.get("quote_age_sec"))
    revalidated_quote_age = _safe_float(revalidated.get("quote_age_sec"))
    initial_spread_pct = _spread_pct(initial_snapshot)
    revalidated_spread_pct = _spread_pct(revalidated)

    def _build_result(
        status: str,
        reason: str,
        *,
        fill_status: str | None = None,
        fill_qty: int | None = None,
        fill_price: float | None = None,
        repriced_limit_price: float | None = None,
        execution_score: float | None = None,
        broker_status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ExecutionSimulationResult:
        summary = summarize_sim_outcome(
            entry_price=fill_price or repriced_limit_price or limit_price,
            side=side,
            future_prices=future_prices,
            stop_loss=_safe_float(_candidate_get(candidate, "stop_loss")),
            target=_safe_float(_candidate_get(candidate, "target")),
            rejected=status in {"SIM_REJECTED", "SIM_CANCELLED"},
            quantity=requested_qty,
        )
        summary_dict = summary.to_dict() if future_prices is not None else {}
        merged_details = dict(details or {})
        if summary_dict:
            merged_details["outcome_summary"] = summary_dict
        residual_qty = None
        if fill_qty is not None:
            residual_qty = max(0, int(requested_qty) - int(fill_qty))
        result = ExecutionSimulationResult(
            status=status,
            reason=reason,
            fill_status=fill_status,
            fill_qty=fill_qty,
            requested_qty=int(requested_qty),
            residual_qty=residual_qty,
            fill_price=fill_price,
            repriced_limit_price=repriced_limit_price,
            simulated_delay_sec=delay_sec,
            latency_jitter_sec=round(float(latency_jitter_sec), 6),
            initial_quote_age_sec=initial_quote_age,
            revalidated_quote_age_sec=revalidated_quote_age,
            initial_spread_pct=initial_spread_pct,
            revalidated_spread_pct=revalidated_spread_pct,
            execution_score=execution_score,
            broker_status=broker_status,
            slippage_noise_bps=round(float(slippage_noise_bps), 6),
            book_deterioration_pct=round(float(book_deterioration_pct), 6),
            mfe=summary_dict.get("mfe"),
            mae=summary_dict.get("mae"),
            simulated_pnl=summary_dict.get("simulated_pnl"),
            exit_reason=summary_dict.get("exit_reason"),
            would_have_worked=summary_dict.get("would_have_worked"),
            rejection_saved_loss=summary_dict.get("rejection_saved_loss"),
            rejection_missed_win=summary_dict.get("rejection_missed_win"),
            realized_r_multiple=summary_dict.get("realized_r_multiple"),
            stop_hit_before_target=summary_dict.get("stop_hit_before_target"),
            risk_plan_respected=summary_dict.get("risk_plan_respected"),
            details=merged_details,
        )
        learning_mode = str(mode or "").strip().upper()
        if bool(getattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", False)) and learning_mode in {"SIM", "PAPER", "OFFHOURS"}:
            try:
                from core.offline_family_learning import record_family_outcome

                outcome_record = build_sim_outcome_record(candidate, result)
                if not str(outcome_record.get("timestamp") or "").strip():
                    snapshot_ts = _safe_float(_snapshot_value(initial_snapshot, "timestamp", "quote_ts_epoch", "ltp_ts_epoch"))
                    if snapshot_ts is not None:
                        outcome_record["timestamp"] = str(snapshot_ts)
                record_family_outcome(outcome_record)
            except Exception:
                logger.warning("offline_family_learning_record_failed", exc_info=True)
        return result

    if broker_behavior and str(broker_behavior).strip().lower() == "reject":
        return _build_result(
            status="SIM_REJECTED",
            reason="broker_reject",
            broker_status="REJECTED",
        )
    if revalidated_quote_age is not None and float(revalidated_quote_age) > float(max_age_sec):
        return _build_result(
            status="SIM_REJECTED",
            reason="stale_at_order_time",
        )

    max_spread_widen_mult = max(
        1.0,
        float(getattr(cfg, "OFFLINE_EXECUTION_SIM_MAX_SPREAD_WIDEN_MULT", 1.75) or 1.75),
    )
    max_abs_spread_pct = float(getattr(cfg, "EXECUTION_QUALITY_LIMIT_MAX_SPREAD_PCT", 0.03) or 0.03)
    spread_widened = False
    if initial_spread_pct is not None and revalidated_spread_pct is not None:
        spread_widened = revalidated_spread_pct > (initial_spread_pct * max_spread_widen_mult)
    elif revalidated_spread_pct is not None:
        spread_widened = revalidated_spread_pct > max_abs_spread_pct
    if spread_widened:
        return _build_result(
            status="SIM_REJECTED",
            reason="spread_widened",
        )

    candidate_payload = dict(revalidated)
    bid_val = _safe_float(_snapshot_value(revalidated, "bid", "best_bid", "opt_bid"))
    ask_val = _safe_float(_snapshot_value(revalidated, "ask", "best_ask", "opt_ask"))
    if bid_val is not None:
        candidate_payload["best_bid"] = bid_val
        candidate_payload["opt_bid"] = bid_val
    if ask_val is not None:
        candidate_payload["best_ask"] = ask_val
        candidate_payload["opt_ask"] = ask_val
    if bid_val is not None and ask_val is not None:
        mid_val = (bid_val + ask_val) / 2.0
        candidate_payload.setdefault("opt_ltp", mid_val)
        candidate_payload.setdefault("current_ltp", mid_val)
    if _candidate_get(candidate, "execution_entry") is not None:
        candidate_payload["execution_entry"] = _candidate_get(candidate, "execution_entry")
    if _candidate_get(candidate, "execution_entry_status") is not None:
        candidate_payload["execution_entry_status"] = _candidate_get(candidate, "execution_entry_status")
    if _candidate_get(candidate, "data_state") is not None:
        candidate_payload["data_state"] = _candidate_get(candidate, "data_state")
    if _candidate_get(candidate, "fresh_quote_ok") is not None:
        candidate_payload["fresh_quote_ok"] = _candidate_get(candidate, "fresh_quote_ok")
    if _candidate_get(candidate, "liquidity_ok") is not None:
        candidate_payload["liquidity_ok"] = _candidate_get(candidate, "liquidity_ok")
    if _candidate_get(candidate, "spread_ok") is not None:
        candidate_payload["spread_ok"] = _candidate_get(candidate, "spread_ok")
    if _candidate_get(candidate, "data_confidence") is not None:
        candidate_payload["data_confidence"] = _candidate_get(candidate, "data_confidence")
    if _candidate_get(candidate, "planning_only") is not None:
        candidate_payload["planning_only"] = _candidate_get(candidate, "planning_only")
    if _candidate_get(candidate, "source_flags") is not None:
        candidate_payload["source_flags"] = _candidate_get(candidate, "source_flags")
    candidate_payload.setdefault("quote_ok", True)
    execution_quality = evaluate_pretrade_execution_quality(candidate_payload)
    execution_score = max(
        0.0,
        min(
            1.0,
            1.0 - (
                float(execution_quality.spread_penalty or 0.0)
                / max(float(getattr(cfg, "EXECUTION_QUALITY_MAX_SCORE_PENALTY", 0.22) or 0.22), 1e-6)
            ),
        ),
    )
    if not bool(execution_quality.execution_ok):
        return _build_result(
            status="SIM_REJECTED",
            reason=str(execution_quality.reason_code or "execution_quality_reject"),
            execution_score=round(execution_score, 6),
            details={"order_policy": execution_quality.order_policy},
        )

    if limit_price is None or limit_price <= 0:
        return _build_result(
            status="SIM_REJECTED",
            reason="missing_execution_entry",
            execution_score=round(execution_score, 6),
        )

    base_rr = _rr(
        _safe_float(_candidate_get(candidate, "entry_price")) or limit_price,
        _safe_float(_candidate_get(candidate, "stop_loss")),
        _safe_float(_candidate_get(candidate, "target")),
        side,
    )
    touch_price = _safe_float(revalidated.get("ask") if side == "BUY" else revalidated.get("bid"))
    if touch_price is None:
        touch_price = _safe_float(execution_quality.executable_price_estimate) or limit_price
    rr_with_revalidated_price = _rr(
        touch_price,
        _safe_float(_candidate_get(candidate, "stop_loss")),
        _safe_float(_candidate_get(candidate, "target")),
        side,
    )
    rr_collapse_pct = max(
        0.0,
        float(getattr(cfg, "OFFLINE_EXECUTION_SIM_MAX_RR_COLLAPSE_PCT", 0.30) or 0.30),
    )
    if (
        base_rr is not None
        and rr_with_revalidated_price is not None
        and rr_with_revalidated_price < (base_rr * max(0.0, 1.0 - rr_collapse_pct))
    ):
        if touch_price is not None:
            return _build_result(
                status="SIM_REPRICED",
                reason="rr_collapsed_reprice",
                repriced_limit_price=round(float(touch_price), 4),
                execution_score=round(execution_score, 6),
            )
        return _build_result(
            status="SIM_CANCELLED",
            reason="rr_collapsed",
            execution_score=round(execution_score, 6),
        )

    order = {
        "symbol": str(_candidate_get(candidate, "symbol") or revalidated.get("symbol") or "UNKNOWN"),
        "side": side,
        "qty": requested_qty,
        "limit_price": float(limit_price),
    }
    fill_model = FillModel()
    fill_result = fill_model.simulate(
        order,
        {
            "bid": _safe_float(revalidated.get("bid")),
            "ask": _safe_float(revalidated.get("ask")),
            "bid_qty": _safe_float(revalidated.get("bid_qty")),
            "ask_qty": _safe_float(revalidated.get("ask_qty")),
            "volume": _safe_float(revalidated.get("volume")),
            "oi": _safe_float(revalidated.get("oi")),
            "vol_z": _safe_float(revalidated.get("vol_z")),
            "spread_pct": revalidated_spread_pct,
        },
        run_id or str(_candidate_get(candidate, "trade_id") or "offline-sim"),
    )
    fill_status = str(fill_result.get("status") or "NOFILL")
    fill_qty = int(max(_safe_float(fill_result.get("fill_qty")) or 0, 0))
    partial_fill_allowed = bool(
        allow_partial_fill if allow_partial_fill is not None else getattr(cfg, "OFFLINE_EXECUTION_SIM_ALLOW_PARTIAL_FILL", True)
    )
    partial_fill_min_ratio = max(
        0.0,
        float(getattr(cfg, "OFFLINE_EXECUTION_SIM_PARTIAL_FILL_MIN_RATIO", 0.25) or 0.25),
    )
    if stochastic_enabled and fill_status in {"FILLED", "PARTIAL"} and slippage_noise_bps:
        fill_price = _safe_float(fill_result.get("fill_price"))
        if fill_price is not None:
            price_noise = float(fill_price) * (float(slippage_noise_bps) / 10000.0)
            noisy_fill = float(fill_price) + price_noise if side == "BUY" else float(fill_price) - price_noise
            fill_result["fill_price"] = round(float(noisy_fill), 4)
            if _safe_float(fill_result.get("slippage_bp")) is not None:
                fill_result["slippage_bp"] = round(float(fill_result.get("slippage_bp")) + float(slippage_noise_bps), 4)
    if fill_status == "PARTIAL":
        if not partial_fill_allowed:
            return _build_result(
                status="SIM_CANCELLED",
                reason="partial_fill_not_allowed",
                fill_status=fill_status,
                fill_qty=fill_qty,
                execution_score=round(execution_score, 6),
            )
        if requested_qty > 0 and (float(fill_qty) / float(requested_qty)) < partial_fill_min_ratio:
            return _build_result(
                status="SIM_CANCELLED",
                reason="partial_fill_too_small",
                fill_status=fill_status,
                fill_qty=fill_qty,
                execution_score=round(execution_score, 6),
            )
    if fill_status in {"FILLED", "PARTIAL"}:
        status = "SIM_PARTIAL_FILL" if fill_status == "PARTIAL" and partial_fill_allowed else "SIM_EXECUTED"
        return _build_result(
            status=status,
            reason="filled",
            fill_status=fill_status,
            fill_qty=fill_qty,
            fill_price=_safe_float(fill_result.get("fill_price")),
            execution_score=round(execution_score, 6),
            details={"slippage_bp": _safe_float(fill_result.get("slippage_bp"))},
        )
    if execution_quality.executable_price_estimate is not None:
        return _build_result(
            status="SIM_REPRICED",
            reason=str(fill_result.get("reason") or "reprice_required"),
            repriced_limit_price=round(float(execution_quality.executable_price_estimate), 4),
            execution_score=round(execution_score, 6),
        )
    return _build_result(
        status="SIM_CANCELLED",
        reason=str(fill_result.get("reason") or "cross_not_met"),
        fill_status=fill_status,
        execution_score=round(execution_score, 6),
    )
