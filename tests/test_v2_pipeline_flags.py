from __future__ import annotations

from core.v2_pipeline import run_v2_pipeline
from config import config as cfg


def _reset_v2_flags(monkeypatch):
    for name in cfg.v2_flags_snapshot().keys():
        monkeypatch.setattr(cfg, name, False, raising=False)


def test_phase1_flags_off_noop(monkeypatch):
    _reset_v2_flags(monkeypatch)
    result = run_v2_pipeline([])
    assert result["enabled"] is False and result["candidates"] == []


def test_phase1_candidate_generator_shadow_only(monkeypatch):
    _reset_v2_flags(monkeypatch)
    monkeypatch.setattr(cfg, "ENABLE_CANDIDATE_GENERATOR_V2", True, raising=False)
    market_data = {
        "symbol": "NIFTY",
        "option_chain": [
            {"strike": 20000, "type": "CE", "expiry": "2026-03-28"},
            {"strike": 20000, "type": "PE", "expiry": "2026-03-28"},
            {"strike": 20100, "type": "CE", "expiry": "2026-03-28"},
            {"strike": 20100, "type": "PE", "expiry": "2026-03-28"},
        ],
        "underlying_spot": 20050,
    }
    result = run_v2_pipeline([market_data])
    assert result["enabled"] is True and result["candidates"] and all(
        "execution_allowed" not in cand for cand in result["candidates"]
    )
