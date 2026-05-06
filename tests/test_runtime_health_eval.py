from core.runtime_health_eval import evaluate_runtime_snapshot_health


def valid_snapshot(**overrides):
    snapshot = {
        "schema_version": "1.0",
        "snapshot_id": "snap-001",
        "timestamp_epoch": 1710000000.0,
        "token_coverage": {
            "index_token": "NIFTY",
            "option_tokens_count": 120,
        },
        "freshness": {
            "max_tick_age_sec": 1.2,
            "sla_threshold_sec": 3.0,
        },
        "data_sources": {
            "ticks": "sqlite",
            "depth": "sqlite_db",
        },
    }
    snapshot.update(overrides)
    return snapshot


def blocker_codes(result):
    return {blocker["code"] for blocker in result["blockers"]}


def test_runtime_snapshot_health_passes_for_valid_offline_snapshot():
    result = evaluate_runtime_snapshot_health(
        valid_snapshot(),
        feed_connected=True,
        db_ok=True,
        min_option_token_count=50,
    )

    assert result == {"ok": True, "blockers": []}


def test_runtime_snapshot_health_blocks_stale_feed():
    snapshot = valid_snapshot(
        freshness={"max_tick_age_sec": 9.0, "sla_threshold_sec": 3.0}
    )

    result = evaluate_runtime_snapshot_health(snapshot, feed_connected=True, db_ok=True)

    assert result["ok"] is False
    assert "FRESHNESS_STALE" in blocker_codes(result)


def test_runtime_snapshot_health_blocks_low_contract_coverage():
    snapshot = valid_snapshot(
        token_coverage={"index_token": "NIFTY", "option_tokens_count": 2}
    )

    result = evaluate_runtime_snapshot_health(
        snapshot,
        feed_connected=True,
        db_ok=True,
        min_option_token_count=50,
    )

    assert result["ok"] is False
    assert "TOKEN_COVERAGE_BELOW_THRESHOLD" in blocker_codes(result)


def test_runtime_snapshot_health_blocks_memory_only_data_source():
    snapshot = valid_snapshot(data_sources={"ticks": "memory"})

    result = evaluate_runtime_snapshot_health(snapshot, feed_connected=True, db_ok=True)

    assert result["ok"] is False
    assert "MEMORY_SOURCE_FORBIDDEN" in blocker_codes(result)
    assert "DB_DERIVED_SOURCE_REQUIRED" in blocker_codes(result)


def test_runtime_snapshot_health_blocks_disconnected_feed_and_db_failure():
    result = evaluate_runtime_snapshot_health(
        valid_snapshot(),
        feed_connected=False,
        db_ok=False,
    )

    assert result["ok"] is False
    assert "FEED_DISCONNECTED" in blocker_codes(result)
    assert "DB_UNAVAILABLE" in blocker_codes(result)


def test_runtime_snapshot_health_fails_fast_on_missing_contract_fields():
    snapshot = valid_snapshot()
    snapshot.pop("token_coverage")

    result = evaluate_runtime_snapshot_health(snapshot, feed_connected=True, db_ok=True)

    assert result["ok"] is False
    assert blocker_codes(result) == {"SNAPSHOT_REQUIRED_FIELDS_MISSING"}
