from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from config import config as cfg
from rl.env_sizing import SizingEnv
from rl.reward import compute_reward, simulate_fill
from rl.policy import load_policy
from rl.utils import features_from_row


def evaluate(model_path: str | None = None):
    env = SizingEnv()
    policy = load_policy(model_path or getattr(cfg, "RL_SIZE_MODEL_PATH", "models/rl_size_agent.json"))

    rewards = []
    actions = []
    for row in env._rows:
        feat = features_from_row(row)
        act = policy.select_action(feat)
        filled, fill_price = simulate_fill(row)
        reward = compute_reward(row, act, filled, fill_price)
        rewards.append(reward)
        actions.append(act)

    avg_reward = float(np.mean(rewards)) if rewards else 0.0
    action_avg = float(np.mean(actions)) if actions else 0.0
    out = {
        "avg_reward": avg_reward,
        "avg_action": action_avg,
        "n": len(rewards),
    }
    out_path = Path("logs/rl_shadow_eval.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    return out


def run_shadow_eval():
    return evaluate()


if __name__ == "__main__":
    res = evaluate()
    print(json.dumps(res, indent=2))
