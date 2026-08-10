import json
import sqlite3
from datetime import datetime

from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.market_event_graph_constituent_source import (
    DEFAULT_MANIFEST_PATH,
    attach_market_event_graph_constituent_source,
    resolve_constituent_tokens,
)
from core.market_event_graph_tick_reader import read_last_ticks_by_minute
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.time_utils import IST_TZ


INDEX_TOKEN = 999999


def _manifest():
    return json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))


def _instrument_rows(manifest):
    rows = [
        {
            "exchange": "NSE",
            "tradingsymbol": symbol,
            "instrument_type": "EQ",
            "instrument_token": 1000 + index,
        }
        for index, symbol in enumerate(manifest["constituents"])
    ]
    rows.append(
        {
            "exchange": "NSE",
            "tradingsymbol": "NIFTY 50",
            "instrument_type": "INDEX",
            "instrument_token": INDEX_TOKEN,
        }
    )
    return rows


def _minute_end(hour: int, minute: int) -> int:
    return int(datetime(2026, 7, 30, hour, minute, tzinfo=IST_TZ).timestamp())


def _tick_fixture(manifest):
    resolution = resolve_constituent_tokens(manifest, _instrument_rows(manifest))
    token_by_symbol = resolution["constituent_tokens"]
    boundaries = [_minute_end(9, minute) for minute in range(15, 21)]
    prices = {token: 100.0 for token in token_by_symbol.values()}
    index_price = 22500.0
    fixture = {boundary: {} for boundary in boundaries}

    for token in token_by_symbol.values():
        fixture[boundaries[0]][token] = {
            "instrument_token": token,
            "ltp": prices[token],
            "ts_epoch": boundaries[0] - 1.0,
        }
    fixture[boundaries[0]][INDEX_TOKEN] = {
        "instrument_token": INDEX_TOKEN,
        "ltp": index_price,
        "ts_epoch": boundaries[0] - 1.0,
    }

    symbols = list(manifest["constituents"])
    negative_counts = [40, 25, 5, 20, 20]
    index_returns = [-0.001, -0.002, 0.001, 0.001, 0.001]
    for offset, boundary in enumerate(boundaries[1:]):
        negative = set(symbols[: negative_counts[offset]])
        for symbol in symbols:
            token = token_by_symbol[symbol]
            multiplier = 0.999 if symbol in negative else 1.001
            prices[token] *= multiplier
            fixture[boundary][token] = {
                "instrument_token": token,
                "ltp": prices[token],
                "ts_epoch": boundary - 1.0,
            }
        index_price *= 1.0 + index_returns[offset]
        fixture[boundary][INDEX_TOKEN] = {
            "instrument_token": INDEX_TOKEN,
            "ltp": index_price,
            "ts_epoch": boundary - 1.0,
        }
    return fixture


def _reader(fixture):
    def read(tokens, boundaries):
        token_set = {int(token) for token in tokens}
        return {
            int(boundary): {
                token: dict(row)
                for token, row in fixture.get(int(boundary), {}).items()
                if token in token_set
            }
            for boundary in boundaries
        }

    return read


def _regime():
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.8,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.0,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.2,
        },
    )


def _context(metadata):
    return StrategyContext(
        symbol="NIFTY",
        ts_epoch=float(_minute_end(9, 20)),
        spot_ltp=22500.0,
        option_ce_ltp=120.0,
        option_pe_ltp=90.0,
        ce_premium_change=8.0,
        pe_premium_change=-1.0,
        ce_spread_pct=0.01,
        pe_spread_pct=0.01,
        ce_depth=1500.0,
        pe_depth=1400.0,
        option_ltp_age_sec=1.0,
        quote_source="live_option_tick",
        fallback_used=False,
        metadata=metadata,
    )


def test_manifest_resolves_exactly_one_nse_equity_token_per_constituent():
    manifest = _manifest()

    resolution = resolve_constituent_tokens(manifest, _instrument_rows(manifest))

    assert resolution["status"] == "READY"
    assert resolution["reason"] == "all_manifest_tokens_resolved"
    assert resolution["expected_constituent_count"] == 50
    assert resolution["resolved_constituent_count"] == 50
    assert resolution["missing_symbols"] == []
    assert resolution["ambiguous_symbols"] == []
    assert resolution["index_token"] == INDEX_TOKEN
    assert tuple(sorted(resolution["constituent_tokens"])) == tuple(
        sorted(manifest["constituents"])
    )


def test_manifest_resolves_kite_index_row_when_segment_is_indices_and_type_is_eq():
    manifest = _manifest()
    rows = _instrument_rows(manifest)
    for row in rows:
        if row["tradingsymbol"] == "NIFTY 50":
            row["instrument_type"] = "EQ"
            row["segment"] = "INDICES"

    resolution = resolve_constituent_tokens(manifest, rows)

    assert resolution["status"] == "READY"
    assert resolution["index_token"] == INDEX_TOKEN


def test_manifest_resolution_fails_closed_for_missing_and_ambiguous_tokens():
    manifest = _manifest()
    rows = _instrument_rows(manifest)
    rows = [row for row in rows if row["tradingsymbol"] != "WIPRO"]
    rows.append(
        {
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE",
            "instrument_type": "EQ",
            "instrument_token": 987654,
        }
    )

    resolution = resolve_constituent_tokens(manifest, rows)

    assert resolution["status"] == "FAILED"
    assert resolution["reason"] == "instrument_tokens_missing_or_ambiguous"
    assert resolution["missing_symbols"] == ["WIPRO"]
    assert resolution["ambiguous_symbols"] == ["RELIANCE"]
    assert resolution["resolved_constituent_count"] == 48


def test_read_only_tick_reader_uses_right_closed_completed_minutes(tmp_path):
    database = tmp_path / "ticks.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE ticks (instrument_token INTEGER, last_price REAL, "
        "timestamp_epoch REAL, volume REAL, oi REAL)"
    )
    connection.executemany(
        "INSERT INTO ticks VALUES (?, ?, ?, ?, ?)",
        [
            (1, 100.0, 59.0, 1.0, 2.0),
            (1, 101.0, 60.0, 1.0, 2.0),
            (1, 102.0, 60.1, 1.0, 2.0),
            (1, 103.0, 119.0, 1.0, 2.0),
            (2, 200.0, 119.0, 1.0, 2.0),
        ],
    )
    connection.commit()
    connection.close()

    rows = read_last_ticks_by_minute([1, 2], [60, 120], db_path=database)

    assert rows[60][1]["ltp"] == 101.0
    assert 2 not in rows[60]
    assert rows[120][1]["ltp"] == 103.0
    assert rows[120][2]["ltp"] == 200.0
    assert rows[120][1]["source"] == "sqlite_read_only"


def test_live_source_builds_strict_completed_history_and_frozen_graph(tmp_path):
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    state_path = tmp_path / "source_state.json"

    metadata = attach_market_event_graph_constituent_source(
        {},
        symbol="NIFTY",
        as_of_epoch=float(_minute_end(9, 20) + 10),
        enabled=True,
        state_path=state_path,
        instrument_provider=lambda: _instrument_rows(manifest),
        subscription_fn=lambda tokens: set(tokens) == {
            INDEX_TOKEN,
            *range(1000, 1050),
        },
        tick_reader=_reader(fixture),
    )

    bars = metadata["completed_constituent_bars"]
    evidence = metadata["market_event_graph_constituent_source_evidence"]
    assert metadata["market_event_graph_constituent_source_status"] == "READY"
    assert metadata["market_event_graph_constituent_source_reason"] == (
        "completed_constituent_bars_current"
    )
    assert tuple(int(row["source_bar_end_epoch"]) for row in bars) == tuple(
        _minute_end(9, minute) for minute in range(16, 21)
    )
    assert tuple(row["participation_count"] for row in bars) == (50, 50, 50, 50, 50)
    assert tuple(round(sum(value < 0 for value in row["constituent_ret1"]) / 50, 2) for row in bars[:3]) == (
        0.8,
        0.5,
        0.1,
    )
    assert evidence["subscription_ok"] is True
    assert evidence["completed_bar_count"] == 5
    assert evidence["latest_participation_count"] == 50
    assert metadata["market_event_graph_constituent_source_managed"] is True
    assert state_path.is_file()


def test_gap_blocks_later_intervals_instead_of_collapsing_time(tmp_path):
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    missing_end = _minute_end(9, 17)
    fixture[missing_end] = {
        token: row
        for token, row in fixture[missing_end].items()
        if token == INDEX_TOKEN
    }

    metadata = attach_market_event_graph_constituent_source(
        {},
        symbol="NIFTY",
        as_of_epoch=float(_minute_end(9, 20) + 10),
        enabled=True,
        state_path=tmp_path / "gap_state.json",
        instrument_provider=lambda: _instrument_rows(manifest),
        subscription_fn=lambda tokens: True,
        tick_reader=_reader(fixture),
    )

    assert metadata["market_event_graph_constituent_source_status"] == "INTERVAL_GAP_BLOCKED"
    assert metadata["market_event_graph_constituent_source_reason"] == (
        "constituent_tick_pair_coverage_below_minimum"
    )
    assert tuple(
        int(row["source_bar_end_epoch"])
        for row in metadata["completed_constituent_bars"]
    ) == (_minute_end(9, 16),)
    failure = metadata["market_event_graph_constituent_source_evidence"][
        "last_build_failures"
    ][0]
    assert failure["minute_end_epoch"] == missing_end
    assert failure["participation_count"] == 0


def test_initial_missing_index_pair_is_skipped_as_warmup_but_later_bars_proceed(tmp_path):
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    first_target_boundary = _minute_end(9, 16)
    fixture[first_target_boundary].pop(INDEX_TOKEN, None)
    state_path = tmp_path / "warmup_state.json"

    metadata = attach_market_event_graph_constituent_source(
        {},
        symbol="NIFTY",
        as_of_epoch=float(_minute_end(9, 20) + 10),
        enabled=True,
        state_path=state_path,
        instrument_provider=lambda: _instrument_rows(manifest),
        subscription_fn=lambda tokens: True,
        tick_reader=_reader(fixture),
    )

    assert metadata["market_event_graph_constituent_source_status"] == "PARTIAL_HISTORY"
    assert metadata["market_event_graph_constituent_source_reason"] == (
        "fewer_than_four_completed_intervals"
    )
    bars = metadata["completed_constituent_bars"]
    assert len(bars) == 3
    assert tuple(int(row["source_bar_end_epoch"]) for row in bars) == tuple(
        _minute_end(9, minute) for minute in range(18, 21)
    )
    failures = metadata["market_event_graph_constituent_source_evidence"]["last_build_failures"]
    assert [failure["reason"] for failure in failures] == [
        "warmup_boundary_skipped:index_tick_pair_missing",
        "warmup_boundary_skipped:index_tick_pair_missing",
    ]
    assert all(failure["skipped"] is True for failure in failures)
    assert all(failure["classification"] == "leading_warmup_gap" for failure in failures)
    assert all(failure["accepted"] is False for failure in failures)
    assert all(failure["completed_bar_produced"] is False for failure in failures)


def test_candidate_pool_persists_emitted_triplet_across_new_context(tmp_path):
    manifest = _manifest()
    fixture = _tick_fixture(manifest)
    state_path = tmp_path / "durable_state.json"
    metadata = attach_market_event_graph_constituent_source(
        {},
        symbol="NIFTY",
        as_of_epoch=float(_minute_end(9, 20) + 10),
        enabled=True,
        state_path=state_path,
        instrument_provider=lambda: _instrument_rows(manifest),
        subscription_fn=lambda tokens: True,
        tick_reader=_reader(fixture),
    )

    first_report = build_candidate_pool_report(
        _context(metadata),
        _regime(),
        include_no_trade_candidate=False,
    )
    first_calls = tuple(
        candidate
        for candidate in first_report.candidates
        if candidate.direction == "BUY_CALL"
    )
    assert tuple(candidate.strategy_id for candidate in first_calls) == (
        "market_event_graph_reversal_v1",
    )
    assert first_calls[0].evidence["allowed_for_live_execution"] is False
    assert first_report.metadata["market_event_graph_constituent_state_persisted"] is True

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    emitted_id = persisted["runtime_state"]["last_emitted_triplet_id"]
    assert emitted_id == first_calls[0].evidence["triplet_id"]

    second_metadata = dict(metadata)
    second_metadata["market_event_graph_runtime_state"] = dict(
        persisted["runtime_state"]
    )
    second_report = build_candidate_pool_report(
        _context(second_metadata),
        _regime(),
        include_no_trade_candidate=False,
    )
    second_calls = tuple(
        candidate
        for candidate in second_report.candidates
        if candidate.direction == "BUY_CALL"
    )
    assert second_calls == ()
    assert second_report.metadata["market_event_graph_constituent_state_persisted"] is True
