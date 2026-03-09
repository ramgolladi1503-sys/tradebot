from scripts.rebuild_advisory_queues import _rebuild_rows


def test_rebuild_rows_clears_stale_planning_entries():
    rows = [
        {
            "trade_id": "A",
            "status": "PLANNING",
            "entry_status": "STALE_PRICE",
            "entry": 100.0,
            "suggested_entry": 101.0,
        },
        {
            "trade_id": "B",
            "status": "ACTIVE",
            "entry_status": "STALE_PRICE",
            "entry": 200.0,
            "suggested_entry": 201.0,
        },
    ]
    rebuilt, stats = _rebuild_rows(rows, clear_stale_entry=True)
    assert stats["rows_in"] == 2
    assert stats["rows_out"] == 2
    assert stats["stale_entries_cleared"] == 1

    planning = next(r for r in rebuilt if r["trade_id"] == "A")
    assert planning["status"] == "PLANNING"
    assert planning["entry"] is None
    assert planning["suggested_entry"] is None

    active = next(r for r in rebuilt if r["trade_id"] == "B")
    assert active["status"] == "ACTIVE"
    assert active["entry"] == 200.0
