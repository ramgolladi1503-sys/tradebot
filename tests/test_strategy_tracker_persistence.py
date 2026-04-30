import json

from config import config as cfg
from core.strategy_tracker import StrategyTracker


def test_decay_probability_persistence_writes_sidecar_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DECAY_SOFT_THRESHOLD", 0.10, raising=False)
    monkeypatch.setattr(cfg, "DECAY_HARD_THRESHOLD", 0.20, raising=False)
    monkeypatch.setattr(cfg, "DECAY_PERSIST_WINDOWS", 1, raising=False)

    tracker = StrategyTracker(load_sidecars=False)
    tracker.apply_decay_probs({"ENSEMBLE_OPT": 0.30})

    logs_root = tmp_path / "logs"
    decay_probs = json.loads((logs_root / "strategy_decay_probs.json").read_text())
    decay_state = json.loads((logs_root / "strategy_decay_state.json").read_text())
    degraded = json.loads((logs_root / "strategy_degradation.json").read_text())

    assert decay_probs == {"ENSEMBLE_OPT": 0.30}
    assert decay_state["decay_state"]["ENSEMBLE_OPT"] == 1
    assert decay_state["soft_disabled"]["ENSEMBLE_OPT"] == 0.30
    assert degraded["degraded"]["ENSEMBLE_OPT"]["reason"] == "decay_probability"


def test_load_first_available_prefers_live_perf_then_shadow(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)

    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    live_path = logs_root / "strategy_perf.json"
    shadow_path = logs_root / "suggestion_strategy_perf.json"

    shadow_tracker = StrategyTracker(load_sidecars=False)
    shadow_tracker.record("ENSEMBLE_OPT", -10.0)
    shadow_tracker.record("ENSEMBLE_OPT", -5.0)
    shadow_tracker.save(str(shadow_path))

    tracker = StrategyTracker(load_sidecars=False)
    selected = tracker.load_first_available([str(live_path), str(shadow_path)])

    assert selected == str(shadow_path)
    assert tracker.stats["ENSEMBLE_OPT"]["trades"] == 2
    assert tracker.stats["ENSEMBLE_OPT"]["pnl"] == -15.0

    live_tracker = StrategyTracker(load_sidecars=False)
    live_tracker.record("ENSEMBLE_OPT", 8.0)
    live_tracker.save(str(live_path))

    shadow_tracker = StrategyTracker(load_sidecars=False)
    shadow_tracker.record("ENSEMBLE_OPT", -50.0)
    shadow_tracker.save(str(shadow_path))

    tracker2 = StrategyTracker(load_sidecars=False)
    selected2 = tracker2.load_first_available([str(live_path), str(shadow_path)])

    assert selected2 == str(live_path)
    assert tracker2.stats["ENSEMBLE_OPT"]["trades"] == 1
    assert tracker2.stats["ENSEMBLE_OPT"]["pnl"] == 8.0
