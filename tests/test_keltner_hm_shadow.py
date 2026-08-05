from datetime import datetime, timedelta
import json
from pathlib import Path

from core.keltner_hm_shadow.aggregation import Bar, aggregate_complete
from core.keltner_hm_shadow.indicators import atr_wilder, ema, rsi_wilder, wma
from core.keltner_hm_shadow.observer import ShadowObserver
from core.keltner_hm_shadow.storage import JsonlPublisher, StateStore


def bar(index: int) -> Bar:
    start = datetime(2026, 1, 1, 9, 15) + timedelta(minutes=5 * index)
    return Bar(
        "NIFTY",
        start,
        start + timedelta(minutes=5),
        100 + index,
        101 + index,
        99 + index,
        100.5 + index,
        "2026-01-01",
        "fixture",
        index,
    )


def test_complete_aggregation():
    rows = aggregate_complete([bar(i) for i in range(6)], 3)
    assert rows == [
        Bar("NIFTY", bar(0).start, bar(2).completion, 100, 103, 99, 102.5, "2026-01-01", "fixture", 2),
        Bar("NIFTY", bar(3).start, bar(5).completion, 103, 106, 102, 105.5, "2026-01-01", "fixture", 5),
    ]


def test_incomplete_group_is_not_emitted():
    rows = aggregate_complete([bar(i) for i in range(5)], 3)
    assert rows == [
        Bar("NIFTY", bar(0).start, bar(2).completion, 100, 103, 99, 102.5, "2026-01-01", "fixture", 2)
    ]


def test_ema_seed_and_progression():
    values = ema([1, 2, 3, 4, 5], 3)
    assert values == [None, None, 2.0, 3.0, 4.0]


def test_wma_weight_order():
    values = wma([1, 2, 3], 3)
    assert values == [None, None, (1 + 4 + 9) / 6]


def test_rsi_uptrend_is_100():
    values = rsi_wilder(list(range(20)), 9)
    assert values[-1] == 100.0


def test_atr_uses_wilder_progression():
    values = atr_wilder([2, 3, 4], [0, 1, 2], [1, 2, 3], 2)
    assert values == [None, 2.0, 2.0]


def test_state_store_atomic_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.save({"x": 1})
    assert store.load() == {"x": 1}


def test_contract_is_permanently_non_executable():
    contract = json.loads(Path("core/keltner_hm_shadow/contract.json").read_text())
    assert contract["research_only"] is True
    assert contract["rankable"] is False
    assert contract["executable"] is False
    assert contract["execution_allowed"] is False
    assert contract["allowed_for_live_execution"] is False
    assert contract["broker_api_called"] is False
    assert contract["is_order_action"] is False


def test_publisher_appends_exact_json_record(tmp_path):
    path = tmp_path / "events.jsonl"
    JsonlPublisher(path).append({"a": 1})
    assert path.read_text() == '{"a":1}\n'


def test_pending_event_advances_only_on_later_completed_bars(tmp_path):
    events = tmp_path / "events.jsonl"
    state = tmp_path / "state.json"
    observer = ShadowObserver("core/keltner_hm_shadow/contract.json", events, state)
    decision = datetime(2026, 1, 1, 10, 30)
    key = "2026-01-01:NIFTY"
    observer.state["pending"][key] = {
        "symbol": "NIFTY",
        "session_id": "2026-01-01",
        "direction": "LONG",
        "decision_time": decision.isoformat(),
        "signal_high": 105.0,
        "signal_low": 100.0,
        "atr": 2.0,
        "extension_atr": 0.5,
        "stage": "WAIT_CONFIRMATION",
    }
    observer.store.save(observer.state)

    confirm = Bar(
        "NIFTY",
        decision,
        decision + timedelta(minutes=5),
        104.0,
        106.0,
        103.0,
        105.5,
        "2026-01-01",
        "fixture",
        1,
    )
    observer.ingest(confirm)
    assert observer.state["pending"][key]["stage"] == "WAIT_ENTRY"

    entry = Bar(
        "NIFTY",
        decision + timedelta(minutes=5),
        decision + timedelta(minutes=10),
        105.7,
        106.0,
        105.0,
        105.8,
        "2026-01-01",
        "fixture",
        2,
    )
    observer.ingest(entry)
    assert observer.state["pending"][key]["stage"] == "ACTIVE"
    assert observer.state["pending"][key]["entry_time"] == entry.start.isoformat()

    exit_bar = Bar(
        "NIFTY",
        entry.start + timedelta(minutes=55),
        entry.start + timedelta(minutes=60),
        106.0,
        108.0,
        105.5,
        107.0,
        "2026-01-01",
        "fixture",
        13,
    )
    observer.ingest(exit_bar)
    assert key not in observer.state["pending"]

    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "KELTNER_HM_CONFIRMATION_PASSED",
        "KELTNER_HM_SHADOW_ENTRY",
        "KELTNER_HM_SHADOW_OUTCOME",
    ]
    assert [row["executable"] for row in rows] == [False, False, False]
    assert [row["rankable"] for row in rows] == [False, False, False]
    assert [row["broker_api_called"] for row in rows] == [False, False, False]
    assert [row["is_order_action"] for row in rows] == [False, False, False]


def test_duplicate_completed_bar_is_rejected_without_state_growth(tmp_path):
    observer = ShadowObserver(
        "core/keltner_hm_shadow/contract.json",
        tmp_path / "events.jsonl",
        tmp_path / "state.json",
    )
    row = bar(0)
    observer.ingest(row)
    observer.ingest(row)
    assert observer._bars5["NIFTY"] == [row]
