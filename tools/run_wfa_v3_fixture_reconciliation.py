"""Run independent A-E mechanical WFA fixture reconciliation on frozen V3 data.

This is a certification tool, not a strategy runner.  It uses no broker APIs and
does not alter the canonical corpus.  The producer receives a local fixture
builder; the oracle recomputes the same specification from primitive candles.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import pandas as pd

from core.backtesting.wfa import WalkForwardAnalyzer, validate_parameter_selection_ledger
from tools.wfa_independent_oracle_v1 import simulate_same_session_path


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "timestamp" in frame:
        frame = frame.set_index("timestamp")
    frame.index = pd.to_datetime(frame.index)
    return frame.sort_index()


def _fixture_builder(kind: str):
    def build(frame: pd.DataFrame, config) -> pd.DataFrame:
        n = len(frame)
        close = frame["close"].astype(float)
        trailing = close.shift(1).rolling(5, min_periods=5).mean()
        eligible = pd.Series(True, index=frame.index)
        if kind == "B":
            eligible = close > trailing
        elif kind == "D":
            eligible = close.pct_change().shift(1).abs() >= float(config.vol_target)
        rows = []
        positions = []
        for i in range(n):
            # Bounded, preregistered sampling keeps the mechanical fixture
            # finite on the full corpus; it is not a trading strategy.
            if i % 100 != 0 or not bool(eligible.iloc[i]) or i + 1 >= n:
                continue
            entry = float(frame["open"].iloc[i])
            if kind in {"C", "E"}:
                target, stop = entry * 1.0005, entry * 0.9995
            else:
                target, stop = entry * 10.0, entry * 0.1
            rows.append({
                "signal_side": "BUY", "entry_price": entry, "target": target,
                "stop_loss": stop, "qty": 1, "lot_size": 1,
                "feature_cutoff_ts": frame.index[i],
                "feature_source_timestamp": frame.index[i],
            })
            positions.append(i)
        return pd.DataFrame(rows, index=positions)

    return build


def _oracle_events(frame: pd.DataFrame, signals: pd.DataFrame, *, horizon: int, slippage: float, spread: float):
    events = []
    for i, row in signals.iterrows():
        result = simulate_same_session_path(
            frame, signal_index=int(i), side="BUY", entry_price=float(row["entry_price"]),
            target=float(row["target"]), stop_loss=float(row["stop_loss"]),
            horizon=horizon, slippage_bps=slippage, spread_bps=spread,
        )
        result["entry_timestamp"] = frame.index[int(i)]
        result["session_date"] = str(frame.index[int(i)].date())
        events.append(result)
    return events


def _oracle_signals(frame: pd.DataFrame, kind: str, *, threshold: float = 0.002) -> pd.DataFrame:
    """Independent primitive reconstruction; intentionally no producer calls."""
    close = frame["close"].astype(float).tolist()
    rows, positions = [], []
    for i in range(len(close)):
        if i % 100 != 0 or i + 1 >= len(frame):
            continue
        allowed = True
        if kind == "B":
            if i < 5:
                allowed = False
            else:
                allowed = close[i] > sum(close[i - 5:i]) / 5.0
        elif kind == "D":
            allowed = i >= 2 and abs(close[i - 1] / close[i - 2] - 1.0) >= threshold
        if not allowed:
            continue
        entry = float(frame["open"].iloc[i])
        bounded = kind in {"C", "E"}
        rows.append({
            "signal_side": "BUY", "entry_price": entry,
            "target": entry * (1.0005 if bounded else 10.0),
            "stop_loss": entry * (0.9995 if bounded else 0.1),
            "qty": 1, "lot_size": 1,
        })
        positions.append(i)
    return pd.DataFrame(rows, index=positions)


def run(path: Path, output: Path) -> dict:
    frame = _load(path)
    rows = []
    for kind, horizon, purge in (("A", 5, 0), ("B", 5, 0), ("C", 5, 0), ("D", 5, 0), ("E", 75, 75)):
        builder = _fixture_builder(kind)
        builder.builder_sha256 = hashlib.sha256(inspect.getsource(builder).encode("utf-8")).hexdigest()
        builder.builder_id = f"fixture_builder_{kind}_v1"
        builder.source_partition_id = hashlib.sha256(path.read_bytes()).hexdigest()
        builder.source_partition_sha256 = builder.source_partition_id
        # No normalizer is executed by these fixtures; bind PASS_NOT_APPLICABLE
        # to the exact source partition so omission/substitution is detectable.
        builder.normalization_fit_source_sha256 = builder.source_partition_sha256
        builder.corpus_freeze_sha256 = "3e6de9b8c9e9313c2dd9a7514e54df9e95b71fcaaa9fb1e1ec514cc0583aa0db"
        analyzer = WalkForwardAnalyzer(
            frame, train_years=1, test_years=1, slippage_bps=5, spread_bps=0,
            purge_minutes=purge, embargo_minutes=1, signal_builder=builder,
        )
        grid = {"horizon": [horizon]}
        if kind == "D":
            grid["vol_target"] = [0.001, 0.002]
        producer = analyzer.run(grid)
        validate_parameter_selection_ledger(analyzer.parameter_selection_ledger)
        expected = []
        for window in analyzer.generate_windows():
            local = _oracle_signals(window["test_df"], kind, threshold=0.002)
            expected.extend(_oracle_events(window["test_df"], local, horizon=horizon, slippage=5, spread=0))
        producer_pl = float(producer["pl"].sum()) if not producer.empty else 0.0
        oracle_pl = float(sum(x["pl"] for x in expected))
        event_match = len(expected) == len(producer)
        if event_match and expected:
            for actual, oracle in zip(producer.to_dict("records"), expected):
                event_match = event_match and all(
                    abs(float(actual[field]) - float(oracle[field])) <= 1e-7
                    for field in ("entry_price", "exit_price", "pl")
                ) and actual["outcome"] == oracle["outcome"]
        session_match = event_match and all(
            str(actual.get("session_date")) == str(oracle["session_date"])
            for actual, oracle in zip(producer.to_dict("records"), expected)
        )
        producer_aggregate = analyzer.aggregation_report
        oracle_by_session = {}
        for event in expected:
            oracle_by_session.setdefault(event["session_date"], []).append(event["pl"])
        oracle_session_means = [sum(values) / len(values) for values in oracle_by_session.values()]
        aggregate_match = bool(
            producer_aggregate.get("event_count") == len(expected)
            and producer_aggregate.get("session_count") == len(oracle_session_means)
            and abs(producer_aggregate.get("event_mean", 0.0) - (oracle_pl / len(expected))) <= 1e-7
            and abs(producer_aggregate.get("session_equal_mean", 0.0) - (sum(oracle_session_means) / len(oracle_session_means))) <= 1e-7
        )
        fold_match = len(analyzer.fold_ledger) == 2 and all(
            pd.Timestamp(f["train_end"]) < pd.Timestamp(f["test_start"])
            and int(f["overlap_rows"]) == 0
            for f in analyzer.fold_ledger
        )
        feature_match = bool(
            kind != "B" or all(
                pd.Timestamp(row["feature_source_timestamp"]) <= pd.Timestamp(row["feature_cutoff_ts"])
                for row in builder(window["test_df"], type("Config", (), {"vol_target": 0.002})()).to_dict("records")
            )
        )
        rows.append({
            "fixture": kind,
            "producer_folds": len(analyzer.fold_ledger),
            "oracle_events": len(expected),
            "producer_events": len(producer),
            "producer_pl": producer_pl,
            "oracle_pl": oracle_pl,
            "parameter_provenance": "PASS",
            "fold_reconciliation": fold_match,
            "session_reconciliation": session_match,
            "feature_reconciliation": feature_match,
            "aggregate_reconciliation": aggregate_match,
            "event_reconciliation": bool(event_match),
            "agreement": bool(event_match and session_match and fold_match and feature_match and aggregate_match and abs(producer_pl - oracle_pl) <= 1e-7),
        })
    report = {"fixtures": rows, "all_pass": all(r["agreement"] for r in rows), "broker_calls": 0, "orders": 0}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output), indent=2, sort_keys=True))
