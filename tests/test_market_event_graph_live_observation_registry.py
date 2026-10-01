import json
from pathlib import Path

from config import config as cfg
from core.market_event_graph_live_observation_registry import (
    BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE,
    build_observation_subscription_merge,
    load_observation_registry,
    observation_budget_preflight,
    reset_observation_registry,
)


def test_observation_registry_loads_cached_kite_contract(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(
        cfg,
        "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH",
        "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json",
    )

    registry = load_observation_registry(force=True)

    assert registry is not None
    assert registry.provider == "kite"
    assert registry.token_domain == "kite_instrument_token"
    assert registry.token_count == 51
    assert registry.index_token == 256265
    assert registry.token_by_symbol["NIFTY"] == 256265
    assert registry.instrument_class_by_token[256265] == "INDEX"
    assert registry.observation_identity(256265)["universe_hash"] == "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371"


def test_observation_budget_preflight_reports_over_budget(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(
        cfg,
        "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH",
        "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json",
    )
    load_observation_registry(force=True)

    decision = observation_budget_preflight(budget=1, current_tokens=[])

    assert decision["ok"] is False
    assert decision["reason"] == "BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET"
    assert decision["observation_count"] == 51


def test_observation_registry_rejects_forged_hash_and_bad_provider(monkeypatch, tmp_path):
    path = tmp_path / "contract.json"
    payload = json.loads(Path("runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json").read_text())
    payload["canonical_sha256"] = "bad"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", str(path))
    try:
        load_observation_registry(force=True)
    except ValueError as exc:
        assert BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE in str(exc)
    else:
        raise AssertionError("expected forged hash to be rejected")


def test_disabled_feature_clears_prior_cached_registry(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json")
    assert load_observation_registry(force=True) is not None
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)
    assert load_observation_registry() is None


def test_observation_merge_is_all_or_none_and_fail_open():
    decision = build_observation_subscription_merge(production_tokens=[1, 2], observation_tokens=[2, 3, 4], budget=3)
    assert decision["ok"] is False
    assert decision["tokens"] == [1, 2]
    assert decision["overlap_count"] == 1
    assert decision["observation_exclusive_count"] == 2


def test_default_depth_subscription_budget_is_governed_123_tokens():
    assert cfg.DEPTH_SUBSCRIPTION_MAX_TOKENS == 123


def test_governed_123_token_topology_accepts_73_production_plus_51_observation_with_index_overlap():
    """Regression: 50 NIFTY constituents are cash observation tokens, not option families."""
    from core.market_event_graph_live_observation_registry import build_observation_subscription_merge

    # Production owns the three index underlyings plus the controlled index-option window.
    # Observation owns NIFTY plus its 50 cash constituents; NIFTY overlaps production once.
    production_tokens = list(range(1, 74))
    observation_tokens = [1] + list(range(1001, 1051))

    decision = build_observation_subscription_merge(
        production_tokens=production_tokens,
        observation_tokens=observation_tokens,
        budget=123,
    )

    assert decision["ok"] is True
    assert decision["production_token_count"] == 73
    assert decision["observation_token_count"] == 51
    assert decision["overlap_count"] == 1
    assert decision["observation_exclusive_count"] == 50
    assert decision["final_union_count"] == 123
    assert len(decision["tokens"]) == 123


def test_governed_123_token_topology_rejects_expansion_beyond_contract():
    from core.market_event_graph_live_observation_registry import (
        BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
        build_observation_subscription_merge,
    )

    production_tokens = list(range(1, 75))
    observation_tokens = [1] + list(range(1001, 1051))
    decision = build_observation_subscription_merge(
        production_tokens=production_tokens,
        observation_tokens=observation_tokens,
        budget=123,
    )

    assert decision["ok"] is False
    assert decision["reason"] == BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET
    assert decision["final_union_count"] == 124
