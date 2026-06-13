import re
with open("tests/test_kite_depth_ws_stability.py", "r") as f:
    code = f.read()

code = code.replace(
    'assert getattr(ws._KITE_TICKER, "on_connect", None) is not None',
    'print("EVENTS:", events)\n    assert getattr(ws._KITE_TICKER, "on_connect", None) is not None'
)

with open("tests/test_kite_depth_ws_stability.py", "w") as f:
    f.write(code)
