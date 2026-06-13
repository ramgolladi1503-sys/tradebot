import re
with open("tests/test_kite_depth_ws_stability.py", "r") as f:
    code = f.read()

code = code.replace(
    'monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: ticker)',
    'monkeypatch.setattr("core.kite_depth_ws.get_kite_ticker", lambda **kwargs: ticker)'
)

with open("tests/test_kite_depth_ws_stability.py", "w") as f:
    f.write(code)
