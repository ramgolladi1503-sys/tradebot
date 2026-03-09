from config import config as cfg
from core import kite_depth_ws as ws


def test_tick_subscription_plan_includes_indices(monkeypatch):
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", False, raising=False)
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY", "BANKNIFTY", "SENSEX"], raising=False)
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: set())
    monkeypatch.setattr(ws, "_underlying_ltp", lambda _symbol: None)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda symbol, exchange="NFO": None)

    index_tokens = {"NIFTY": 256265, "BANKNIFTY": 260105, "SENSEX": 265001}
    monkeypatch.setattr(ws.kite_client, "resolve_index_token", lambda symbol: index_tokens.get(str(symbol).upper(), 0))

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY", "BANKNIFTY", "SENSEX"], max_tokens=20)

    token_set = set(int(t) for t in tokens)
    assert set(index_tokens.values()).issubset(token_set)
    resolution_by_symbol = {str(r.get("symbol")).upper(): r for r in resolution}
    for sym, tok in index_tokens.items():
        assert sym in resolution_by_symbol
        assert int(resolution_by_symbol[sym].get("index_token")) == int(tok)

