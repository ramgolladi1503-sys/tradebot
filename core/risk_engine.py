import logging
from dataclasses import dataclass, field
from typing import Any

from config import config as cfg
from core.decision_authority import apply_stage_authority
from core.exposure_ledger import estimate_trade_exposure, estimate_trade_greeks
from core.position_sizer import PositionSizer
from core.threshold_audit import classify_rejection_metadata
from core.risk_utils import to_pct

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "None"):
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def adjust_system_aggressiveness(metrics: dict[str, Any] | None) -> str:
    payload = dict(metrics or {})
    risk_policy = cfg.get_risk_policy()
    survival_rate = max(0.0, min(1.0, float(_safe_float(payload.get("survival_rate"), 0.0) or 0.0)))
    no_trade_rate = max(0.0, min(1.0, float(_safe_float(payload.get("no_trade_rate"), 0.0) or 0.0)))
    if survival_rate < float(risk_policy.get("aggressiveness_too_timid_survival_rate", 0.10) or 0.10):
        return "TOO_TIMID"
    if no_trade_rate > float(risk_policy.get("aggressiveness_starving_no_trade_rate", 0.70) or 0.70):
        return "STARVING"
    if survival_rate > float(risk_policy.get("aggressiveness_overtrading_survival_rate", 0.50) or 0.50):
        return "OVERTRADING"
    return "NORMAL"


def _family_key(strategy_family: Any, direction_family: Any) -> str:
    strategy = str(strategy_family or "unknown").strip().lower() or "unknown"
    direction = str(direction_family or "unknown").strip().lower() or "unknown"
    return f"{strategy}|{direction}"


def _lookup_offline_risk_learning(
    strategy_family: Any,
    direction_family: Any,
    *,
    family_learning_state: dict[str, Any] | None = None,
) -> tuple[float, float]:
    if not bool(getattr(cfg, "OFFLINE_RISK_LEARNING_ENABLE", True)):
        return 0.0, 0.0
    state = family_learning_state
    if state is None:
        try:
            from core.offline_family_learning import load_family_learning_state

            state = load_family_learning_state()
        except Exception:
            state = None
    row = (((state or {}).get("families") or {}) or {}).get(_family_key(strategy_family, direction_family))
    if not isinstance(row, dict):
        return 0.0, 0.0
    sample_count = int(row.get("sample_count") or 0)
    min_samples = max(1, int(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", 25) or 25))
    if sample_count < min_samples:
        return 0.0, 0.0
    family_confidence = _clamp01(_safe_float(row.get("family_confidence"), 0.0), default=0.0)
    shrinkage = float(sample_count) / float(sample_count + min_samples)
    expectancy_component = max(-1.0, min(1.0, float(_safe_float(row.get("expectancy_score"), 0.0) or 0.0)))
    realized_r_component = max(
        -1.0,
        min(1.0, float(_safe_float(row.get("median_realized_r_multiple"), 0.0) or 0.0) / 2.0),
    )
    mae_component = -max(
        0.0,
        min(1.0, abs(min(float(_safe_float(row.get("median_mae"), 0.0) or 0.0), 0.0))),
    )
    saved_loss_component = max(
        -1.0,
        min(
            1.0,
            float(_safe_float(row.get("rejection_saved_loss_rate"), 0.0) or 0.0)
            - float(_safe_float(row.get("rejection_missed_win_rate"), 0.0) or 0.0),
        ),
    )
    weighted = (
        expectancy_component * float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_EXPECTANCY_WEIGHT", 0.36))
        + realized_r_component * float(getattr(cfg, "OFFLINE_RISK_LEARNING_R_MULTIPLE_WEIGHT", 0.35))
        + mae_component * float(getattr(cfg, "OFFLINE_RISK_LEARNING_MAE_WEIGHT", 0.40))
        + saved_loss_component * float(getattr(cfg, "OFFLINE_RISK_LEARNING_SAVED_LOSS_WEIGHT", 0.25))
    )
    adjustment = max(
        -float(getattr(cfg, "OFFLINE_RISK_LEARNING_MAX_ADJUSTMENT", 0.03) or 0.03),
        min(
            float(getattr(cfg, "OFFLINE_RISK_LEARNING_MAX_ADJUSTMENT", 0.03) or 0.03),
            float(weighted) * float(family_confidence) * float(shrinkage),
        ),
    )
    return round(float(adjustment), 6), round(float(family_confidence * shrinkage), 6)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason_code: str
    reason: str
    context: dict[str, Any] = field(default_factory=dict)

    def as_tuple(self):
        return bool(self.allowed), str(self.reason)


@dataclass(frozen=True)
class OfflineCandidateRiskAssessment:
    risk_budget_ok: bool
    risk_budget_reason: str
    max_risk_amount: float
    risk_per_trade_pct: float
    stop_distance: float | None
    risk_reward_ratio: float | None
    position_size_estimate: int
    portfolio_heat_score: float
    directional_heat: float
    family_exposure: int
    correlation_cluster: str | None
    correlation_penalty: float
    exposure_blocker: str | None
    daily_kill_switch_active: bool
    regime_failure_throttle: float
    family_failure_throttle: float
    risk_learning_adjustment: float
    risk_learning_confidence: float
    rejected_at_stage: str | None = None
    rejection_reason_code: str | None = None
    rejection_bucket: str | None = None
    rejection_severity: str | None = None
    stage_authority_warning: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_budget_ok": bool(self.risk_budget_ok),
            "risk_budget_reason": str(self.risk_budget_reason),
            "max_risk_amount": float(self.max_risk_amount),
            "risk_per_trade_pct": float(self.risk_per_trade_pct),
            "stop_distance": self.stop_distance,
            "risk_reward_ratio": self.risk_reward_ratio,
            "position_size_estimate": int(self.position_size_estimate),
            "portfolio_heat_score": float(self.portfolio_heat_score),
            "directional_heat": float(self.directional_heat),
            "family_exposure": int(self.family_exposure),
            "correlation_cluster": self.correlation_cluster,
            "correlation_penalty": float(self.correlation_penalty),
            "exposure_blocker": self.exposure_blocker,
            "daily_kill_switch_active": bool(self.daily_kill_switch_active),
            "regime_failure_throttle": float(self.regime_failure_throttle),
            "family_failure_throttle": float(self.family_failure_throttle),
            "risk_learning_adjustment": float(self.risk_learning_adjustment),
            "risk_learning_confidence": float(self.risk_learning_confidence),
            "rejected_at_stage": self.rejected_at_stage,
            "rejection_reason_code": self.rejection_reason_code,
            "rejection_bucket": self.rejection_bucket,
            "rejection_severity": self.rejection_severity,
            "stage_authority_warning": bool(self.stage_authority_warning),
            "context": dict(self.context or {}),
        }


def evaluate_candidate_risk(
    candidate: Any,
    *,
    portfolio_state: dict[str, Any] | None = None,
    selected_candidates: list[Any] | None = None,
    family_learning_state: dict[str, Any] | None = None,
) -> OfflineCandidateRiskAssessment:
    portfolio = dict(portfolio_state or {})
    selected = list(selected_candidates or [])
    risk_policy = cfg.get_risk_policy()
    entry_price = _safe_float(
        _candidate_get(candidate, "execution_entry", _candidate_get(candidate, "entry_price")),
        0.0,
    ) or 0.0
    stop_loss = _safe_float(_candidate_get(candidate, "stop_loss"))
    target = _safe_float(_candidate_get(candidate, "target"))
    stop_distance = abs(float(entry_price) - float(stop_loss)) if entry_price > 0 and stop_loss is not None else None
    reward_distance = abs(float(target) - float(entry_price)) if entry_price > 0 and target is not None else None
    risk_reward_ratio = None
    if stop_distance not in (None, 0.0) and reward_distance is not None:
        risk_reward_ratio = float(reward_distance) / max(float(stop_distance), 1e-6)

    atr = _safe_float(
        _candidate_get(candidate, "atr")
        or ((_candidate_get(candidate, "source_flags", {}) or {}).get("atr"))
        or (((_candidate_get(candidate, "score_breakdown", {}) or {}).get("quality_detail") or {}).get("atr")),
        None,
    )
    if atr is None:
        underlying_ltp = _safe_float(_candidate_get(candidate, "underlying_spot")) or _safe_float(_candidate_get(candidate, "current_ltp"))
        instrument = str(_candidate_get(candidate, "instrument") or _candidate_get(candidate, "instrument_type") or "").strip().upper()
        if instrument == "OPT":
            option_ref = max(
                _safe_float(_candidate_get(candidate, "execution_entry"), 0.0) or 0.0,
                _safe_float(_candidate_get(candidate, "entry_price"), 0.0) or 0.0,
                _safe_float(_candidate_get(candidate, "opt_ltp"), 0.0) or 0.0,
            )
            atr = max(float(option_ref or 0.0) * 0.10, float(stop_distance or 0.0) * 0.75, 1.0)
        else:
            atr = max(float(underlying_ltp or 0.0) * 0.002, 1.0)
    regime = str(_candidate_get(candidate, "regime") or portfolio.get("regime") or "NEUTRAL").strip().upper()
    direction_family = str(_candidate_get(candidate, "direction_family") or "unknown").strip().lower() or "unknown"
    strategy_family = str(_candidate_get(candidate, "strategy_family") or "unknown").strip().lower() or "unknown"
    symbol = str(_candidate_get(candidate, "symbol") or "").strip().upper()
    cluster_key = f"{symbol}|{direction_family}|{strategy_family}" if symbol else None

    account_capital = max(
        1.0,
        float(_safe_float(portfolio.get("capital"), risk_policy.get("account_capital", getattr(cfg, "CAPITAL", 100000.0))) or 1.0),
    )
    risk_per_trade_pct = max(
        0.0,
        float(_safe_float(portfolio.get("risk_per_trade_pct"), risk_policy.get("risk_per_trade_pct", 0.004)) or 0.0),
    )
    max_risk_amount = float(account_capital) * float(risk_per_trade_pct)
    size_result = PositionSizer().size_from_budget(max_risk_amount, stop_distance)
    position_size_estimate = int(size_result.qty)

    risk_budget_ok = True
    risk_budget_reason = "ok"
    stop_distance_pct = (float(stop_distance) / max(float(entry_price), 1e-6)) if stop_distance not in (None, 0.0) else None
    if stop_distance in (None, 0.0):
        risk_budget_ok = False
        risk_budget_reason = "missing_stop_distance"
    elif stop_distance_pct is not None and stop_distance_pct > float(risk_policy.get("max_stop_distance_pct", 0.35) or 0.35):
        risk_budget_ok = False
        risk_budget_reason = "stop_distance_too_wide_pct"
    elif atr and float(stop_distance) > (float(atr) * float(risk_policy.get("max_stop_atr_mult", 1.80) or 1.80)):
        risk_budget_ok = False
        risk_budget_reason = "stop_distance_too_wide_atr"
    elif risk_reward_ratio is not None and float(risk_reward_ratio) < float(risk_policy.get("min_rr", 1.20) or 1.20):
        risk_budget_ok = False
        risk_budget_reason = "risk_reward_too_low"
    elif size_result.qty <= 0:
        risk_budget_ok = False
        risk_budget_reason = str(size_result.reason or "position_size_zero").strip().lower() or "position_size_zero"

    portfolio_heat_score = float(
        _safe_float(portfolio.get("open_risk_pct"), _safe_float(portfolio.get("total_open_exposure_pct"), 0.0)) or 0.0
    )
    directional_heat_map = dict(portfolio.get("directional_heat") or {})
    selected_directional_count = sum(
        1
        for row in selected
        if str(_candidate_get(row, "direction_family") or "").strip().lower() == direction_family
    )
    directional_heat = float(_safe_float(directional_heat_map.get(direction_family), 0.0) or 0.0) + (
        float(selected_directional_count) * float(risk_per_trade_pct)
    )
    family_exposure_map = dict(portfolio.get("family_exposure") or {})
    family_key = _family_key(strategy_family, direction_family)
    selected_family_count = sum(
        1
        for row in selected
        if _family_key(_candidate_get(row, "strategy_family"), _candidate_get(row, "direction_family")) == family_key
    )
    family_exposure = int(_safe_int(family_exposure_map.get(family_key), 0))

    correlation_penalty = 0.0
    if symbol:
        same_symbol_related = sum(
            1
            for row in selected
            if str(_candidate_get(row, "symbol") or "").strip().upper() == symbol
            and (
                str(_candidate_get(row, "direction_family") or "").strip().lower() == direction_family
                or str(_candidate_get(row, "strategy_family") or "").strip().lower() == strategy_family
            )
        )
        if same_symbol_related > 0:
            correlation_penalty = min(
                1.0,
                float(same_symbol_related) * float(risk_policy.get("correlation_penalty", 0.08) or 0.08),
            )

    exposure_blocker = None
    if portfolio_heat_score >= float(risk_policy.get("max_portfolio_heat", 0.025) or 0.025):
        exposure_blocker = "portfolio_heat_limit"
    elif directional_heat >= float(risk_policy.get("max_directional_heat", 0.015) or 0.015):
        exposure_blocker = "directional_heat_limit"
    elif family_exposure >= int(risk_policy.get("max_family_exposure", 1) or 1):
        exposure_blocker = "family_exposure_limit"

    daily_kill_switch_active = bool(portfolio.get("daily_kill_switch_active", False))
    daily_pnl_pct = _safe_float(portfolio.get("daily_pnl_pct"))
    if daily_pnl_pct is not None and float(daily_pnl_pct) <= -abs(float(risk_policy.get("daily_kill_switch_pct", getattr(cfg, "MAX_DAILY_LOSS_PCT", 0.02)) or 0.02)):
        daily_kill_switch_active = True

    regime_failure_count = int(
        (dict(portfolio.get("regime_failure_counts") or {})).get(regime, portfolio.get("regime_failure_count", 0)) or 0
    )
    family_failure_count = int(
        (dict(portfolio.get("family_failure_counts") or {})).get(family_key, portfolio.get("family_failure_count", 0)) or 0
    )
    session_mode = str(_candidate_get(candidate, "session_mode") or portfolio.get("session_mode") or "MIDDAY").strip().upper()
    session_failure_count = int(
        (dict(portfolio.get("session_failure_counts") or {})).get(session_mode, portfolio.get("session_failure_count", 0)) or 0
    )
    regime_failure_throttle = 0.0
    family_failure_throttle = 0.0
    if regime_failure_count >= int(risk_policy.get("regime_failure_limit", 3) or 3):
        regime_failure_throttle = float(risk_policy.get("failure_throttle_penalty", 0.12) or 0.12)
    if family_failure_count >= int(risk_policy.get("family_failure_limit", 3) or 3):
        family_failure_throttle = float(risk_policy.get("failure_throttle_penalty", 0.12) or 0.12)
    if session_failure_count >= int(risk_policy.get("session_failure_limit", 2) or 2):
        family_failure_throttle = max(
            family_failure_throttle,
            float(risk_policy.get("failure_throttle_penalty", 0.12) or 0.12) * 0.5,
        )

    risk_learning_adjustment, risk_learning_confidence = _lookup_offline_risk_learning(
        strategy_family,
        direction_family,
        family_learning_state=family_learning_state,
    )
    rejection_reason_code = None
    if daily_kill_switch_active:
        rejection_reason_code = "daily_kill_switch_active"
    elif exposure_blocker not in (None, "", "None"):
        rejection_reason_code = str(exposure_blocker)
    elif not risk_budget_ok:
        rejection_reason_code = str(risk_budget_reason)
    elif regime_failure_throttle > 0.0:
        rejection_reason_code = "regime_failure_throttle"
    elif family_failure_throttle > 0.0:
        rejection_reason_code = "family_failure_throttle"
    rejection_meta = apply_stage_authority(
        {
            "existing_rejected_at_stage": _candidate_get(candidate, "rejected_at_stage"),
            "existing_rejection_reason_code": _candidate_get(candidate, "rejection_reason_code"),
            "incoming_rejected_at_stage": None,
            "incoming_rejection_reason_code": rejection_reason_code,
        }
    )
    return OfflineCandidateRiskAssessment(
        risk_budget_ok=bool(risk_budget_ok),
        risk_budget_reason=str(risk_budget_reason),
        max_risk_amount=round(float(max_risk_amount), 6),
        risk_per_trade_pct=round(float(risk_per_trade_pct), 6),
        stop_distance=round(float(stop_distance), 6) if stop_distance not in (None, 0.0) else None,
        risk_reward_ratio=round(float(risk_reward_ratio), 6) if risk_reward_ratio is not None else None,
        position_size_estimate=int(position_size_estimate),
        portfolio_heat_score=round(float(portfolio_heat_score), 6),
        directional_heat=round(float(directional_heat), 6),
        family_exposure=int(family_exposure),
        correlation_cluster=cluster_key,
        correlation_penalty=round(float(correlation_penalty), 6),
        exposure_blocker=exposure_blocker,
        daily_kill_switch_active=bool(daily_kill_switch_active),
        regime_failure_throttle=round(float(regime_failure_throttle), 6),
        family_failure_throttle=round(float(family_failure_throttle), 6),
        risk_learning_adjustment=round(float(risk_learning_adjustment), 6),
        risk_learning_confidence=round(float(risk_learning_confidence), 6),
        rejected_at_stage=rejection_meta.get("rejected_at_stage"),
        rejection_reason_code=rejection_meta.get("rejection_reason_code"),
        rejection_bucket=rejection_meta.get("rejection_bucket"),
        rejection_severity=rejection_meta.get("rejection_severity"),
        stage_authority_warning=bool(rejection_meta.get("stage_authority_warning", False)),
        context={
            "sizing_reason": str(size_result.reason),
            "stop_distance_pct": round(float(stop_distance_pct), 6) if stop_distance_pct is not None else None,
            "session_mode": session_mode,
            "regime_failure_count": regime_failure_count,
            "family_failure_count": family_failure_count,
            "session_failure_count": session_failure_count,
            "selected_family_count": selected_family_count,
            "effective_risk_policy": dict(risk_policy),
        },
    )


class RiskEngine:
    def __init__(self, risk_state=None):
        self.risk_state = risk_state
        self.max_daily_loss_pct = getattr(cfg, "MAX_DAILY_LOSS_PCT", getattr(cfg, "MAX_DAILY_LOSS", 0.15))
        self.max_trades = getattr(cfg, "MAX_TRADES_PER_DAY", 5)
        self.max_risk_per_trade = getattr(cfg, "MAX_RISK_PER_TRADE_PCT", getattr(cfg, "MAX_RISK_PER_TRADE", 0.03))
        self.risk_per_trade_pct = float(getattr(cfg, "RISK_PER_TRADE_PCT", self.max_risk_per_trade))
        self.max_open_risk_pct = getattr(cfg, "MAX_OPEN_RISK_PCT", 0.02)
        self.max_net_delta = float(getattr(cfg, "MAX_NET_DELTA", 200.0))
        self.max_net_vega = float(getattr(cfg, "MAX_NET_VEGA", 120.0))
        self.max_risk_eq = getattr(cfg, "MAX_RISK_PER_TRADE_EQ", 0.02)
        self.max_risk_fut = getattr(cfg, "MAX_RISK_PER_TRADE_FUT", 0.03)
        self.max_risk_opt = getattr(cfg, "MAX_RISK_PER_TRADE_OPT", 0.03)
        self.position_sizer = PositionSizer()
        self.last_size_reason = "UNINITIALIZED"
        self.last_size_meta = {}
        self.last_decision = None

    @staticmethod
    def _reason_code(reason: str) -> str:
        text = str(reason or "").strip()
        if not text:
            return "UNKNOWN"
        if text.startswith("RISK_DATA_UNAVAILABLE:"):
            return text
        if text.startswith("PORTFOLIO_LIMIT:"):
            return text
        mapping = {
            "OK": "OK",
            "RiskState hard halt": "RISKSTATE_HARD_HALT",
            "Daily profit lock hit": "DAILY_PROFIT_LOCK_HIT",
            "Daily loss limit hit": "DAILY_LOSS_LIMIT_HIT",
            "Trade count exceeded": "TRADE_COUNT_EXCEEDED",
            "Open risk limit hit": "OPEN_RISK_LIMIT_HIT",
            "Daily drawdown lock hit": "DAILY_DRAWDOWN_LOCK_HIT",
        }
        return mapping.get(text, text.upper().replace(" ", "_"))

    def _resolve_regime(self, portfolio, regime=None, trade=None):
        if regime:
            return str(regime).upper()
        if trade is not None:
            tr = getattr(trade, "regime", None)
            if tr:
                return str(tr).upper()
        if isinstance(portfolio, dict):
            pr = portfolio.get("primary_regime") or portfolio.get("regime")
            if pr:
                return str(pr).upper()
        return "NEUTRAL"

    def _daily_loss_mult_for_regime(self, regime: str) -> float:
        if regime == "EVENT":
            return float(getattr(cfg, "REGIME_EVENT_DAILY_LOSS_MULT", 0.5))
        if regime == "TREND":
            return float(getattr(cfg, "REGIME_TREND_DAILY_LOSS_MULT", 1.0))
        if regime in ("RANGE", "RANGE_VOLATILE"):
            return float(getattr(cfg, "REGIME_RANGE_DAILY_LOSS_MULT", 1.0))
        return 1.0

    def _open_risk_mult_for_regime(self, regime: str) -> float:
        if regime == "EVENT":
            return float(getattr(cfg, "REGIME_EVENT_OPEN_RISK_MULT", 0.6))
        if regime == "TREND":
            return float(getattr(cfg, "REGIME_TREND_OPEN_RISK_MULT", 1.0))
        if regime in ("RANGE", "RANGE_VOLATILE"):
            return float(getattr(cfg, "REGIME_RANGE_OPEN_RISK_MULT", 1.0))
        return 1.0

    def _max_trades_mult_for_regime(self, regime: str) -> float:
        if regime == "EVENT":
            return float(getattr(cfg, "REGIME_EVENT_MAX_TRADES_MULT", 0.6))
        if regime == "TREND":
            return float(getattr(cfg, "REGIME_TREND_MAX_TRADES_MULT", 1.0))
        if regime in ("RANGE", "RANGE_VOLATILE"):
            return float(getattr(cfg, "REGIME_RANGE_MAX_TRADES_MULT", 1.0))
        return 1.0

    def _size_mult_for_regime(self, regime: str) -> float:
        if regime == "EVENT":
            return float(getattr(cfg, "REGIME_EVENT_SIZE_MULT", 0.6))
        if regime == "TREND":
            return float(getattr(cfg, "REGIME_TREND_SIZE_MULT", 1.0))
        if regime in ("RANGE", "RANGE_VOLATILE"):
            return float(getattr(cfg, "REGIME_RANGE_SIZE_MULT", 1.0))
        return 1.0

    def _block(self, reason: str, context: dict | None = None):
        payload = {"reason": reason}
        if context:
            payload.update(context)
        logger.error("[RISK_ENGINE_BLOCK] %s", payload)
        return False, reason

    def _coerce_float(self, value, field: str):
        try:
            return float(value), None
        except (TypeError, ValueError):
            reason = f"RISK_DATA_UNAVAILABLE:{field}"
            return None, reason

    def _required_daily_pnl_pct(self, portfolio):
        raw_pct = portfolio.get("daily_pnl_pct", None)
        if raw_pct is not None:
            pct_val, err = self._coerce_float(raw_pct, "daily_pnl_pct")
            if err:
                return None, err
            return pct_val, None

        daily_profit = portfolio.get("daily_profit", None)
        daily_loss = portfolio.get("daily_loss", None)
        if daily_profit is None and daily_loss is None:
            return None, "RISK_DATA_UNAVAILABLE:daily_pnl_pct"

        profit_val, err = self._coerce_float(daily_profit or 0.0, "daily_profit")
        if err:
            return None, err
        loss_val, err = self._coerce_float(daily_loss or 0.0, "daily_loss")
        if err:
            return None, err
        equity_high = portfolio.get("equity_high", portfolio.get("capital", None))
        equity_val, err = self._coerce_float(equity_high, "equity_high")
        if err:
            return None, err
        if equity_val <= 0:
            return None, "RISK_DATA_UNAVAILABLE:equity_high"
        return to_pct(profit_val + loss_val, equity_val), None

    def _required_open_risk_pct(self, portfolio):
        raw_open_risk = portfolio.get("open_risk_pct", None)
        if raw_open_risk is None:
            return None, "RISK_DATA_UNAVAILABLE:open_risk_pct"
        return self._coerce_float(raw_open_risk, "open_risk_pct")

    def _portfolio_limit_checks(self, portfolio, trade=None, exposure_state=None, equity_high_val: float = 0.0, regime: str = "NEUTRAL"):
        if trade is None:
            return True, "OK"

        source = exposure_state if isinstance(exposure_state, dict) else portfolio
        exposure_by_underlying = source.get("exposure_by_underlying") or {}
        exposure_by_expiry = source.get("exposure_by_expiry") or {}
        count_by_underlying = source.get("open_positions_count_by_underlying") or {}
        total_open_exposure = source.get("total_open_exposure")
        if total_open_exposure is None:
            try:
                total_open_exposure = float(sum(float(v) for v in exposure_by_underlying.values()))
            except Exception:
                total_open_exposure = 0.0
        net_delta = source.get("net_delta", 0.0)
        net_vega = source.get("net_vega", 0.0)
        net_delta_val, delta_err = self._coerce_float(net_delta, "net_delta")
        if delta_err:
            return self._block(delta_err, {"check": "portfolio_net_delta"})
        net_vega_val, vega_err = self._coerce_float(net_vega, "net_vega")
        if vega_err:
            return self._block(vega_err, {"check": "portfolio_net_vega"})

        if isinstance(trade, dict):
            trade_underlying = trade.get("symbol") or trade.get("underlying")
            trade_expiry = trade.get("expiry")
        else:
            trade_underlying = getattr(trade, "symbol", None) or getattr(trade, "underlying", None)
            trade_expiry = getattr(trade, "expiry", None)
        if not trade_underlying:
            return self._block("RISK_DATA_UNAVAILABLE:trade_underlying", {"check": "portfolio_limits"})

        trade_underlying = str(trade_underlying).upper()
        try:
            trade_exposure = float(estimate_trade_exposure(trade))
        except Exception:
            trade_exposure = 0.0
        trade_delta, trade_vega = estimate_trade_greeks(trade)

        underlying_limit_pct = float(getattr(cfg, "MAX_UNDERLYING_EXPOSURE_PCT", 0.4))
        positions_limit = int(getattr(cfg, "MAX_POSITIONS_PER_UNDERLYING", 3))
        expiry_conc_limit = float(getattr(cfg, "MAX_EXPIRY_CONCENTRATION_PCT", 0.65))
        net_delta_limit = self.max_net_delta
        net_vega_limit = self.max_net_vega
        if str(regime or "").upper() == "EVENT":
            net_delta_limit *= float(getattr(cfg, "EVENT_NET_DELTA_MULT", 0.5))
            net_vega_limit *= float(getattr(cfg, "EVENT_NET_VEGA_MULT", 0.5))

        existing_underlying_exposure = float(exposure_by_underlying.get(trade_underlying, 0.0) or 0.0)
        underlying_exposure_after = existing_underlying_exposure + max(0.0, trade_exposure)
        if equity_high_val > 0 and (underlying_exposure_after / equity_high_val) > underlying_limit_pct:
            return False, "PORTFOLIO_LIMIT:UNDERLYING_EXPOSURE"

        existing_positions = int(count_by_underlying.get(trade_underlying, 0) or 0)
        if existing_positions + 1 > positions_limit:
            return False, "PORTFOLIO_LIMIT:POSITIONS_PER_UNDERLYING"

        if trade_expiry:
            trade_expiry = str(trade_expiry)
            existing_expiry_exposure = float(exposure_by_expiry.get(trade_expiry, 0.0) or 0.0)
            total_after = float(total_open_exposure or 0.0) + max(0.0, trade_exposure)
            expiry_after = existing_expiry_exposure + max(0.0, trade_exposure)
            if total_after > 0 and (expiry_after / total_after) > expiry_conc_limit:
                return False, "PORTFOLIO_LIMIT:EXPIRY_CONCENTRATION"

        if abs(net_delta_val + float(trade_delta)) > net_delta_limit:
            return False, "PORTFOLIO_LIMIT:NET_DELTA"
        if abs(net_vega_val + float(trade_vega)) > net_vega_limit:
            return False, "PORTFOLIO_LIMIT:NET_VEGA"

        return True, "OK"

    def allow_trade(self, portfolio, regime=None, trade=None, exposure_state=None):
        if self.risk_state and self.risk_state.mode == "HARD_HALT":
            return False, "RiskState hard halt"
        resolved_regime = self._resolve_regime(portfolio, regime=regime)
        daily_loss_limit = abs(self.max_daily_loss_pct) * self._daily_loss_mult_for_regime(resolved_regime)
        open_risk_limit = self.max_open_risk_pct * self._open_risk_mult_for_regime(resolved_regime)
        max_trades_limit = max(1, int(self.max_trades * self._max_trades_mult_for_regime(resolved_regime)))
        # Daily profit lock
        equity_high = portfolio.get("equity_high", portfolio.get("capital", None))
        equity_high_val, equity_err = self._coerce_float(equity_high, "equity_high")
        if equity_err:
            return self._block(equity_err, {"check": "daily_profit_lock"})
        if equity_high_val <= 0:
            return self._block("RISK_DATA_UNAVAILABLE:equity_high", {"check": "daily_profit_lock"})
        daily_profit_val, daily_profit_err = self._coerce_float(portfolio.get("daily_profit", 0.0), "daily_profit")
        if daily_profit_err:
            return self._block(daily_profit_err, {"check": "daily_profit_lock"})
        daily_profit_pct = to_pct(daily_profit_val, equity_high_val)
        if daily_profit_pct >= getattr(cfg, "DAILY_PROFIT_LOCK", 0.012):
            return False, "Daily profit lock hit"

        daily_pnl_pct, daily_pnl_err = self._required_daily_pnl_pct(portfolio)
        if daily_pnl_err:
            return self._block(daily_pnl_err, {"check": "daily_loss_limit"})
        if daily_pnl_pct <= -daily_loss_limit:
            return False, "Daily loss limit hit"
        # Per-symbol daily profit lock
        symbol_profits = portfolio.get("symbol_profit", {})
        if symbol_profits is None:
            symbol_profits = {}
        if not isinstance(symbol_profits, dict):
            return self._block("RISK_DATA_UNAVAILABLE:symbol_profit", {"check": "symbol_profit_lock"})
        for sym, pnl in symbol_profits.items():
            pnl_val, pnl_err = self._coerce_float(pnl, f"symbol_profit:{sym}")
            if pnl_err:
                return self._block(pnl_err, {"check": "symbol_profit_lock", "symbol": sym})
            pnl_pct = to_pct(pnl_val, equity_high_val)
            if pnl_pct >= getattr(cfg, "SYMBOL_DAILY_PROFIT_LOCK", 0.006):
                return False, f"Symbol profit lock hit for {sym}"
        # Daily drawdown lock (from equity high)
        cap_val, cap_err = self._coerce_float(portfolio.get("capital", None), "capital")
        if cap_err:
            return self._block(cap_err, {"check": "daily_drawdown_lock"})
        if (cap_val - equity_high_val) / max(1.0, equity_high_val) <= getattr(cfg, "DAILY_DRAWNDOWN_LOCK", -0.01):
            return False, "Daily drawdown lock hit"

        if portfolio.get("trades_today", 0) >= max_trades_limit:
            return False, "Trade count exceeded"

        open_risk_pct, open_risk_err = self._required_open_risk_pct(portfolio)
        if open_risk_err:
            return self._block(open_risk_err, {"check": "open_risk_limit"})
        if open_risk_pct >= open_risk_limit:
            return False, "Open risk limit hit"

        portfolio_ok, portfolio_reason = self._portfolio_limit_checks(
            portfolio,
            trade=trade,
            exposure_state=exposure_state,
            equity_high_val=equity_high_val,
            regime=resolved_regime,
        )
        if not portfolio_ok:
            return False, portfolio_reason

        return True, "OK"

    def evaluate_trade(self, portfolio, regime=None, trade=None, exposure_state=None) -> RiskDecision:
        allowed, reason = self.allow_trade(
            portfolio,
            regime=regime,
            trade=trade,
            exposure_state=exposure_state,
        )
        decision = RiskDecision(
            allowed=bool(allowed),
            reason_code=self._reason_code(str(reason)),
            reason=str(reason),
            context={
                "regime": self._resolve_regime(portfolio if isinstance(portfolio, dict) else {}, regime=regime, trade=trade),
                "has_trade": bool(trade is not None),
                "has_exposure_state": bool(isinstance(exposure_state, dict)),
            },
        )
        self.last_decision = decision
        return decision

    def size_trade(self, trade, capital, lot_size, current_vol=None, loss_streak=0, vol_target=None):
        self.last_size_reason = "UNINITIALIZED"
        self.last_size_meta = {}
        capital_val, cap_err = self._coerce_float(capital, "capital")
        if cap_err or capital_val is None or capital_val <= 0:
            self.last_size_reason = "SIZING_BLOCK:INVALID_CAPITAL"
            return 0

        risk_budget = capital_val * self.risk_per_trade_pct
        regime = self._resolve_regime({}, trade=trade)
        risk_budget *= self.position_sizer.regime_multiplier(regime)

        if self.risk_state:
            risk_budget *= float(self.risk_state.risk_budget_multiplier())

        day_type = getattr(trade, "day_type", "UNKNOWN")
        risk_budget *= float(getattr(cfg, "DAYTYPE_RISK_MULT", {}).get(day_type, 1.0))

        if current_vol and current_vol > 0:
            target = vol_target or getattr(cfg, "VOL_TARGET", 0.002)
            scale = target / current_vol
            risk_budget *= max(0.5, min(1.5, scale))
        if loss_streak >= getattr(cfg, "LOSS_STREAK_CAP", 3):
            risk_budget *= float(getattr(cfg, "LOSS_STREAK_RISK_MULT", 0.6))

        size_mult = getattr(trade, "size_mult", None)
        if size_mult is None and isinstance(trade, dict):
            size_mult = trade.get("size_mult")
        if size_mult is not None:
            try:
                risk_budget *= float(size_mult)
            except (TypeError, ValueError):
                logger.error(
                    "[RISK_ENGINE_DATA_ERROR] %s",
                    {"reason": "RISK_DATA_UNAVAILABLE:size_mult", "value": size_mult},
                )

        stop_distance_rupees = self._extract_stop_distance_rupees(trade, lot_size)
        ml_proba, confluence, ml_proba_source, confluence_source = self._extract_confidence_inputs(trade)
        result = self.position_sizer.size_from_budget(
            risk_budget,
            stop_distance_rupees,
            ml_proba=ml_proba,
            confluence_score=confluence,
        )
        self.last_size_reason = result.reason
        self.last_size_meta = {
            "risk_budget": result.risk_budget,
            "stop_distance_rupees": result.stop_distance_rupees,
            "effective_stop_distance": result.effective_stop_distance,
            "regime": regime,
            "ml_proba": ml_proba,
            "ml_proba_source": ml_proba_source,
            "confluence_score": confluence,
            "confluence_source": confluence_source,
            "confidence_size_multiplier": result.confidence_multiplier,
            "opportunity_score": (
                trade.get("opportunity_score") if isinstance(trade, dict) else getattr(trade, "opportunity_score", None)
            ),
            "opportunity_rank": (
                trade.get("opportunity_rank") if isinstance(trade, dict) else getattr(trade, "opportunity_rank", None)
            ),
            "selected_for_execution": (
                trade.get("selected_for_execution") if isinstance(trade, dict) else getattr(trade, "selected_for_execution", None)
            ),
            "base_qty": result.base_qty,
            "final_qty": result.qty,
        }
        return int(result.qty)

    def _extract_stop_distance_rupees(self, trade, lot_size):
        stop_distance = None
        if isinstance(trade, dict):
            stop_distance = trade.get("stop_distance")
            entry_price = trade.get("entry_price")
            stop_loss = trade.get("stop_loss")
        else:
            stop_distance = getattr(trade, "stop_distance", None)
            entry_price = getattr(trade, "entry_price", None)
            stop_loss = getattr(trade, "stop_loss", None)

        if stop_distance is None:
            try:
                if entry_price is None or stop_loss is None:
                    return None
                stop_distance = abs(float(entry_price) - float(stop_loss))
            except (TypeError, ValueError):
                return None
        try:
            stop_distance_val = float(stop_distance)
        except (TypeError, ValueError):
            return None
        if stop_distance_val <= 0:
            return None
        lot = max(float(lot_size or 1), 1.0)
        return stop_distance_val * lot

    def _extract_confidence_inputs(self, trade):
        if isinstance(trade, dict):
            proba = trade.get("builder_confidence")
            proba_source = "builder_confidence"
            if proba is None:
                proba = trade.get("confidence_raw")
                proba_source = "confidence_raw"
            if proba is None:
                proba = trade.get("confidence")
                proba_source = "confidence" if proba is not None else proba_source
            detail = trade.get("trade_score_detail") or {}
            confluence = trade.get("sizing_confluence_score")
        else:
            proba = getattr(trade, "builder_confidence", None)
            proba_source = "builder_confidence"
            if proba is None:
                proba = getattr(trade, "confidence_raw", None)
                proba_source = "confidence_raw"
            if proba is None:
                proba = getattr(trade, "confidence", None)
                proba_source = "confidence" if proba is not None else proba_source
            detail = getattr(trade, "trade_score_detail", {}) or {}
            confluence = getattr(trade, "sizing_confluence_score", None)

        confluence_source = "sizing_confluence_score"
        if confluence is None:
            confluence = detail.get("confluence_score")
            confluence_source = "trade_score_detail.confluence_score"
        try:
            proba = float(proba) if proba is not None else None
        except (TypeError, ValueError):
            proba = None
            proba_source = "unavailable"
        try:
            confluence = float(confluence) if confluence is not None else None
        except (TypeError, ValueError):
            confluence = None
            confluence_source = "unavailable"
        return proba, confluence, proba_source, confluence_source
