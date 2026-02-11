from __future__ import annotations

from pathlib import Path

import numpy as np
from stable_baselines3 import DDPG, PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from rl.trading_env import TradingEnv


def _make_eval_env(data_csv: str):
    base_env = DummyVecEnv([lambda: TradingEnv(data_csv=data_csv, debug_steps=20)])
    vec_path = Path("models/ppo_trading_vecnormalize.pkl")
    if vec_path.exists():
        env = VecNormalize.load(str(vec_path), base_env)
        env.training = False
        env.norm_reward = False
        return env
    return base_env


def evaluate(model_path, algo="PPO", episodes=3, data_csv="data/ml_features.csv"):
    env = _make_eval_env(data_csv=data_csv)
    if algo == "PPO":
        model = PPO.load(model_path)
    else:
        model = DDPG.load(model_path)
    rewards = []
    for episode_index in range(episodes):
        obs = env.reset()
        done = np.array([False])
        total = 0.0
        trace = []
        step_count = 0
        while not bool(done[0]):
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, _ = env.step(action)
            reward_value = float(reward[0]) if hasattr(reward, "__len__") else float(reward)
            action_value = int(action[0]) if hasattr(action, "__len__") else int(action)
            total += reward_value
            step_count += 1
            if len(trace) < 20:
                trace.append((step_count, action_value, reward_value))
        rewards.append(total)
        print(f"Episode {episode_index + 1}/{episodes} first 20 rewards/actions:")
        for step, action_value, reward_value in trace:
            print(f"  step={step} action={action_value} reward={reward_value:.6f}")
        print(f"Episode {episode_index + 1} total_reward={total:.6f}")
    print(f"{algo} avg reward: {sum(rewards)/len(rewards):.2f}")


if __name__ == "__main__":
    evaluate("models/ppo_trading", algo="PPO")
