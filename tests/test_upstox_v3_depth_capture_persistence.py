from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

import scripts.capture_upstox_market_daily as capture
from core.upstox_v3_feed_parser import UpstoxV3ParseError, parse_upstox_v3_message


def _official_full_feed_message() -> dict:
    return {
        "type": "live_feed",
        "currentTs": "1740729566039",
        "feeds": {
            "NSE_FO|45450": {
                "fullFeed": {
                    "marketFF": {
                        "ltpc": {"ltp": 219.3, "ltt": "1740729552723"},
                        "marketLevel": {
                            "bidAskQuote": [
                                {
                                    "bidQ": "75",
                                    "bidP": 219.2,
                                    "askQ": "150",
                                    "askP": 219.4,
                                },
                                {
                                    "bidQ": "225",
                                    "bidP": 219.1,
                                    "askQ": "300",
                                    "askP": 219.5,
                                },
                            ]
                        },
                        "optionGreeks": {"delta": 0.5, "iv": 0.14},
                        "eFeedDetails": {"vtt": "1000", "oi": 500},
                    }
                }
            }
        },
    }


def test_rest_quote_depth_shape_is_rejected_not_inferred() -> None:
    message = {
        "type": "live_feed",
        "feeds": {
            "NSE_FO|1": {
                "ltpc": {"ltp": 100.0},
                "depth": {
                    "buy": [{"price": 99.9, "quantity": 10}],
                    "sell": [{"price": 100.1, "quantity": 20}],
                },
            }
        },
    }

    with pytest.raises(UpstoxV3ParseError, match="REST-style depth"):
        parse_upstox_v3_message(message)


def test_one_sided_generic_price_quantity_depth_is_rejected() -> None:
    message = {
        "type": "live_feed",
        "feeds": {
            "NSE_FO|1": {
                "firstLevelWithGreeks": {
                    "ltpc": {"ltp": 100.0},
                    "firstDepth": {"price": 99.9, "quantity": 10},
                }
            }
        },
    }

    [record] = parse_upstox_v3_message(message)
    assert record["depth"] == []
    assert record["depth_valid"] is False
    assert record["bid_price"] is None
    assert record["ask_price"] is None


def test_collector_round_trips_full_depth_and_marks_session_valid(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(capture, "UPSTOX_AVAILABLE", False)

    collector = capture.DataCollector("token", ["NSE_FO|45450"])
    collector.on_market_update(_official_full_feed_message())

    assert collector.record_count == 1
    assert collector.valid_depth_counts_by_instrument["NSE_FO|45450"] == 1
    assert collector.finalize() is True

    [parquet_path] = sorted(collector.out_dir.glob("ticks_*.parquet"))
    [row] = pq.read_table(parquet_path).to_pylist()
    assert row["bid_price"] == pytest.approx(219.2)
    assert row["ask_price"] == pytest.approx(219.4)
    assert row["bid_quantity"] == 75
    assert row["ask_quantity"] == 150
    assert row["depth_level_count"] == 2
    assert row["depth_valid"] is True
    assert row["depth"][1] == {
        "bid_price": 219.1,
        "bid_quantity": 225,
        "ask_price": 219.5,
        "ask_quantity": 300,
    }

    manifest = json.loads((collector.out_dir / "manifest.json").read_text())
    assert manifest["capture_valid"] is True
    assert manifest["research_depth_eligible"] is True
    assert manifest["capture_classification"] == "UPSTOX_V3_DEPTH_CAPTURE_VALID"
    assert manifest["parsed_records"] == 1
    assert manifest["records_written"] == 1
    assert not (collector.out_dir / "INVALID_DEPTH_CAPTURE.json").exists()


def test_collector_marks_empty_depth_session_invalid(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(capture, "UPSTOX_AVAILABLE", False)

    collector = capture.DataCollector("token", ["NSE_FO|45450"])
    collector.on_market_update(
        {
            "type": "live_feed",
            "feeds": {
                "NSE_FO|45450": {
                    "fullFeed": {
                        "marketFF": {
                            "ltpc": {"ltp": 219.3},
                            "marketLevel": {"bidAskQuote": []},
                        }
                    }
                }
            },
        }
    )

    assert collector.record_count == 1
    assert collector.finalize() is False
    manifest = json.loads((collector.out_dir / "manifest.json").read_text())
    assert manifest["capture_valid"] is False
    assert manifest["research_depth_eligible"] is False
    assert "NO_VALID_DEPTH_RECORDS" in manifest["reasons"]
    assert (collector.out_dir / "INVALID_DEPTH_CAPTURE.json").exists()
