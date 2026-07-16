from __future__ import annotations

from pathlib import Path

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.movement_regime import MovementRegimeResult
from core.opening_range_retest_emission_store import OpeningRangeRetestEmissionStore
from core.runtime_snapshot_producer import _build_and_write_canonical_ranked_snapshot
from core import runtime_snapshot_producer
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from tests.test_candidate_phase2_ownership import _full_context, _regime as _ownership_regime
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    _history_state_for_rows,
    _temporal_context,
)


def _orb_regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.8,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.8,
            "VOLATILITY_EXPANSION": 0.45,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _orb_context(**overrides: object):
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    return _temporal_context(state, ce_premium_change=10.0, **overrides)


def _runtime_payload() -> dict[str, object]:
    return {
        "symbols": {
            "NIFTY": {
                "symbol": "NIFTY",
                "ohlc": {"close": 22608.0},
            }
        }
    }


def test_runtime_caller_uses_one_cached_owner_store_and_replays_restart_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    owner_db = tmp_path / "opening_range_retest_emission.sqlite"
    monkeypatch.setattr(runtime_snapshot_producer, "default_owner_db_path", lambda: owner_db)
    runtime_snapshot_producer._opening_range_retest_owner_store.cache_clear()

    context = _orb_context()
    setup_id = generate_opening_range_retest_candidates(context, _orb_regime())[0].evidence["setup_identity"]["setup_id"]
    captured_stores: list[object | None] = []
    reports = []
    real_build = runtime_snapshot_producer.build_ranked_opportunity_report

    def wrapped_build_ranked_opportunity_report(*args, **kwargs):
        kwargs.setdefault("candidate_generators", [generate_opening_range_retest_candidates])
        kwargs.setdefault("include_no_trade_candidate", False)
        captured_stores.append(kwargs.get("opening_range_retest_owner_store"))
        report = real_build(*args, **kwargs)
        reports.append(report)
        return report

    monkeypatch.setattr(runtime_snapshot_producer, "build_ranked_opportunity_report", wrapped_build_ranked_opportunity_report)
    monkeypatch.setattr(runtime_snapshot_producer, "_strategy_context_from_market_symbol", lambda symbol, data: context)
    monkeypatch.setattr(runtime_snapshot_producer, "write_ranked_pipeline_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(runtime_snapshot_producer, "write_ranked_vs_legacy_snapshot", lambda **kwargs: None)

    runtime_snapshot_producer._build_and_write_canonical_ranked_snapshot(_runtime_payload(), "unit", {"rows": []})
    runtime_snapshot_producer._build_and_write_canonical_ranked_snapshot(_runtime_payload(), "unit", {"rows": []})

    cached_store = runtime_snapshot_producer._opening_range_retest_owner_store()
    assert len(captured_stores) == 2
    assert captured_stores[0] is captured_stores[1] is cached_store

    first_report, second_report = reports
    assert first_report.candidate_pool.metadata["opening_range_retest_owner_results"][0]["result"] == "ACCEPTED_FOR_PUBLICATION"
    assert first_report.candidate_pool.metadata["opening_range_retest_owner_authoritative_count"] == 1
    assert first_report.candidate_pool.metadata["opening_range_retest_owner_existing_record_count"] == 1
    assert first_report.candidate_pool.candidate_count == 1
    assert second_report.candidate_pool.metadata["opening_range_retest_owner_results"][0]["result"] == "ALREADY_EMITTED"
    assert second_report.candidate_pool.metadata["opening_range_retest_owner_authoritative_count"] == 0
    assert second_report.candidate_pool.metadata["opening_range_retest_owner_existing_record_count"] == 1
    assert second_report.candidate_pool.candidate_count == 0
    assert OpeningRangeRetestEmissionStore(db_path=owner_db).get_outbox_record(setup_id) is not None


def test_runtime_caller_fails_closed_when_owner_store_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runtime_snapshot_producer._opening_range_retest_owner_store.cache_clear()
    monkeypatch.setattr(runtime_snapshot_producer, "_opening_range_retest_owner_store", lambda: None)

    context = _orb_context()
    setup_id = generate_opening_range_retest_candidates(context, _orb_regime())[0].evidence["setup_identity"]["setup_id"]
    reports = []
    real_build = runtime_snapshot_producer.build_ranked_opportunity_report

    def wrapped_build_ranked_opportunity_report(*args, **kwargs):
        kwargs.setdefault("candidate_generators", [generate_opening_range_retest_candidates])
        kwargs.setdefault("include_no_trade_candidate", False)
        report = real_build(*args, **kwargs)
        reports.append(report)
        return report

    monkeypatch.setattr(runtime_snapshot_producer, "build_ranked_opportunity_report", wrapped_build_ranked_opportunity_report)
    monkeypatch.setattr(runtime_snapshot_producer, "_strategy_context_from_market_symbol", lambda symbol, data: context)
    monkeypatch.setattr(runtime_snapshot_producer, "write_ranked_pipeline_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(runtime_snapshot_producer, "write_ranked_vs_legacy_snapshot", lambda **kwargs: None)

    _build_and_write_canonical_ranked_snapshot(_runtime_payload(), "unit", {"rows": []})

    report = reports[0]
    owner_results = report.candidate_pool.metadata["opening_range_retest_owner_results"]
    assert owner_results[0]["result"] == "OWNER_UNAVAILABLE"
    assert owner_results[0]["detail"] == "missing_owner_store"
    assert report.candidate_pool.candidate_count == 0
    assert report.candidate_pool.metadata["opening_range_retest_owner_authoritative_count"] == 0
    assert report.candidate_pool.metadata["opening_range_retest_owner_blocked_count"] == 1
    assert f"opening_range_retest_owner_blocked:OWNER_UNAVAILABLE:{setup_id}" in report.candidate_pool.blockers


def test_non_orb_candidate_pool_order_and_counts_are_unchanged_when_owner_store_is_supplied(tmp_path: Path):
    ctx = _full_context(orb_high=None, orb_low=None)
    regime = _ownership_regime()
    generators = [generate_compression_breakout_candidates, generate_trend_pullback_candidates]

    without_owner_store = build_candidate_pool_report(
        ctx,
        regime,
        candidate_generators=generators,
        include_no_trade_candidate=False,
    )
    with_owner_store = build_candidate_pool_report(
        ctx,
        regime,
        candidate_generators=generators,
        opening_range_retest_owner_store=OpeningRangeRetestEmissionStore(db_path=tmp_path / "opening_range_retest.sqlite"),
        include_no_trade_candidate=False,
    )

    assert [candidate.strategy_id for candidate in without_owner_store.candidates] == [candidate.strategy_id for candidate in with_owner_store.candidates]
    assert [candidate.direction for candidate in without_owner_store.candidates] == [candidate.direction for candidate in with_owner_store.candidates]
    assert [candidate.status for candidate in without_owner_store.candidates] == [candidate.status for candidate in with_owner_store.candidates]
    assert [round(candidate.raw_score, 6) for candidate in without_owner_store.candidates] == [round(candidate.raw_score, 6) for candidate in with_owner_store.candidates]
    assert without_owner_store.candidate_count == with_owner_store.candidate_count
    assert without_owner_store.movement_candidate_count == with_owner_store.movement_candidate_count
    assert with_owner_store.metadata["opening_range_retest_owner_authoritative_count"] == 0
    assert with_owner_store.metadata["opening_range_retest_owner_blocked_count"] == 0
