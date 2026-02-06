from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import config as cfg
from rl.reward import compute_reward, simulate_fill


@dataclass
class StepResult:
    obs: List[float]
    reward: float
    done: bool
    info: Dict[str, Any]


class SizingEnv:
    """
    Gym-like offline environment for sizing.
    Reads DecisionEvent dataset (SQLite preferred, JSONL fallback).
    """
    def __init__(self, source: str | None = None, seed: int = 42):
        self.source = source or getattr(cfg, "TRADE_DB_PATH", "data/trades.db")
        self._rows: List[Dict[str, Any]] = []
        self._idx = 0
        random.seed(seed)
        self._load()

    def _load(self):
        path = Path(self.source)
        if path.suffix == ".db" and path.exists():
            self._rows = self._load_sqlite(path)
        elif path.exists():
            self._rows = self._load_jsonl(path)
        else:
            # fallback to logs jsonl
            fallback = Path("logs/decision_events.jsonl")
            if fallback.exists():
                self._rows = self._load_jsonl(fallback)
        if not self._rows:
            raise RuntimeError("No DecisionEvent rows found for RL sizing.")

    def _load_sqlite(self, path: Path):
        rows = []
        conn = sqlite3.connect(str(path))
        try:
            cur = conn.execute("SELECT * FROM decision_events ORDER BY ts ASC")
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                obj = dict(zip(cols, r))
                # decode regime_probs and veto_reasons if JSON
                try:
                    if obj.get("regime_probs"):
                        obj["regime_probs"] = json.loads(obj["regime_probs"])
                except Exception:
                    pass
                rows.append(obj)
        finally:
            conn.close()
        return rows

    def _load_jsonl(self, path: Path):
        rows = []
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows

    def _feat(self, row: Dict[str, Any]) -> List[float]:
        score = float(row.get("score_0_100") or 0.0) / 100.0
        reg = row.get("regime_probs") or {}
        reg_max = 0.0
        try:
            reg_max = max(reg.values()) if reg else 0.0
        except Exception:
            reg_max = 0.0
        shock = float(row.get("shock_score") or 0.0)
        spread = float(row.get("spread_pct") or 0.0)
        depth = float(row.get("depth_imbalance") or 0.0)
        drawdown = float(row.get("drawdown_pct") or 0.0)
        loss_streak = float(row.get("loss_streak") or 0.0)
        open_risk = float(row.get("open_risk") or 0.0)
        delta = float(row.get("delta_exposure") or 0.0)
        gamma = float(row.get("gamma_exposure") or 0.0)
        vega = float(row.get("vega_exposure") or 0.0)
        return [
            score, reg_max, shock, spread, depth, drawdown,
            loss_streak, open_risk, delta, gamma, vega
        ]

    def reset(self) -> List[float]:
        self._idx = 0
        return self._feat(self._rows[self._idx])

    def step(self, action: float) -> StepResult:
        row = self._rows[self._idx]
        filled, fill_price = simulate_fill(row)
        reward = compute_reward(row, action, filled, fill_price)
        info = {"filled": filled, "fill_price": fill_price, "trade_id": row.get("trade_id")}
        self._idx += 1
        done = self._idx >= len(self._rows)
        obs = self._feat(self._rows[self._idx]) if not done else []
        return StepResult(obs=obs, reward=reward, done=done, info=info)

    @property
    def actions(self) -> List[float]:
        return list(getattr(cfg, "RL_ACTIONS", [0.0, 0.25, 0.5, 0.75, 1.0]))
