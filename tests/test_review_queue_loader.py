import json

from core.review_queue import load_queue_rows


def test_load_queue_rows_corrupted_json_returns_empty(tmp_path):
    path = tmp_path / "review_queue.json"
    path.write_text("{bad-json")
    rows = load_queue_rows(path)
    assert rows == []


def test_load_queue_rows_handles_scalar_payload(tmp_path):
    path = tmp_path / "review_queue.json"
    path.write_text("3.14159")
    rows = load_queue_rows(path)
    assert rows == []


def test_load_queue_rows_dict_instead_of_list_returns_empty(tmp_path):
    path = tmp_path / "review_queue.json"
    payload = {"symbol": "NIFTY", "strike": 25000, "type": "CE"}
    path.write_text(json.dumps(payload))
    rows = load_queue_rows(path)
    assert rows == []


def test_load_queue_rows_converts_float_seconds_timestamp(tmp_path):
    path = tmp_path / "review_queue.json"
    payload = [
        {
            "symbol": "BANKNIFTY",
            "strike": 61000,
            "type": "PE",
            "timestamp": 1700000000.0,
        }
    ]
    path.write_text(json.dumps(payload))
    rows = load_queue_rows(path)
    assert len(rows) == 1
    assert rows[0]["timestamp_epoch_ms"] == 1700000000000
    assert rows[0]["timestamp_utc_iso"].endswith("+00:00")


def test_load_queue_rows_partial_write_returns_empty(tmp_path):
    path = tmp_path / "review_queue.json"
    path.write_text('[{"symbol":"BANKNIFTY","strike":61000')
    rows = load_queue_rows(path)
    assert rows == []


def test_load_queue_rows_clears_entry_when_entry_status_stale(tmp_path):
    path = tmp_path / "review_queue.json"
    payload = [
        {
            "symbol": "NIFTY",
            "strike": 24600,
            "type": "PE",
            "entry": 101.67,
            "entry_price": 101.67,
            "suggested_entry": None,
            "entry_status": "STALE_PRICE",
            "timestamp": "2026-03-02T03:35:04Z",
        }
    ]
    path.write_text(json.dumps(payload))
    rows = load_queue_rows(path)
    assert len(rows) == 1
    assert rows[0]["entry"] is None
