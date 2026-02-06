from config import config as cfg

class RiskEngine:
    def __init__(self, risk_state=None):
        self.risk_state = risk_state
        self.max_daily_loss = getattr(cfg, "MAX_DAILY_LOSS", 0.15)
        self.max_trades = getattr(cfg, "MAX_TRADES_PER_DAY", 5)
        self.max_risk_per_trade = getattr(cfg, "MAX_RISK_PER_TRADE", 0.03)
        self.max_risk_eq = getattr(cfg, "MAX_RISK_PER_TRADE_EQ", 0.02)
        self.max_risk_fut = getattr(cfg, "MAX_RISK_PER_TRADE_FUT", 0.03)
        self.max_risk_opt = getattr(cfg, "MAX_RISK_PER_TRADE_OPT", 0.03)
        # Apply risk profile overrides (if any)
        try:
            profile = getattr(cfg, "RISK_PROFILE", "").upper()
            profs = getattr(cfg, "RISK_PROFILES", {})
            if profile in profs:
                p = profs[profile]
                if "max_daily_loss" in p:
                    self.max_daily_loss = p["max_daily_loss"]
                if "max_trades" in p:
                    self.max_trades = p["max_trades"]
                if "risk_per_trade" in p:
                    self.max_risk_per_trade = p["risk_per_trade"]
                    self.max_risk_eq = p["risk_per_trade"]
                    self.max_risk_fut = p["risk_per_trade"]
                    self.max_risk_opt = p["risk_per_trade"]
        except Exception:
            pass

    def allow_trade(self, portfolio):
        if self.risk_state and self.risk_state.mode == "HARD_HALT":
            return False, "RiskState hard halt"
        # Daily profit lock
        try:
            if portfolio.get("daily_profit", 0) >= getattr(cfg, "DAILY_PROFIT_LOCK", 0.012):
                return False, "Daily profit lock hit"
        except Exception:
            pass
        if portfolio.get("daily_loss", 0) <= -abs(self.max_daily_loss):
            return False, "Daily loss limit hit"
        # Per-symbol daily profit lock
        try:
            symbol_profits = portfolio.get("symbol_profit", {})
            for sym, pnl in symbol_profits.items():
                if pnl >= getattr(cfg, "SYMBOL_DAILY_PROFIT_LOCK", 0.006):
                    return False, f"Symbol profit lock hit for {sym}"
        except Exception:
            pass
        # Daily drawdown lock (from equity high)
        try:
            eq_high = portfolio.get("equity_high", portfolio.get("capital", 0))
            cap = portfolio.get("capital", 0)
            if eq_high and (cap - eq_high) / max(1.0, eq_high) <= getattr(cfg, "DAILY_DRAWNDOWN_LOCK", -0.01):
                return False, "Daily drawdown lock hit"
        except Exception:
            pass

        if portfolio.get("trades_today", 0) >= self.max_trades:
            return False, "Trade count exceeded"

        return True, "OK"

    def size_trade(self, trade, capital, lot_size, current_vol=None, loss_streak=0, vol_target=None):
        instr = None
        try:
            if isinstance(trade, dict):
                instr = trade.get("instrument")
            else:
                instr = getattr(trade, "instrument", None)
        except Exception:
            instr = None
        instr = instr or "OPT"
        if instr == "EQ":
            risk_budget = capital * self.max_risk_eq
        elif instr == "FUT":
            risk_budget = capital * self.max_risk_fut
        else:
            risk_budget = capital * self.max_risk_opt
        # Day-type risk multiplier
        day_type = getattr(trade, "day_type", "UNKNOWN")
        mult = getattr(cfg, "DAYTYPE_RISK_MULT", {}).get(day_type, 1.0)
        risk_budget *= mult
        if current_vol and current_vol > 0:
            target = vol_target or getattr(cfg, "VOL_TARGET", 0.002)
            scale = target / current_vol
            risk_budget *= max(0.5, min(1.5, scale))
        if loss_streak >= getattr(cfg, "LOSS_STREAK_CAP", 3):
            risk_budget *= getattr(cfg, "LOSS_STREAK_RISK_MULT", 0.6)
        # Optional size multiplier from alpha ensemble / policy layer
        try:
            size_mult = getattr(trade, "size_mult", None)
            if size_mult is None and isinstance(trade, dict):
                size_mult = trade.get("size_mult")
            if size_mult:
                risk_budget *= float(size_mult)
        except Exception:
            pass
        per_lot_risk = max(trade.entry_price - trade.stop_loss, 0.01) * lot_size
        if per_lot_risk <= 0:
            return 1
        lots = int(risk_budget // per_lot_risk)
        return max(1, lots)
