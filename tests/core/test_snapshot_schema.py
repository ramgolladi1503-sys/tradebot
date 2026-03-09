from __future__ import annotations

import copy

from core.snapshot_schema import MarketSnapshotV1, compute_snapshot_id


def _snapshot_dict() -> dict:
    return {
        "schema_version": "1.0",
        "snapshot_id": "placeholder",
        "timestamp_epoch": 1772428800.123,
        "symbol": "NIFTY",
        "token_coverage": {
            "index_token": 256265,
            "option_tokens_count": 2,
            "option_tokens": [101, 102],
            "strike_window": {"atm": 24700, "min": 24400, "max": 25000, "step": 50},
        },
        "freshness": {
            "sla_threshold_sec": 2.5,
            "max_tick_age_sec": 1.2,
            "stale_tokens_count": 0,
        },
        "ticks": {
            "index": {
                "instrument_token": 256265,
                "last_price": 24705.05,
                "timestamp_epoch": 1772428800.123,
            },
            "options": {
                "101": {
                    "instrument_token": 101,
                    "last_price": 24.50,
                    "timestamp_epoch": 1772428800.100,
                    "bid": 24.45,
                    "ask": 24.55,
                },
                "102": {
                    "instrument_token": 102,
                    "last_price": 31.25,
                    "timestamp_epoch": 1772428800.110,
                    "bid": 31.20,
                    "ask": 31.30,
                },
            },
        },
        "expiry": {
            "is_expiry_day": True,
            "expiry_date": "2026-03-02",
        },
        "regime": {
            "state": "EVENT",
            "confidence": 0.82,
        },
        "health": {
            "ok": True,
            "blockers": [],
        },
        "data_sources": {
            "ticks": "sqlite",
            "token_resolution": "cache+resolver",
        },
    }


def test_snapshot_id_stable_for_same_content() -> None:
    snapshot_a = _snapshot_dict()
    snapshot_b = copy.deepcopy(snapshot_a)
    snapshot_b["snapshot_id"] = "different-id-should-not-affect-hash"

    digest_a = compute_snapshot_id(snapshot_a)
    digest_b = compute_snapshot_id(snapshot_b)

    assert digest_a == digest_b


def test_snapshot_id_changes_when_tick_changes() -> None:
    snapshot_a = _snapshot_dict()
    snapshot_b = copy.deepcopy(snapshot_a)
    snapshot_b["ticks"]["options"]["101"]["last_price"] = 24.60

    digest_a = compute_snapshot_id(snapshot_a)
    digest_b = compute_snapshot_id(snapshot_b)

    assert digest_a != digest_b


def test_market_snapshot_v1_to_dict_shape() -> None:
    payload = _snapshot_dict()
    payload["snapshot_id"] = compute_snapshot_id(payload)
    model = MarketSnapshotV1(
        snapshot_id=payload["snapshot_id"],
        timestamp_epoch=payload["timestamp_epoch"],
        symbol=payload["symbol"],
        token_coverage=payload["token_coverage"],
        freshness=payload["freshness"],
        ticks=payload["ticks"],
        expiry=payload["expiry"],
        regime=payload["regime"],
        health=payload["health"],
        data_sources=payload["data_sources"],
    )
    out = model.to_dict()
    assert out["schema_version"] == "1.0"
    assert out["snapshot_id"] == payload["snapshot_id"]
    assert out["ticks"]["options"]["101"]["last_price"] == 24.50
