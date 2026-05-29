from __future__ import annotations

import json
import os

import pytest

from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def _runtime_dirs(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    return runtime_root, logs_root


def test_phase2_rejection_evidence_counts_missing_quote_age(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    runtime_root, logs_root = _runtime_dirs

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T1",
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
    assert out

    artifact_logs = logs_root / "phase2_rejection_latest.json"
    artifact_runtime = runtime_root / "phase2_rejection_latest.json"
    assert artifact_logs.exists()
    assert artifact_runtime.exists()

    payload = _read_json(artifact_logs)
    assert payload["input_candidate_count"] == 1
    assert payload["ranked_candidate_count"] == 1
    assert payload["missing_quote_age_count"] == 1


def test_phase2_rejection_evidence_counts_missing_spread(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    _runtime_dirs

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": None,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ]
    )
    assert out

    from core.paths import logs_dir

    payload = _read_json(logs_dir() / "phase2_rejection_latest.json")
    assert payload["missing_spread_count"] == 1


def test_phase2_rejection_evidence_counts_missing_liquidity(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    _runtime_dirs

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T3",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": None,
                "quote_source": "option_chain_live",
            }
        ]
    )
    assert out

    from core.paths import logs_dir

    payload = _read_json(logs_dir() / "phase2_rejection_latest.json")
    assert payload["missing_liquidity_count"] == 1


def test_phase2_rejection_evidence_counts_unknown_quote_source(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    _runtime_dirs

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T4",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "unknown",
            }
        ]
    )
    assert out

    from core.paths import logs_dir

    payload = _read_json(logs_dir() / "phase2_rejection_latest.json")
    assert payload["input_candidate_count"] == 1
    assert payload["unknown_quote_source_count"] == 1
    assert int(payload.get("drop_reason_counts", {}).get("strict_unknown_quote_source", 0)) == 1


def test_phase2_rejection_evidence_does_not_change_output(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    runtime_root, logs_root = _runtime_dirs

    candidate = {
        "trade_id": "T5",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "quote_age_sec": 1.0,
        "spread_pct": 0.002,
        "liquidity_score": 1.0,
        "quote_source": "option_chain_live",
    }

    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", False, raising=False)
    out_no = build_candidates_phase2([dict(candidate)])

    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    out_yes = build_candidates_phase2([dict(candidate)])

    assert out_no == out_yes
    assert (logs_root / "phase2_rejection_latest.json").exists()
    assert (runtime_root / "phase2_rejection_latest.json").exists()


def test_phase2_evidence_does_not_reuse_stale_counts_across_calls(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    runtime_root, logs_root = _runtime_dirs

    build_candidates_phase2(
        [
            {
                "trade_id": "S1",
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
    first = _read_json(logs_root / "phase2_rejection_latest.json")
    assert first["missing_quote_age_count"] == 1

    build_candidates_phase2([])
    second = _read_json(logs_root / "phase2_rejection_latest.json")
    assert second["input_candidate_count"] == 0
    assert second["missing_quote_age_count"] == 0
