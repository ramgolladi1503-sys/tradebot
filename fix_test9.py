import re
with open("tests/test_kite_ws_subprocess.py", "r") as f:
    code = f.read()

code = code.replace(
    'ret = ws.restart_depth_ws([101])\n    print("RETURN VALUE:", ret)',
    'events = []\n    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))\n    ret = ws.restart_depth_ws([101])\n    print("RETURN VALUE:", ret, "\\nEVENTS:", events)'
)

with open("tests/test_kite_ws_subprocess.py", "w") as f:
    f.write(code)
