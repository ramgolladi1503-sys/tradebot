# Edge-purpose tests for Phase 2 candidate truth preservation and fail-closed behavior.
from __future__ import annotations

import json

import pytest

from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.regression]


def _candidate(**overrides):
    row = {
        "trade_id": "trade-1",
        "candidate_id": "cand-1",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "setup_id": "breakout-setup",
        "final_score": 0.91,
        "score": 0.91,
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "liquidity_score": 1.0,
        "spread_pct": 0.002,
        "quote_source": "option_chain_live",
        "execution_mode": "LIVE",
        "timestamp_epoch": 1718181000,
    }
    row.update(overrides)
    return row


@pytest.fixture()
def _runtime_dirs(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setenv("REPO_LOG_DIR", str(logs_root))
    return logs_root


def test_phase2_missing_option_token_candidate_is_dropped_with_explicit_rejection(_runtime_dirs, monkeypatch):
    """
    Edge purpose:
    Proves missing option-token candidates are dropped and rejection evidence is emitted.
    Bug/risk protected:
    Unorderable option candidates surviving Phase 2 as if they were executable.
    Expected behavior:
    Output is empty and rejection evidence records a hard execution drop.
    """
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)

    out = build_candidates_phase2(
        [
            _candidate(
                trade_id="missing-token",
                execution_allowed=False,
                tradable=False,
                execution_ok=False,
                hard_blockers=["MISSING_OPTION_TOKEN"],
            )
        ]
    )

    assert out == []

    payload = json.loads((_runtime_dirs / "phase2_rejection_latest.json").read_text(encoding="utf-8"))
    assert payload["phase2_input_count"] == 1
    assert payload["phase2_output_count"] == 0
    assert payload["hard_execution"] == 1
    assert payload["phase2_drop_reasons_by_category"]["hard_execution"] == 1


def test_phase2_missing_depth_candidate_is_dropped_from_output(_runtime_dirs, monkeypatch):
    """
    Edge purpose:
    Proves missing depth does not survive Phase 2 as live executable truth.
    Bug/risk protected:
    Option candidates with unusable execution depth leaking into ranked output.
    Expected behavior:
    Missing-depth candidate is removed.
    """
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)

    out = build_candidates_phase2(
        [
            _candidate(
                trade_id="missing-depth",
                execution_allowed=False,
                execution_ok=False,
                hard_blockers=["MISSING_DEPTH"],
            )
        ]
    )

    assert out == []


def test_phase2_contract_resolution_fallback_never_leaks_executable():
    """
    Edge purpose:
    Proves contract-resolution fallback rows cannot survive as executable Phase 2 output.
    Bug/risk protected:
    Unsafe fallback-resolved instruments reaching orderable candidate lists.
    Expected behavior:
    Fallback-resolved candidate is removed.
    """
    out = build_candidates_phase2(
        [
            _candidate(
                trade_id="fallback-contract",
                contract_resolution_status="fallback",
                source_flags={"contract_resolution_source": "fallback"},
            )
        ]
    )

    assert out == []


def test_phase2_runtime_fallback_quote_stays_non_executable_but_visible(monkeypatch):
    """
    Edge purpose:
    Proves runtime fallback quote rows do not masquerade as executable truth.
    Bug/risk protected:
    Recovered or subscription-failed quote rows being treated as live-ready edge.
    Expected behavior:
    Candidate can remain visible, but it is degraded and queue-capped.
    """
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)

    out = build_candidates_phase2(
        [
            _candidate(
                trade_id="runtime-fallback",
                quote_source="subscription_failed",
                timestamp_epoch=None,
            )
        ]
    )

    assert len(out) == 1
    row = out[0]
    assert row["trade_id"] == "runtime-fallback"
    assert row["execution_ok"] is False
    assert row["execution_context_degraded"] is True
    assert row["max_final_action"] == "QUEUE_ONLY"
    assert row["phase2_soft_degrade_reason"] == "execution_not_ready_noncritical"


def test_phase2_clean_candidate_preserves_identity_fields():
    """
    Edge purpose:
    Proves Phase 2 keeps candidate identity and strategy lineage intact for clean rows.
    Bug/risk protected:
    Candidate IDs and setup attribution being lost between strategy and ranking.
    Expected behavior:
    Trade, candidate, setup, and strategy fields survive unchanged.
    """
    out = build_candidates_phase2(
        [
            _candidate(
                trade_id="clean-trade",
                candidate_id="clean-candidate",
                strategy_family="mean_reversion",
                setup_id="mean-reversion-setup",
            )
        ]
    )

    assert len(out) == 1
    row = out[0]
    assert row["trade_id"] == "clean-trade"
    assert row["candidate_id"] == "clean-candidate"
    assert row["strategy_family"] == "mean_reversion"
    assert row["setup_id"] == "mean-reversion-setup"
