from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.upstox_depth_shadow_capture_v2.parser import (
    PARSER_SCHEMA_VERSION,
    DepthParseError,
    parse_market_message,
)
from research.upstox_depth_shadow_capture_v2.session import (
    ShadowDepthSession,
    audit_shadow_session,
)


def _official_message(*, current_ts: int = 1_747_984_841_739) -> dict:
    return {
        "type": "live_feed",
        "feeds": {
            "NSE_FO|61755": {
                "fullFeed": {
                    "marketFF": {
                        "ltpc": {
                            "ltp": 181.95,
                            "ltt": "1747984841612",
                            "ltq": "75",
                            "cp": 73.85,
                        },
                        "marketLevel": {
                            "bidAskQuote": [
                                {"bidQ": "600", "bidP": 182.05, "askQ": "750", "askP": 182.4},
                                {"bidQ": "1950", "bidP": 182.0, "askQ": "675", "askP": 182.45},
                                {"bidQ": "900", "bidP": 181.95, "askQ": "1800", "askP": 182.5},
                                {"bidQ": "1350", "bidP": 181.9, "askQ": "1200", "askP": 182.55},
                                {"bidQ": "900", "bidP": 181.85, "askQ": "750", "askP": 182.6},
                            ]
                        },
                    }
                }
            }
        },
        "currentTs": str(current_ts),
    }


def test_official_v3_full_payload_preserves_all_five_levels() -> None:
    parsed = parse_market_message(
        _official_message(), received_at_ns=1_747_984_841_800_000_000, mode="full"
    )
    assert parsed.market_feed_count == 1
    assert parsed.index_feed_count == 0
    assert parsed.empty_depth_count == 0
    record = parsed.records[0]
    assert record["instrument_key"] == "NSE_FO|61755"
    assert record["valid_depth_level_count"] == 5
    assert record["two_sided_level_count"] == 5
    assert record["best_bid_price"] == pytest.approx(182.05)
    assert record["best_ask_price"] == pytest.approx(182.4)
    assert record["best_bid_qty"] == 600
    assert record["best_ask_qty"] == 750
    assert record["bid_ladder_monotonic"] is True
    assert record["ask_ladder_monotonic"] is True
    assert record["schema_version"] == PARSER_SCHEMA_VERSION
    levels = json.loads(record["depth_json"])
    assert len(levels) == 5
    assert levels[4]["bid_price"] == pytest.approx(181.85)


def test_sdk_snake_case_aliases_are_explicitly_supported() -> None:
    message = {
        "feeds": {
            "NSE_FO|1": {
                "full_feed": {
                    "market_ff": {
                        "ltpc": {"ltp": "10", "ltt": "1000", "ltq": "2", "cp": "9"},
                        "market_level": {
                            "bid_ask_quote": [
                                {"bid_q": "5", "bid_p": "9.9", "ask_q": "6", "ask_p": "10.1"}
                            ]
                        },
                    }
                }
            }
        },
        "current_ts": "1001",
    }
    parsed = parse_market_message(message, received_at_ns=2_000_000_000, mode="full")
    assert parsed.records[0]["two_sided_level_count"] == 1
    assert "OFFICIAL_V3_FEEDS:FULL_FEED_MARKET_FF" == parsed.records[0]["parser_variant"]


def test_index_full_feed_is_not_invented_as_depth() -> None:
    message = {
        "type": "live_feed",
        "feeds": {
            "NSE_INDEX|Nifty 50": {
                "fullFeed": {
                    "indexFF": {"ltpc": {"ltp": 25000.0, "ltt": "1000", "cp": 24900.0}}
                }
            }
        },
        "currentTs": "1001",
    }
    parsed = parse_market_message(message, received_at_ns=2_000_000_000)
    assert parsed.records == ()
    assert parsed.index_feed_count == 1
    assert parsed.market_feed_count == 0


def test_market_info_is_accepted_without_depth_records() -> None:
    parsed = parse_market_message(
        {"type": "market_info", "currentTs": "1000", "marketInfo": {}},
        received_at_ns=2_000_000_000,
    )
    assert parsed.message_type == "market_info"
    assert parsed.records == ()


def test_full_mode_rejects_more_than_five_levels() -> None:
    message = _official_message()
    quotes = message["feeds"]["NSE_FO|61755"]["fullFeed"]["marketFF"]["marketLevel"]["bidAskQuote"]
    quotes.append({"bidQ": "1", "bidP": 181.8, "askQ": "1", "askP": 182.65})
    with pytest.raises(DepthParseError, match="maximum is 5"):
        parse_market_message(message, received_at_ns=2_000_000_000, mode="full")


def test_invalid_level_is_counted_without_destroying_valid_levels() -> None:
    message = _official_message()
    quotes = message["feeds"]["NSE_FO|61755"]["fullFeed"]["marketFF"]["marketLevel"]["bidAskQuote"]
    quotes[2]["bidP"] = "not-a-price"
    parsed = parse_market_message(message, received_at_ns=2_000_000_000)
    record = parsed.records[0]
    assert parsed.invalid_level_count == 1
    assert record["valid_depth_level_count"] == 4
    assert record["invalid_depth_level_count"] == 1


def test_shadow_session_writes_atomic_hashed_chunks_and_no_token(tmp_path: Path) -> None:
    session = ShadowDepthSession(
        output_root=tmp_path,
        requested_instrument_keys=["NSE_FO|61755"],
        mode="full",
        chunk_rows=2,
        flush_seconds=3600,
        session_date="20260723",
    )
    first = _official_message(current_ts=1_747_984_841_000)
    second = _official_message(current_ts=1_747_984_842_000)
    session.record_message(first, received_at_ns=1_747_984_841_100_000_000)
    session.record_message(second, received_at_ns=1_747_984_842_100_000_000)
    manifest = session.finalize()

    assert manifest["status"] == "COMPLETE"
    assert manifest["chunk_count"] == 1
    assert manifest["access_token_persisted"] is False
    assert manifest["raw_payload_persisted"] is False
    chunk = session.session_dir / manifest["chunks"][0]["path"]
    assert chunk.is_file()
    data = pd.read_parquet(chunk)
    assert len(data) == 2
    assert set(data["schema_version"]) == {PARSER_SCHEMA_VERSION}
    text = session.manifest_path.read_text(encoding="utf-8")
    assert "UPSTOX_ACCESS_TOKEN" not in text


def test_session_readiness_passes_for_valid_fixture_with_relaxed_test_duration(tmp_path: Path) -> None:
    session = ShadowDepthSession(
        output_root=tmp_path,
        requested_instrument_keys=["NSE_FO|61755"],
        mode="full",
        chunk_rows=10,
        flush_seconds=3600,
        session_date="20260723",
    )
    for offset in range(3):
        session.record_message(
            _official_message(current_ts=1_747_984_841_000 + offset * 1_000),
            received_at_ns=1_747_984_841_100_000_000 + offset * 1_000_000_000,
        )
    session.finalize()
    result = audit_shadow_session(
        session.session_dir,
        minimum_session_minutes=0.03,
        maximum_median_gap_seconds=2.0,
        maximum_p95_gap_seconds=2.0,
    )
    assert result["classification"] == "SHADOW_DEPTH_SESSION_READY_FOR_DEVELOPMENT"
    assert result["two_sided_depth_rate"] == pytest.approx(1.0)
    assert result["instrument_coverage_rate"] == pytest.approx(1.0)


def test_session_readiness_blocks_empty_depth(tmp_path: Path) -> None:
    message = _official_message()
    message["feeds"]["NSE_FO|61755"]["fullFeed"]["marketFF"]["marketLevel"]["bidAskQuote"] = []
    session = ShadowDepthSession(
        output_root=tmp_path,
        requested_instrument_keys=["NSE_FO|61755"],
        mode="full",
        chunk_rows=10,
        flush_seconds=3600,
        session_date="20260723",
    )
    for offset in range(3):
        message["currentTs"] = str(1_747_984_841_000 + offset * 1_000)
        session.record_message(message, received_at_ns=2_000_000_000 + offset)
    session.finalize()
    result = audit_shadow_session(
        session.session_dir,
        minimum_session_minutes=0.03,
        maximum_median_gap_seconds=2.0,
        maximum_p95_gap_seconds=2.0,
    )
    assert result["classification"] == "SHADOW_DEPTH_SESSION_NOT_READY"
    assert any(blocker.startswith("TWO_SIDED_DEPTH_RATE_BELOW_MINIMUM") for blocker in result["blockers"])
