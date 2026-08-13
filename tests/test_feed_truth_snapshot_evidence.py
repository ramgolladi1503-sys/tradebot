from __future__ import annotations

import json

import pytest

from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2
from core.feed.artifact_loader import FEED_RUNTIME_CANONICAL_WRITER, FEED_RUNTIME_SCHEMA_VERSION
from core.feed.artifact_provenance import stamp_feed_runtime_provenance
from core.runtime_truth_integrity import truth_hash_from_mapping


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
    if path.name == "feed_runtime_latest.json":
        payload = stamp_feed_runtime_provenance({
            **payload,
            "writer": FEED_RUNTIME_CANONICAL_WRITER,
            "schema_version": FEED_RUNTIME_SCHEMA_VERSION,
        })
        payload["snapshot_hash"] = truth_hash_from_mapping(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_ws_connected_true_but_option_ticks_stale_marks_feed_not_fresh(_runtime_dirs, monkeypatch):
    runtime_root, logs_root = _runtime_dirs
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 2.0, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)

    feed_json_path = logs_root / "feed_runtime_latest.json"
    _write_json(
        feed_json_path,
        {
            "effective_ws_connected": True,
            "market_open": True,
            "last_ws_tick_age_sec": 1.0,
            "subscribed_option_tokens_count": 10,
            "subscribed_tokens_count": 11,
            "option_last_tick_age_by_symbol": {"NIFTY": 10.0},
            "last_depth_age_sec": 0.5,
            "feed_ok": False,
        },
    )

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": False,
                "tradable": True,
                "execution_ok": False,
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ]
    )
    assert out == []

    truth = _read_json(logs_root / "feed_truth_latest.json")
    assert truth["ws_connected"] is True
    assert truth["option_tick_fresh"] is False
    assert truth["feed_fresh"] is False


def test_market_closed_marks_market_closed_detected(_runtime_dirs, monkeypatch):
    _runtime_dirs
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)

    from core.paths import logs_dir

    _write_json(
        logs_dir() / "feed_runtime_latest.json",
        {
            "effective_ws_connected": True,
            "market_open": False,
            "last_ws_tick_age_sec": None,
            "subscribed_option_tokens_count": 0,
            "subscribed_tokens_count": 0,
            "option_last_tick_age_by_symbol": {},
            "last_depth_age_sec": None,
            "feed_ok": False,
        },
    )

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": False,
                "tradable": True,
                "execution_ok": False,
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ]
    )
    assert out == []

    truth = _read_json(logs_dir() / "feed_truth_latest.json")
    assert truth["market_closed_detected"] is True
    assert truth["feed_fresh"] is False


def test_feed_truth_includes_phase2_missing_quote_age_count(_runtime_dirs, monkeypatch):
    runtime_root, logs_root = _runtime_dirs
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)

    _write_json(
        logs_root / "feed_runtime_latest.json",
        {
            "effective_ws_connected": True,
            "market_open": True,
            "last_ws_tick_age_sec": 1.0,
            "subscribed_option_tokens_count": 10,
            "subscribed_tokens_count": 11,
            "option_last_tick_age_by_symbol": {"NIFTY": 1.0},
            "last_depth_age_sec": 0.5,
            "feed_ok": True,
        },
    )

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T3",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": None,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ]
    )
    # Phase2 may hard-drop in strict modes depending on other config toggles;
    # the evidence artifact must still reflect the missing quote age condition.
    assert out == [] or out[0].get("phase2_missing_quote_age_sec") in (True, None)

    truth = _read_json(logs_root / "feed_truth_latest.json")
    assert truth["phase2_missing_quote_age_count"] == 1
