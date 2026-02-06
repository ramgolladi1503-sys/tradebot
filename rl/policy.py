from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np

from rl.utils import features_from_row


@dataclass
class BanditPolicy:
    actions: List[float]
    centroids: Dict[float, List[float]]

    def select_action(self, feat: List[float]) -> float:
        if not self.centroids:
            return 1.0
        x = np.array(feat)
        best = None
        best_dist = 1e18
        for a, c in self.centroids.items():
            v = np.array(c)
            d = np.linalg.norm(x - v)
            if d < best_dist:
                best_dist = d
                best = float(a)
        return best if best is not None else 1.0

    def predict(self, row: dict) -> float:
        return self.select_action(features_from_row(row))


def load_policy(path: str) -> BanditPolicy:
    p = Path(path)
    if not p.exists():
        return BanditPolicy(actions=[0.0, 0.25, 0.5, 0.75, 1.0], centroids={})
    model = joblib.load(p)
    return BanditPolicy(actions=model.get("actions", [0.0, 0.25, 0.5, 0.75, 1.0]), centroids=model.get("centroids", {}))


def save_policy(policy: BanditPolicy, path: str):
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    model = {"actions": policy.actions, "centroids": policy.centroids}
    joblib.dump(model, p)
