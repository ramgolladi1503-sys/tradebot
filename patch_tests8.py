import re

with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()

c = c.replace("""monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=False: {"ok": True, "user_id": "ABCD1234"}, raising=False)""",
"""monkeypatch.setattr("core.kite_depth_ws.get_kite_auth_health", lambda force=False, **kwargs: {"ok": True, "user_id": "ABCD1234"}, raising=False)""")

with open("tests/test_feed_reconnect_safety.py", "w") as f:
    f.write(c)
