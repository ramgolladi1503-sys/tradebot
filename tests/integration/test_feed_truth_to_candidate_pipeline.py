from __future__ import annotations

import json

import pytest

from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2


pytestmark = [pytest.mark.integration, pytest.mark.edge, pytest.mark.regression]


@pytest.fixture()
def _runtime_dirs(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setenv("REPO_LOG_DIR", str(logs_root))
    return runtime_root, logs_root


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_stale_depth_runtime_truth_reaches_candidate_pipeline(_runtime_dirs, monkeypatch):
    """
    Edge purpose:
    Prevents a websocket-connected runtime snapshot with stale depth from becoming feed-fresh candidate truth.
    """
    _runtime_root, logs_root = _runtime_dirs
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SLA_SECONDS", 2.0, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)

    _write_json(
        logs_root / "feed_runtime_latest.json",
        {
            "effective_ws_connected": True,
            "market_open": True,
            "last_ws_tick_age_sec": 0.5,
            "subscribed_option_tokens_count": 10,
            "subscribed_tokens_count": 11,
            "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
            "last_depth_age_sec": 9.0,
        },
    )

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T-FEED-DEPTH-STALE",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 0.5,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ]
    )
    assert out

    truth = _read_json(logs_root / "feed_truth_latest.json")
    assert truth["ws_connected"] is True
    assert truth["option_tick_fresh"] is True
    assert truth["depth_fresh"] is False
    assert truth["feed_fresh"] is False
    assert "depth_stale_or_missing" in truth["stale_reason"]
