from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces


class TradingEnv(gym.Env):
    """
    RL trading environment with normalized, non-zero reward dynamics.

    - Action space: 0=HOLD, 1=TARGET_LONG, 2=TARGET_SHORT
    - Reward: position * price_delta / vol_scale - trading_cost, clipped
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        data_csv: str = "data/ml_features.csv",
        feature_cols: list[str] | None = None,
        transaction_cost_bps: float = 1.0,
        slippage_bps: float = 1.0,
        reward_clip: float = 2.0,
        volatility_floor_bps: float = 20.0,
        max_episode_steps: int | None = None,
        debug_steps: int = 0,
        debug_log_path: str = "logs/rl_env_steps.jsonl",
        random_seed: int | None = None,
    ) -> None:
        super().__init__()
        self.data = pd.read_csv(data_csv).dropna().reset_index(drop=True)
        if len(self.data) < 2:
            raise RuntimeError("rl_env_insufficient_rows:need_at_least_2")

        default_feature_cols = [
            "ltp",
            "bid",
            "ask",
            "spread_pct",
            "volume",
            "atr",
            "vwap_dist",
            "moneyness",
            "is_call",
            "vwap_slope",
            "rsi_mom",
            "vol_z",
        ]
        requested_cols = feature_cols or default_feature_cols
        self.feature_cols = [column for column in requested_cols if column in self.data.columns]
        if not self.feature_cols:
            self.feature_cols = [column for column in self.data.columns if pd.api.types.is_numeric_dtype(self.data[column])]
        if not self.feature_cols:
            raise RuntimeError("rl_env_no_numeric_features")

        self.ptr = 0
        self.steps = 0
        self.position = 0  # -1 short, 0 flat, 1 long
        self.equity = 0.0

        self.transaction_cost_bps = float(transaction_cost_bps)
        self.slippage_bps = float(slippage_bps)
        self.reward_clip = float(max(reward_clip, 0.1))
        self.volatility_floor_bps = float(max(volatility_floor_bps, 1.0))
        self.last_transition_ptr = len(self.data) - 2
        self.max_episode_steps = int(max_episode_steps) if max_episode_steps else len(self.data) - 1

        self.debug_steps = int(max(debug_steps, 0))
        self.debug_log_path = Path(debug_log_path)
        self.debug_log_path.parent.mkdir(parents=True, exist_ok=True)

        obs_dim = len(self.feature_cols)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)

        self._rng = random.Random(random_seed)
        if random_seed is not None:
            np.random.seed(random_seed)

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng.seed(seed)
            np.random.seed(seed)
        self.ptr = 0
        self.steps = 0
        self.position = 0
        self.equity = 0.0
        return self._get_obs(), {}

    def _price_at(self, idx: int) -> float:
        row = self.data.iloc[idx]
        for key in ("ltp", "close"):
            value = row.get(key)
            if pd.notna(value):
                return float(value)
        return 0.0

    def _vol_scale(self, idx: int, current_price: float) -> float:
        row = self.data.iloc[idx]
        atr = row.get("atr", np.nan)
        if pd.notna(atr) and float(atr) > 1e-8:
            return float(abs(atr))
        return max(abs(current_price) * (self.volatility_floor_bps / 10000.0), 1e-6)

    def _get_obs(self):
        row = self.data.iloc[min(self.ptr, len(self.data) - 1)]
        values = row[self.feature_cols].astype(float).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        return values.values.astype(np.float32)

    def _log_debug_step(self, payload: dict[str, Any]) -> None:
        if self.steps > self.debug_steps:
            return
        with self.debug_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def step(self, action):
        action_value = int(action)
        if action_value not in (0, 1, 2):
            raise RuntimeError(f"rl_env_invalid_action:{action_value}")

        current_price = self._price_at(self.ptr)
        next_price = self._price_at(self.ptr + 1)
        price_delta = next_price - current_price
        vol_scale = self._vol_scale(self.ptr, current_price)

        position_before = self.position
        if action_value == 1:
            target_position = 1
        elif action_value == 2:
            target_position = -1
        else:
            target_position = position_before

        turnover = abs(target_position - position_before)
        trade_cost = turnover * ((self.transaction_cost_bps + self.slippage_bps) / 10000.0)

        self.position = target_position
        raw_reward = (self.position * price_delta) / vol_scale
        reward_pre_clip = raw_reward - trade_cost
        reward = float(np.clip(reward_pre_clip, -self.reward_clip, self.reward_clip))

        self.equity += reward

        self.ptr += 1
        self.steps += 1
        done = self.ptr > self.last_transition_ptr or self.steps >= self.max_episode_steps

        obs = self._get_obs()
        info = {
            "ptr": self.ptr,
            "action": action_value,
            "position_before": position_before,
            "position_after": self.position,
            "current_price": current_price,
            "next_price": next_price,
            "price_delta": price_delta,
            "vol_scale": vol_scale,
            "trade_cost": trade_cost,
            "raw_reward": raw_reward,
            "reward_pre_clip": reward_pre_clip,
            "equity": self.equity,
        }

        self._log_debug_step(
            {
                "ts_step": self.steps,
                "obs_head": obs[: min(5, len(obs))].tolist(),
                "action": action_value,
                "position_before": position_before,
                "position_after": self.position,
                "price_delta": price_delta,
                "raw_reward": raw_reward,
                "trade_cost": trade_cost,
                "reward": reward,
                "done": done,
            }
        )

        return obs, reward, done, False, info
