from datetime import datetime, timedelta
import json
from pathlib import Path
from core.keltner_hm_shadow.aggregation import Bar, aggregate_complete
from core.keltner_hm_shadow.indicators import ema, wma, rsi_wilder, atr_wilder
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
