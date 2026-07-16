from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.movement_contract import StrategyCandidate
from core.movement_regime import MovementRegimeResult
from core.opening_range_retest_emission_store import (
    OpeningRangeRetestEmissionStore,
    PublicationResult,
)
from core.opening_range_retest_publication import build_opening_range_retest_proposal
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    _history_state_for_rows,
    _temporal_context,
)


def _regime(**scores: float) -> MovementRegimeResult:
    base = {
        "TREND_UP": 0.6,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.2,
        "VOLATILITY_EXPANSION": 0.3,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime="TREND_UP", scores=base)


def _orb_context(**overrides: object):
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    return _temporal_context(state, ce_premium_change=10.0, **overrides)


def _orb_generator(ctx, regime):
    return generate_opening_range_retest_candidates(ctx, regime)


def _control_candidate() -> StrategyCandidate:
    return StrategyCandidate(
        schema_version=1,
        strategy_id="control_no_trade_v1",
        movement_type="NO_TRADE_CHOP",
        symbol="NIFTY",
        direction="NO_TRADE",
        status="NO_TRADE",
        raw_score=0.1,
        confidence_score=0.1,
        price_structure_score=0.1,
        option_confirmation_score=None,
        liquidity_score=None,
        freshness_score=None,
        volatility_score=0.1,
        regime_alignment_score=0.1,
        timing_score=0.1,
        trap_risk_score=0.0,
        confluence_score=0.1,
        entry_trigger="control",
        invalid_if="control",
        rank_reason="control",
        evidence={"setup_identity": {"control": True}},
    )


def _control_generator(ctx, regime):
    return (_control_candidate(),)


def _fake_owner_store(result: str, detail: str = "simulated") -> object:
    class _Store:
        def __init__(self, publication_result: PublicationResult) -> None:
            self.publication_result = publication_result
            self.calls: list[str] = []

        def accept_candidate_proposal(self, proposal):
            self.calls.append(proposal.setup_id)
            return self.publication_result

    return _Store(PublicationResult(result=result, setup_id="orb-owner-1", detail=detail))


def test_publication_helper_preserves_candidate_identity_and_fingerprint():
    candidate = generate_opening_range_retest_candidates(_orb_context(), _regime())[0]
    proposal = build_opening_range_retest_proposal(candidate)

    assert proposal.setup_id == candidate.evidence["setup_identity"]["setup_id"]
    assert proposal.history_hash == candidate.evidence["setup_identity"]["history_hash"]
    assert proposal.created_at_iso == candidate.evidence["setup_identity"]["proposal_ready_at_iso"]
    assert proposal.candidate_fingerprint == json.dumps(
        {
            "strategy_id": "opening_range_retest_v1",
            "direction": "BUY_CALL",
            "status": "RAW_CANDIDATE",
            "raw_score": round(candidate.raw_score, 6),
            "entry_trigger": candidate.entry_trigger,
            "invalid_if": candidate.invalid_if,
            "rank_reason": candidate.rank_reason,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_owner_acceptance_exposes_one_authoritative_candidate(tmp_path: Path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "opening_range_owner.sqlite")
    report = build_candidate_pool_report(
        _orb_context(),
        _regime(),
        candidate_generators=[_orb_generator],
        opening_range_retest_owner_store=store,
        include_no_trade_candidate=False,
    )

    directional = [candidate for candidate in report.candidates if candidate.strategy_id == "opening_range_retest_v1"]
    assert len(directional) == 1
    assert report.metadata["opening_range_retest_owner_authoritative_count"] == 1
    assert report.metadata["opening_range_retest_owner_blocked_count"] == 0
    owner_result = report.metadata["opening_range_retest_owner_results"][0]
    assert owner_result["setup_id"] == directional[0].evidence["setup_identity"]["setup_id"]
    assert owner_result["strategy_id"] == "opening_range_retest_v1"
    assert owner_result["result"] == "ACCEPTED_FOR_PUBLICATION"
    assert owner_result["detail"] is None
    assert owner_result["lineage_state"] == "EMITTED"
    assert owner_result["publication_state"] == "PENDING"
    assert owner_result["publication_attempts"] == 0
    assert owner_result["outbox_id"]
    assert owner_result["authoritative"] is True
    assert directional[0].evidence["setup_identity"]["history_hash"]
    assert directional[0].evidence["setup_identity"]["proposal_ready_at_iso"] == "2026-07-14T09:34:00+05:30"
    assert directional[0].lineage["promotion_state"] == "READY_FOR_PUBLICATION"


def test_owner_duplicate_restart_remains_authoritative_but_not_republished(tmp_path: Path):
    db_path = tmp_path / "opening_range_owner.sqlite"
    first_store = OpeningRangeRetestEmissionStore(db_path=db_path)
    first_report = build_candidate_pool_report(
        _orb_context(),
        _regime(),
        candidate_generators=[_orb_generator],
        opening_range_retest_owner_store=first_store,
        include_no_trade_candidate=False,
    )
    second_store = OpeningRangeRetestEmissionStore(db_path=db_path)
    second_report = build_candidate_pool_report(
        _orb_context(),
        _regime(),
        candidate_generators=[_orb_generator],
        opening_range_retest_owner_store=second_store,
        include_no_trade_candidate=False,
    )

    assert first_report.metadata["opening_range_retest_owner_results"][0]["result"] == "ACCEPTED_FOR_PUBLICATION"
    assert second_report.metadata["opening_range_retest_owner_results"][0]["result"] == "ALREADY_EMITTED"
    assert len([candidate for candidate in first_report.candidates if candidate.strategy_id == "opening_range_retest_v1"]) == 1
    assert len([candidate for candidate in second_report.candidates if candidate.strategy_id == "opening_range_retest_v1"]) == 0
    assert first_report.metadata["opening_range_retest_owner_authoritative_count"] == 1
    assert second_report.metadata["opening_range_retest_owner_authoritative_count"] == 0
    assert first_report.metadata["opening_range_retest_owner_existing_record_count"] == 1
    assert second_report.metadata["opening_range_retest_owner_existing_record_count"] == 1
    assert first_report.metadata["opening_range_retest_owner_proposal_count"] == 1
    assert second_report.metadata["opening_range_retest_owner_proposal_count"] == 1
    assert first_report.metadata["raw_candidate_count_before_phase2_enrichment"] == 1
    assert second_report.metadata["raw_candidate_count_before_phase2_enrichment"] == 0


def test_owner_duplicate_within_single_report_is_suppressed(tmp_path: Path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "opening_range_owner.sqlite")

    def duplicate_generator(ctx, regime):
        return generate_opening_range_retest_candidates(ctx, regime) + generate_opening_range_retest_candidates(ctx, regime)

    report = build_candidate_pool_report(
        _orb_context(),
        _regime(),
        candidate_generators=[duplicate_generator],
        opening_range_retest_owner_store=store,
        include_no_trade_candidate=False,
    )

    directional = [candidate for candidate in report.candidates if candidate.strategy_id == "opening_range_retest_v1"]
    assert len(directional) == 1
    assert report.metadata["opening_range_retest_owner_authoritative_count"] == 1
    assert len(report.metadata["opening_range_retest_owner_results"]) == 2
    assert report.metadata["opening_range_retest_owner_results"][0]["result"] == "ACCEPTED_FOR_PUBLICATION"
    assert report.metadata["opening_range_retest_owner_results"][1]["result"] == "ALREADY_EMITTED"


@pytest.mark.parametrize(
    ("owner_result", "detail"),
    [
        ("OWNER_BUSY", "simulated_busy"),
        ("OWNER_UNAVAILABLE", "simulated_unavailable"),
        ("OWNER_STATE_CONFLICT", "simulated_conflict"),
    ],
)
def test_owner_blocked_states_do_not_expose_or_abort_other_generators(owner_result: str, detail: str, tmp_path: Path):
    report = build_candidate_pool_report(
        _orb_context(),
        _regime(),
        candidate_generators=[_orb_generator, _control_generator],
        opening_range_retest_owner_store=_fake_owner_store(owner_result, detail),
        include_no_trade_candidate=False,
    )

    assert [candidate.strategy_id for candidate in report.candidates] == ["control_no_trade_v1"]
    assert report.metadata["opening_range_retest_owner_authoritative_count"] == 0
    assert report.metadata["opening_range_retest_owner_blocked_count"] == 1
    assert report.metadata["opening_range_retest_owner_results"][0]["result"] == owner_result
    assert f"opening_range_retest_owner_blocked:{owner_result}:orb-owner-1" in report.blockers
    assert "OPTION_CONFIRMATION_MISSING" in report.blockers


def test_owner_acceptance_is_concurrent_and_deterministic(tmp_path: Path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "opening_range_owner.sqlite")
    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []
    lock = threading.Lock()

    def _run() -> None:
        barrier.wait(timeout=10)
        report = build_candidate_pool_report(
            _orb_context(),
            _regime(),
            candidate_generators=[_orb_generator],
            opening_range_retest_owner_store=store,
            include_no_trade_candidate=False,
        )
        with lock:
            results.append(
                {
                    "owner_result": report.metadata["opening_range_retest_owner_results"][0]["result"],
                    "candidate_count": report.candidate_count,
                    "setup_id": report.metadata["opening_range_retest_owner_results"][0]["setup_id"],
                }
            )

    threads = [threading.Thread(target=_run, daemon=True), threading.Thread(target=_run, daemon=True)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == 2
    assert sorted(item["owner_result"] for item in results) == ["ACCEPTED_FOR_PUBLICATION", "ALREADY_EMITTED"]
    assert sorted(item["candidate_count"] for item in results) == [0, 1]
    assert len({item["setup_id"] for item in results}) == 1
