from __future__ import annotations

from pathlib import Path

from config import config as cfg
from scripts.run_paper_replay import run_replay


def _fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "snapshots" / name


def _cfg_snapshot() -> dict[str, object]:
    return {
        "EXECUTION_MODE": getattr(cfg, "EXECUTION_MODE", None),
        "PAPER_STRICT_MODE": getattr(cfg, "PAPER_STRICT_MODE", None),
        "PAPER_STRICT_QUOTES": getattr(cfg, "PAPER_STRICT_QUOTES", None),
        "ALLOW_SYNTHETIC_CHAIN": getattr(cfg, "ALLOW_SYNTHETIC_CHAIN", None),
        "REQUIRE_LIVE_OPTION_QUOTES": getattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", None),
        "REQUIRE_LIVE_QUOTES": getattr(cfg, "REQUIRE_LIVE_QUOTES", None),
    }


def _cfg_restore(snapshot: dict[str, object]) -> None:
    for key, value in snapshot.items():
        setattr(cfg, key, value)


def test_replay_gap_move_up_emits_candidate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snapshot = _cfg_snapshot()
    try:
        payload = run_replay(_fixture_path("gap_move_up.json"), seed=21)
    finally:
        _cfg_restore(snapshot)
    assert payload["candidate_count"] >= 1
    assert payload["fallback_candidate_count"] == 0


def test_replay_stale_feed_burst_still_planning_candidate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snapshot = _cfg_snapshot()
    try:
        payload = run_replay(_fixture_path("stale_feed_burst.json"), seed=17)
    finally:
        _cfg_restore(snapshot)
    assert payload["candidate_count"] >= 1
    first = payload["candidates"][0]
    assert first["planning_only"] is True
    assert first["execution_allowed"] is False


def test_replay_partial_chain_failure_recovers(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snapshot = _cfg_snapshot()
    try:
        payload = run_replay(_fixture_path("partial_chain_failure.json"), seed=31)
    finally:
        _cfg_restore(snapshot)
    assert payload["candidate_count"] >= 1
    assert payload["fallback_candidate_count"] == 0


def test_replay_clock_skew_is_no_trade_not_crash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snapshot = _cfg_snapshot()
    try:
        payload = run_replay(_fixture_path("clock_skew.json"), seed=9)
    finally:
        _cfg_restore(snapshot)
    assert payload["candidate_count"] == 0
    assert payload["no_trade"] is True
    assert payload["top_reject_reasons"].get("no_signal", 0) >= 1

