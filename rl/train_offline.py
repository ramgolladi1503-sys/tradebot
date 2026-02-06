from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from config import config as cfg
from rl.env_sizing import SizingEnv
from rl.reward import compute_reward, simulate_fill
from rl.utils import features_from_row
from rl.policy import BanditPolicy, save_policy


def _label_action(row: Dict[str, Any], actions: List[float]) -> float:
    filled, fill_price = simulate_fill(row)
    best_a = 0.0
    best_r = -1e9
    for a in actions:
        r = compute_reward(row, a, filled, fill_price)
        if r > best_r:
            best_r = r
            best_a = a
    return best_a


def train(output_path: str | None = None):
    env = SizingEnv()
    actions = list(getattr(cfg, "RL_ACTIONS", [0.0, 0.25, 0.5, 0.75, 1.0]))

    rows = env._rows  # offline dataset
    X = []
    y = []
    for row in rows:
        X.append(features_from_row(row))
        y.append(_label_action(row, actions))

    X = np.array(X)
    y = np.array(y)

    centroids = {}
    for a in actions:
        mask = y == a
        if mask.any():
            centroids[a] = X[mask].mean(axis=0).tolist()

    policy = BanditPolicy(actions=actions, centroids=centroids)
    path = Path(output_path or getattr(cfg, "RL_SIZE_MODEL_PATH", "models/rl_size_agent.json"))
    save_policy(policy, str(path))
    return str(path)


if __name__ == "__main__":
    out = train()
    print(f"Saved RL sizing model to {out}")
