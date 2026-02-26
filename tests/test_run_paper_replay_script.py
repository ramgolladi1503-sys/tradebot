from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from scripts.run_paper_replay import run_replay


def _fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "snapshots" / name


def test_paper_replay_is_deterministic_for_same_seed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    original = {
        "EXECUTION_MODE": getattr(cfg, "EXECUTION_MODE", None),
        "PAPER_STRICT_MODE": getattr(cfg, "PAPER_STRICT_MODE", None),
        "PAPER_STRICT_QUOTES": getattr(cfg, "PAPER_STRICT_QUOTES", None),
        "ALLOW_SYNTHETIC_CHAIN": getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", None),
        "REQUIRE_LIVE_OPTION_QUOTES": getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", None),
        "REQUIRE_LIVE_QUOTES": getattr(cfg, "REQUIRE_LIVE_QUOTES", None),
        "REJECT_REASONS_LOG_PATH": getattr(cfg, "REJECT_REASONS_LOG_PATH", None),
    }
    try:
        first = run_replay(_fixture_path("trend_up.json"), seed=11)
        second = run_replay(_fixture_path("trend_up.json"), seed=11)
    finally:
        for key, value in original.items():
            setattr(cfg, key, value)

    assert first["candidate_count"] >= 1
    assert first["candidates"] == second["candidates"]
    assert first["top_reject_reasons"] == second["top_reject_reasons"]


def test_paper_replay_trend_up_prefers_trade_builder_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    original = {
        "EXECUTION_MODE": getattr(cfg, "EXECUTION_MODE", None),
        "PAPER_STRICT_MODE": getattr(cfg, "PAPER_STRICT_MODE", None),
        "PAPER_STRICT_QUOTES": getattr(cfg, "PAPER_STRICT_QUOTES", None),
        "ALLOW_SYNTHETIC_CHAIN": getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", None),
        "REQUIRE_LIVE_OPTION_QUOTES": getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", None),
        "REQUIRE_LIVE_QUOTES": getattr(cfg, "REQUIRE_LIVE_QUOTES", None),
        "REJECT_REASONS_LOG_PATH": getattr(cfg, "REJECT_REASONS_LOG_PATH", None),
    }
    try:
        payload = run_replay(_fixture_path("trend_up.json"), seed=7)
    finally:
        for key, value in original.items():
            setattr(cfg, key, value)

    assert payload["candidate_count"] >= 1
    assert payload["fallback_candidate_count"] == 0
    first_candidate = payload["candidates"][0]
    assert first_candidate["source"] == "trade_builder"
    assert first_candidate["strategy"] != "REPLAY_SYNTH"


def test_paper_replay_range_dead_emits_no_trade(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    original = {
        "EXECUTION_MODE": getattr(cfg, "EXECUTION_MODE", None),
        "PAPER_STRICT_MODE": getattr(cfg, "PAPER_STRICT_MODE", None),
        "PAPER_STRICT_QUOTES": getattr(cfg, "PAPER_STRICT_QUOTES", None),
        "ALLOW_SYNTHETIC_CHAIN": getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", None),
        "REQUIRE_LIVE_OPTION_QUOTES": getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", None),
        "REQUIRE_LIVE_QUOTES": getattr(cfg, "REQUIRE_LIVE_QUOTES", None),
        "REJECT_REASONS_LOG_PATH": getattr(cfg, "REJECT_REASONS_LOG_PATH", None),
    }
    try:
        payload = run_replay(_fixture_path("range_dead.json"), seed=13)
    finally:
        for key, value in original.items():
            setattr(cfg, key, value)

    assert payload["candidate_count"] == 0
    assert payload["no_trade"] is True
    assert payload["top_reject_reasons"]
    assert payload["top_reject_reasons"].get("no_signal", 0) >= 1


def test_paper_replay_writes_reject_telemetry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reject_path = tmp_path / "logs" / "reject_reasons.jsonl"
    original = {
        "EXECUTION_MODE": getattr(cfg, "EXECUTION_MODE", None),
        "PAPER_STRICT_MODE": getattr(cfg, "PAPER_STRICT_MODE", None),
        "PAPER_STRICT_QUOTES": getattr(cfg, "PAPER_STRICT_QUOTES", None),
        "ALLOW_SYNTHETIC_CHAIN": getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", None),
        "REQUIRE_LIVE_OPTION_QUOTES": getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", None),
        "REQUIRE_LIVE_QUOTES": getattr(cfg, "REQUIRE_LIVE_QUOTES", None),
        "REJECT_REASONS_LOG_PATH": getattr(cfg, "REJECT_REASONS_LOG_PATH", None),
    }
    try:
        cfg.REJECT_REASONS_LOG_PATH = str(reject_path)
        payload = run_replay(_fixture_path("range_dead.json"), seed=7)
    finally:
        for key, value in original.items():
            setattr(cfg, key, value)

    assert payload["candidate_count"] == 0
    assert reject_path.exists()
    rows = [
        json.loads(line)
        for line in reject_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    paper_rows = [row for row in rows if str(row.get("source") or "") == "paper_replay"]
    assert paper_rows
    assert all(str(row.get("reason") or "").strip() for row in paper_rows)
    assert all(str(row.get("symbol") or "").upper() == "NIFTY" for row in paper_rows)
    assert all(str(row.get("mode") or "").upper() == "PAPER" for row in paper_rows)


def test_paper_replay_restores_cfg_and_scoring_patch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    original_exec_mode = getattr(cfg, "EXECUTION_MODE", None)
    original_paper_strict = getattr(cfg, "PAPER_STRICT_MODE", None)
    original_score_fn = trade_builder_module.compute_trade_score

    _ = run_replay(_fixture_path("range_dead.json"), seed=5)

    assert getattr(cfg, "EXECUTION_MODE", None) == original_exec_mode
    assert getattr(cfg, "PAPER_STRICT_MODE", None) == original_paper_strict
    assert trade_builder_module.compute_trade_score is original_score_fn
