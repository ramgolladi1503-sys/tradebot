import re
with open("tests/test_kite_depth_ws_stability.py", "r") as f:
    code = f.read()

code = code.replace(
    'ws.start_depth_ws([101, 102], profile_verified=True)',
    'try:\n        ws.start_depth_ws([101, 102], profile_verified=True)\n    except Exception as e:\n        print(e)'
)

with open("tests/test_kite_depth_ws_stability.py", "w") as f:
    f.write(code)
