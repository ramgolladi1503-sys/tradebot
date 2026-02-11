import time

from core import auth_health


def test_auth_health_cache_skips_probe(monkeypatch):
    auth_health._reset_cache_for_tests()
    now = time.time()
    cached = {
        "ok": True,
        "ts_epoch": now,
        "source": "cache",
        "ttl_sec": 60,
        "api_key_tail4": "TEST",
        "access_token_tail4": "TOKN",
        "access_token_has_whitespace": False,
        "user_id": "U123",
        "user_name": "Tester",
        "error": "",
    }
    auth_health._CACHE["ts_epoch"] = now
    auth_health._CACHE["payload"] = cached

    def _probe_fail():
        raise AssertionError("probe should not be called when cache is fresh")

    monkeypatch.setattr(auth_health, "_kite_profile_payload", _probe_fail)
    payload = auth_health.get_kite_auth_health(force=False)
    assert payload["ok"] is True
    assert payload["source"] == "cache"
