from pathlib import Path

from config import config as cfg
from core.fixture_validator import ensure_tradingsymbols


def test_fixture_validator_fills_missing_tradingsymbol(tmp_path, monkeypatch):
    log_path = tmp_path / "fixture_symbols.jsonl"
    monkeypatch.setattr(cfg, "REPLAY_FIXTURE_LOG_PATH", str(log_path))
    payload = {
        "name": "fixture_test",
        "snapshots": [
            {
                "symbol": "NIFTY",
                "option_chain": [
                    {
                        "symbol": "NIFTY",
                        "type": "CE",
                        "strike": 25000,
                        "expiry": "2026-02-26",
                        "instrument_token": 12345,
                        "ltp": 100.0,
                    }
                ],
            }
        ],
    }
    updates = ensure_tradingsymbols(payload, fixture_name="fixture_test")
    assert updates == 1
    row = payload["snapshots"][0]["option_chain"][0]
    assert row.get("tradingsymbol") == "NIFTY26FEB25000CE"
    assert log_path.exists()

