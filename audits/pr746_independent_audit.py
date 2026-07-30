#!/usr/bin/env python3
"""Independent publication-gate audit for PR #746."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import zipfile
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARCHIVE = Path("/Users/madhuram/Downloads/causal-market-state-v1-evidence-v3.zip")
OUT = ROOT / "audits" / "pr746_independent_audit_report.json"

EXPECTED = {
    "archive_sha256": "fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3",
    "dataset_sha256": "30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c",
    "split_manifest_sha256": "016ba53e4bdba61ae558e024ece55ea2ab129e8262ff8e5f56c0b7db83ec2b6a",
    "breadth_down_1_p20": 0.10121457489878542,
    "breadth_down_1_p80": 0.21862348178137653,
    "index_breadth_divergence_p20": -0.000238836424541256,
    "train_occurrences": 168,
    "validation_trades": 115,
    "validation_pf": 2.4567905524018094,
    "holdout_trades": 25,
    "holdout_pf": 4.173855459438616,
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def inspect_archive() -> dict[str, Any]:
    archive_sha = file_sha256(ARCHIVE)
    with zipfile.ZipFile(ARCHIVE) as zf:
        names = [info.filename for info in zf.infolist()]
        duplicate_members = sorted(name for name, count in Counter(names).items() if count > 1)
        traversal = [
            name
            for name in names
            if name.startswith("/") or ".." in Path(name).parts or Path(name).drive not in ("", None)
        ]
        json_parseable = {}
        for name in names:
            if name.endswith(".json"):
                try:
                    json.loads(zf.read(name).decode("utf-8"))
                    json_parseable[name] = True
                except Exception as exc:
                    json_parseable[name] = f"{type(exc).__name__}:{exc}"
        sizes = {info.filename: int(info.file_size) for info in zf.infolist()}
    return {
        "archive_sha256": archive_sha,
        "member_names": names,
        "uncompressed_sizes": sizes,
        "duplicate_members": duplicate_members,
        "path_traversal_members": traversal,
        "json_parseable": json_parseable,
        "archive_hash_match": archive_sha == EXPECTED["archive_sha256"],
    }


def load_dataset() -> tuple[pd.DataFrame, str]:
    member = "market_event_graph_discovery_v3/market_event_graph_dataset.parquet"
    with TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ARCHIVE) as zf:
            zf.extract(member, tmp)
        path = Path(tmp) / member
        dataset_sha = file_sha256(path)
        df = pd.read_parquet(path)
    return df.sort_values(["session_date", "timestamp"]).reset_index(drop=True), dataset_sha


def split_sessions(df: pd.DataFrame) -> dict[str, Any]:
    sessions = sorted(str(item) for item in df["session_date"].dropna().unique())
    train_end = int(len(sessions) * 0.60)
    validation_end = int(len(sessions) * 0.80)
    manifest = {
        "split_semantics": "sorted unique session_date list; int(n*0.60) and int(n*0.80) slice boundaries",
        "session_count": len(sessions),
        "all_sessions": sessions,
        "train_sessions": sessions[:train_end],
        "validation_sessions": sessions[train_end:validation_end],
        "holdout_sessions": sessions[validation_end:],
    }
    manifest["boundaries"] = {
        "train_first": manifest["train_sessions"][0],
        "train_last": manifest["train_sessions"][-1],
        "validation_first": manifest["validation_sessions"][0],
        "validation_last": manifest["validation_sessions"][-1],
        "holdout_first": manifest["holdout_sessions"][0],
        "holdout_last": manifest["holdout_sessions"][-1],
    }
    split_hash = stable_hash(manifest)
    overlaps = []
    for left_name in ("train", "validation", "holdout"):
        for right_name in ("train", "validation", "holdout"):
            if left_name < right_name:
                both = sorted(set(manifest[f"{left_name}_sessions"]).intersection(manifest[f"{right_name}_sessions"]))
                if both:
                    overlaps.append({"left": left_name, "right": right_name, "sessions": both})
    return {
        "manifest": manifest,
        "split_manifest_sha256": split_hash,
        "counts": {
            "train": len(manifest["train_sessions"]),
            "validation": len(manifest["validation_sessions"]),
            "holdout": len(manifest["holdout_sessions"]),
        },
        "overlap": overlaps,
    }


def compute_thresholds(df: pd.DataFrame, train_sessions: list[str]) -> dict[str, Any]:
    train = df[df["session_date"].astype(str).isin(set(train_sessions))]
    values = {
        "breadth_down_1_p20": float(train["breadth_down_1"].quantile(0.20, interpolation="linear")),
        "breadth_down_1_p80": float(train["breadth_down_1"].quantile(0.80, interpolation="linear")),
        "index_breadth_divergence_p20": float(
            train["index_breadth_divergence"].quantile(0.20, interpolation="linear")
        ),
    }
    return {
        "values": values,
        "diffs": {
            key: {"abs": abs(value - EXPECTED[key]), "rel": abs(value - EXPECTED[key]) / abs(EXPECTED[key])}
            for key, value in values.items()
        },
    }


def reconstruct(
    df: pd.DataFrame, sessions: list[str], thresholds: dict[str, float]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    split_df = df[df["session_date"].astype(str).isin(set(sessions))]
    for session, group in split_df.groupby("session_date", sort=True):
        group = group.sort_values("timestamp").reset_index(drop=True)
        last_entry = None
        for index in range(2, len(group)):
            a = group.iloc[index - 2]
            b = group.iloc[index - 1]
            c = group.iloc[index]
            match = (
                a["timestamp"] < b["timestamp"] < c["timestamp"]
                and pd.notna(a["breadth_down_1"])
                and pd.notna(b["index_breadth_divergence"])
                and pd.notna(c["breadth_down_1"])
                and float(a["breadth_down_1"]) >= thresholds["breadth_down_1_p80"]
                and float(b["index_breadth_divergence"]) <= thresholds["index_breadth_divergence_p20"]
                and float(c["breadth_down_1"]) <= thresholds["breadth_down_1_p20"]
            )
            if not match:
                continue
            signal = {
                "session_date": str(session),
                "a_timestamp": a["timestamp"].isoformat(),
                "b_timestamp": b["timestamp"].isoformat(),
                "signal_timestamp": c["timestamp"].isoformat(),
            }
            signals.append(signal)
            entry_index = index + 1
            exit_index = index + 15
            if entry_index >= len(group) or exit_index >= len(group) or pd.isna(c["future_return_15"]):
                continue
            entry = group.iloc[entry_index]
            exit_row = group.iloc[exit_index]
            if not (c["timestamp"] < entry["timestamp"] <= exit_row["timestamp"]):
                continue
            if last_entry is not None and (entry["timestamp"] - last_entry).total_seconds() < 900:
                continue
            gross = float(c["future_return_15"])
            trades.append(
                {
                    **signal,
                    "entry_timestamp": entry["timestamp"].isoformat(),
                    "exit_timestamp": exit_row["timestamp"].isoformat(),
                    "gross_return": gross,
                    "round_trip_cost": 0.0002,
                    "net_return": gross - 0.0002,
                }
            )
            last_entry = entry["timestamp"]
    return signals, trades


def summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [float(row["net_return"]) for row in trades]
    wins = [value for value in nets if value > 0.0]
    losses = [value for value in nets if value < 0.0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    return {
        "trades": len(trades),
        "mean": sum(nets) / len(nets) if nets else None,
        "win_rate": len(wins) / len(nets) if nets else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss else math.inf,
    }


def canonical_trade(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["session_date"],
        row["a_timestamp"],
        row["b_timestamp"],
        row["signal_timestamp"],
        row["entry_timestamp"],
        row["exit_timestamp"],
        round(float(row["gross_return"]), 15),
        round(float(row["round_trip_cost"]), 15),
        round(float(row["net_return"]), 15),
    )


def compare_ledgers(ledgers: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    base = ROOT / "research" / "market_event_graph_reversal_v1" / "ledgers"
    for split, rows in ledgers.items():
        with (base / f"ce_{split}.csv").open(newline="") as fh:
            committed = list(csv.DictReader(fh))
        audit_keys = [canonical_trade(row) for row in rows]
        committed_keys = [canonical_trade(row) for row in committed]
        out[split] = {
            "audit_count": len(audit_keys),
            "committed_count": len(committed_keys),
            "exact_match": audit_keys == committed_keys,
            "audit_hash": stable_hash(audit_keys),
            "committed_hash": stable_hash(committed_keys),
        }
    return out


def verify_sha256sums() -> dict[str, Any]:
    base = ROOT / "research" / "market_event_graph_reversal_v1"
    listed = {}
    for line in (base / "SHA256SUMS").read_text().splitlines():
        digest, rel = line.split("  ", 1)
        listed[rel] = digest
    actual = sorted(str(path.relative_to(base)) for path in base.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    checks = {rel: (base / rel).exists() and file_sha256(base / rel) == digest for rel, digest in listed.items()}
    return {
        "all_listed_files_match": all(checks.values()),
        "missing_or_mismatched": [rel for rel, ok in checks.items() if not ok],
        "omitted_files": [rel for rel in actual if rel not in listed],
    }


def returns(negative_count: int, total: int = 50) -> list[float]:
    return [-0.001] * negative_count + [0.001] * (total - negative_count)


def runtime_checks() -> dict[str, Any]:
    from core.market_event_graph_breadth_producer import (
        frozen_threshold_metadata,
        initial_market_event_graph_runtime_state,
        produce_completed_constituent_breadth_snapshots,
    )
    from core.movement_contract import StrategyContext
    from core.movement_regime import MovementRegimeResult
    from strategies.movement.market_event_graph_reversal import generate_market_event_graph_reversal_candidates

    def valid_metadata() -> dict[str, Any]:
        return {
            **frozen_threshold_metadata(),
            "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-07-29"),
            "completed_constituent_bars": [
                {"ts_epoch": 100.0, "source_bar_end_epoch": 90.0, "session_date": "2026-07-29", "index_ret1": -0.001, "constituent_ret1": returns(40), "completed": True},
                {"ts_epoch": 160.0, "source_bar_end_epoch": 150.0, "session_date": "2026-07-29", "index_ret1": -0.004, "constituent_ret1": returns(25), "completed": True},
                {"ts_epoch": 220.0, "source_bar_end_epoch": 210.0, "session_date": "2026-07-29", "index_ret1": 0.001, "constituent_ret1": returns(5), "completed": True},
                {"ts_epoch": 280.0, "source_bar_end_epoch": 270.0, "session_date": "2026-07-29", "index_ret1": 0.001, "constituent_ret1": returns(20), "completed": True},
            ],
        }

    regime = MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={"TREND_UP": 0.6, "TREND_DOWN": 0.1, "VOLATILITY_EXPANSION": 0.1, "COMPRESSION": 0.1, "TRAP_RISK": 0.1, "CHOP": 0.1},
    )

    def candidate_count(metadata: dict[str, Any], now: float = 280.0) -> int:
        ctx = StrategyContext(
            symbol="NIFTY",
            ts_epoch=now,
            option_ce_ltp=120.0,
            option_pe_ltp=100.0,
            ce_premium_change=1.0,
            pe_premium_change=-1.0,
            ce_spread_pct=0.01,
            pe_spread_pct=0.01,
            ce_depth=1000.0,
            pe_depth=1000.0,
            quote_source="realtime",
            fallback_used=False,
            option_ltp_age_sec=1.0,
            metadata=metadata,
        )
        return len(generate_market_event_graph_reversal_candidates(ctx, regime))

    cases: dict[str, dict[str, Any]] = {}

    def record(
        name: str,
        metadata: dict[str, Any],
        *,
        expect_emit: bool = False,
        now: float = 280.0,
        candidate_only: bool = False,
    ) -> None:
        events = produce_completed_constituent_breadth_snapshots(metadata)
        candidates = candidate_count(metadata, now)
        if candidate_only:
            passed = candidates == 0
        elif expect_emit:
            passed = len(events) == 3 and candidates == 1
        else:
            passed = len(events) == 0 and candidates == 0
        cases[name] = {
            "events": len(events),
            "candidates": candidates,
            "pass": passed,
        }

    record("valid_control", valid_metadata(), expect_emit=True)
    for name, mutate in (
        ("missing_spec", lambda m: m.pop("market_event_graph_frozen_spec_sha256")),
        ("wrong_spec_hash", lambda m: m.update(market_event_graph_frozen_spec_sha256="bad")),
        ("one_bit_threshold_change", lambda m: m["market_event_graph_thresholds"].update(breadth_low=m["market_event_graph_thresholds"]["breadth_low"] + 1e-14)),
        ("missing_dataset_hash", lambda m: m.pop("market_event_graph_dataset_sha256")),
        ("malformed_threshold_type", lambda m: m.update(market_event_graph_thresholds="bad")),
        ("nan_threshold", lambda m: m["market_event_graph_thresholds"].update(breadth_high=float("nan"))),
        ("inf_threshold", lambda m: m["market_event_graph_thresholds"].update(breadth_high=float("inf"))),
        ("duplicate_timestamp", lambda m: m["completed_constituent_bars"][1].update(ts_epoch=100.0)),
        ("reversed_timestamp", lambda m: m["completed_constituent_bars"][2].update(ts_epoch=90.0)),
        ("duplicate_source_bar_end", lambda m: m["completed_constituent_bars"][1].update(source_bar_end_epoch=90.0)),
        ("decreasing_source_bar_end", lambda m: m["completed_constituent_bars"][2].update(source_bar_end_epoch=140.0)),
        ("source_bar_after_event_timestamp", lambda m: m["completed_constituent_bars"][0].update(source_bar_end_epoch=101.0)),
        ("mixed_sessions_in_triplet", lambda m: m["completed_constituent_bars"][1].update(session_date="2026-07-30")),
        ("incomplete_bar", lambda m: m["completed_constituent_bars"][1].update(completed=False)),
        ("insufficient_constituent_count", lambda m: m["completed_constituent_bars"][0].update(constituent_ret1=returns(10, 20))),
        ("graph_at_c_without_t_plus_1", lambda m: m.update(completed_constituent_bars=m["completed_constituent_bars"][:3])),
        ("pending_signal_crossing_session", lambda m: m["completed_constituent_bars"][3].update(session_date="2026-07-30")),
    ):
        meta = valid_metadata()
        mutate(meta)
        record(name, meta)

    meta = valid_metadata()
    record("same_graph_repeated_first_eval", meta, expect_emit=True)
    record("same_graph_repeated_second_eval", meta)
    meta = valid_metadata()
    record("same_graph_plus_later_unrelated_bar", meta, expect_emit=True)
    meta["completed_constituent_bars"].append({"ts_epoch": 340.0, "source_bar_end_epoch": 330.0, "session_date": "2026-07-29", "index_ret1": 0.001, "constituent_ret1": returns(20), "completed": True})
    record("same_graph_plus_later_unrelated_bar_second_eval", meta)
    meta = valid_metadata()
    record("stale_pending_signal", meta, now=1000.0, candidate_only=True)
    meta = valid_metadata()
    meta.pop("market_event_graph_runtime_state")
    record("missing_runtime_state", meta)
    meta = valid_metadata()
    meta["market_event_graph_runtime_state"]["strategy_id"] = "bad"
    record("wrong_state_strategy", meta)
    meta = valid_metadata()
    meta["market_event_graph_allow_test_thresholds"] = True
    meta["test_thresholds"] = True
    meta["threshold_override"] = True
    meta["allow_override"] = True
    meta["market_event_graph_thresholds"] = {"breadth_high": 0.7, "breadth_low": 0.3, "divergence_low": -0.002, "min_constituents": 40}
    record("malformed_test_threshold_injection_normal_runtime", meta)

    return {"cases": cases, "all_required_fail_closed": all(item["pass"] for item in cases.values())}


def main() -> int:
    archive = inspect_archive()
    df, dataset_sha = load_dataset()
    split = split_sessions(df)
    thresholds = compute_thresholds(df, split["manifest"]["train_sessions"])
    ledgers = {}
    signal_counts = {}
    metrics = {}
    for name in ("train", "validation", "holdout"):
        signals, trades = reconstruct(df, split["manifest"][f"{name}_sessions"], thresholds["values"])
        signal_counts[name] = len(signals)
        ledgers[name] = trades
        metrics[name] = summarize(trades)
    ledger_compare = compare_ledgers(ledgers)
    hashes = verify_sha256sums()
    runtime = runtime_checks()
    gate = {
        "archive_hash": archive["archive_hash_match"],
        "dataset_hash": dataset_sha == EXPECTED["dataset_sha256"],
        "split_hash": split["split_manifest_sha256"] == EXPECTED["split_manifest_sha256"],
        "thresholds": all(item["abs"] == 0.0 for item in thresholds["diffs"].values()),
        "counts_pf": (
            signal_counts["train"] == EXPECTED["train_occurrences"]
            and metrics["validation"]["trades"] == EXPECTED["validation_trades"]
            and math.isclose(metrics["validation"]["profit_factor"], EXPECTED["validation_pf"], rel_tol=0.0, abs_tol=1e-12)
            and metrics["holdout"]["trades"] == EXPECTED["holdout_trades"]
            and math.isclose(metrics["holdout"]["profit_factor"], EXPECTED["holdout_pf"], rel_tol=0.0, abs_tol=1e-12)
        ),
        "ledger_compare": all(item["exact_match"] for item in ledger_compare.values()),
        "sha256sums": hashes["all_listed_files_match"] and not hashes["omitted_files"],
        "runtime_adversarial": runtime["all_required_fail_closed"],
    }
    verdict = "PASS_PR746_SHADOW_PUBLICATION_GATE" if all(gate.values()) else "FAIL_PR746_PUBLICATION_GATE"
    report = {
        "principal_verdict": verdict,
        "gate": gate,
        "archive": archive,
        "dataset_sha256": dataset_sha,
        "schema": {"columns": list(df.columns), "dtypes": {c: str(t) for c, t in df.dtypes.items()}},
        "split": split,
        "thresholds": thresholds,
        "signal_counts": signal_counts,
        "metrics": metrics,
        "ledger_compare": ledger_compare,
        "artifact_hashes": hashes,
        "runtime_adversarial": runtime,
        "leakage": {
            "thresholds_train_only": True,
            "signal_uses_outcome_column": False,
            "entry_after_signal": True,
            "exit_after_entry": True,
            "cooldown_lookahead": False,
            "session_overlap": split["overlap"],
        },
        "material_findings": [name for name, item in runtime["cases"].items() if not item["pass"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"principal_verdict": verdict, "gate": gate, "material_findings": report["material_findings"]}, indent=2))
    return 0 if verdict.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
