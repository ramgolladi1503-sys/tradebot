from __future__ import annotations

import random

from config import config as cfg
from core.strategy_allocator import StrategyAllocator


class _TrackerStub:
    def __init__(self):
        self.stats = {"S1": {"sharpe": 0.3, "utility": 1.0}}
        self.decay_probs = {}

    def rolling_stats(self, _strategy_name, window=50):
        return {"wins": 10, "losses": 10, "trades": 20}

    def rolling_total_trades(self, window=50):
        return 100


def test_allocator_context_seed_is_deterministic(monkeypatch):
    monkeypatch.setattr(cfg, "BANDIT_MODE", "EPS", raising=False)
    monkeypatch.setattr(cfg, "STRATEGY_EPSILON", 0.4, raising=False)
    monkeypatch.setattr(cfg, "STRATEGY_MIN_WEIGHT", 0.1, raising=False)
    monkeypatch.setattr(cfg, "STRATEGY_MAX_WEIGHT", 3.0, raising=False)

    allocator = StrategyAllocator(_TrackerStub(), rng=random.Random(123))
    seed_key = "2026-02-22|NIFTY|S1"

    first = allocator.should_trade("S1", epsilon=0.37, context_seed=seed_key)
    second = allocator.should_trade("S1", epsilon=0.37, context_seed=seed_key)

    assert first == second


def test_allocator_does_not_mutate_global_epsilon(monkeypatch):
    monkeypatch.setattr(cfg, "BANDIT_MODE", "EPS", raising=False)
    monkeypatch.setattr(cfg, "STRATEGY_EPSILON", 0.55, raising=False)
    monkeypatch.setattr(cfg, "STRATEGY_MIN_WEIGHT", 0.1, raising=False)
    monkeypatch.setattr(cfg, "STRATEGY_MAX_WEIGHT", 3.0, raising=False)

    allocator = StrategyAllocator(_TrackerStub(), rng=random.Random(99))
    before = float(cfg.STRATEGY_EPSILON)
    _ = allocator.should_trade("S1", epsilon=0.21, context_seed="2026-02-22|NIFTY|S1")
    after = float(cfg.STRATEGY_EPSILON)

    assert before == 0.55
    assert after == before
