import re
with open("tests/test_kite_auth_consistency.py", "r") as f:
    c = f.read()
if "mock_api_key" not in c:
    c = c.replace("def test_", """@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key")
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token")

def test_""", 1)
    with open("tests/test_kite_auth_consistency.py", "w") as f:
        f.write(c)
