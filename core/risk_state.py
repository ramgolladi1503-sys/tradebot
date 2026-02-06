import time
from collections import deque
from datetime import date
from config import config as cfg


class RiskState:
    """
    Unified risk state for live trading decisions.
    Tracks drawdown, PnL, volatility shock, regime flip frequency,
    fill ratio decay, model drift, strategy heat, and CVaR.
    """
    def __init__(self, start_capital=0.0):
        self.start_capital = float(start_capital)
        self.mode = "NORMAL"  # NORMAL | SOFT_HALT | HARD_HALT | RECOVERY_MODE
        self.last_mode_reason = ""
        self.quarantined = set()

        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.equity = float(start_capital)
        self._current_day = date.today()
        self.daily_equity_high = float(start_capital)
        self.all_time_equity_high = float(start_capital)
        self.daily_max_drawdown = 0.0
        self.all_time_max_drawdown = 0.0

        self.vol_shock_index = 0.0
        self.regime_last = {}
        self.regime_flip_ts = deque(maxlen=2000)
        self.regime_flip_freq = 0.0

        self.fill_ratio_ewma = None
        self.fill_decay_alpha = float(getattr(cfg, "FILL_DECAY_ALPHA", 0.2))

        self.model_drift_metrics = {}

        self.strategy_heat = {}
        self.strategy_heat_decay = float(getattr(cfg, "STRATEGY_HEAT_DECAY", 0.98))
        self.strategy_heat_limit = float(getattr(cfg, "STRATEGY_HEAT_LIMIT", 2.5))

        self.cvar_alpha = float(getattr(cfg, "RISK_CVAR_ALPHA", 0.95))
        self.trade_pnls = deque(maxlen=int(getattr(cfg, "RISK_CVAR_WINDOW", 200)))
        self.cvar = 0.0

    # -------------------------
    # State updates
    # -------------------------
    def update_portfolio(self, portfolio):
        self._reset_daily_if_needed()
        capital = float(portfolio.get("capital", self.equity))
        # Note: capital reflects reserved risk; treat as realized PnL proxy
        self.realized_pnl = capital - self.start_capital
        self.equity = capital + self.unrealized_pnl
        self._update_drawdown()
        self._evaluate_halts()

    def update_unrealized(self, unrealized_pnl):
        self._reset_daily_if_needed()
        self.unrealized_pnl = float(unrealized_pnl or 0.0)
        self.equity = (self.start_capital + self.realized_pnl) + self.unrealized_pnl
        self._update_drawdown()
        self._evaluate_halts()

    def update_market(self, symbol, market_data):
        vol_z = market_data.get("vol_z")
        atr = market_data.get("atr", 0) or 0
        ltp = market_data.get("ltp", 0) or 0
        atr_pct = (atr / ltp) if ltp else 0
        shock = abs(vol_z) if vol_z is not None else atr_pct * 100.0
        self.vol_shock_index = round(float(shock), 4)

        regime = market_data.get("regime") or market_data.get("regime_day")
        last = self.regime_last.get(symbol)
        if regime and last and regime != last:
            self.regime_flip_ts.append(time.time())
        if regime:
            self.regime_last[symbol] = regime
        self._compute_regime_flip_freq()

    def record_trade_attempt(self, trade):
        strategy = getattr(trade, "strategy", None)
        if strategy:
            self.strategy_heat[strategy] = self.strategy_heat.get(strategy, 0.0) * self.strategy_heat_decay

    def record_fill(self, filled: bool):
        obs = 1.0 if filled else 0.0
        if self.fill_ratio_ewma is None:
            self.fill_ratio_ewma = obs
        else:
            a = self.fill_decay_alpha
            self.fill_ratio_ewma = round((a * obs) + ((1 - a) * self.fill_ratio_ewma), 4)
        self._evaluate_halts()

    def record_realized_pnl(self, strategy, pnl):
        pnl = float(pnl or 0.0)
        self.trade_pnls.append(pnl)
        if strategy:
            heat = self.strategy_heat.get(strategy, 0.0)
            if pnl < 0:
                heat += abs(pnl)
            else:
                heat = max(0.0, heat - pnl * 0.5)
            self.strategy_heat[strategy] = heat
            if heat >= self.strategy_heat_limit:
                self.quarantine_strategy(strategy, reason="strategy_heat_limit")
        self._compute_cvar()
        self._evaluate_halts()

    def update_model_drift(self, metrics: dict | None):
        self.model_drift_metrics = metrics or {}
        # Soft halt on model drift if configured
        drift_threshold = float(getattr(cfg, "MODEL_DRIFT_THRESHOLD", 0.0))
        if drift_threshold:
            acc = self.model_drift_metrics.get("accuracy")
            if acc is not None and acc < drift_threshold:
                self.set_mode("SOFT_HALT", "model_drift")

    # -------------------------
    # Approvals & modes
    # -------------------------
    def approve(self, trade):
        if self.mode == "HARD_HALT":
            return False, "hard_halt"
        strategy = getattr(trade, "strategy", None)
        if strategy and strategy in self.quarantined:
            return False, "strategy_quarantined"
        if self.mode == "RECOVERY_MODE":
            instr = getattr(trade, "instrument", "")
            if instr == "SPREAD" or "SPREAD" in str(strategy):
                return True, "recovery_ok"
            return False, "recovery_mode_only_spreads"
        if self.mode == "SOFT_HALT":
            if strategy in ("SCALP", "ZERO_HERO", "ZERO_HERO_EXPIRY") or str(strategy).startswith("QUICK"):
                return False, "soft_halt_block_aggressive"
        return True, "ok"

    def quarantine_strategy(self, strategy_id, reason=""):
        if strategy_id:
            self.quarantined.add(strategy_id)

    def unquarantine_strategy(self, strategy_id):
        if strategy_id in self.quarantined:
            self.quarantined.remove(strategy_id)

    def set_mode(self, mode, reason=""):
        self.mode = mode
        self.last_mode_reason = reason or self.last_mode_reason

    # -------------------------
    # Internal helpers
    # -------------------------
    def _reset_daily_if_needed(self):
        today = date.today()
        if today != self._current_day:
            self._current_day = today
            self.daily_equity_high = self.equity
            self.daily_max_drawdown = 0.0

    def _update_drawdown(self):
        if self.equity > self.all_time_equity_high:
            self.all_time_equity_high = self.equity
        if self.equity > self.daily_equity_high:
            self.daily_equity_high = self.equity
        dd_all = (self.equity - self.all_time_equity_high) / max(self.all_time_equity_high, 1.0)
        dd_day = (self.equity - self.daily_equity_high) / max(self.daily_equity_high, 1.0)
        self.all_time_max_drawdown = min(self.all_time_max_drawdown, dd_all)
        self.daily_max_drawdown = min(self.daily_max_drawdown, dd_day)

    def _compute_regime_flip_freq(self):
        now = time.time()
        window = 3600
        self.regime_flip_ts = deque([t for t in self.regime_flip_ts if now - t <= window], maxlen=2000)
        self.regime_flip_freq = round(len(self.regime_flip_ts) / (window / 3600.0), 4)

    def _compute_cvar(self):
        if not self.trade_pnls:
            self.cvar = 0.0
            return
        pnls = sorted(self.trade_pnls)
        k = max(1, int(len(pnls) * (1 - self.cvar_alpha)))
        tail = pnls[:k]
        self.cvar = round(sum(tail) / len(tail), 6)

    def _evaluate_halts(self):
        hard_dd = float(getattr(cfg, "RISK_HARD_DD", -0.05))
        soft_dd = float(getattr(cfg, "RISK_SOFT_DD", -0.02))
        cvar_limit = float(getattr(cfg, "RISK_CVAR_LIMIT", -0.02))
        fill_min = float(getattr(cfg, "RISK_MIN_FILL_RATIO", 0.5))
        vol_shock = float(getattr(cfg, "RISK_VOL_SHOCK", 2.0))

        if self.all_time_max_drawdown <= hard_dd or self.cvar <= cvar_limit:
            self.set_mode("HARD_HALT", "drawdown_or_cvar")
            return

        if self.daily_max_drawdown <= soft_dd:
            self.set_mode("SOFT_HALT", "daily_drawdown")
            return

        if self.fill_ratio_ewma is not None and self.fill_ratio_ewma < fill_min:
            self.set_mode("SOFT_HALT", "fill_ratio_decay")
            return

    def to_dict(self):
        return {
            "mode": self.mode,
            "last_mode_reason": self.last_mode_reason,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "equity": self.equity,
            "daily_max_drawdown": self.daily_max_drawdown,
            "all_time_max_drawdown": self.all_time_max_drawdown,
            "vol_shock_index": self.vol_shock_index,
            "regime_flip_freq": self.regime_flip_freq,
            "fill_ratio_ewma": self.fill_ratio_ewma,
            "model_drift_metrics": self.model_drift_metrics,
            "strategy_heat": self.strategy_heat,
            "cvar": self.cvar,
            "quarantined": list(self.quarantined),
        }

        if self.vol_shock_index >= vol_shock:
            self.set_mode("SOFT_HALT", "vol_shock")
            return

        if self.mode in ("SOFT_HALT", "HARD_HALT"):
            self.set_mode("NORMAL", "recovered")
