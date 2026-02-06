import json
from collections import defaultdict, deque
from config import config as cfg

class StrategyTracker:
    def __init__(self, max_len=200):
        self.results = defaultdict(lambda: deque(maxlen=max_len))
        self.pnl_history = defaultdict(lambda: deque(maxlen=max_len))
        self.stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})

    def record(self, strategy_name, pnl):
        if not strategy_name:
            return
        outcome = 1 if pnl > 0 else -1
        self.results[strategy_name].append(outcome)
        self.pnl_history[strategy_name].append(pnl)
        st = self.stats[strategy_name]
        st["trades"] += 1
        if pnl > 0:
            st["wins"] += 1
        else:
            st["losses"] += 1
        st["pnl"] = round(st.get("pnl", 0.0) + pnl, 2)
        st["profit_factor"] = self._profit_factor(strategy_name)
        st["max_drawdown"] = self._max_drawdown(strategy_name)
        st["sharpe"] = self._sharpe(strategy_name)
        st["sharpe_ci"] = self._sharpe_ci(strategy_name)
        st["risk_adj_pf"] = self._risk_adj_pf(strategy_name)
        st["sharpe_roll"] = self._rolling_sharpe(strategy_name, window=getattr(cfg, "STRATEGY_SHARPE_WINDOW", 30))
        st["utility"] = self._utility(strategy_name)
        st["rolling"] = self._rolling_stats(strategy_name, window=getattr(cfg, "BANDIT_WINDOW", 50))

    def win_rate(self, strategy_name):
        data = self.results.get(strategy_name, [])
        if not data:
            return 1.0
        return sum(1 for x in data if x > 0) / len(data)

    def is_disabled(self, strategy_name, min_trades=30, threshold=0.45):
        data = self.results.get(strategy_name, [])
        # If live drift auto-disable is enabled, use WF thresholds too
        wf_min_trades = getattr(cfg, "WF_MIN_TRADES", min_trades)
        min_trades_eff = max(min_trades, wf_min_trades) if getattr(cfg, "LIVE_WF_DRIFT_DISABLE", True) else min_trades
        if len(data) < min_trades_eff:
            return False
        # Live drift gating based on WF thresholds
        if getattr(cfg, "LIVE_WF_DRIFT_DISABLE", True):
            stats = self.stats.get(strategy_name, {})
            win_rate = self.win_rate(strategy_name)
            pf = stats.get("profit_factor", None)
            max_dd = stats.get("max_drawdown", 0.0)
            try:
                if pf == "inf":
                    pf_val = 9.99
                else:
                    pf_val = float(pf)
                if pf_val < getattr(cfg, "WF_MIN_PF", 1.2):
                    return True
            except Exception:
                return True
            try:
                if float(win_rate) < getattr(cfg, "WF_MIN_WIN_RATE", 0.45):
                    return True
            except Exception:
                return True
            try:
                if float(max_dd) < getattr(cfg, "WF_MAX_DD", -5000.0):
                    return True
            except Exception:
                pass
        return self.win_rate(strategy_name) < threshold

    def snapshot(self):
        return {
            "results": {k: list(v) for k, v in self.results.items()},
            "pnl_history": {k: list(v) for k, v in self.pnl_history.items()},
            "stats": self.stats
        }

    def load(self, path):
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            if "results" in raw:
                for k, v in raw["results"].items():
                    dq = deque(v, maxlen=len(v))
                    self.results[k] = dq
                for k, v in raw.get("pnl_history", {}).items():
                    dq = deque(v, maxlen=len(v))
                    self.pnl_history[k] = dq
                for k, v in raw.get("stats", {}).items():
                    self.stats[k] = v
            else:
                for k, v in raw.items():
                    dq = deque(v, maxlen=len(v))
                    self.results[k] = dq
        except Exception:
            pass

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.snapshot(), f, indent=2)

    def record_symbol(self, symbol, pnl):
        if not symbol:
            return
        key = f"SYMBOL::{symbol}"
        self.record(key, pnl)

    def _profit_factor(self, strategy_name):
        pnl_list = list(self.pnl_history.get(strategy_name, []))
        gains = sum(p for p in pnl_list if p > 0)
        losses = abs(sum(p for p in pnl_list if p < 0))
        return round(gains / losses, 3) if losses else "inf"

    def _max_drawdown(self, strategy_name):
        pnl_list = list(self.pnl_history.get(strategy_name, []))
        if not pnl_list:
            return 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnl_list:
            equity += p
            if equity > peak:
                peak = equity
            dd = equity - peak
            if dd < max_dd:
                max_dd = dd
        return round(max_dd, 2)

    def _sharpe(self, strategy_name):
        pnl_list = list(self.pnl_history.get(strategy_name, []))
        if len(pnl_list) < 5:
            return None
        import statistics as stats
        mean = stats.mean(pnl_list)
        stdev = stats.pstdev(pnl_list)
        if stdev == 0:
            return None
        return round(mean / stdev, 3)

    def _sharpe_ci(self, strategy_name, alpha=0.05):
        pnl_list = list(self.pnl_history.get(strategy_name, []))
        if len(pnl_list) < 5:
            return None
        import statistics as stats
        import math
        mean = stats.mean(pnl_list)
        stdev = stats.pstdev(pnl_list)
        if stdev == 0:
            return None
        sharpe = mean / stdev
        n = len(pnl_list)
        se = math.sqrt((1 + 0.5 * sharpe * sharpe) / n)
        z = 1.96  # approx 95% CI
        return [round(sharpe - z * se, 3), round(sharpe + z * se, 3)]

    def _risk_adj_pf(self, strategy_name):
        pf = self._profit_factor(strategy_name)
        if pf == "inf":
            pf_val = 2.0
        else:
            pf_val = float(pf)
        dd = abs(self._max_drawdown(strategy_name))
        return round(pf_val / (1 + dd), 3)

    def _utility(self, strategy_name):
        pnl = self.stats.get(strategy_name, {}).get("pnl", 0.0)
        dd = abs(self._max_drawdown(strategy_name))
        return round(pnl / (1 + dd), 3)

    def _rolling_sharpe(self, strategy_name, window=30):
        pnl_list = list(self.pnl_history.get(strategy_name, []))
        if len(pnl_list) < max(5, window):
            return None
        windowed = pnl_list[-window:]
        import statistics as stats
        mean = stats.mean(windowed)
        stdev = stats.pstdev(windowed)
        if stdev == 0:
            return None
        return round(mean / stdev, 3)

    def _rolling_stats(self, strategy_name, window=50):
        data = list(self.results.get(strategy_name, []))
        if not data:
            return {"trades": 0, "wins": 0, "losses": 0}
        windowed = data[-window:]
        wins = sum(1 for x in windowed if x > 0)
        losses = sum(1 for x in windowed if x < 0)
        return {"trades": len(windowed), "wins": wins, "losses": losses}

    def rolling_stats(self, strategy_name, window=50):
        return self._rolling_stats(strategy_name, window=window)

    def rolling_total_trades(self, window=50):
        total = 0
        for name in self.results.keys():
            total += self._rolling_stats(name, window=window).get("trades", 0)
        return total
