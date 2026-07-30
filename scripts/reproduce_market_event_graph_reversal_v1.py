#!/usr/bin/env python3
"""Reproduce the frozen Market Event Graph CE candidate from original evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.market_event_graph_contract import (
    DATASET_SHA256,
    FROZEN_DISCOVERY_SPEC_SHA256,
    FROZEN_THRESHOLDS,
    SECONDARY_PE_THRESHOLDS,
    SOURCE_ARCHIVE_SHA256,
    file_sha256,
)

EXPECTED = {
    "train_occurrences": 168,
    "validation_trades": 115,
    "validation_profit_factor": 2.456790552401809,
    "holdout_trades": 25,
    "holdout_profit_factor": 4.173855459438617,
}

GRAPH = ("breadth_down_1:HIGH", "index_breadth_divergence:LOW", "breadth_down_1:LOW")
SECONDARY_PE_GRAPH = ("breadth_up_1:LOW", "volume_shock_share:HIGH", "breadth_mean_ret1:LOW")


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    return wins / losses if losses else math.inf


def split_sessions(df: pd.DataFrame) -> dict[str, list[str]]:
    sessions = sorted(str(value) for value in df["session_date"].dropna().unique())
    train_end = int(len(sessions) * 0.60)
    validation_end = int(len(sessions) * 0.80)
    return {
        "all_sessions": sessions,
        "train_sessions": sessions[:train_end],
        "validation_sessions": sessions[train_end:validation_end],
        "holdout_sessions": sessions[validation_end:],
    }


def rows_for(df: pd.DataFrame, sessions: list[str]) -> pd.DataFrame:
    return df[df["session_date"].astype(str).isin(set(sessions))].copy()


def ce_ledgers(df: pd.DataFrame, sessions: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    for session_date, group in rows_for(df, sessions).groupby("session_date", sort=True):
        group = group.sort_values("timestamp").reset_index(drop=True)
        last_entry_ts: pd.Timestamp | None = None
        for index in range(2, len(group)):
            first = group.iloc[index - 2]
            second = group.iloc[index - 1]
            third = group.iloc[index]
            if (
                pd.notna(first["breadth_down_1"])
                and pd.notna(second["index_breadth_divergence"])
                and pd.notna(third["breadth_down_1"])
                and float(first["breadth_down_1"]) >= FROZEN_THRESHOLDS["breadth_high"]
                and float(second["index_breadth_divergence"]) <= FROZEN_THRESHOLDS["divergence_low"]
                and float(third["breadth_down_1"]) <= FROZEN_THRESHOLDS["breadth_low"]
            ):
                signal = {
                    "session_date": str(session_date),
                    "a_timestamp": first["timestamp"].isoformat(),
                    "b_timestamp": second["timestamp"].isoformat(),
                    "signal_timestamp": third["timestamp"].isoformat(),
                    "a_breadth_down_1": float(first["breadth_down_1"]),
                    "b_index_breadth_divergence": float(second["index_breadth_divergence"]),
                    "c_breadth_down_1": float(third["breadth_down_1"]),
                }
                signals.append(signal)
                entry_index = index + 1
                exit_index = index + 15
                if entry_index >= len(group) or exit_index >= len(group) or pd.isna(third["future_return_15"]):
                    continue
                entry = group.iloc[entry_index]
                exit_row = group.iloc[exit_index]
                entry_ts = entry["timestamp"]
                if last_entry_ts is not None and (entry_ts - last_entry_ts).total_seconds() < 15 * 60:
                    signal["cooldown_suppressed"] = True
                    continue
                gross = float(third["future_return_15"])
                net = gross - 0.0002
                trades.append(
                    {
                        **signal,
                        "entry_timestamp": entry_ts.isoformat(),
                        "exit_timestamp": exit_row["timestamp"].isoformat(),
                        "entry_close": float(entry["close"]),
                        "exit_close": float(exit_row["close"]),
                        "gross_return": gross,
                        "round_trip_cost": 0.0002,
                        "net_return": net,
                    }
                )
                last_entry_ts = entry_ts
    return signals, trades


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out-dir", default="research/market_event_graph_reversal_v1")
    args = parser.parse_args()

    archive = Path(args.archive)
    out_dir = Path(args.out_dir)
    archive_sha = file_sha256(archive)
    if archive_sha != SOURCE_ARCHIVE_SHA256:
        raise SystemExit(f"archive_sha256_mismatch:{archive_sha}")

    with TemporaryDirectory() as tmp:
        with zipfile.ZipFile(archive) as zf:
            zf.extract("market_event_graph_discovery_v3/market_event_graph_dataset.parquet", tmp)
            zf.extract("market_event_graph_discovery_v3/market_event_graph_report.json", tmp)
            zf.extract("market_event_graph_discovery_v3/market_event_graph_candidate_ledger.json", tmp)
        evidence = Path(tmp) / "market_event_graph_discovery_v3"
        dataset = evidence / "market_event_graph_dataset.parquet"
        dataset_sha = file_sha256(dataset)
        if dataset_sha != DATASET_SHA256:
            raise SystemExit(f"dataset_sha256_mismatch:{dataset_sha}")
        report = json.loads((evidence / "market_event_graph_report.json").read_text())
        df = pd.read_parquet(dataset).sort_values(["session_date", "timestamp"]).reset_index(drop=True)

    splits = split_sessions(df)
    train_df = rows_for(df, splits["train_sessions"])
    recovered = {
        "breadth_down_1_p20": float(train_df["breadth_down_1"].quantile(0.20)),
        "breadth_down_1_p80": float(train_df["breadth_down_1"].quantile(0.80)),
        "index_breadth_divergence_p20": float(train_df["index_breadth_divergence"].quantile(0.20)),
        "breadth_up_1_p20": float(train_df["breadth_up_1"].quantile(0.20)),
        "volume_shock_share_p80": float(train_df["volume_shock_share"].quantile(0.80)),
        "breadth_mean_ret1_p20": float(train_df["breadth_mean_ret1"].quantile(0.20)),
    }
    expected_thresholds = {
        "breadth_down_1_p20": FROZEN_THRESHOLDS["breadth_low"],
        "breadth_down_1_p80": FROZEN_THRESHOLDS["breadth_high"],
        "index_breadth_divergence_p20": FROZEN_THRESHOLDS["divergence_low"],
        "breadth_up_1_p20": SECONDARY_PE_THRESHOLDS["breadth_up_1_low"],
        "volume_shock_share_p80": SECONDARY_PE_THRESHOLDS["volume_shock_share_high"],
        "breadth_mean_ret1_p20": SECONDARY_PE_THRESHOLDS["breadth_mean_ret1_low"],
    }
    for key, expected in expected_thresholds.items():
        if not math.isclose(recovered[key], expected, rel_tol=0.0, abs_tol=1e-15):
            raise SystemExit(f"threshold_mismatch:{key}:{recovered[key]}:{expected}")

    ledgers: dict[str, list[dict[str, Any]]] = {}
    signal_counts: dict[str, int] = {}
    metrics: dict[str, dict[str, Any]] = {}
    for name, sessions in (
        ("train", splits["train_sessions"]),
        ("validation", splits["validation_sessions"]),
        ("holdout", splits["holdout_sessions"]),
    ):
        signals, trades = ce_ledgers(df, sessions)
        ledgers[name] = trades
        signal_counts[name] = len(signals)
        nets = [float(row["net_return"]) for row in trades]
        metrics[name] = {
            "signals": len(signals),
            "trades": len(trades),
            "mean": sum(nets) / len(nets) if nets else None,
            "win_rate": sum(value > 0 for value in nets) / len(nets) if nets else None,
            "profit_factor": profit_factor(nets) if nets else None,
        }

    if signal_counts["train"] != EXPECTED["train_occurrences"]:
        raise SystemExit(f"train_occurrence_mismatch:{signal_counts['train']}")
    for split_name in ("validation", "holdout"):
        if metrics[split_name]["trades"] != EXPECTED[f"{split_name}_trades"]:
            raise SystemExit(f"{split_name}_trade_count_mismatch:{metrics[split_name]['trades']}")
        if not math.isclose(
            float(metrics[split_name]["profit_factor"]),
            EXPECTED[f"{split_name}_profit_factor"],
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise SystemExit(f"{split_name}_pf_mismatch:{metrics[split_name]['profit_factor']}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ledgers").mkdir(exist_ok=True)
    for name, rows in ledgers.items():
        write_csv(out_dir / "ledgers" / f"ce_{name}.csv", rows)

    split_manifest = {
        "split_semantics": "sorted unique session_date list; int(n*0.60) and int(n*0.80) slice boundaries",
        "session_count": len(splits["all_sessions"]),
        **splits,
        "boundaries": {
            "train_first": splits["train_sessions"][0],
            "train_last": splits["train_sessions"][-1],
            "validation_first": splits["validation_sessions"][0],
            "validation_last": splits["validation_sessions"][-1],
            "holdout_first": splits["holdout_sessions"][0],
            "holdout_last": splits["holdout_sessions"][-1],
        },
    }
    split_manifest["split_manifest_sha256"] = sha256_json(split_manifest)

    dataset_manifest = {
        "source_archive": str(archive),
        "source_archive_sha256": archive_sha,
        "dataset_internal_path": "market_event_graph_discovery_v3/market_event_graph_dataset.parquet",
        "dataset_sha256": dataset_sha,
        "rows": int(len(df)),
        "sessions": int(df["session_date"].nunique()),
        "breadth_rows": int(report.get("breadth_rows", 0)),
        "option_rows": int(report.get("option_rows", 0)),
        "columns": list(df.columns),
        "dtypes": {column: str(dtype) for column, dtype in df.dtypes.items()},
        "timestamp_column": "timestamp",
        "session_identifier": "session_date",
        "row_ordering": ["session_date", "timestamp"],
        "feature_columns": [
            column
            for column in df.columns
            if column not in {"timestamp", "close", "session_date", "future_return_15"}
        ],
        "outcome_columns": ["future_return_15"],
        "split_or_label_columns": [],
    }
    thresholds = {
        "thresholds": recovered,
        "quantile_semantics": {
            "library": "pandas.Series.quantile",
            "q_values": [0.20, 0.80],
            "interpolation": "linear",
            "nan_handling": "drop NaN values per feature",
            "duplicate_handling": "all non-NaN rows retained",
            "weighting": "per row, not per session",
            "inequality_semantics": {"LOW": "<= p20", "HIGH": ">= p80"},
            "precision": "float64",
        },
    }
    contract = {
        "strategy_id": "market_event_graph_reversal_v1",
        "candidate_identity": {"graph": list(GRAPH), "direction": "CE"},
        "secondary_pe_research_only": {"graph": list(SECONDARY_PE_GRAPH), "direction": "PE"},
        "thresholds": thresholds["thresholds"],
        "feature_definitions": "columns are recovered from original frozen Parquet; no runtime discovery",
        "inequality_rules": thresholds["quantile_semantics"]["inequality_semantics"],
        "timing": {
            "graph": "strict consecutive rows A(t-2)->B(t-1)->C(t)",
            "entry_delay_bars": 1,
            "holding_bars": 15,
            "cooldown_minutes": 15,
            "cost_bps": 2,
            "economics_source": "future_return_15 on signal row C(t), minus 2 bps",
        },
        "dataset_sha256": dataset_sha,
        "split_manifest_sha256": split_manifest["split_manifest_sha256"],
        "frozen_discovery_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
        "original_metrics": report["viable_graphs"][0],
        "current_certification_state": [
            "EXACT_UNDERLYING_DISCOVERY_REPRODUCED",
            "NOT_OPTION_PREMIUM_VALIDATED",
            "NOT_INDEPENDENTLY_CERTIFIED",
            "SHADOW_ADVISORY_ONLY",
        ],
    }
    reproduction_report = {
        "verdict": "EXACT_UNDERLYING_DISCOVERY_REPRODUCED",
        "limitations": [
            "option_rows = 0",
            "holdout was used for final candidate acceptance/ranking",
            "11258 graph-direction combinations were tested",
            "not independently certified",
            "shadow advisory only",
        ],
        "metrics": metrics,
        "expected": EXPECTED,
        "exact_gate_passed": True,
    }

    outputs = {
        "frozen_thresholds.json": thresholds,
        "dataset_manifest.json": dataset_manifest,
        "split_manifest.json": split_manifest,
        "frozen_strategy_contract.json": contract,
        "reproduction_report.json": reproduction_report,
    }
    for name, payload in outputs.items():
        (out_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (out_dir / "reproduction_command.txt").write_text(
        f"python scripts/reproduce_market_event_graph_reversal_v1.py --archive {archive}\n"
    )
    sums = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            sums.append(f"{file_sha256(path)}  {path.relative_to(out_dir)}")
    (out_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(json.dumps({"metrics": metrics, "thresholds": recovered, "split": split_manifest["boundaries"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
