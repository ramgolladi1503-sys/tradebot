import json
from pathlib import Path

from config import config as cfg
from core.market_event_graph_live_observation_registry import BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE, load_observation_registry, observation_budget_preflight


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
