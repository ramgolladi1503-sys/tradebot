import re
with open("tests/test_kite_depth_ws_stability.py", "r") as f:
    code = f.read()

code = code.replace(
    'try:\n        ws.start_depth_ws([101, 102], profile_verified=True)\n    except Exception as e:\n        print(e)',
    'ws.start_depth_ws([101, 102], profile_verified=True)\n        print("Is ticker same as ws._KITE_TICKER?", ticker is ws._KITE_TICKER)'
)

with open("tests/test_kite_depth_ws_stability.py", "w") as f:
    f.write(code)
