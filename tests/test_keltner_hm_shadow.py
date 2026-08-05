from datetime import datetime, timedelta
import json
from pathlib import Path
from core.keltner_hm_shadow.aggregation import Bar, aggregate_complete
from core.keltner_hm_shadow.indicators import ema, wma, rsi_wilder, atr_wilder
from core.keltner_hm_shadow.observer import ShadowObserver
from core.keltner_hm_shadow.storage import StateStore, JsonlPublisher

def bar(index: int) -> Bar:
    start = datetime(2026, 1, 1, 9, 15) + timedelta(minutes=5 * index)
    return Bar("NIFTY", start, start + timedelta(minutes=5), 100 + index, 101 + index,
        99 + index, 100.5 + index, "2026-01-01", "fixture", index)

def test_complete_aggregation():
    rows = aggregate_complete([bar(i) for i in range(6)], 3)
    assert len(rows) == 2 and rows[0].open == 100 and rows[0].close == 102.5

def test_incomplete_group_is_not_emitted():
    assert len(aggregate_complete([bar(i) for i in range(5)], 3)) == 1

def test_ema_seed_and_progression():
    values = ema([1, 2, 3, 4, 5], 3)
    assert values[2] == 2 and round(values[4], 6) == 4

def test_wma_weight_order():
    values = wma([1, 2, 3], 3)
    assert round(values[2], 6) == round((1 + 4 + 9) / 6, 6)

def test_rsi_uptrend_is_100():
    assert rsi_wilder(list(range(20)), 9)[-1] == 100

def test_atr_positive():
    assert atr_wilder([2, 3, 4], [0, 1, 2], [1, 2, 3], 2)[-1] > 0

def test_state_store_atomic_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.save({"x": 1})
    assert store.load() == {"x": 1}

def test_contract_is_permanently_non_executable():
    contract = json.loads(Path("core/keltner_hm_shadow/contract.json").read_text())
    assert contract["research_only"] is True
    assert contract["rankable"] is False and contract["executable"] is False
    assert contract["execution_allowed"] is False and contract["allowed_for_live_execution"] is False
    assert contract["broker_api_called"] is False and contract["is_order_action"] is False

def test_no_broker_or_order_imports():
    text = "\n".join(path.read_text() for path in Path("core/keltner_hm_shadow").glob("*.py"))
    banned = ["kiteconnect", "place_order", "modify_order", "cancel_order", "broker_client"]
    assert not any(token in text for token in banned)

def test_publisher_appends_json(tmp_path):
    path = tmp_path / "events.jsonl"
    JsonlPublisher(path).append({"a": 1})
    assert json.loads(path.read_text()) == {"a": 1}

def test_pending_event_advances_only_on_later_completed_bars(tmp_path):
    events = tmp_path / "events.jsonl"
    state = tmp_path / "state.json"
    observer = ShadowObserver("core/keltner_hm_shadow/contract.json", events, state)
    decision = datetime(2026, 1, 1, 10, 30)
    key = "2026-01-01:NIFTY"
    observer.state["pending"][key] = {"symbol": "NIFTY", "session_id": "2026-01-01",
        "direction": "LONG", "decision_time": decision.isoformat(), "signal_high": 105.0,
        "signal_low": 100.0, "atr": 2.0, "extension_atr": 0.5, "stage": "WAIT_CONFIRMATION"}
    observer.store.save(observer.state)
    confirm = Bar("NIFTY", decision, decision + timedelta(minutes=5), 104.0, 106.0, 103.0,
        105.5, "2026-01-01", "fixture", 1)
    observer.ingest(confirm)
    assert observer.state["pending"][key]["stage"] == "WAIT_ENTRY"
    entry = Bar("NIFTY", decision + timedelta(minutes=5), decision + timedelta(minutes=10),
        105.7, 106.0, 105.0, 105.8, "2026-01-01", "fixture", 2)
    observer.ingest(entry)
    assert observer.state["pending"][key]["stage"] == "ACTIVE"
    assert observer.state["pending"][key]["entry_time"] == entry.start.isoformat()
    exit_bar = Bar("NIFTY", entry.start + timedelta(minutes=55), entry.start + timedelta(minutes=60),
        106.0, 108.0, 105.5, 107.0, "2026-01-01", "fixture", 13)
    observer.ingest(exit_bar)
    assert key not in observer.state["pending"]
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "KELTNER_HM_CONFIRMATION_PASSED", "KELTNER_HM_SHADOW_ENTRY", "KELTNER_HM_SHADOW_OUTCOME"]
    assert all(row["executable"] is False and row["rankable"] is False for row in rows)

def test_duplicate_completed_bar_is_ignored(tmp_path):
    observer = ShadowObserver("core/keltner_hm_shadow/contract.json", tmp_path / "events.jsonl", tmp_path / "state.json")
    row = bar(0)
    observer.ingest(row)
    observer.ingest(row)
    assert len(observer._bars5["NIFTY"]) == 1
