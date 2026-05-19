from __future__ import annotations

import builtins
import importlib

import pytest

import core.engine_phase2_adapter as phase2


def _production_phase2_module():
    """Reload Phase2 without the legacy CI import hook wrapping the builder.

    PR #101 moves the fallback-contract firewall into the production adapter.
    The legacy CI compatibility hook can wrap `build_candidates_phase2` during
    the full suite and re-add compatibility rows. These tests intentionally
    target the production adapter contract, not that test-only wrapper.
    """

    current_import = builtins.__import__
    original_import = current_import
    try:
        import core.ci_compat_contracts as ci_compat

        original_import = getattr(ci_compat, "_original_import", current_import)
    except Exception:
        original_import = current_import

    builtins.__import__ = original_import
    try:
        return importlib.reload(phase2)
    finally:
        builtins.__import__ = current_import


@pytest.fixture(autouse=True)
def _use_production_phase2_adapter(monkeypatch):
    prod = _production_phase2_module()
    monkeypatch.setattr(phase2, "build_candidates_phase2", prod.build_candidates_phase2, raising=False)
    monkeypatch.setattr(phase2, "_base_build_candidates_phase2", prod._base_build_candidates_phase2, raising=False)


def _base_candidate(**overrides):
    candidate = {
        "trade_id": "t-1",
        "symbol": "NIFTY",
        "execution_mode": "LIVE",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "execution_score": 1.0,
        "liquidity_score": 1.0,
        "final_score": 0.91,
        "score": 0.91,
        "best_bid": 100.0,
        "best_ask": 101.0,
        "opt_ltp": 100.5,
        "spread_pct": 0.005,
        "quote_source": "live_depth",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "candidate_status": "executable",
        "execution_status": "executable",
    }
    candidate.update(overrides)
    return candidate


def test_detects_contract_resolution_fallback_from_boolean_flag():
    candidate = _base_candidate(contract_resolution_fallback_used=True)

    assert phase2._is_contract_resolution_fallback(candidate) is True


def test_detects_contract_resolution_fallback_from_nested_source_flags():
    candidate = _base_candidate(
        source_flags={
            "contract_resolution_event": "CONTRACT_RESOLUTION_FALLBACK",
            "requested_strike": 23750,
            "resolved_strike": 23700,
        }
    )

    assert phase2._is_contract_resolution_fallback(candidate) is True


def test_block_contract_resolution_fallback_forces_non_executable_shape():
    candidate = _base_candidate(contract_resolution_fallback_used=True)

    blocked = phase2._block_contract_resolution_fallback(candidate)

    assert blocked["execution_allowed"] is False
    assert blocked["tradable"] is False
    assert blocked["execution_ok"] is False
    assert blocked["truth_allows_execution"] is False
    assert blocked["execution_blocked"] is True
    assert blocked["permission"] == "QUEUE_ONLY"
    assert blocked["final_action"] == "QUEUE_ONLY"
    assert blocked["max_final_action"] == "QUEUE_ONLY"
    assert blocked["execution_status"] == "blocked"
    assert blocked["candidate_status"] == "blocked"
    assert blocked["execution_block_reason"] == phase2.CONTRACT_FALLBACK_REASON
    assert phase2.CONTRACT_FALLBACK_BLOCKER in blocked["hard_blockers"]
    assert blocked["source_flags"]["contract_resolution_fallback_blocked"] is True


def test_phase2_contract_hard_drop_rejects_fallback_contract_candidate():
    candidate = _base_candidate(contract_resolution_fallback_used=True)

    assert phase2._phase2_contract_hard_drop(candidate) is True
    assert candidate["execution_allowed"] is False
    assert candidate["final_action"] == "QUEUE_ONLY"
    assert phase2.CONTRACT_FALLBACK_BLOCKER in candidate["hard_blockers"]


def test_build_candidates_phase2_drops_fallback_contract_candidate(monkeypatch):
    fallback = _base_candidate(
        trade_id="fallback-1",
        contract_resolution_status="fallback",
        final_score=0.99,
        score=0.99,
    )
    clean = _base_candidate(
        trade_id="clean-1",
        symbol="BANKNIFTY",
        final_score=0.75,
        score=0.75,
    )

    monkeypatch.setattr(phase2, "_base_build_candidates_phase2", lambda raw_candidates: [fallback, clean])

    out = phase2.build_candidates_phase2([fallback, clean])

    assert [row["trade_id"] for row in out] == ["clean-1"]
    assert all(row["trade_id"] != "fallback-1" for row in out)
    assert all(row.get("permission") != "EXECUTE" or row["trade_id"] != "fallback-1" for row in out)


def test_build_candidates_phase2_does_not_readd_raw_fallback_candidate(monkeypatch):
    fallback = _base_candidate(
        trade_id="fallback-raw-1",
        source_flags={"contract_resolution_source": "fallback"},
        final_score=0.99,
        score=0.99,
    )

    monkeypatch.setattr(phase2, "_base_build_candidates_phase2", lambda raw_candidates: [])

    out = phase2.build_candidates_phase2([fallback])

    assert out == []
