from config import config as cfg
from core.risk_utils import to_pct
from core.exposure_ledger import estimate_trade_exposure, estimate_trade_greeks
from core.position_sizer import PositionSizer
import logging

logger = logging.getLogger(__name__)

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
        ml_proba, confluence = self._extract_confidence_inputs(trade)
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
            "confluence_score": confluence,
            "confidence_size_multiplier": result.confidence_multiplier,
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
            proba = trade.get("confidence")
            detail = trade.get("trade_score_detail") or {}
            score = trade.get("trade_score")
            alignment = trade.get("trade_alignment")
        else:
            proba = getattr(trade, "confidence", None)
            detail = getattr(trade, "trade_score_detail", {}) or {}
            score = getattr(trade, "trade_score", None)
            alignment = getattr(trade, "trade_alignment", None)

        confluence = detail.get("confluence_score")
        if confluence is None:
            raw_score = score if score is not None else detail.get("score")
            raw_align = alignment if alignment is not None else detail.get("alignment")
            if raw_score is None and raw_align is None:
                confluence = None
            else:
                try:
                    score_val = float(raw_score or 0.0)
                    align_val = float(raw_align or 0.0)
                    confluence = max(0.0, min(1.0, ((0.6 * score_val) + (0.4 * align_val)) / 100.0))
                except (TypeError, ValueError):
                    confluence = None
        try:
            proba = float(proba) if proba is not None else None
        except (TypeError, ValueError):
            proba = None
        try:
            confluence = float(confluence) if confluence is not None else None
        except (TypeError, ValueError):
            confluence = None
        return proba, confluence
