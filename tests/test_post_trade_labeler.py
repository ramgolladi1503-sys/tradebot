from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.post_trade_labeler import PostTradeLabeler
from scripts.build_training_dataset import build_training_dataset


def _base_row(trade_id: str, ts_epoch: float) -> dict:
    exit_iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "trade_id": trade_id,
        "timestamp_epoch": ts_epoch - 100.0,
        "timestamp": datetime.fromtimestamp(ts_epoch - 100.0, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "symbol": "NIFTY",
        "strategy": "ENSEMBLE_OPT",
        "regime": "TREND",
        "side": "BUY",
        "entry": 100.0,
        "stop_loss": 90.0,
        "target": 130.0,
        "qty_units": 10,
        "exit_price": 120.0,
        "exit_time": exit_iso,
        "realized_pnl": 200.0,
        "r_multiple_realized": 2.0,
    }


def test_post_trade_labeler_emits_expected_schema(tmp_path):
    out_dir = tmp_path / "data" / "training"
    labeler = PostTradeLabeler(output_dir=str(out_dir))
    trade_row = _base_row("T-1", 1_700_000_100.0)
    meta = {
        "mae": -5.0,
        "mfe": 25.0,
        "features_snapshot": {"vwap": 101.0, "atr": 18.0},
        "decision_trace_id": "DT-1",
        "regime_at_entry": "TREND",
    }
    label = labeler.label_and_persist(
        trade_row,
        meta=meta,
        decision_trace_id=meta["decision_trace_id"],
        features_snapshot=meta["features_snapshot"],
        regime_at_entry=meta["regime_at_entry"],
    )
    assert label["trade_id"] == "T-1"
    assert label["decision_trace_id"] == "DT-1"
    assert label["pnl"] == 200.0
    assert round(float(label["r_multiple"]), 4) == 2.0
    assert label["label"] == "WIN"
    assert label["mae"] == -5.0
    assert label["mfe"] == 25.0
    assert isinstance(label["features_snapshot"], dict)
    assert label["features_snapshot"]["vwap"] == 101.0

    files = list(out_dir.glob("trade_labels_*.jsonl"))
    assert len(files) == 1
    saved_rows = [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]
    assert len(saved_rows) == 1
    assert saved_rows[0]["trade_id"] == "T-1"
    assert saved_rows[0]["decision_trace_id"] == "DT-1"


def test_build_training_dataset_merges_jsonl_files(tmp_path):
    input_dir = tmp_path / "data" / "training"
    input_dir.mkdir(parents=True, exist_ok=True)

    row_a = PostTradeLabeler(output_dir=str(input_dir)).build_label(
        _base_row("T-A", 1_700_000_200.0),
        meta={"features_snapshot": {"f": 1}, "regime_at_entry": "TREND"},
        decision_trace_id="DT-A",
    )
    row_b = PostTradeLabeler(output_dir=str(input_dir)).build_label(
        _base_row("T-B", 1_700_086_600.0),
        meta={"features_snapshot": {"f": 2}, "regime_at_entry": "RANGE"},
        decision_trace_id="DT-B",
    )

    file_a = input_dir / "trade_labels_2023-11-14.jsonl"
    file_b = input_dir / "trade_labels_2023-11-15.jsonl"
    file_a.write_text(json.dumps(row_a) + "\n")
    file_b.write_text(json.dumps(row_b) + "\n")

    out_path = tmp_path / "data" / "training" / "trade_labels_training.jsonl"
    ok, reason, count = build_training_dataset(str(input_dir), str(out_path))
    assert ok is True
    assert reason == "ok"
    assert count == 2
    merged = [json.loads(line) for line in out_path.read_text().splitlines() if line.strip()]
    assert len(merged) == 2
    assert {row["trade_id"] for row in merged} == {"T-A", "T-B"}

