import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd

class TradingEnv(gym.Env):
    """
    Minimal RL environment scaffold.
    Observation: feature vector from dataset
    Actions: 0=HOLD, 1=BUY, 2=SELL
    Reward: simple PnL-based proxy (placeholder)
    """
    metadata = {"render_modes": []}

    def __init__(self, data_csv="data/ml_features.csv", feature_cols=None):
        super().__init__()
        self.data = pd.read_csv(data_csv).dropna().reset_index(drop=True)
        self.feature_cols = feature_cols or [
            "ltp", "bid", "ask", "spread_pct", "volume",
            "atr", "vwap_dist", "moneyness", "is_call",
            "vwap_slope", "rsi_mom", "vol_z"
        ]
        self.ptr = 0
        self.position = 0  # -1 short, 0 flat, 1 long
        self.entry_price = None
        self.peak_equity = 0.0
        self.equity = 0.0

        obs_dim = len(self.feature_cols)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.ptr = 0
        self.position = 0
        self.entry_price = None
        self.peak_equity = 0.0
        self.equity = 0.0
        return self._get_obs(), {}

    def _get_obs(self):
        row = self.data.iloc[self.ptr]
        return row[self.feature_cols].values.astype(np.float32)

    def step(self, action):
        row = self.data.iloc[self.ptr]
        price = row.get("ltp", row.get("close", 0))
        reward = 0.0

        if action == 1 and self.position == 0:
            self.position = 1
            self.entry_price = price
        elif action == 2 and self.position == 0:
            self.position = -1
            self.entry_price = price
        elif action == 0 and self.position != 0 and self.entry_price is not None:
            # R-multiple reward
            risk = max(abs(self.entry_price * 0.01), 1e-6)
            r_mult = ((price - self.entry_price) * self.position) / risk
            reward = r_mult

        # drawdown penalty
        self.equity += reward
        self.peak_equity = max(self.peak_equity, self.equity)
        dd = self.equity - self.peak_equity
        reward += dd * 0.01

        self.ptr += 1
        done = self.ptr >= len(self.data) - 1
        return self._get_obs(), reward, done, False, {}
