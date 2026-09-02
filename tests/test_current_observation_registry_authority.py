import hashlib
import json

from core.market_event_graph_live_observation_registry import load_observation_registry, reset_observation_registry


def test_current_session_registry_loads_from_explicit_authority_path(monkeypatch, tmp_path):
    rows = [{"symbol": f"S{i}", "instrument_token": 1000 + i} for i in range(50)]
    payload = {
        "broker_provider": "kite", "token_domain": "kite_instrument_token",
        "official_raw_sha256": "a" * 64,
        "broker_instrument_master": {"sha256": "a" * 64},
        "index_symbol": "NIFTY", "index_instrument_token": 256265,
        "constituents": rows,
    }
    # The canonical hash is intentionally calculated with the repository helper.
    from core.market_event_graph_live_runtime_bridge import canonical_live_universe_sha256
    payload["canonical_sha256"] = canonical_live_universe_sha256(payload)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "true")
    monkeypatch.setenv("MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", str(path))
    reset_observation_registry()
    registry = load_observation_registry(force=True)
    assert registry is not None
    assert registry.token_count == 51
