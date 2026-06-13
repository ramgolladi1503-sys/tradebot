import re
with open("tests/test_kite_ws_subprocess.py", "r") as f:
    code = f.read()

code = code.replace(
    'monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)',
    'monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)\n    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda *args, **kwargs: ([101], {}), raising=False)'
)

with open("tests/test_kite_ws_subprocess.py", "w") as f:
    f.write(code)
