import random
from config import config as cfg

class StrategyAllocator:
    """
    Bandit-style allocator: epsilon-greedy and weights by Sharpe (fallback to profit factor).
    """
    def __init__(self, tracker, risk_state=None):
        self.tracker = tracker
        self.risk_state = risk_state
        self._wf_cache = {"ts": 0, "allowed": None}

    def _load_wf_allowed(self):
        try:
            import time
            from pathlib import Path
            import pandas as pd
            ttl = getattr(cfg, "STRATEGY_WF_LOCK_TTL", 300)
            if self._wf_cache["allowed"] is not None and (time.time() - self._wf_cache["ts"]) < ttl:
                return self._wf_cache["allowed"]
            path = Path("logs/walk_forward_strategy_summary.csv")
            if not path.exists():
                self._wf_cache = {"ts": time.time(), "allowed": None}
                return None
            if path.stat().st_size == 0:
                self._wf_cache = {"ts": time.time(), "allowed": None}
                return None
            df = pd.read_csv(path)
            if df.empty or "strategy" not in df.columns:
                self._wf_cache = {"ts": time.time(), "allowed": None}
                return None
            if "passed" in df.columns:
                allowed = set(df.loc[df["passed"] == True, "strategy"].astype(str).tolist())
            else:
                allowed = set(df["strategy"].astype(str).tolist())
            self._wf_cache = {"ts": time.time(), "allowed": allowed}
            return allowed
        except Exception:
            return None

    def _weight(self, strategy_name):
        stats = self.tracker.stats.get(strategy_name, {})
        sharpe = stats.get("sharpe", None)
        if sharpe is None:
            util = stats.get("utility", stats.get("risk_adj_pf", 1.0))
            if util == "inf":
                util = 2.0
            weight = float(util)
        else:
            weight = max(0.1, float(sharpe) + 1.0)
        # Execution quality penalty (0-100 scaled)
        exec_q = stats.get("exec_quality_avg", None)
        if exec_q is not None:
            try:
                weight *= max(0.5, min(1.2, float(exec_q) / 100.0 + 0.5))
            except Exception:
                pass
        # Decay probability downsize
        try:
            dp = self.tracker.decay_probs.get(strategy_name, {}).get("decay_probability")
            if dp is not None:
                if dp >= float(getattr(cfg, "DECAY_DOWNSIZE_THRESHOLD", 0.5)):
                    weight *= float(getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6))
        except Exception:
            pass
        return max(cfg.STRATEGY_MIN_WEIGHT, min(cfg.STRATEGY_MAX_WEIGHT, weight))

    def should_trade(self, strategy_name):
        if self.risk_state:
            if self.risk_state.mode == "HARD_HALT":
                return False
            if strategy_name in self.risk_state.quarantined:
                return False
            if self.risk_state.mode == "RECOVERY_MODE":
                if "SPREAD" not in str(strategy_name):
                    return False
            if self.risk_state.mode == "SOFT_HALT":
                if strategy_name in ("SCALP", "ZERO_HERO", "ZERO_HERO_EXPIRY") or str(strategy_name).startswith("QUICK"):
                    return False
        if getattr(cfg, "STRATEGY_WF_LOCK_ENABLE", False):
            allowed = self._load_wf_allowed()
            if allowed is not None and strategy_name not in allowed:
                return False
        # Decay probability hard block
        try:
            dp = self.tracker.decay_probs.get(strategy_name, {}).get("decay_probability")
            if dp is not None and dp >= float(getattr(cfg, "DECAY_PROB_THRESHOLD", 0.7)):
                return False
        except Exception:
            pass
        window = getattr(cfg, "BANDIT_WINDOW", 50)
        if cfg.BANDIT_MODE == "BAYES":
            stats = self.tracker.stats.get(strategy_name, {})
            roll = self.tracker.rolling_stats(strategy_name, window=window)
            wins = roll.get("wins", 0) + 1
            losses = roll.get("losses", 0) + 1
            # Thompson sampling with rolling window
            sample = random.betavariate(wins, losses)
            util = stats.get("utility", 1.0)
            score = sample * (1 + cfg.BANDIT_UTILITY_WEIGHT * float(util))
            self._record_weight(strategy_name, score)
            return score > 0.5
        if cfg.BANDIT_MODE == "UCB":
            roll = self.tracker.rolling_stats(strategy_name, window=window)
            n = max(1, roll.get("trades", 0))
            wins = roll.get("wins", 0)
            total = max(1, self.tracker.rolling_total_trades(window=window))
            mean = wins / n
            # UCB1 score (rolling window)
            import math
            ucb = mean + math.sqrt(2 * math.log(total + 1) / n)
            self._record_weight(strategy_name, ucb)
            return ucb > 0.5
        if random.random() < cfg.STRATEGY_EPSILON:
            return True
        w = self._weight(strategy_name)
        temp = max(0.1, getattr(cfg, "ALLOC_TEMPERATURE", 1.0))
        # Softmax-like acceptance
        prob = min(1.0, max(0.0, (w / cfg.STRATEGY_MAX_WEIGHT) ** (1.0 / temp)))
        self._record_weight(strategy_name, prob)
        return random.random() < prob

    def _record_weight(self, strategy_name, weight):
        try:
            import json, time
            from pathlib import Path
            path = Path("logs/bandit_weights.json")
            data = []
            if path.exists():
                data = json.loads(path.read_text())
            data.append({"ts": time.time(), "strategy": strategy_name, "weight": float(weight)})
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(data[-1000:], indent=2))
            # alert if weight collapses
            if float(weight) < cfg.BANDIT_ALERT_THRESHOLD:
                from core.telegram_alerts import send_telegram_message
                send_telegram_message(f"Bandit alert: {strategy_name} weight dropped to {float(weight):.2f}")
        except Exception:
            pass
