from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from core.movement_contract import StrategyCandidate
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.canonical_intent_campaign import (
    CanonicalIntentPolicy,
    candidate_is_intent_eligible,
    generate_session_intents,
)
from scripts import run_canonical_option_intent_campaign_v1 as campaign


def _candidate(
    *,
    direction: str = "BUY_CALL",
    blockers: tuple[str, ...] = ("OPTION_CONFIRMATION_MISSING",),
) -> StrategyCandidate:
    return StrategyCandidate(
        schema_version=1,
        strategy_id="opening_drive_v1",
        movement_type="OPENING_DRIVE",
        symbol="NIFTY",
        direction=direction,
        status="RAW_CANDIDATE",
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.8,
        option_confirmation_score=None,
        liquidity_score=None,
        freshness_score=None,
        volatility_score=0.6,
        regime_alignment_score=0.7,
        timing_score=0.8,
        trap_risk_score=0.1,
        confluence_score=0.5,
        entry_trigger="completed_bar_breakout",
        invalid_if="structure_fails",
        rank_reason="not_ranked",
        blockers=blockers,
        warnings=(),
        confluence_tags=(),
        suppression_tags=(),
        source_signals=("canonical_test",),
        regime_scores={},
        evidence={},
        lineage={},
        generated_epoch=1.0,
    )


def _frame() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-07-01 09:15:00",
        periods=4,
        freq="5min",
        tz="Asia/Kolkata",
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1000, 1000, 1000, 1000],
        }
    )


def test_canonical_candidate_maps_to_ce_and_strictly_later_entry() -> None:
    contexts = []

    def invoker(strategy_key, context):
        contexts.append(context)
        record = SimpleNamespace(
            invocation_count=1,
            candidate_count=1,
            exception_count=0,
            callable_identity="strategies.movement.opening_drive.generate",
            callable_source_hash="a" * 64,
            exact_reason=None,
        )
        return (_candidate(),), record

    intents, summary = generate_session_intents(
        strategy_key="OPENING_DRIVE",
        frame=_frame(),
        session_date="2026-07-01",
        symbol="NIFTY",
        partition="development",
        invoker=invoker,
    )
    assert len(intents) == 1
    row = intents[0]
    assert row["intended_option_type"] == "CE"
    assert pd.Timestamp(row["earliest_entry_timestamp"]) > pd.Timestamp(
        row["signal_timestamp"]
    )
    assert row["intended_expiry_rule"] == "nearest_non_expired"
    assert row["partition"] == "development"
    assert summary["invocation_count"] == 1
    assert len(contexts[0].completed_bar_history) == 2
    assert contexts[0].ts_epoch == pd.Timestamp(
        "2026-07-01 09:25:00", tz="Asia/Kolkata"
    ).timestamp()


def test_future_mutation_cannot_change_first_canonical_intent() -> None:
    def invoker(strategy_key, context):
        record = SimpleNamespace(
            invocation_count=1,
            candidate_count=1,
            exception_count=0,
            callable_identity="canonical.owner",
            callable_source_hash="b" * 64,
            exact_reason=None,
        )
        return (_candidate(direction="BUY_PUT"),), record

    original, _ = generate_session_intents(
        strategy_key="OPENING_DRIVE",
        frame=_frame(),
        session_date="2026-07-01",
        symbol="NIFTY",
        partition="validation",
        invoker=invoker,
    )
    mutated = _frame()
    mutated.loc[2:, ["open", "high", "low", "close"]] = [
        [9990, 10010, 9980, 10000],
        [10000, 10020, 9990, 10010],
    ]
    changed, _ = generate_session_intents(
        strategy_key="OPENING_DRIVE",
        frame=mutated,
        session_date="2026-07-01",
        symbol="NIFTY",
        partition="validation",
        invoker=invoker,
    )
    assert original == changed
    assert original[0]["intended_option_type"] == "PE"


def test_structural_blocker_is_not_converted_to_option_intent() -> None:
    assert not candidate_is_intent_eligible(
        _candidate(blockers=("CONFLICTING_TRAP_SIGNAL",))
    )


def test_identity_is_deterministic() -> None:
    def invoker(strategy_key, context):
        return (
            (_candidate(),),
            SimpleNamespace(
                invocation_count=1,
                candidate_count=1,
                exception_count=0,
                callable_identity="canonical.owner",
                callable_source_hash="c" * 64,
                exact_reason=None,
            ),
        )

    kwargs = dict(
        strategy_key="OPENING_DRIVE",
        frame=_frame(),
        session_date="2026-07-01",
        symbol="NIFTY",
        partition="development",
        policy=CanonicalIntentPolicy(),
        invoker=invoker,
    )
    first, _ = generate_session_intents(**kwargs)
    second, _ = generate_session_intents(**kwargs)
    assert first[0]["signal_identity_hash"] == second[0]["signal_identity_hash"]


def test_campaign_never_invokes_holdout_sessions(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame()
    sessions = {
        ("2026-07-01", "NIFTY"): frame,
        ("2026-07-02", "NIFTY"): frame,
        ("2026-07-03", "NIFTY"): frame,
    }
    partition = {
        "schema_version": "test",
        "holdout_outcomes_read": False,
        "indexes": {
            "NIFTY": {
                "development_dates": ["2026-07-01"],
                "validation_dates": ["2026-07-02"],
                "holdout_dates": ["2026-07-03"],
                "ordered_dates": ["2026-07-01", "2026-07-02", "2026-07-03"],
                "session_count": 3,
                "date_range": ["2026-07-01", "2026-07-03"],
            }
        },
    }
    invoked_dates = []

    monkeypatch.setattr(
        campaign,
        "audit_corpus",
        lambda root: (sessions, [], [], {"schema_version": "test"}),
    )
    monkeypatch.setattr(campaign, "build_partitions", lambda value: partition)

    def fake_generate(**kwargs):
        invoked_dates.append(kwargs["session_date"])
        return [], {
            "strategy_id": kwargs["strategy_key"],
            "underlying": "NIFTY",
            "session_date": kwargs["session_date"],
            "partition": kwargs["partition"],
            "invocation_count": 1,
            "candidate_count": 0,
            "intent_count": 0,
            "exception_count": 0,
            "callable_identities": "[]",
            "callable_source_hashes": "[]",
            "exact_reasons": "[]",
            "holdout_outcomes_read": False,
            "allowed_for_live_execution": False,
        }

    monkeypatch.setattr(campaign, "generate_session_intents", fake_generate)
    manifest = campaign.run_campaign(
        tmp_path,
        tmp_path / "out",
        underlyings=("NIFTY",),
    )
    assert "2026-07-03" not in invoked_dates
    assert manifest["holdout_outcomes_read"] is False
    assert manifest["directional_proxy_pnl_computed"] is False
