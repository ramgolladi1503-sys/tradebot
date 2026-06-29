import re

with open("tests/test_kite_auth_consistency.py", "r") as f:
    c = f.read()
c = c.replace("""monkeypatch.setattr(orchestrator_mod, "read_latest_runtime_snapshot", lambda: {})""",
"""import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {})""")
with open("tests/test_kite_auth_consistency.py", "w") as f:
    f.write(c)

with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()
c = c.replace("""import core.orchestrator as orchestrator_mod
    monkeypatch.setattr(orchestrator_mod, "read_latest_runtime_snapshot", lambda: {}, raising=False)""",
"""import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)""")
with open("tests/test_feed_reconnect_safety.py", "w") as f:
    f.write(c)
