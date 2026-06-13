import re
with open("tests/test_kite_depth_ws_stability.py", "r") as f:
    code = f.read()

code = code.replace(
    'monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)',
    'monkeypatch.setattr(ws, "_RUNTIME_STATE", "STOPPED", raising=False)\n    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)'
)

with open("tests/test_kite_depth_ws_stability.py", "w") as f:
    f.write(code)
