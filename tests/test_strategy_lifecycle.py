from core.strategy_lifecycle import StrategyLifecycle
from config import config as cfg


def test_default_state(monkeypatch, tmp_path):
    path = tmp_path / "lifecycle.json"
    monkeypatch.setattr(cfg, "STRATEGY_LIFECYCLE_PATH", str(path))
    monkeypatch.setattr(cfg, "STRATEGY_LIFECYCLE_DEFAULT_STATE", "PAPER")
    lc = StrategyLifecycle()
    assert lc.get_state("STRAT_A") == "PAPER"


def test_live_pilot_blocks_non_pilot(monkeypatch, tmp_path):
    path = tmp_path / "lifecycle.json"
    monkeypatch.setattr(cfg, "STRATEGY_LIFECYCLE_PATH", str(path))
    monkeypatch.setattr(cfg, "LIVE_PILOT_MODE", True)
    lc = StrategyLifecycle()
    lc.set_state("STRAT_B", "PAPER", reason="test")
    allowed, reason = lc.can_allocate("STRAT_B", mode="MAIN")
    assert allowed is False
    assert "lifecycle_not_pilot_or_live" in reason
