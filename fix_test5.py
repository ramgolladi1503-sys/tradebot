import re
with open("tests/test_kite_depth_ws_stability.py", "r") as f:
    code = f.read()

# Fix the test
start = code.find("def test_on_open_resubscribes_instruments")
if start != -1:
    code = code[:start]

code += """def test_on_open_resubscribes_instruments(monkeypatch, tmp_path):
    _patch_common(monkeypatch)
    monkeypatch.setattr(ws, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(ws, "runtime_dir", lambda: tmp_path)
    
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr("core.kite_depth_ws.get_kite_ticker", lambda **kwargs: ticker)
    
    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda: ([101, 102], {}))
    
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    
    ws.start_depth_ws([101, 102], profile_verified=True)
    
    assert getattr(ws._KITE_TICKER, "on_connect", None) is not None
    assert getattr(ws._KITE_TICKER, "on_open", None) is not None
    assert getattr(ws._KITE_TICKER, "on_reconnect", None) is not None
    
    ticker = ws._KITE_TICKER
    
    # 1. First we simulate a connection start
    ticker.on_connect(ticker, {})
    assert any(e[0] == "ws_connect_handshake_started" for e in events)
    
    # Prove that connect does not subscribe (it's handled in on_open now)
    assert getattr(ticker, "tokens", None) is None
    
    # 2. Simulate socket open (the real subscription)
    ticker.on_open(ticker)
    assert any(e[0] == "ws_connected" for e in events)
    assert getattr(ticker, "tokens", None) == [101, 102]
    
    # 3. Simulate reconnect attempt
    events.clear()
    ticker.on_reconnect(ticker, 1)
    assert any(e[0] == "ws_reconnect_attempt" for e in events)
    
    # Prove that reconnect attempt does not call subscribe directly (protecting against disconnected state crash)
    # We test this by making subscribe raise an error and ensuring on_reconnect does not crash or call it.
    def mock_subscribe(tokens):
        raise Exception("Should not be called")
    ticker.subscribe = mock_subscribe
    
    ticker.on_reconnect(ticker, 2)
    assert any(e[0] == "ws_reconnect_attempt" and e[1].get("attempts") == 2 for e in events)
"""

with open("tests/test_kite_depth_ws_stability.py", "w") as f:
    f.write(code)
