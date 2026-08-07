#!/usr/bin/env python3
"""Independent recertification for the frozen Market Event Graph reversal candidate.

Thin mechanism adapter over the already-built Pattern Atlas certification helpers.
It does not rerun MEG discovery, retune thresholds, call a broker, or grant
live/paper/order authority.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
MEG_ROOT = ROOT / "research" / "market_event_graph_reversal_v1"
ARCHIVE_SHA256 = "fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3"
DATASET_SHA256 = "30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c"
DATASET_INTERNAL_PATH = "market_event_graph_discovery_v3/market_event_graph_dataset.parquet"
ENTRY_DELAY_BARS = 1
HOLDING_BARS = 15
ROUND_TRIP_COST_BPS = 2.0
ROBUST_COST_BPS = 5.0
ORIGINAL_TESTED_GRAPH_DIRECTION_PAIRS = 11258
ORIGINAL_HOLDOUT_LAST = "2026-07-22"
MIN_INDEPENDENT_SESSIONS = 45
MIN_INDEPENDENT_TRADES = 20


def load_certification_core():
    path = Path(__file__).with_name(
        "run_observation_first_pattern_atlas_full_certification_v1.py"
    )
    spec = importlib.util.spec_from_file_location(
        "shared_pattern_atlas_certification_core", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load shared certification helpers: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CERT = load_certification_core()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(payload: Any) -> str:
    return CERT.digest(payload)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    CERT.stable_write(path, payload)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def profit_factor(values: Sequence[float]) -> float | None:
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        return None
    gains = float(arr[arr > 0].sum())
    losses = abs(float(arr[arr < 0].sum()))
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def summarize_returns(net_bps: Sequence[float]) -> dict[str, Any]:
    values = np.asarray(net_bps, dtype=float)
    if len(values) == 0:
        return {
            "n": 0,
            "mean_bps": None,
            "median_bps": None,
            "hit_rate": None,
            "profit_factor": None,
            "mean_ci90": [None, None],
            "one_sided_sign_p": 1.0,
            "top5_positive_concentration": 1.0,
            "remove_best_10pct_mean_bps": None,
        }
    hits = int(np.sum(values > 0.0))
    ci_low, ci_high = CERT.bootstrap_mean_ci(values.tolist(), confidence=0.90)
    remove_count = max(1, int(math.ceil(len(values) * 0.10)))
    keep = np.ones(len(values), dtype=bool)
    keep[np.argsort(values)[-remove_count:]] = False
    stripped = values[keep]
    return {
        "n": int(len(values)),
        "mean_bps": float(values.mean()),
        "median_bps": float(np.median(values)),
        "hit_rate": float(hits / len(values)),
        "profit_factor": profit_factor(values.tolist()),
        "mean_ci90": [float(ci_low), float(ci_high)],
        "one_sided_sign_p": float(
            binomtest(hits, len(values), 0.5, alternative="greater").pvalue
        ),
        "top5_positive_concentration": float(CERT.concentration_ratio(values, 5)),
        "remove_best_10pct_mean_bps": (
            float(stripped.mean()) if len(stripped) else None
        ),
    }


def audit_ledger_frame(frame: pd.DataFrame, split: str) -> dict[str, Any]:
    required = {
        "signal_timestamp",
        "entry_timestamp",
        "exit_timestamp",
        "entry_close",
        "exit_close",
        "gross_return",
        "net_return",
        "round_trip_cost",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"ledger_missing_columns split={split} columns={missing}")
    if frame.empty:
        return {
            "split": split,
            "rows": 0,
            "execution_economics_mismatch_rows": 0,
            "verdict": "EMPTY_LEDGER",
        }

    signal = pd.to_datetime(frame["signal_timestamp"], utc=True, errors="raise")
    entry = pd.to_datetime(frame["entry_timestamp"], utc=True, errors="raise")
    exit_ts = pd.to_datetime(frame["exit_timestamp"], utc=True, errors="raise")
    entry_close = pd.to_numeric(frame["entry_close"], errors="raise").to_numpy(float)
    exit_close = pd.to_numeric(frame["exit_close"], errors="raise").to_numpy(float)
    reported_gross = pd.to_numeric(frame["gross_return"], errors="raise").to_numpy(float)
    reported_net = pd.to_numeric(frame["net_return"], errors="raise").to_numpy(float)
    reported_cost = pd.to_numeric(frame["round_trip_cost"], errors="raise").to_numpy(float)

    actual_gross = exit_close / entry_close - 1.0
    discrepancy_bps = (reported_gross - actual_gross) * 10000.0
    net_identity_error_bps = (
        reported_net - (reported_gross - reported_cost)
    ) * 10000.0
    mismatch = np.abs(discrepancy_bps) > 1e-8
    net_identity_mismatch = np.abs(net_identity_error_bps) > 1e-8
    entry_delay_minutes = (entry - signal).dt.total_seconds().to_numpy(float) / 60.0
    recorded_holding_minutes = (
        (exit_ts - entry).dt.total_seconds().to_numpy(float) / 60.0
    )

    return {
        "split": split,
        "rows": int(len(frame)),
        "execution_economics_mismatch_rows": int(np.sum(mismatch)),
        "execution_economics_match_rows": int(len(frame) - np.sum(mismatch)),
        "reported_net_identity_mismatch_rows": int(np.sum(net_identity_mismatch)),
        "max_abs_reported_vs_recorded_execution_discrepancy_bps": float(
            np.max(np.abs(discrepancy_bps))
        ),
        "median_abs_reported_vs_recorded_execution_discrepancy_bps": float(
            np.median(np.abs(discrepancy_bps))
        ),
        "median_entry_delay_minutes": float(np.median(entry_delay_minutes)),
        "median_recorded_holding_minutes": float(np.median(recorded_holding_minutes)),
        "expected_entry_delay_bars": ENTRY_DELAY_BARS,
        "declared_holding_bars": HOLDING_BARS,
        "verdict": (
            "LEGACY_MEG_EXECUTION_ECONOMICS_INVALID"
            if bool(np.any(mismatch))
            else "LEGACY_MEG_EXECUTION_ECONOMICS_MATCH_RECORDED_PRICES"
        ),
    }


def audit_preserved_ledgers(repo_root: Path = ROOT) -> dict[str, Any]:
    ledger_dir = (
        repo_root / "research" / "market_event_graph_reversal_v1" / "ledgers"
    )
    splits = {}
    for split in ("train", "validation", "holdout"):
        path = ledger_dir / f"ce_{split}.csv"
        if not path.exists():
            raise FileNotFoundError(f"preserved_ledger_missing:{path}")
        splits[split] = audit_ledger_frame(pd.read_csv(path), split)
    mismatches = sum(
        int(item["execution_economics_mismatch_rows"]) for item in splits.values()
    )
    rows = sum(int(item["rows"]) for item in splits.values())
    payload = {
        "principal_verdict": (
            "LEGACY_MEG_EXECUTION_ECONOMICS_SUPERSEDED"
            if mismatches > 0
            else "LEGACY_MEG_EXECUTION_ECONOMICS_RECONCILED"
        ),
        "rows_audited": rows,
        "mismatch_rows": mismatches,
        "splits": splits,
        "policy": {
            "reported_future_return_15_used_as_execution_truth": False,
            "ledger_entry_exit_prices_treated_as_recorded_execution_proxy": True,
            "thresholds_changed": False,
            "graph_changed": False,
        },
    }
    payload["semantic_sha256"] = semantic_hash(payload)
    return payload


def verify_archive_and_load_dataset(archive: Path) -> pd.DataFrame:
    actual_archive_sha = file_sha256(archive)
    if actual_archive_sha != ARCHIVE_SHA256:
        raise ValueError(
            f"archive_sha256_mismatch actual={actual_archive_sha} expected={ARCHIVE_SHA256}"
        )
    with TemporaryDirectory() as tmp:
        with zipfile.ZipFile(archive) as zf:
            zf.extract(DATASET_INTERNAL_PATH, tmp)
        dataset = Path(tmp) / DATASET_INTERNAL_PATH
        actual_dataset_sha = file_sha256(dataset)
        if actual_dataset_sha != DATASET_SHA256:
            raise ValueError(
                f"dataset_sha256_mismatch actual={actual_dataset_sha} expected={DATASET_SHA256}"
            )
        frame = pd.read_parquet(dataset)
    required = {
        "timestamp",
        "session_date",
        "close",
        "breadth_down_1",
        "index_breadth_divergence",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"dataset_missing_columns:{missing}")
    return frame.sort_values(
        ["session_date", "timestamp"], kind="mergesort"
    ).reset_index(drop=True)


def split_sessions(frame: pd.DataFrame) -> dict[str, list[str]]:
    sessions = sorted(frame["session_date"].dropna().astype(str).unique().tolist())
    train_end = int(len(sessions) * 0.60)
    validation_end = int(len(sessions) * 0.80)
    return {
        "all": sessions,
        "train": sessions[:train_end],
        "validation": sessions[train_end:validation_end],
        "holdout": sessions[validation_end:],
    }


def recover_thresholds(
    frame: pd.DataFrame, train_sessions: Iterable[str]
) -> dict[str, float]:
    train = frame[
        frame["session_date"].astype(str).isin(set(map(str, train_sessions)))
    ]
    return {
        "breadth_down_1_p20": float(train["breadth_down_1"].quantile(0.20)),
        "breadth_down_1_p80": float(train["breadth_down_1"].quantile(0.80)),
        "index_breadth_divergence_p20": float(
            train["index_breadth_divergence"].quantile(0.20)
        ),
    }


def frozen_thresholds() -> dict[str, float]:
    contract = load_json(MEG_ROOT / "frozen_strategy_contract.json")
    values = dict(contract["thresholds"])
    return {
        "breadth_down_1_p20": float(values["breadth_down_1_p20"]),
        "breadth_down_1_p80": float(values["breadth_down_1_p80"]),
        "index_breadth_divergence_p20": float(
            values["index_breadth_divergence_p20"]
        ),
    }


def assert_thresholds_reproduce(
    recovered: dict[str, float], frozen: dict[str, float]
) -> None:
    for key, expected in frozen.items():
        actual = recovered[key]
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(
                f"threshold_reproduction_mismatch:{key}:{actual}:{expected}"
            )


def graph_matches(
    group: pd.DataFrame, index: int, thresholds: dict[str, float]
) -> bool:
    if index < 2:
        return False
    a = group.iloc[index - 2]
    b = group.iloc[index - 1]
    c = group.iloc[index]
    values = (
        a["breadth_down_1"],
        b["index_breadth_divergence"],
        c["breadth_down_1"],
    )
    if any(pd.isna(value) for value in values):
        return False
    return bool(
        float(a["breadth_down_1"]) >= thresholds["breadth_down_1_p80"]
        and float(b["index_breadth_divergence"])
        <= thresholds["index_breadth_divergence_p20"]
        and float(c["breadth_down_1"]) <= thresholds["breadth_down_1_p20"]
    )


def fixed_graph_trades(
    frame: pd.DataFrame,
    sessions: Iterable[str],
    thresholds: dict[str, float],
    *,
    holding_bars: int = HOLDING_BARS,
    cost_bps: float = ROUND_TRIP_COST_BPS,
) -> list[dict[str, Any]]:
    allowed = set(map(str, sessions))
    trades: list[dict[str, Any]] = []
    subset = frame[frame["session_date"].astype(str).isin(allowed)]
    for session_date, raw_group in subset.groupby("session_date", sort=True):
        group = raw_group.sort_values("timestamp", kind="mergesort").reset_index(
            drop=True
        )
        last_entry_ts: pd.Timestamp | None = None
        for index in range(2, len(group)):
            if not graph_matches(group, index, thresholds):
                continue
            entry_index = index + ENTRY_DELAY_BARS
            exit_index = entry_index + holding_bars
            if entry_index >= len(group) or exit_index >= len(group):
                continue
            entry = group.iloc[entry_index]
            exit_row = group.iloc[exit_index]
            entry_close = float(entry["close"])
            exit_close = float(exit_row["close"])
            if (
                not (math.isfinite(entry_close) and math.isfinite(exit_close))
                or entry_close <= 0
            ):
                continue
            signal_ts = pd.Timestamp(group.iloc[index]["timestamp"])
            entry_ts = pd.Timestamp(entry["timestamp"])
            exit_ts = pd.Timestamp(exit_row["timestamp"])
            if (
                last_entry_ts is not None
                and (entry_ts - last_entry_ts).total_seconds() < 15 * 60
            ):
                continue
            gross = exit_close / entry_close - 1.0
            record = {
                "session_date": str(session_date),
                "signal_timestamp": signal_ts.isoformat(),
                "entry_timestamp": entry_ts.isoformat(),
                "exit_timestamp": exit_ts.isoformat(),
                "entry_close": entry_close,
                "exit_close": exit_close,
                "gross_return": gross,
                "gross_bps": gross * 10000.0,
                "net_bps": gross * 10000.0 - cost_bps,
                "cost_bps": cost_bps,
                "holding_bars_from_entry": holding_bars,
                "legacy_future_return_15": (
                    float(group.iloc[index]["future_return_15"])
                    if "future_return_15" in group.columns
                    and pd.notna(group.iloc[index]["future_return_15"])
                    else None
                ),
            }
            trades.append(record)
            last_entry_ts = entry_ts
    return trades


def chronological_fold_audit(
    trades: Sequence[dict[str, Any]], folds: int = 5
) -> dict[str, Any]:
    dates = sorted(set(str(item["session_date"]) for item in trades))
    if len(dates) < max(20, folds * 4):
        return {
            "passed": False,
            "reason": "insufficient_dates",
            "date_count": len(dates),
            "folds": [],
        }
    date_folds = np.array_split(np.asarray(dates, dtype=object), folds)
    records = []
    for number, date_array in enumerate(date_folds, start=1):
        date_set = set(map(str, date_array.tolist()))
        values = [
            float(item["net_bps"])
            for item in trades
            if str(item["session_date"]) in date_set
        ]
        records.append({"fold": number, **summarize_returns(values)})
    means = [float(item["mean_bps"]) for item in records if item["n"] > 0]
    positive = sum(value > 0.0 for value in means)
    passed = bool(
        len(means) >= 4
        and positive >= 3
        and float(np.median(means)) > 0.0
        and min(means) > -10.0
    )
    return {
        "passed": passed,
        "date_count": len(dates),
        "positive_fold_count": positive,
        "median_fold_mean_bps": float(np.median(means)) if means else None,
        "worst_fold_mean_bps": min(means) if means else None,
        "folds": records,
    }


def robustness_audit(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    base = np.asarray([float(item["net_bps"]) for item in trades], dtype=float)
    if len(base) < MIN_INDEPENDENT_TRADES:
        return {"passed": False, "reason": "insufficient_trades"}
    gross = np.asarray([float(item["gross_bps"]) for item in trades], dtype=float)
    high_cost = gross - ROBUST_COST_BPS
    remove_count = max(1, int(math.ceil(len(base) * 0.10)))
    keep = np.ones(len(base), dtype=bool)
    keep[np.argsort(base)[-remove_count:]] = False
    stripped = base[keep]
    gates = {
        "base_mean_positive": float(base.mean()) > 0.0,
        "five_bps_cost_mean_positive": float(high_cost.mean()) > 0.0,
        "remove_best_10pct_mean_positive": len(stripped) > 0
        and float(stripped.mean()) > 0.0,
        "top5_positive_concentration_le_60pct": float(
            CERT.concentration_ratio(base, 5)
        )
        <= 0.60,
    }
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "base_mean_bps": float(base.mean()),
        "five_bps_cost_mean_bps": float(high_cost.mean()),
        "remove_best_10pct_mean_bps": (
            float(stripped.mean()) if len(stripped) else None
        ),
        "top5_positive_concentration": float(CERT.concentration_ratio(base, 5)),
    }


def contaminated_diagnostics(
    frame: pd.DataFrame,
    splits: dict[str, list[str]],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    results = {}
    for split in ("train", "validation", "holdout"):
        trades = fixed_graph_trades(frame, splits[split], thresholds)
        summary = summarize_returns([float(item["net_bps"]) for item in trades])
        summary["bonferroni_discovery_family_p"] = min(
            1.0,
            float(summary["one_sided_sign_p"])
            * ORIGINAL_TESTED_GRAPH_DIRECTION_PAIRS,
        )
        summary["trade_count"] = len(trades)
        results[split] = summary
    payload = {
        "principal_verdict": "CORRECTED_MEG_ORIGINAL_SPLITS_DIAGNOSTIC_ONLY",
        "splits": results,
        "policy": {
            "independent_certification": False,
            "holdout_reused_for_certification": False,
            "original_holdout_was_previously_used_for_final_acceptance": True,
            "original_tested_graph_direction_pairs": ORIGINAL_TESTED_GRAPH_DIRECTION_PAIRS,
            "legacy_future_return_15_used_for_execution": False,
            "entry_delay_bars": ENTRY_DELAY_BARS,
            "holding_bars_from_entry": HOLDING_BARS,
        },
    }
    payload["semantic_sha256"] = semantic_hash(payload)
    return payload


def validate_independent_frame(
    frame: pd.DataFrame,
) -> tuple[list[str], dict[str, Any]]:
    required = {
        "timestamp",
        "session_date",
        "close",
        "breadth_down_1",
        "index_breadth_divergence",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"independent_dataset_missing_columns:{missing}")
    sessions = sorted(frame["session_date"].dropna().astype(str).unique().tolist())
    if not sessions:
        raise ValueError("independent_dataset_has_no_sessions")
    overlapping = [date for date in sessions if date <= ORIGINAL_HOLDOUT_LAST]
    if overlapping:
        raise ValueError(
            "independent_dataset_not_strictly_post_holdout "
            f"first_overlap={overlapping[0]}"
        )
    policy = {
        "first_session": sessions[0],
        "last_session": sessions[-1],
        "session_count": len(sessions),
        "strictly_after_original_holdout": True,
        "threshold_refit_allowed": False,
        "graph_search_allowed": False,
    }
    return sessions, policy


def independent_certification(
    frame: pd.DataFrame, thresholds: dict[str, float]
) -> dict[str, Any]:
    sessions, policy = validate_independent_frame(frame)
    trades = fixed_graph_trades(frame, sessions, thresholds)
    stats = summarize_returns([float(item["net_bps"]) for item in trades])
    wfa = chronological_fold_audit(trades)
    robust = robustness_audit(trades)
    ci_low = stats["mean_ci90"][0]
    edge_gates = {
        "minimum_sessions": len(sessions) >= MIN_INDEPENDENT_SESSIONS,
        "minimum_trades": stats["n"] >= MIN_INDEPENDENT_TRADES,
        "mean_net_ge_2bps": stats["mean_bps"] is not None
        and float(stats["mean_bps"]) >= 2.0,
        "hit_rate_ge_55pct": stats["hit_rate"] is not None
        and float(stats["hit_rate"]) >= 0.55,
        "bootstrap_ci90_lower_gt_zero": ci_low is not None
        and float(ci_low) > 0.0,
        "one_sided_sign_p_le_5pct": float(stats["one_sided_sign_p"]) <= 0.05,
        "walk_forward_passed": bool(wfa.get("passed")),
        "robustness_passed": bool(robust.get("passed")),
    }
    passed = all(edge_gates.values())
    payload = {
        "principal_verdict": (
            "INDEPENDENT_MEG_UNDERLYING_EDGE_CERTIFIED"
            if passed
            else "NO_MEG_UNDERLYING_EDGE_SURVIVED_INDEPENDENT_RECERTIFICATION"
        ),
        "passed": passed,
        "edge_gates": edge_gates,
        "stats": stats,
        "walk_forward": wfa,
        "robustness": robust,
        "policy": policy,
        "trade_count": len(trades),
        "options_edge_certified": False,
        "shadow_authorized": False,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authorized": False,
    }
    payload["semantic_sha256"] = semantic_hash(payload)
    return payload


def build_report(stages: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Market Event Graph — Independent Recertification V2",
        "",
        "No discovery rerun, threshold tuning, broker call, option-edge claim, or execution authority.",
        "",
    ]
    for name, stage in stages.items():
        lines.extend(
            [
                f"## {name}",
                "",
                f"- verdict: `{stage.get('principal_verdict', 'UNKNOWN')}`",
                f"- semantic_sha256: `{stage.get('semantic_sha256', 'n/a')}`",
                "",
            ]
        )
    final = stages["final_authority"]
    lines.extend(
        [
            "## Final authority",
            "",
            f"`{final['principal_verdict']}`",
            "",
            "The original 2023-2026 dataset is diagnostic-only because its holdout was already used for final candidate acceptance.",
            "A positive independent certification requires a separate dataset strictly after 2026-07-22.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--independent-dataset", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT
        / "runtime"
        / "research"
        / "market_event_graph_independent_recertification_v2",
    )
    parser.add_argument("--ledger-audit-only", action="store_true")
    args = parser.parse_args()

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    stages: dict[str, dict[str, Any]] = {}

    ledger_audit = audit_preserved_ledgers(ROOT)
    stages["stage0_legacy_execution_audit"] = ledger_audit
    write_json(output / "stage0_legacy_execution_audit.json", ledger_audit)

    if args.ledger_audit_only:
        final = {
            "principal_verdict": ledger_audit["principal_verdict"],
            "independent_edge_certified": False,
            "options_edge_certified": False,
            "shadow_authorized": False,
            "order_authorized": False,
        }
        final["semantic_sha256"] = semantic_hash(final)
        stages["final_authority"] = final
        write_json(output / "final_authority.json", final)
        (output / "REPORT.md").write_text(build_report(stages), encoding="utf-8")
        return 0

    if args.archive is None:
        raise SystemExit(
            "--archive is required unless --ledger-audit-only is used"
        )

    frame = verify_archive_and_load_dataset(args.archive)
    splits = split_sessions(frame)
    frozen = frozen_thresholds()
    recovered = recover_thresholds(frame, splits["train"])
    assert_thresholds_reproduce(recovered, frozen)

    source_authority = {
        "principal_verdict": "MEG_ORIGINAL_SOURCE_AND_THRESHOLDS_REPRODUCED",
        "archive_sha256": ARCHIVE_SHA256,
        "dataset_sha256": DATASET_SHA256,
        "session_count": len(splits["all"]),
        "train_sessions": len(splits["train"]),
        "validation_sessions": len(splits["validation"]),
        "holdout_sessions": len(splits["holdout"]),
        "holdout_last": splits["holdout"][-1] if splits["holdout"] else None,
        "frozen_thresholds": frozen,
        "recovered_thresholds": recovered,
        "legacy_future_return_15_ignored_for_execution": True,
    }
    source_authority["semantic_sha256"] = semantic_hash(source_authority)
    stages["stage1_source_authority"] = source_authority
    write_json(output / "stage1_source_authority.json", source_authority)

    diagnostic = contaminated_diagnostics(frame, splits, frozen)
    stages["stage2_corrected_original_split_diagnostic"] = diagnostic
    write_json(
        output / "stage2_corrected_original_split_diagnostic.json", diagnostic
    )

    if args.independent_dataset is None:
        independent = {
            "principal_verdict": "INDEPENDENT_MEG_CERTIFICATION_BLOCKED_NO_UNTOUCHED_DATA",
            "required_first_session_after": ORIGINAL_HOLDOUT_LAST,
            "minimum_independent_sessions": MIN_INDEPENDENT_SESSIONS,
            "minimum_independent_trades": MIN_INDEPENDENT_TRADES,
            "old_holdout_reuse_forbidden": True,
            "passed": False,
            "options_edge_certified": False,
            "shadow_authorized": False,
        }
        independent["semantic_sha256"] = semantic_hash(independent)
    else:
        independent_frame = pd.read_parquet(args.independent_dataset).sort_values(
            ["session_date", "timestamp"], kind="mergesort"
        )
        independent = independent_certification(independent_frame, frozen)
    stages["stage3_independent_certification"] = independent
    write_json(output / "stage3_independent_certification.json", independent)

    final = {
        "principal_verdict": (
            "MEG_INDEPENDENT_RECERTIFICATION_COMPLETE_EDGE_CERTIFIED"
            if independent.get("passed") is True
            else "MEG_INDEPENDENT_RECERTIFICATION_COMPLETE_EDGE_NOT_CERTIFIED"
        ),
        "legacy_execution_economics_superseded": (
            ledger_audit["principal_verdict"]
            == "LEGACY_MEG_EXECUTION_ECONOMICS_SUPERSEDED"
        ),
        "original_split_diagnostics_are_certification_authority": False,
        "independent_edge_certified": independent.get("passed") is True,
        "options_edge_certified": False,
        "shadow_authorized": False,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authorized": False,
        "thresholds_retuned": False,
        "graph_rediscovered": False,
    }
    final["semantic_sha256"] = semantic_hash(final)
    stages["final_authority"] = final
    write_json(output / "final_authority.json", final)
    (output / "REPORT.md").write_text(build_report(stages), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
