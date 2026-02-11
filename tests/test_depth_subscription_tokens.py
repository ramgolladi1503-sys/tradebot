from config import config as cfg
from core import kite_depth_ws as ws


def _make_option(strike, token, expiry, opt_type="CE"):
    return {
        "segment": "NFO-OPT",
        "name": "NIFTY",
        "expiry": expiry,
        "strike": strike,
        "instrument_token": token,
        "instrument_type": opt_type,
    }


def test_build_depth_subscription_tokens_window(monkeypatch):
    expiry = "2026-02-17"
    strikes = [19900, 19950, 20000, 20050, 20100]
    tokens = []
    token_id = 1000
    for strike in strikes:
        tokens.append(_make_option(strike, token_id, expiry, "CE"))
        token_id += 1
        tokens.append(_make_option(strike, token_id, expiry, "PE"))
        token_id += 1
    # out-of-window strike
    tokens.append(_make_option(21000, token_id, expiry, "CE"))

    def fake_instruments_cached(exchange=None, ttl_sec=3600):
        if exchange == "NFO":
            return list(tokens)
        if exchange == "NSE":
            return [
                {
                    "tradingsymbol": "NIFTY 50",
                    "name": "NIFTY 50",
                    "segment": "NSE-INDICES",
                    "exchange": "NSE",
                    "instrument_token": 999,
                }
            ]
        return []

    monkeypatch.setattr(ws.kite_client, "instruments_cached", fake_instruments_cached)
    monkeypatch.setattr(ws.kite_client, "ltp", lambda symbols: {"NSE:NIFTY 50": {"last_price": 20010}})
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 2)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {})
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 50)
    monkeypatch.setattr(cfg, "STRIKE_STEP_BY_SYMBOL", {"NIFTY": 50})
    monkeypatch.setattr(cfg, "STRIKE_STEP", 50)
    monkeypatch.setattr(cfg, "PREMARKET_INDICES_LTP", {"NIFTY": "NSE:NIFTY 50"})

    result_tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"])
    assert 999 in result_tokens
    assert len(result_tokens) == 11
    assert resolution[0]["count"] == 11
