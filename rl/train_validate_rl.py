from __future__ import annotations

import csv
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev

import numpy as np
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.trading_env import TradingEnv

DATA_FILE = Path("data/ml_features.csv")
TRAIN_FILE = Path("data/rl_train.csv")
VAL_FILE = Path("data/rl_val.csv")
MODEL_FILE = Path("models/ppo_trading")
VECNORM_FILE = Path("models/ppo_trading_vecnormalize.pkl")


def split_data():
    df = pd.read_csv(DATA_FILE).dropna().reset_index(drop=True)
    split = int(len(df) * 0.8)
    if split <= 0 or split >= len(df):
        raise RuntimeError("rl_split_invalid:data_size_too_small")
    TRAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    VAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.iloc[:split].to_csv(TRAIN_FILE, index=False)
    df.iloc[split:].to_csv(VAL_FILE, index=False)
    return len(df.iloc[:split]), len(df.iloc[split:])


def _build_env(data_csv: str, debug_steps: int = 0):
    return TradingEnv(
        data_csv=data_csv,
        transaction_cost_bps=1.5,
        slippage_bps=1.5,
        reward_clip=2.0,
        volatility_floor_bps=20.0,
        debug_steps=debug_steps,
    )


def _evaluate_with_trace(model: PPO, vec_env: VecNormalize, trace_steps: int = 20):
    obs = vec_env.reset()
    done = np.array([False])
    total_reward = 0.0
    steps = 0
    rewards = []
    trace = []

    while not bool(done[0]):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, info = vec_env.step(action)
        reward_value = float(reward[0])
        action_value = int(action[0]) if hasattr(action, "__len__") else int(action)
        total_reward += reward_value
        rewards.append(reward_value)
        steps += 1
        if len(trace) < trace_steps:
            trace.append({"step": steps, "action": action_value, "reward": reward_value})

    return {
        "total_reward": total_reward,
        "steps": steps,
        "rewards": rewards,
        "trace": trace,
    }


def _baseline_policy_eval(data_csv: str, policy_name: str, seed: int = 42):
    env = _build_env(data_csv=data_csv, debug_steps=0)
    random_gen = random.Random(seed)
    obs, _ = env.reset()
    done = False
    total_reward = 0.0
    steps = 0

    while not done:
        if policy_name == "always_long":
            action = 1
        elif policy_name == "always_flat":
            action = 0
        elif policy_name == "random":
            action = random_gen.choice([0, 1, 2])
        else:
            raise RuntimeError(f"unknown_baseline_policy:{policy_name}")
        obs, reward, done, _, _ = env.step(action)
        total_reward += float(reward)
        steps += 1

    return {"policy": policy_name, "total_reward": total_reward, "steps": steps}


def _calc_metrics(pnl_series):
    if not pnl_series:
        return {"sharpe": 0.0, "max_drawdown": 0.0}
    reward_mean = mean(pnl_series)
    reward_stdev = pstdev(pnl_series) if len(pnl_series) > 1 else 0.0
    sharpe = reward_mean / reward_stdev if reward_stdev else 0.0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for reward in pnl_series:
        equity += reward
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return {"sharpe": sharpe, "max_drawdown": max_dd}


def train_and_validate():
    train_rows, val_rows = split_data()
    print(f"RL split rows -> train={train_rows}, val={val_rows}")

    train_env = DummyVecEnv([lambda: _build_env(str(TRAIN_FILE), debug_steps=50)])
    train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True, clip_obs=10.0, clip_reward=10.0)

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        n_steps=128,
        batch_size=64,
        learning_rate=3e-4,
    )
    total_timesteps = int(os.getenv("RL_TOTAL_TIMESTEPS", "20000"))
    print(f"RL training total_timesteps={total_timesteps}")
    model.learn(total_timesteps=total_timesteps)

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(MODEL_FILE))
    train_env.save(str(VECNORM_FILE))

    explained_variance = None
    try:
        explained_variance = model.logger.name_to_value.get("train/explained_variance")
    except Exception:
        explained_variance = None
    if explained_variance is not None:
        print(f"train_explained_variance={float(explained_variance):.4f}")
        if float(explained_variance) < 0.2:
            print("WARNING: explained_variance_below_target_0.2")

    val_base_env = DummyVecEnv([lambda: _build_env(str(VAL_FILE), debug_steps=50)])
    val_env = VecNormalize.load(str(VECNORM_FILE), val_base_env)
    val_env.training = False
    val_env.norm_reward = False

    eval_out = _evaluate_with_trace(model, val_env, trace_steps=20)
    total = float(eval_out["total_reward"])
    steps = int(eval_out["steps"])
    pnl_series = eval_out["rewards"]
    print("Validation trace (first 20 steps):")
    for row in eval_out["trace"]:
        print(f"step={row['step']} action={row['action']} reward={row['reward']:.6f}")

    metrics = _calc_metrics(pnl_series)
    sharpe = metrics["sharpe"]
    max_dd = metrics["max_drawdown"]
    print(f"Validation total reward: {total:.2f}, steps: {steps}")
    print(f"Sharpe: {sharpe:.3f}, Max Drawdown: {max_dd:.2f}")

    baselines = {
        "train": {
            "always_long": _baseline_policy_eval(str(TRAIN_FILE), "always_long"),
            "always_flat": _baseline_policy_eval(str(TRAIN_FILE), "always_flat"),
            "random": _baseline_policy_eval(str(TRAIN_FILE), "random"),
        },
        "val": {
            "always_long": _baseline_policy_eval(str(VAL_FILE), "always_long"),
            "always_flat": _baseline_policy_eval(str(VAL_FILE), "always_flat"),
            "random": _baseline_policy_eval(str(VAL_FILE), "random"),
        },
    }
    print("Baseline performance:")
    print(json.dumps(baselines, indent=2))

    out_csv = Path("logs/rl_metrics.csv")
    out_csv.parent.mkdir(exist_ok=True)
    is_new = not out_csv.exists()
    with out_csv.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(
                [
                    "timestamp",
                    "total_reward",
                    "steps",
                    "sharpe",
                    "max_drawdown",
                    "explained_variance",
                    "baseline_train_always_long",
                    "baseline_train_always_flat",
                    "baseline_train_random",
                    "baseline_val_always_long",
                    "baseline_val_always_flat",
                    "baseline_val_random",
                ]
            )
        writer.writerow(
            [
                datetime.now().isoformat(),
                round(total, 6),
                steps,
                round(sharpe, 6),
                round(max_dd, 6),
                round(float(explained_variance), 6) if explained_variance is not None else "",
                round(baselines["train"]["always_long"]["total_reward"], 6),
                round(baselines["train"]["always_flat"]["total_reward"], 6),
                round(baselines["train"]["random"]["total_reward"], 6),
                round(baselines["val"]["always_long"]["total_reward"], 6),
                round(baselines["val"]["always_flat"]["total_reward"], 6),
                round(baselines["val"]["random"]["total_reward"], 6),
            ]
        )

    json_path = Path("logs/rl_metrics.json")
    data = []
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data.append(
        {
            "timestamp": datetime.now().isoformat(),
            "total_reward": round(total, 6),
            "steps": steps,
            "sharpe": round(sharpe, 6),
            "max_drawdown": round(max_dd, 6),
            "explained_variance": round(float(explained_variance), 6) if explained_variance is not None else None,
            "baselines": baselines,
        }
    )
    json_path.write_text(json.dumps(data[-500:], indent=2), encoding="utf-8")

    try:
        from config import config as cfg
        from core.telegram_alerts import send_telegram_message

        send_telegram_message(
            f"RL Metrics | Reward: {round(total,2)} | Sharpe: {round(sharpe,3)} | DD: {round(max_dd,2)}"
        )
        if sharpe < cfg.RL_SHARPE_ALERT or max_dd < cfg.RL_DD_ALERT:
            send_telegram_message(
                f"RL Alert: Sharpe {round(sharpe,3)} or Drawdown {round(max_dd,2)} below threshold"
            )
    except Exception:
        pass


if __name__ == "__main__":
    train_and_validate()
