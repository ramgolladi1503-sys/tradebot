import json
from pathlib import Path

from strategies.strategy_registry import load_strategy_registry


REPO_ROOT = Path(__file__).resolve().parents[1]
TOMBSTONE_PATH = REPO_ROOT / "docs" / "strategy_truth" / "legacy_strategy_tombstones_v1.json"
SYNTHETIC_RUNNERS = (
    REPO_ROOT / "scripts" / "run_candidate_strategy_backtest.py",
    REPO_ROOT / "scripts" / "run_candidate_strategy_wfa.py",
)


def _tombstone_payload():
    return json.loads(TOMBSTONE_PATH.read_text(encoding="utf-8"))


def test_tombstoned_strategies_are_not_legacy_registry_reachable():
    payload = _tombstone_payload()
    registry = load_strategy_registry()
    assert set(payload["strategies"]).isdisjoint(registry)


def test_synthetic_legacy_economic_runners_are_removed():
    assert all(not path.exists() for path in SYNTHETIC_RUNNERS)


def test_tombstone_preserves_zero_execution_authority():
    authority = _tombstone_payload()["current_authority"]
    assert authority["legacy_registry_authorized"] is False
    assert authority["paper_authorized"] is False
    assert authority["live_authorized"] is False
    assert authority["broker_write_authority"] is False
    assert authority["order_authority"] is False


def test_meg_shadow_path_is_not_tombstoned():
    payload = _tombstone_payload()
    assert "MARKET_EVENT_GRAPH_REVERSAL" not in payload["strategies"]
    entry = load_strategy_registry()["MARKET_EVENT_GRAPH_REVERSAL"]
    assert entry.certification_supported is False
    assert entry.certification_track == "shadow_live_observation_only"
