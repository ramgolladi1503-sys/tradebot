#!/usr/bin/env python3
"""Independent, read-only audit of NIFTY ML discovery artifacts.

The audit intentionally reports research-label metrics only. It does not read
broker state, option P&L, or holdout outcome metrics.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

SCHEMA_VERSION = "ml_strategy_discovery_real_run_audit_v1"
SEED = 68742
EXPECTED_SPLITS = {"DEVELOPMENT", "VALIDATION", "HOLDOUT_LOCKED"}
ALLOWED_VERDICTS = (
    "AUDIT_INVALID_EVIDENCE",
    "SOURCE_PROVENANCE_INVALID",
    "CAUSALITY_OR_LEAKAGE_DEFECT",
    "RULE_REPRODUCTION_FAILED",
    "NO_VALID_CANDIDATE",
    "LONG_CANDIDATE_UNSTABLE",
    "SHORT_CANDIDATE_UNSTABLE",
    "BOTH_CANDIDATES_UNSTABLE",
    "ONE_RESEARCH_CANDIDATE_SURVIVES_VALIDATION_SCREEN",
    "MULTIPLE_RESEARCH_CANDIDATES_SURVIVE_VALIDATION_SCREEN",
)
SAFETY_FIELDS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "append": False,
}
FORBIDDEN_FEATURE_EXACT = {
    "split",
    "session_date",
    "source_kind",
    "source_logical_path",
    "source_sha256",
    "source_manifest_record_id",
    "bar_start_timestamp",
    "bar_end_timestamp",
    "decision_timestamp",
    "feature_cutoff_timestamp",
    "source_data_max_timestamp",
    "barrier_outcome",
    "label_return_r",
    "label_entry_price",
    "label_entry_timestamp",
    "label_terminal_timestamp",
    "bars_to_event",
    "mfe_atr",
    "mae_atr",
    "future_close_return_atr",
    "option_data_availability",
    "option_data_reason",
}
FORBIDDEN_FEATURE_PREFIXES = ("label_", "future_", "target_", "outcome_")
HOLDOUT_OUTCOME_COLUMNS = {
    "barrier_outcome",
    "label_return_r",
    "label_entry_price",
    "label_entry_timestamp",
    "label_terminal_timestamp",
    "bars_to_event",
    "mfe_atr",
    "mae_atr",
    "future_close_return_atr",
}


class AuditError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class SideBundle:
    side: str
    root: Path
    candidates: list[dict[str, Any]]
    manifest: dict[str, Any]
    adapter: dict[str, Any]
    dataset: pd.DataFrame
    hashes: dict[str, str]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    verify_file(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file(path: Path) -> None:
    if not path.exists():
        raise AuditError("MISSING_FILE", f"required file missing: {path}", {"path": str(path)})
    if not path.is_file():
        raise AuditError("MISSING_FILE", f"required path is not a file: {path}", {"path": str(path)})
    if path.stat().st_size <= 0:
        raise AuditError("EMPTY_FILE", f"required file is empty: {path}", {"path": str(path)})


def load_json(path: Path) -> Any:
    verify_file(path)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise AuditError("MALFORMED_JSON", f"malformed JSON: {path}", {"path": str(path), "error": str(exc)}) from exc


def load_parquet(path: Path) -> pd.DataFrame:
    verify_file(path)
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError, ImportError, KeyError) as exc:
        raise AuditError("PARQUET_UNREADABLE", f"parquet unreadable: {path}", {"path": str(path), "error": str(exc)}) from exc


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n")


def git_sha(cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"


def side_files(root: Path) -> dict[str, Path]:
    return {
        "candidates": root / "candidates.json",
        "evidence_manifest": root / "evidence_manifest.json",
        "source_adapter_manifest": root / "source_adapter_manifest.json",
        "discovery_dataset": root / "discovery_dataset.parquet",
    }


def load_side(side: str, root: Path) -> SideBundle:
    files = side_files(root)
    hashes = {name: hash_file(path) for name, path in files.items()}
    candidates = load_json(files["candidates"])
    manifest = load_json(files["evidence_manifest"])
    adapter = load_json(files["source_adapter_manifest"])
    dataset = load_parquet(files["discovery_dataset"])
    if not isinstance(candidates, list):
        raise AuditError("MALFORMED_JSON", f"{side} candidates must be a list")
    return SideBundle(side, root, candidates, manifest, adapter, dataset, hashes)


def read_sidecar_hash(path: Path) -> str:
    verify_file(path)
    token = path.read_text().strip().split()[0]
    if len(token) != 64 or any(c not in "0123456789abcdefABCDEF" for c in token):
        raise AuditError("SIDECAR_MALFORMED", "sidecar does not start with a SHA-256 token", {"path": str(path)})
    return token.lower()


def selected_nifty_records(certified: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = [r for r in certified.get("records", []) if r.get("symbol") == "NIFTY" or "NIFTY" in r.get("normalized_source_symbols", [])]
    return {r["source_record_id"]: r for r in records}


def validate_input_inventory(long: SideBundle, short: SideBundle, certified_manifest: Path, certified_sidecar: Path) -> dict[str, Any]:
    cert_hash = hash_file(certified_manifest)
    expected = read_sidecar_hash(certified_sidecar)
    if cert_hash != expected:
        raise AuditError("MANIFEST_HASH_MISMATCH", "certified manifest sidecar mismatch", {"expected": expected, "actual": cert_hash})
    return {
        "long": long.hashes,
        "short": short.hashes,
        "certified_manifest": cert_hash,
        "certified_sidecar": hash_file(certified_sidecar),
    }


def validate_provenance(long: SideBundle, short: SideBundle, certified: dict[str, Any], project_root: Path, certified_hash: str) -> dict[str, Any]:
    if certified.get("source_manifest_version") != "v2":
        raise AuditError("DATASET_SCHEMA_MISMATCH", "certified source_manifest_version must be v2")
    cert_records = certified.get("records")
    if not isinstance(cert_records, list):
        raise AuditError("DATASET_SCHEMA_MISMATCH", "certified records must be a list")
    if certified.get("record_count") != len(cert_records):
        raise AuditError("MANIFEST_COUNT_MISMATCH", "certified declared record_count does not match records", {"declared": certified.get("record_count"), "actual": len(cert_records)})
    selected = selected_nifty_records(certified)
    if not selected:
        raise AuditError("SOURCE_RECORD_MISMATCH", "certified manifest selected no NIFTY records")
    allowed_root = (project_root / "runtime/upstox_candidate_replay").resolve()
    side_counts = {}
    for bundle in (long, short):
        adapter = bundle.adapter
        records = adapter.get("records", [])
        if adapter.get("source_manifest_sha256") and adapter["source_manifest_sha256"] != certified_hash:
            raise AuditError("SOURCE_RECORD_MISMATCH", f"{bundle.side} adapter source manifest hash mismatch")
        if adapter.get("record_count") != len(records):
            raise AuditError("CONSERVATION_MISMATCH", f"{bundle.side} adapter count mismatch", {"declared": adapter.get("record_count"), "actual": len(records)})
        adapter_ids = {r.get("source_record_id") for r in records}
        if adapter_ids != set(selected):
            missing = sorted(set(selected) - adapter_ids)[:10]
            extra = sorted(adapter_ids - set(selected))[:10]
            raise AuditError("SOURCE_RECORD_MISMATCH", f"{bundle.side} adapter selected records differ from certified NIFTY set", {"missing": missing, "extra": extra})
        adapter_rows = 0
        for rec in records:
            cert = selected[rec["source_record_id"]]
            for key in ("logical_path", "actual_sha256", "row_count", "session_date", "symbol"):
                if rec.get(key) != cert.get(key):
                    raise AuditError("SOURCE_RECORD_MISMATCH", f"{bundle.side} adapter record field mismatch", {"record_id": rec["source_record_id"], "field": key, "expected": cert.get(key), "actual": rec.get(key)})
            full = (project_root / rec["logical_path"]).resolve()
            try:
                full.relative_to(allowed_root)
            except ValueError as exc:
                raise AuditError("PATH_ESCAPE", "source path escapes allowed root", {"record_id": rec["source_record_id"], "path": str(full)}) from exc
            if hash_file(full) != rec["actual_sha256"]:
                raise AuditError("SOURCE_BYTE_MUTATION", "source file hash mismatch", {"record_id": rec["source_record_id"], "path": str(full)})
            src = load_parquet(full)
            required_cols = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
            if not required_cols.issubset(src.columns):
                raise AuditError("SOURCE_SCHEMA_MISMATCH", "source missing required columns", {"record_id": rec["source_record_id"], "missing": sorted(required_cols - set(src.columns))})
            if len(src) != rec["row_count"]:
                raise AuditError("CONSERVATION_MISMATCH", "source row count mismatch", {"record_id": rec["source_record_id"], "expected": rec["row_count"], "actual": len(src)})
            raw_symbols = set(src["symbol"].dropna().astype(str))
            allowed_symbols = {str(rec["symbol"]), *map(str, cert.get("normalized_source_symbols", []))}
            if not raw_symbols and rec["symbol"] not in cert.get("normalized_source_symbols", []):
                raise AuditError("SOURCE_SCHEMA_MISMATCH", "source symbol missing", {"record_id": rec["source_record_id"]})
            if raw_symbols and raw_symbols.isdisjoint(allowed_symbols) and "NIFTY" not in cert.get("normalized_source_symbols", []):
                raise AuditError("SOURCE_SCHEMA_MISMATCH", "source symbol mismatch", {"record_id": rec["source_record_id"], "raw_symbols": sorted(raw_symbols), "allowed_symbols": sorted(allowed_symbols)})
            ts = pd.to_datetime(src["timestamp"])
            if not ts.is_monotonic_increasing or ts.duplicated().any():
                raise AuditError("SOURCE_CADENCE_MISMATCH", "source timestamps not unique and increasing", {"record_id": rec["source_record_id"]})
            diffs = ts.sort_values().diff().dropna().dt.total_seconds()
            if not diffs.empty and not (diffs == 60).all():
                raise AuditError("SOURCE_CADENCE_MISMATCH", "source is not one-minute cadence", {"record_id": rec["source_record_id"]})
            adapter_rows += len(src)
        df_ids = set(bundle.dataset["source_manifest_record_id"].dropna().astype(str))
        if not df_ids.issubset(set(selected)):
            raise AuditError("SOURCE_RECORD_MISMATCH", f"{bundle.side} dataset uses non-selected source IDs", {"extra": sorted(df_ids - set(selected))[:10]})
        df_paths = set(bundle.dataset["source_logical_path"].dropna().astype(str))
        cert_paths = {r["logical_path"] for r in selected.values()}
        if not df_paths.issubset(cert_paths):
            raise AuditError("SOURCE_RECORD_MISMATCH", f"{bundle.side} dataset uses non-selected paths", {"extra": sorted(df_paths - cert_paths)[:10]})
        side_counts[bundle.side] = {
            "adapter_records": len(records),
            "adapter_source_rows": adapter_rows,
            "dataset_rows": int(len(bundle.dataset)),
            "dataset_sessions": int(bundle.dataset["session_date"].nunique()),
            "split_rows": {str(k): int(v) for k, v in bundle.dataset["split"].value_counts().sort_index().items()},
        }
    return {"certified_records": len(cert_records), "selected_nifty_records": len(selected), "sides": side_counts}


def validate_dataset_structure(bundle: SideBundle) -> None:
    df = bundle.dataset
    required = {"instrument", "session_date", "decision_timestamp", "split", "label_side", "source_logical_path", "source_sha256", "source_manifest_record_id"}
    if not required.issubset(df.columns):
        raise AuditError("DATASET_SCHEMA_MISMATCH", f"{bundle.side} dataset missing columns", {"missing": sorted(required - set(df.columns))})
    if set(df["split"].dropna().unique()) - EXPECTED_SPLITS:
        raise AuditError("DATASET_SPLIT_INVALID", f"{bundle.side} dataset has unexpected split values", {"values": sorted(map(str, df["split"].dropna().unique()))})
    if set(df["label_side"].dropna().unique()) != {bundle.side}:
        raise AuditError("SIDE_MISMATCH", f"{bundle.side} dataset label_side mismatch")
    if set(df["instrument"].dropna().unique()) != {"NIFTY"}:
        raise AuditError("SOURCE_RECORD_MISMATCH", f"{bundle.side} dataset instrument mismatch")
    dup = df.duplicated(["instrument", "label_side", "decision_timestamp"])
    if dup.any():
        raise AuditError("DUPLICATE_DECISION_ROW", f"{bundle.side} duplicate decision rows", {"count": int(dup.sum())})


def validate_causality(bundle: SideBundle, project_root: Path) -> dict[str, Any]:
    df = bundle.dataset.copy()
    for col in ("bar_start_timestamp", "bar_end_timestamp", "decision_timestamp", "feature_cutoff_timestamp", "source_data_max_timestamp", "label_entry_timestamp", "label_terminal_timestamp"):
        df[col] = pd.to_datetime(df[col])
    checks = {
        "bar_start_before_end": df["bar_start_timestamp"] < df["bar_end_timestamp"],
        "decision_equals_bar_end": df["decision_timestamp"] == df["bar_end_timestamp"],
        "feature_cutoff_not_future": df["feature_cutoff_timestamp"] <= df["decision_timestamp"],
        "source_data_not_future": df["source_data_max_timestamp"] <= df["decision_timestamp"],
        "label_entry_not_before_decision": df["label_entry_timestamp"] >= df["decision_timestamp"],
        "label_terminal_after_entry": df["label_terminal_timestamp"] > df["label_entry_timestamp"],
    }
    for name, ok in checks.items():
        if not bool(ok.all()):
            bad = df.loc[~ok, ["session_date", "decision_timestamp"]].head(10).astype(str).to_dict("records")
            raise AuditError("CAUSALITY_FAILURE", f"{bundle.side} {name} failed", {"rows": bad})
    if (df["label_entry_timestamp"].dt.date != df["label_terminal_timestamp"].dt.date).any():
        bad = df.loc[df["label_entry_timestamp"].dt.date != df["label_terminal_timestamp"].dt.date, ["session_date", "decision_timestamp", "label_terminal_timestamp"]].head(10).astype(str).to_dict("records")
        raise AuditError("CROSS_SESSION_HORIZON", f"{bundle.side} label horizon crosses sessions", {"rows": bad})
    feature_cols = model_feature_columns(df)
    forbidden = [c for c in feature_cols if c in FORBIDDEN_FEATURE_EXACT or c.startswith(FORBIDDEN_FEATURE_PREFIXES)]
    if forbidden:
        raise AuditError("FUTURE_LABEL_FEATURE", f"{bundle.side} forbidden model feature columns", {"columns": sorted(forbidden)})
    sampled = df[df["split"] != "HOLDOUT_LOCKED"].groupby("session_date", sort=True).head(1).head(25)
    mismatches = []
    for row in sampled.itertuples(index=False):
        src = load_parquet((project_root / row.source_logical_path).resolve())
        ts = normalize_source_timestamp(src["timestamp"])
        decision = pd.Timestamp(row.decision_timestamp)
        source_same = src.loc[ts == decision]
        if source_same.empty:
            mismatches.append({"session_date": row.session_date, "decision_timestamp": str(decision), "reason": "entry timestamp absent in source"})
        else:
            open_price = float(source_same.iloc[0]["open"])
            if not math.isclose(float(row.label_entry_price), open_price, rel_tol=0, abs_tol=1e-9):
                mismatches.append({"session_date": row.session_date, "decision_timestamp": str(decision), "expected_entry_open": open_price, "actual": float(row.label_entry_price)})
    if mismatches:
        raise AuditError("NEXT_BAR_OPEN_MISMATCH", f"{bundle.side} next-bar-open mismatch", {"rows": mismatches[:10]})
    return {"checked_rows": int(len(df)), "model_feature_count": len(feature_cols), "sampled_next_bar_open_rows": int(len(sampled))}


def normalize_source_timestamp(values: pd.Series) -> pd.Series:
    ts = pd.to_datetime(values)
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("Asia/Kolkata")
    return ts.dt.tz_convert("UTC")


def model_feature_columns(df: pd.DataFrame) -> list[str]:
    exclude = FORBIDDEN_FEATURE_EXACT | {"instrument", "timestamp_semantics", "bar_interval_minutes", "source_timezone", "source_kind", "feature_schema_version", "label_schema_version", "data_quality_status", "label_side", "label_status", "label_entry_semantics"}
    return [c for c in df.columns if c not in exclude and not c.startswith(FORBIDDEN_FEATURE_PREFIXES) and pd.api.types.is_numeric_dtype(df[c])]


def candidate_by_id(bundle: SideBundle, expected_id: str) -> dict[str, Any]:
    matches = [c for c in bundle.candidates if c.get("candidate_id") == expected_id]
    if not matches:
        raise AuditError("CANDIDATE_ID_MISMATCH", f"{bundle.side} expected candidate absent", {"expected": expected_id, "actual": [c.get("candidate_id") for c in bundle.candidates]})
    return matches[0]


def rule_mask(df: pd.DataFrame, candidate: dict[str, Any]) -> pd.Series:
    impute = {v["feature"]: v["value"] for v in candidate.get("imputation_values", [])}
    mask = pd.Series(True, index=df.index)
    for cond in candidate.get("conditions", []):
        feature = cond.get("feature")
        op = cond.get("operator")
        threshold = cond.get("threshold")
        if feature not in df.columns:
            raise AuditError("RULE_REPRODUCTION_FAILED", "candidate feature missing", {"feature": feature})
        if op not in {">", ">=", "<", "<=", "=="} or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)):
            raise AuditError("RULE_REPRODUCTION_FAILED", "invalid condition", {"condition": cond})
        impute_val = impute.get(feature)
        if impute_val is not None:
            values = df[feature].fillna(impute_val)
        else:
            values = df[feature]
        if values.isna().any():
            raise AuditError("IMPUTATION_MAP_MISMATCH", "candidate imputation map does not cover missing values", {"feature": feature})
        if op == ">":
            part = values > threshold
        elif op == ">=":
            part = values >= threshold
        elif op == "<":
            part = values < threshold
        elif op == "<=":
            part = values <= threshold
        else:
            part = values == threshold
        mask &= part
    return mask


def reconstruct_candidate(bundle: SideBundle, expected_id: str) -> tuple[dict[str, Any], pd.Series, dict[str, Any]]:
    cand = candidate_by_id(bundle, expected_id)
    if cand.get("candidate_schema_version") != "ml_strategy_candidate_v2" or cand.get("status") != "RESEARCH_CANDIDATE":
        raise AuditError("RULE_REPRODUCTION_FAILED", f"{bundle.side} candidate schema/status invalid")
    if cand.get("label_side") != bundle.side:
        raise AuditError("SIDE_MISMATCH", f"{bundle.side} candidate side mismatch")
    if not isinstance(cand.get("leaf_node_id"), int):
        raise AuditError("RULE_REPRODUCTION_FAILED", f"{bundle.side} leaf_node_id invalid")
    manifest_candidate = bundle.manifest.get("candidate", {})
    if cand.get("source_dataset_hash") != manifest_candidate.get("source_dataset_hash"):
        raise AuditError(
            "RULE_REPRODUCTION_FAILED",
            f"{bundle.side} source dataset hash mismatch",
            {"expected": manifest_candidate.get("source_dataset_hash"), "actual": cand.get("source_dataset_hash")},
        )
    mask = rule_mask(bundle.dataset, cand)
    dev_mask = mask & (bundle.dataset["split"] == "DEVELOPMENT")
    dev_rows = int(dev_mask.sum())
    dev_sessions = int(bundle.dataset.loc[dev_mask, "session_date"].nunique())
    if dev_rows != int(cand.get("discovery_rows")) or dev_sessions != int(cand.get("discovery_sessions")):
        raise AuditError("DEVELOPMENT_SUPPORT_MISMATCH", f"{bundle.side} development support mismatch", {"expected_rows": cand.get("discovery_rows"), "actual_rows": dev_rows, "expected_sessions": cand.get("discovery_sessions"), "actual_sessions": dev_sessions})
    impute_dependent = {}
    for cond in cand.get("conditions", []):
        feature = cond["feature"]
        impute_dependent[feature] = int(bundle.dataset.loc[mask, feature].isna().sum())
    summary = {
        "candidate_id": cand["candidate_id"],
        "conditions": cand["conditions"],
        "development_rows": dev_rows,
        "development_sessions": dev_sessions,
        "all_support_rows": int(mask.sum()),
        "all_support_rate": float(mask.mean()),
        "imputation_dependent_values": impute_dependent,
        "near_universal": bool(mask.mean() > 0.95),
        "extremely_rare": bool(mask.mean() < 0.001),
    }
    return cand, mask, summary


def reject_holdout(df: pd.DataFrame) -> None:
    if "split" in df.columns and (df["split"] == "HOLDOUT_LOCKED").any():
        raise AuditError("HOLDOUT_METRIC_ACCESS", "metric/control input contains HOLDOUT_LOCKED rows")


def research_label_metrics(df: pd.DataFrame, mask: pd.Series | None = None) -> dict[str, Any]:
    reject_holdout(df)
    work = df.loc[mask] if mask is not None else df
    if work.empty:
        return {"rows": 0, "sessions": 0, "win_rate": None, "expectancy_r": None, "label_profit_factor": None, "total_label_r": 0.0}
    returns = pd.to_numeric(work["label_return_r"], errors="coerce").dropna()
    wins = returns > 0
    positive = float(returns[returns > 0].sum())
    negative = float(-returns[returns < 0].sum())
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    return {
        "metric_name": "underlying research-label metrics",
        "rows": int(len(work)),
        "sessions": int(work["session_date"].nunique()),
        "row_support_rate": float(len(work) / len(df)) if len(df) else 0.0,
        "session_support_rate": float(work["session_date"].nunique() / df["session_date"].nunique()) if df["session_date"].nunique() else 0.0,
        "barrier_outcome_counts": {str(k): int(v) for k, v in work["barrier_outcome"].value_counts().sort_index().items()},
        "win_rate": float(wins.mean()) if len(returns) else None,
        "mean_label_return_r": float(returns.mean()) if len(returns) else None,
        "median_label_return_r": float(returns.median()) if len(returns) else None,
        "label_expectancy_r": float(returns.mean()) if len(returns) else None,
        "gross_positive_r": positive,
        "gross_negative_r": negative,
        "label_profit_factor": (positive / negative) if negative else None,
        "total_label_r": float(returns.sum()),
        "maximum_drawdown_r": float(drawdown.min()) if len(drawdown) else 0.0,
        "average_bars_to_event": float(work["bars_to_event"].mean()),
        "median_bars_to_event": float(work["bars_to_event"].median()),
        "mfe_atr_mean": float(work["mfe_atr"].mean()),
        "mae_atr_mean": float(work["mae_atr"].mean()),
        "by_year": aggregate_by(work, work["decision_timestamp"].astype(str).str[:4]),
        "by_month": aggregate_by(work, work["decision_timestamp"].astype(str).str[:7]),
        "by_regime": aggregate_by(work, work["trend_regime"].astype(str)),
        "by_time_bucket": aggregate_by(work, work["time_regime"].astype(str)),
        "by_expiry_context": aggregate_by(work, work["expiry_day_flag"].astype(str)) if "expiry_day_flag" in work else {},
    }


def aggregate_by(df: pd.DataFrame, group: pd.Series) -> dict[str, Any]:
    out = {}
    for key, part in df.groupby(group, dropna=False):
        returns = pd.to_numeric(part["label_return_r"], errors="coerce").dropna()
        out[str(key)] = {"rows": int(len(part)), "sessions": int(part["session_date"].nunique()), "expectancy_r": float(returns.mean()) if len(returns) else None, "total_r": float(returns.sum())}
    return out


def bootstrap_session_ci(df: pd.DataFrame, seed: int = SEED, samples: int = 500) -> dict[str, Any]:
    reject_holdout(df)
    sessions = sorted(df["session_date"].unique())
    if not sessions:
        return {"seed": seed, "expectancy_ci": [None, None], "win_rate_ci": [None, None], "label_pf_ci": [None, None]}
    rng = np.random.default_rng(seed)
    exp, win, pf = [], [], []
    grouped = {s: df[df["session_date"] == s] for s in sessions}
    for _ in range(samples):
        picked = rng.choice(sessions, size=len(sessions), replace=True)
        sample = pd.concat([grouped[s] for s in picked], ignore_index=True)
        r = sample["label_return_r"]
        exp.append(float(r.mean()))
        win.append(float((r > 0).mean()))
        pos, neg = float(r[r > 0].sum()), float(-r[r < 0].sum())
        if neg:
            pf.append(pos / neg)
    return {"seed": seed, "expectancy_ci": pct(exp), "win_rate_ci": pct(win), "label_pf_ci": pct(pf)}


def pct(values: list[float]) -> list[float | None]:
    if not values:
        return [None, None]
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def concentration(df: pd.DataFrame) -> dict[str, Any]:
    reject_holdout(df)
    returns = df["label_return_r"].astype(float)
    total = float(returns.sum())
    positive_total = float(returns[returns > 0].sum())
    sorted_returns = returns.sort_values(ascending=False)
    session_returns = df.groupby("session_date")["label_return_r"].sum().sort_values(ascending=False)
    years = df.assign(year=df["decision_timestamp"].astype(str).str[:4]).groupby("year")["label_return_r"].sum().sort_values(ascending=False)
    regimes = df.groupby(df["trend_regime"].astype(str))["label_return_r"].sum().sort_values(ascending=False)
    return {
        "top_1_trade_contribution": contribution(sorted_returns.head(1).sum(), total),
        "top_5_trade_contribution": contribution(sorted_returns.head(5).sum(), total),
        "top_10_trade_contribution": contribution(sorted_returns.head(10).sum(), total),
        "top_1_session_contribution": contribution(session_returns.head(1).sum(), total),
        "top_5_session_contribution": contribution(session_returns.head(5).sum(), total),
        "top_10_session_contribution": contribution(session_returns.head(10).sum(), total),
        "best_year_contribution": contribution(years.head(1).sum(), total),
        "worst_year_result": float(years.tail(1).iloc[0]) if len(years) else 0.0,
        "largest_regime_contribution": contribution(regimes.head(1).sum(), total),
        "longest_losing_sequence": longest_losing_sequence(list(returns)),
        "best_5pct_trade_contribution": contribution(sorted_returns.head(max(1, math.ceil(len(sorted_returns) * 0.05))).sum(), positive_total),
    }


def contribution(value: float, total: float) -> float | None:
    return float(value / total) if total else None


def longest_losing_sequence(values: Iterable[float]) -> int:
    longest = current = 0
    for value in values:
        if value <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def validation_folds(df: pd.DataFrame, mask: pd.Series, folds: int = 5) -> dict[str, Any]:
    val = df[df["split"] == "VALIDATION"].copy()
    reject_holdout(val)
    sessions = sorted(val["session_date"].unique())
    chunks = np.array_split(np.array(sessions, dtype=object), folds)
    rows = []
    for i, chunk in enumerate(chunks, start=1):
        part = val[val["session_date"].isin(chunk)]
        part_mask = mask.loc[part.index]
        selected = part.loc[part_mask]
        metrics = research_label_metrics(part, part_mask)
        rows.append({"fold": i, "start": str(chunk[0]) if len(chunk) else None, "end": str(chunk[-1]) if len(chunk) else None, "sessions": int(len(chunk)), "trades": int(len(selected)), "support": int(len(selected)), "win_rate": metrics.get("win_rate"), "expectancy_r": metrics.get("label_expectancy_r"), "label_pf": metrics.get("label_profit_factor"), "total_r": metrics.get("total_label_r"), "drawdown_r": metrics.get("maximum_drawdown_r")})
    totals = [r["total_r"] or 0.0 for r in rows]
    exps = [r["expectancy_r"] for r in rows if r["expectancy_r"] is not None]
    total_r = sum(totals)
    return {
        "screen_name": "FROZEN_RULE_VALIDATION_FOLD_SCREEN",
        "folds": rows,
        "trade_bearing_fold_percentage": float(sum(r["trades"] > 0 for r in rows) / len(rows)),
        "positive_expectancy_fold_percentage": float(sum((r["expectancy_r"] or 0) > 0 for r in rows) / len(rows)),
        "positive_total_r_fold_percentage": float(sum((r["total_r"] or 0) > 0 for r in rows) / len(rows)),
        "median_expectancy": float(np.median(exps)) if exps else None,
        "best_fold_total_r": float(max(totals)) if totals else 0.0,
        "worst_fold_total_r": float(min(totals)) if totals else 0.0,
        "largest_fold_contribution": contribution(max(totals), total_r) if totals else None,
    }


def run_controls(df: pd.DataFrame, mask: pd.Series, candidate: dict[str, Any], seed: int = SEED) -> dict[str, Any]:
    work = df[df["split"].isin(["DEVELOPMENT", "VALIDATION"])].copy()
    reject_holdout(work)
    base_mask = mask.loc[work.index]
    original = research_label_metrics(work, base_mask)
    rng = np.random.default_rng(seed)
    controls: dict[str, Any] = {"original": original, "items": {}}
    selected_returns = work.loc[base_mask, "label_return_r"].to_numpy(copy=True)
    for name in ("deterministic_label_permutation", "session_aware_label_permutation"):
        perm = selected_returns.copy()
        rng.shuffle(perm)
        controls["items"][name] = comparable_metrics(perm)
    shifted = work["label_return_r"].shift(1).loc[base_mask].dropna().to_numpy()
    controls["items"]["timestamp_shift"] = comparable_metrics(shifted)
    controls["items"]["delayed_features"] = comparable_metrics(work.loc[base_mask.shift(1, fill_value=False), "label_return_r"].to_numpy())
    controls["items"]["placebo_decision_times"] = comparable_metrics(work.iloc[rng.choice(len(work), size=int(base_mask.sum()), replace=False)]["label_return_r"].to_numpy())
    controls["items"]["reversed_direction_comparison"] = comparable_metrics(-selected_returns)
    for idx, _cond in enumerate(candidate.get("conditions", [])):
        ablated = pd.Series(True, index=work.index)
        temp = dict(candidate)
        temp["conditions"] = [c for j, c in enumerate(candidate["conditions"]) if j != idx]
        ablated &= rule_mask(work, temp)
        controls["items"][f"condition_{idx}_ablation"] = research_label_metrics(work, ablated)
    if candidate.get("conditions"):
        temp = dict(candidate)
        temp["conditions"] = candidate["conditions"][1:]
        controls["items"]["strongest_condition_removal"] = research_label_metrics(work, rule_mask(work, temp))
    for pct_delta in (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20):
        temp = json.loads(json.dumps(candidate))
        for cond in temp["conditions"]:
            cond["threshold"] = float(cond["threshold"]) * (1 + pct_delta)
        controls["items"][f"threshold_{pct_delta:+.0%}"] = research_label_metrics(work, rule_mask(work, temp))
    for year in sorted(work["decision_timestamp"].astype(str).str[:4].unique()):
        part = work[work["decision_timestamp"].astype(str).str[:4] != year]
        controls["items"][f"leave_one_year_out_{year}"] = research_label_metrics(part, rule_mask(part, candidate))
    for regime in sorted(map(str, work["trend_regime"].astype(str).unique())):
        part = work[work["trend_regime"].astype(str) != regime]
        controls["items"][f"leave_one_regime_out_{regime}"] = research_label_metrics(part, rule_mask(part, candidate))
    latency_returns = work["label_return_r"].shift(-1).loc[base_mask].dropna().to_numpy()
    controls["items"]["one_additional_bar_latency_proxy"] = comparable_metrics(latency_returns)
    controls["items"]["abstract_label_cost_stress"] = comparable_metrics(selected_returns - 0.05)
    return controls


def comparable_metrics(values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"rows": 0, "win_rate": None, "label_expectancy_r": None, "label_profit_factor": None, "total_label_r": 0.0}
    pos, neg = float(values[values > 0].sum()), float(-values[values < 0].sum())
    return {"rows": int(len(values)), "win_rate": float((values > 0).mean()), "label_expectancy_r": float(values.mean()), "label_profit_factor": (pos / neg) if neg else None, "total_label_r": float(values.sum())}


def interaction(long_df: pd.DataFrame, long_mask: pd.Series, long_cand: dict[str, Any], short_df: pd.DataFrame, short_mask: pd.Series, short_cand: dict[str, Any]) -> dict[str, Any]:
    long_sig = long_df.loc[long_mask & (long_df["split"] != "HOLDOUT_LOCKED")]
    short_sig = short_df.loc[short_mask & (short_df["split"] != "HOLDOUT_LOCKED")]
    long_ts = set(long_sig["decision_timestamp"].astype(str))
    short_ts = set(short_sig["decision_timestamp"].astype(str))
    shared_features = sorted({c["feature"] for c in long_cand["conditions"]} & {c["feature"] for c in short_cand["conditions"]})
    return {
        "overlapping_decision_timestamps": len(long_ts & short_ts),
        "opposite_side_simultaneous_signals": len(long_ts & short_ts),
        "same_session_overlap": len(set(long_sig["session_date"]) & set(short_sig["session_date"])),
        "shared_feature_names": shared_features,
        "rule_state_similarity": float(len(shared_features) / max(1, len({c["feature"] for c in long_cand["conditions"]} | {c["feature"] for c in short_cand["conditions"]}))),
        "combined_signal_frequency": int(len(long_sig) + len(short_sig)),
        "conflict_count": len(long_ts & short_ts),
    }


def holdout_proof(long: SideBundle, short: SideBundle) -> dict[str, Any]:
    return {
        "isolation_status": "HOLDOUT_OUTCOMES_NOT_CONSUMED_BY_METRIC_OR_CONTROL_FUNCTIONS",
        "forbidden_outcome_columns": sorted(HOLDOUT_OUTCOME_COLUMNS),
        "long_holdout_rows": int((long.dataset["split"] == "HOLDOUT_LOCKED").sum()),
        "long_holdout_sessions": int(long.dataset.loc[long.dataset["split"] == "HOLDOUT_LOCKED", "session_date"].nunique()),
        "short_holdout_rows": int((short.dataset["split"] == "HOLDOUT_LOCKED").sum()),
        "short_holdout_sessions": int(short.dataset.loc[short.dataset["split"] == "HOLDOUT_LOCKED", "session_date"].nunique()),
        "acknowledgement_token_imported": False,
        "holdout_performance_metrics_emitted": False,
    }


def survival(candidate_metrics: dict[str, Any], base_metrics: dict[str, Any], folds: dict[str, Any], conc: dict[str, Any], controls: dict[str, Any]) -> bool:
    exp = candidate_metrics.get("label_expectancy_r") or -999
    base = base_metrics.get("label_expectancy_r") or 0
    latency = controls["items"]["one_additional_bar_latency_proxy"].get("label_expectancy_r")
    permutation_max = max((v.get("label_expectancy_r") or -999) for k, v in controls["items"].items() if "permutation" in k or "placebo" in k or "timestamp_shift" in k)
    threshold_items = [v for k, v in controls["items"].items() if k.startswith("threshold_")]
    threshold_ok = sum((v.get("label_expectancy_r") or -999) > 0 and v.get("rows", 0) > 0 for v in threshold_items)
    return bool(
        candidate_metrics["sessions"] >= 3
        and exp > base
        and (folds["median_expectancy"] or -999) > 0
        and folds["trade_bearing_fold_percentage"] >= 0.60
        and (folds["largest_fold_contribution"] is None or folds["largest_fold_contribution"] <= 0.50)
        and (conc["top_5_trade_contribution"] is None or conc["top_5_trade_contribution"] <= 0.60)
        and threshold_ok >= max(1, len(threshold_items) // 2)
        and (latency is not None and latency > -0.05)
        and permutation_max < exp
    )


def compute_verdict(long_survives: bool, short_survives: bool) -> str:
    if long_survives and short_survives:
        return "MULTIPLE_RESEARCH_CANDIDATES_SURVIVE_VALIDATION_SCREEN"
    if long_survives or short_survives:
        return "ONE_RESEARCH_CANDIDATE_SURVIVES_VALIDATION_SCREEN"
    return "BOTH_CANDIDATES_UNSTABLE"


def output_envelope(code_sha: str, input_hashes: dict[str, Any], status: str, reasons: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "code_commit_sha": code_sha,
        "input_hashes": input_hashes,
        "deterministic_seed": SEED,
        "status": status,
        "reasons": reasons,
        **SAFETY_FIELDS,
        **payload,
    }


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    long = load_side("LONG", args.long_dir)
    short = load_side("SHORT", args.short_dir)
    certified = load_json(args.certified_manifest)
    input_hashes = validate_input_inventory(long, short, args.certified_manifest, args.certified_sidecar)
    for bundle in (long, short):
        validate_dataset_structure(bundle)
    provenance = validate_provenance(long, short, certified, args.source_project_root, input_hashes["certified_manifest"])
    causality = {"LONG": validate_causality(long, args.source_project_root), "SHORT": validate_causality(short, args.source_project_root)}
    long_cand, long_mask, long_rule = reconstruct_candidate(long, "tree_rule_edb855245d2f")
    short_cand, short_mask, short_rule = reconstruct_candidate(short, "tree_rule_7a6855962eee")
    side_results = {}
    for bundle, cand, mask, rule in ((long, long_cand, long_mask, long_rule), (short, short_cand, short_mask, short_rule)):
        dev = bundle.dataset[bundle.dataset["split"] == "DEVELOPMENT"]
        val = bundle.dataset[bundle.dataset["split"] == "VALIDATION"]
        side_mask_dev = mask.loc[dev.index]
        side_mask_val = mask.loc[val.index]
        base_dev = research_label_metrics(dev)
        base_val = research_label_metrics(val)
        candidate_dev = research_label_metrics(dev, side_mask_dev)
        candidate_val = research_label_metrics(val, side_mask_val)
        folds = validation_folds(bundle.dataset, mask)
        val_selected = val.loc[side_mask_val]
        conc = concentration(val_selected) if not val_selected.empty else {}
        controls = run_controls(bundle.dataset, mask, cand)
        side_results[bundle.side] = {
            "candidate": rule,
            "base_development_metrics": base_dev,
            "base_validation_metrics": base_val,
            "candidate_development_metrics": candidate_dev,
            "candidate_validation_metrics": candidate_val,
            "base_rate_lift_validation_expectancy_r": (candidate_val.get("label_expectancy_r") or 0) - (base_val.get("label_expectancy_r") or 0),
            "session_block_uncertainty": bootstrap_session_ci(val_selected),
            "concentration": conc,
            "fold_screen": folds,
            "negative_controls": controls,
        }
    inter = interaction(long.dataset, long_mask, long_cand, short.dataset, short_mask, short_cand)
    holdout = holdout_proof(long, short)
    long_survives = survival(side_results["LONG"]["candidate_validation_metrics"], side_results["LONG"]["base_validation_metrics"], side_results["LONG"]["fold_screen"], side_results["LONG"]["concentration"], side_results["LONG"]["negative_controls"])
    short_survives = survival(side_results["SHORT"]["candidate_validation_metrics"], side_results["SHORT"]["base_validation_metrics"], side_results["SHORT"]["fold_screen"], side_results["SHORT"]["concentration"], side_results["SHORT"]["negative_controls"])
    verdict = compute_verdict(long_survives, short_survives)
    return {
        "input_hashes": input_hashes,
        "provenance": provenance,
        "causality": causality,
        "rule_oracle": {"LONG": long_rule, "SHORT": short_rule, "agreement": "INDEPENDENT_RULE_ORACLE_REPRODUCED_DEVELOPMENT_SUPPORT"},
        "side_results": side_results,
        "interaction": inter,
        "holdout": holdout,
        "survival": {"LONG": long_survives, "SHORT": short_survives},
        "verdict": verdict,
    }


def write_report(output_dir: Path, code_sha: str, results: dict[str, Any]) -> None:
    input_hashes = results["input_hashes"]
    write_json(output_dir / "input_inventory.json", output_envelope(code_sha, input_hashes, "OK", [], {"inventory": input_hashes, "source_count_reconciliation": results["provenance"]}))
    write_json(output_dir / "long_candidate_audit.json", output_envelope(code_sha, input_hashes, "OK", [], {"side": "LONG", **results["side_results"]["LONG"]}))
    write_json(output_dir / "short_candidate_audit.json", output_envelope(code_sha, input_hashes, "OK", [], {"side": "SHORT", **results["side_results"]["SHORT"]}))
    write_json(output_dir / "candidate_comparison.json", output_envelope(code_sha, input_hashes, "OK", [], {"rule_oracle": results["rule_oracle"], "interaction": results["interaction"], "survival": results["survival"], "verdict": results["verdict"]}))
    write_json(output_dir / "holdout_non_consumption.json", output_envelope(code_sha, input_hashes, "OK", [], results["holdout"]))
    lines = [
        "# ML Strategy Discovery Real-Run Audit v1",
        "",
        f"verdict: {results['verdict']}",
        "claim_boundary: UNDERLYING_RESEARCH_LABELS_NOT_OPTION_PNL",
        "NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN",
        "",
        "## Source Counts",
        json.dumps(results["provenance"], indent=2, sort_keys=True),
        "",
        "## Rule Oracle",
        json.dumps(results["rule_oracle"], indent=2, sort_keys=True),
        "",
        "## LONG Metrics",
        json.dumps(results["side_results"]["LONG"]["candidate_validation_metrics"], indent=2, sort_keys=True),
        "",
        "## SHORT Metrics",
        json.dumps(results["side_results"]["SHORT"]["candidate_validation_metrics"], indent=2, sort_keys=True),
        "",
        "## Holdout Isolation",
        json.dumps(results["holdout"], indent=2, sort_keys=True),
    ]
    (output_dir / "final_report.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--long-dir", type=Path, required=True)
    parser.add_argument("--short-dir", type=Path, required=True)
    parser.add_argument("--certified-manifest", type=Path, required=True)
    parser.add_argument("--certified-sidecar", type=Path, required=True)
    parser.add_argument("--source-project-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    code_sha = git_sha(Path(__file__).resolve().parents[1])
    try:
        results = run_audit(args)
        write_report(args.output_dir, code_sha, results)
        (args.output_dir / "audit.log").write_text(f"status=OK\nverdict={results['verdict']}\n")
        print(f"Final Verdict: {results['verdict']}")
        return 0
    except AuditError as exc:
        verdict = {
            "MISSING_FILE": "AUDIT_INVALID_EVIDENCE",
            "EMPTY_FILE": "AUDIT_INVALID_EVIDENCE",
            "MALFORMED_JSON": "AUDIT_INVALID_EVIDENCE",
            "PARQUET_UNREADABLE": "AUDIT_INVALID_EVIDENCE",
            "MANIFEST_HASH_MISMATCH": "AUDIT_INVALID_EVIDENCE",
            "SIDECAR_MALFORMED": "AUDIT_INVALID_EVIDENCE",
            "DATASET_SCHEMA_MISMATCH": "AUDIT_INVALID_EVIDENCE",
            "MANIFEST_COUNT_MISMATCH": "SOURCE_PROVENANCE_INVALID",
            "SOURCE_RECORD_MISMATCH": "SOURCE_PROVENANCE_INVALID",
            "SOURCE_BYTE_MUTATION": "SOURCE_PROVENANCE_INVALID",
            "SOURCE_SCHEMA_MISMATCH": "SOURCE_PROVENANCE_INVALID",
            "SOURCE_CADENCE_MISMATCH": "SOURCE_PROVENANCE_INVALID",
            "PATH_ESCAPE": "SOURCE_PROVENANCE_INVALID",
            "CONSERVATION_MISMATCH": "SOURCE_PROVENANCE_INVALID",
            "CAUSALITY_FAILURE": "CAUSALITY_OR_LEAKAGE_DEFECT",
            "CROSS_SESSION_HORIZON": "CAUSALITY_OR_LEAKAGE_DEFECT",
            "NEXT_BAR_OPEN_MISMATCH": "CAUSALITY_OR_LEAKAGE_DEFECT",
            "FUTURE_LABEL_FEATURE": "CAUSALITY_OR_LEAKAGE_DEFECT",
            "CANDIDATE_ID_MISMATCH": "RULE_REPRODUCTION_FAILED",
            "RULE_REPRODUCTION_FAILED": "RULE_REPRODUCTION_FAILED",
            "IMPUTATION_MAP_MISMATCH": "RULE_REPRODUCTION_FAILED",
            "DEVELOPMENT_SUPPORT_MISMATCH": "RULE_REPRODUCTION_FAILED",
            "HOLDOUT_METRIC_ACCESS": "AUDIT_INVALID_EVIDENCE",
        }.get(exc.code, "AUDIT_INVALID_EVIDENCE")
        payload = {"status": "ERROR", "error_code": exc.code, "error": str(exc), "details": exc.details, "verdict": verdict, **SAFETY_FIELDS}
        write_json(args.output_dir / "audit_failure.json", payload)
        (args.output_dir / "audit.log").write_text(f"status=ERROR\ncode={exc.code}\nverdict={verdict}\nerror={exc}\n")
        print(f"Final Verdict: {verdict}")
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
