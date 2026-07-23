from __future__ import annotations

import pytest

from core.upstox_v3_feed_parser import (
    UpstoxV3ParseError,
    assess_capture_quality,
    parse_upstox_v3_message,
)


def test_parse_official_full_market_feed_with_five_level_depth() -> None:
    message = {
        "type": "live_feed",
        "currentTs": "1740729566039",
        "feeds": {
            "NSE_FO|45450": {
                "fullFeed": {
                    "marketFF": {
                        "ltpc": {
                            "ltp": 219.3,
                            "ltt": "1740729552723",
                            "ltq": "75",
                            "cp": 494.05,
                        },
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
                        "optionGreeks": {
                            "delta": 0.5078,
                            "theta": -8.5499,
                            "gamma": 0.0007,
                            "vega": 16.7691,
                            "rho": 3.9612,
                            "iv": 0.1334,
                        },
                        "eFeedDetails": {"vtt": "919725", "oi": 256800},
                    }
                }
            }
        },
    }

    [record] = parse_upstox_v3_message(message, received_ts_epoch=123.5)

    assert record["instrument_key"] == "NSE_FO|45450"
    assert record["feed_kind"] == "MARKET_FF"
    assert record["source_ts_epoch_ms"] == 1740729566039
    assert record["ts"] == pytest.approx(123.5)
    assert record["ltp"] == pytest.approx(219.3)
    assert record["bid_price"] == pytest.approx(219.2)
    assert record["ask_price"] == pytest.approx(219.4)
    assert record["bid_quantity"] == 75
    assert record["ask_quantity"] == 150
    assert record["depth_level_count"] == 2
    assert record["depth_valid"] is True
    assert record["depth"][1] == {
        "bid_price": 219.1,
        "bid_quantity": 225,
        "ask_price": 219.5,
        "ask_quantity": 300,
    }
    assert record["delta"] == pytest.approx(0.5078)
    assert record["rho"] == pytest.approx(3.9612)
    assert record["iv"] == pytest.approx(0.1334)
    assert record["volume"] == 919725
    assert record["oi"] == pytest.approx(256800)


def test_parse_official_first_level_with_greeks() -> None:
    message = {
        "type": "live_feed",
        "feeds": {
            "NSE_FO|45450": {
                "firstLevelWithGreeks": {
                    "ltpc": {"ltp": 225.7, "ltt": "1740729368660"},
                    "firstDepth": {
                        "bidQ": "75",
                        "bidP": 225.4,
                        "askQ": "150",
                        "askP": 225.7,
                    },
                    "optionGreeks": {
                        "delta": 0.5078,
                        "theta": -8.5499,
                        "gamma": 0.0007,
                        "vega": 16.7691,
                    },
                    "vtt": "919725",
                    "oi": 256800,
                    "iv": 0.133438,
                }
            }
        },
    }

    [record] = parse_upstox_v3_message(message, received_ts_epoch=100.0)

    assert record["feed_kind"] == "FIRST_LEVEL_WITH_GREEKS"
    assert record["source_ts_epoch_ms"] == 1740729368660
    assert record["depth_level_count"] == 1
    assert record["depth_valid"] is True
    assert record["bid_price"] == pytest.approx(225.4)
    assert record["ask_price"] == pytest.approx(225.7)
    assert record["iv"] == pytest.approx(0.133438)


def test_parse_index_full_feed_without_inventing_depth() -> None:
    message = {
        "type": "live_feed",
        "currentTs": "1740729566039",
        "feeds": {
            "NSE_INDEX|Nifty 50": {
                "fullFeed": {
                    "indexFF": {
                        "ltpc": {"ltp": 24936.4, "ltt": "1740729552000"}
                    }
                }
            }
        },
    }

    [record] = parse_upstox_v3_message(message)

    assert record["feed_kind"] == "INDEX_FF"
    assert record["ltp"] == pytest.approx(24936.4)
    assert record["depth"] == []
    assert record["depth_valid"] is False


def test_parse_legacy_sdk_aliases_without_rest_depth_shape() -> None:
    message = {
        "NSE_FO|1": {
            "ff": {
                "market_ff": {
                    "ltpc": {"ltp": 100.0, "ltt": "1740729552000"},
                    "market_level": {
                        "bid_ask_quote": [
                            {"bp": 99.9, "bq": 10, "ap": 100.1, "aq": 20}
                        ]
                    },
                    "option_greeks": {"delta": 0.4},
                    "e_feed_details": {"vtt": 1000, "oi": 500},
                }
            }
        }
    }

    [record] = parse_upstox_v3_message(message)

    assert record["feed_kind"] == "MARKET_FF"
    assert record["depth_valid"] is True
    assert record["bid_quantity"] == 10
    assert record["ask_quantity"] == 20


def test_market_info_control_message_emits_no_records() -> None:
    message = {
        "type": "market_info",
        "currentTs": "1740729566039",
        "marketInfo": {"segmentStatus": {"NSE_FO": "NORMAL_OPEN"}},
    }
    assert parse_upstox_v3_message(message) == []


def test_unrecognized_live_feed_fails_closed() -> None:
    with pytest.raises(UpstoxV3ParseError, match="unrecognized"):
        parse_upstox_v3_message(
            {"type": "live_feed", "feeds": {"NSE_FO|1": {"unknown": {}}}}
        )


def test_capture_quality_rejects_empty_depth_placeholder_session() -> None:
    quality = assess_capture_quality(
        subscribed_instrument_keys=["NSE_FO|1", "NSE_FO|2", "NSE_INDEX|Nifty 50"],
        record_counts={"NSE_FO|1": 100, "NSE_FO|2": 100, "NSE_INDEX|Nifty 50": 100},
        valid_depth_counts={"NSE_FO|1": 0, "NSE_FO|2": 0},
    )

    assert quality.research_depth_eligible is False
    assert quality.classification == "UPSTOX_V3_DEPTH_CAPTURE_INVALID"
    assert "NO_VALID_DEPTH_RECORDS" in quality.reasons
    assert any(
        reason.startswith("ACTIVE_FO_DEPTH_COVERAGE_BELOW_MINIMUM")
        for reason in quality.reasons
    )


def test_capture_quality_accepts_sufficient_active_fo_coverage() -> None:
    quality = assess_capture_quality(
        subscribed_instrument_keys=["NSE_FO|1", "NSE_FO|2", "NSE_INDEX|Nifty 50"],
        record_counts={"NSE_FO|1": 100, "NSE_FO|2": 100, "NSE_INDEX|Nifty 50": 100},
        valid_depth_counts={"NSE_FO|1": 10, "NSE_FO|2": 0},
        minimum_active_fo_depth_coverage_ratio=0.50,
        minimum_valid_depth_records_per_instrument=1,
    )

    assert quality.research_depth_eligible is True
    assert quality.classification == "UPSTOX_V3_DEPTH_CAPTURE_VALID"
    assert quality.active_fo_depth_coverage_ratio == pytest.approx(0.5)
