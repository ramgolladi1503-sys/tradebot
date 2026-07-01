import re
with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()
if "mock_api_key" not in c:
    c = c.replace("def ticker_callbacks():", """@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key")
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token")

@pytest.fixture
def ticker_callbacks():""")
    with open("tests/test_feed_reconnect_safety.py", "w") as f:
        f.write(c)
