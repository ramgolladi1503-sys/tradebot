from core.market_event_graph_breadth_producer import (
    attach_completed_constituent_breadth_snapshots,
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
    produce_completed_constituent_breadth_snapshots,
)
from core.market_event_graph_contract import FROZEN_DISCOVERY_SPEC_SHA256, FROZEN_THRESHOLDS
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.market_event_graph_reversal import (
    generate_market_event_graph_reversal_candidates,
)


def _returns(negative_count: int, total: int = 50, value: float = 0.001):
    return [-value] * negative_count + [value] * (total - negative_count)


def _bar(
    ts_epoch: float,
    source_bar_end_epoch: float,
    *,
    negative_count: int,
    index_ret1: float,
    session_date: str = "2026-07-29",
    total: int = 50,
    completed: bool = True,
):
    return {
        "ts_epoch": ts_epoch,
        "source_bar_end_epoch": source_bar_end_epoch,
        "session_date": session_date,
        "index_ret1": index_ret1,
        "constituent_ret1": _returns(negative_count, total=total),
        "completed": completed,
    }


def _metadata():
    return {
        **frozen_threshold_metadata(),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-07-29"),
        "completed_constituent_bars": [
            _bar(100.0, 90.0, negative_count=40, index_ret1=-0.001),
            _bar(160.0, 150.0, negative_count=25, index_ret1=-0.004),
            _bar(220.0, 210.0, negative_count=5, index_ret1=0.001),
            _bar(280.0, 270.0, negative_count=20, index_ret1=0.001),
        ],
    }


def _regime():
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.6,
            "TREND_DOWN": 0.2,
            "VOLATILITY_EXPANSION": 0.4,
            "COMPRESSION": 0.2,
            "TRAP_RISK": 0.1,
            "CHOP": 0.1,
        },
    )


def _context(metadata, ts_epoch: float = 280.0):
    return StrategyContext(
        symbol="NIFTY",
        ts_epoch=ts_epoch,
        option_ce_ltp=120.0,
        option_pe_ltp=105.0,
        ce_premium_change=2.0,
        pe_premium_change=-1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01,
        ce_depth=1500.0,
        pe_depth=1300.0,
        quote_source="realtime",
        fallback_used=False,
        option_ltp_age_sec=1.0,
        metadata=metadata,
    )


def test_produces_exact_consecutive_causal_graph_from_completed_returns():
    rows = produce_completed_constituent_breadth_snapshots(_metadata())

    assert tuple(row["event_label"] for row in rows) == (
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    )
    assert tuple(row["ts_epoch"] for row in rows) == (100.0, 160.0, 220.0)
    assert tuple(row["source_bar_end_epoch"] for row in rows) == (90.0, 150.0, 210.0)
    assert tuple(row["participation_count"] for row in rows) == (50, 50, 50)
    assert rows[-1]["market_event_graph_entry_bar_ts_epoch"] == 280.0
    assert rows[-1]["market_event_graph_frozen_spec_sha256"] == FROZEN_DISCOVERY_SPEC_SHA256
    assert rows[-1]["market_event_graph_triplet_id"]


def test_does_not_match_open_ended_sequence_with_intervening_row():
    metadata = _metadata()
    metadata["completed_constituent_bars"] = [
        metadata["completed_constituent_bars"][0],
        _bar(130.0, 120.0, negative_count=25, index_ret1=0.001),
        metadata["completed_constituent_bars"][1],
        metadata["completed_constituent_bars"][2],
        metadata["completed_constituent_bars"][3],
    ]

    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_fails_closed_without_frozen_thresholds_runtime_state_or_coverage():
    assert produce_completed_constituent_breadth_snapshots({"completed_constituent_bars": []}) == []

    metadata = _metadata()
    metadata.pop("market_event_graph_runtime_state")
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["completed_constituent_bars"][0]["constituent_ret1"] = _returns(10, total=20)
    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_missing_or_wrong_frozen_spec_fails_closed():
    metadata = _metadata()
    metadata.pop("market_event_graph_frozen_spec_sha256")
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["market_event_graph_frozen_spec_sha256"] = "bad"
    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_changed_threshold_fails_contract_verification():
    metadata = _metadata()
    metadata["market_event_graph_thresholds"] = dict(FROZEN_THRESHOLDS, breadth_low=0.30)

    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_threshold_bypass_metadata_is_rejected():
    metadata = {
        "market_event_graph_allow_test_thresholds": True,
        "test_thresholds": True,
        "threshold_override": True,
        "allow_override": True,
        "market_event_graph_thresholds": {
            "breadth_high": 0.8,
            "breadth_low": 0.2,
            "divergence_low": -0.002,
            "min_constituents": 10,
        },
        "completed_constituent_bars": [
            _bar(100.0, 90.0, negative_count=8, total=10, index_ret1=0.0),
            _bar(160.0, 150.0, negative_count=0, total=10, index_ret1=-0.002),
            _bar(220.0, 210.0, negative_count=2, total=10, index_ret1=0.0),
            _bar(280.0, 270.0, negative_count=5, total=10, index_ret1=0.0),
        ],
    }

    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_threshold_boundaries_are_inclusive_without_override_metadata():
    metadata = {
        **frozen_threshold_metadata(),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-07-29"),
        "completed_constituent_bars": [
            _bar(100.0, 90.0, negative_count=54, total=247, index_ret1=0.0),
            {
                "ts_epoch": 160.0,
                "source_bar_end_epoch": 150.0,
                "session_date": "2026-07-29",
                "index_ret1": FROZEN_THRESHOLDS["divergence_low"],
                "constituent_ret1": [0.0] * 247,
                "completed": True,
            },
            _bar(220.0, 210.0, negative_count=25, total=247, index_ret1=0.0),
            _bar(280.0, 270.0, negative_count=100, total=247, index_ret1=0.0),
        ],
    }

    events = produce_completed_constituent_breadth_snapshots(metadata)

    assert tuple(event["event_label"] for event in events) == (
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    )
    assert tuple(event["ts_epoch"] for event in events) == (100.0, 160.0, 220.0)
    assert events[-1]["market_event_graph_entry_bar_ts_epoch"] == 280.0
    assert events[-1]["market_event_graph_frozen_spec_sha256"] == FROZEN_DISCOVERY_SPEC_SHA256


def test_session_boundary_and_timestamp_ordering_fail_closed():
    metadata = _metadata()
    metadata["completed_constituent_bars"][1]["session_date"] = "2026-07-30"
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["completed_constituent_bars"][2]["ts_epoch"] = 90.0
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["completed_constituent_bars"][1]["ts_epoch"] = 100.0
    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_source_bar_ordering_fail_closed():
    metadata = _metadata()
    metadata["completed_constituent_bars"][0]["source_bar_end_epoch"] = 101.0
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["completed_constituent_bars"][1]["source_bar_end_epoch"] = 90.0
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["completed_constituent_bars"][2]["source_bar_end_epoch"] = 150.0
    assert produce_completed_constituent_breadth_snapshots(metadata) == []

    metadata = _metadata()
    metadata["completed_constituent_bars"] = [
        metadata["completed_constituent_bars"][1],
        metadata["completed_constituent_bars"][0],
        metadata["completed_constituent_bars"][2],
        metadata["completed_constituent_bars"][3],
    ]
    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_entry_bar_must_share_graph_session():
    metadata = _metadata()
    metadata["completed_constituent_bars"][3]["session_date"] = "2026-07-30"

    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_no_same_bar_emission_until_next_completed_bar():
    metadata = _metadata()
    metadata["completed_constituent_bars"] = metadata["completed_constituent_bars"][:3]

    assert produce_completed_constituent_breadth_snapshots(metadata) == []


def test_incomplete_bar_breaks_consecutive_graph_and_reports_invalid():
    metadata = _metadata()
    metadata["completed_constituent_bars"][1]["completed"] = False

    enriched = attach_completed_constituent_breadth_snapshots(metadata)

    assert enriched["constituent_breadth_producer_status"] == "MISSING_OR_INVALID"
    assert enriched["constituent_breadth_event_count"] == 0
    assert "completed_constituent_breadth_snapshots" not in enriched


def test_strategy_can_emit_advisory_candidate_from_raw_completed_constituent_bars():
    metadata = _metadata()
    candidates = generate_market_event_graph_reversal_candidates(_context(metadata), _regime())

    assert tuple(candidate.direction for candidate in candidates) == ("BUY_CALL",)
    candidate = candidates[0]
    assert candidate.lineage["promotion_state"] == "ADVISORY_ONLY"
    assert candidate.evidence["allowed_for_live_execution"] is False
    assert candidate.evidence["is_order_action"] is False
    assert candidate.evidence["broker_api_called"] is False
    assert candidate.evidence["idempotency_key"] == candidate.evidence["triplet_id"]
    assert metadata["market_event_graph_runtime_state"]["last_processed_entry_bar_ts_epoch"] == 280.0
    assert metadata["market_event_graph_runtime_state"]["last_emitted_triplet_id"] == candidate.evidence["triplet_id"]


def test_strategy_idempotency_uses_persisted_runtime_state():
    metadata = _metadata()
    context = _context(metadata)

    first = generate_market_event_graph_reversal_candidates(context, _regime())
    assert tuple(candidate.direction for candidate in first) == ("BUY_CALL",)
    first_triplet_id = first[0].evidence["triplet_id"]
    assert first[0].evidence["idempotency_key"] == first_triplet_id

    second = generate_market_event_graph_reversal_candidates(context, _regime())
    assert second == ()

    fresh_context = _context(metadata)
    assert generate_market_event_graph_reversal_candidates(fresh_context, _regime()) == ()

    metadata["completed_constituent_bars"].append(
        _bar(340.0, 330.0, negative_count=20, index_ret1=0.001)
    )
    assert generate_market_event_graph_reversal_candidates(fresh_context, _regime()) == ()
    assert metadata["market_event_graph_runtime_state"]["last_emitted_triplet_id"] == first_triplet_id


def test_distinct_later_graph_emits_once_after_state_watermark():
    metadata = _metadata()

    first = generate_market_event_graph_reversal_candidates(_context(metadata), _regime())
    assert tuple(candidate.direction for candidate in first) == ("BUY_CALL",)
    first_triplet_id = first[0].evidence["triplet_id"]

    metadata["completed_constituent_bars"].extend(
        [
            _bar(340.0, 330.0, negative_count=40, index_ret1=-0.001),
            _bar(400.0, 390.0, negative_count=25, index_ret1=-0.004),
            _bar(460.0, 450.0, negative_count=5, index_ret1=0.001),
            _bar(520.0, 510.0, negative_count=20, index_ret1=0.001),
        ]
    )
    later_context = _context(metadata, ts_epoch=520.0)
    later = generate_market_event_graph_reversal_candidates(later_context, _regime())

    assert tuple(candidate.direction for candidate in later) == ("BUY_CALL",)
    assert later[0].evidence["triplet_id"] != first_triplet_id
    assert later[0].evidence["allowed_for_live_execution"] is False
    assert generate_market_event_graph_reversal_candidates(later_context, _regime()) == ()


def test_strategy_does_not_emit_when_graph_has_a_gap():
    metadata = _metadata()
    metadata["completed_constituent_bars"].insert(
        1,
        _bar(130.0, 120.0, negative_count=25, index_ret1=0.001),
    )

    assert generate_market_event_graph_reversal_candidates(_context(metadata), _regime()) == ()
