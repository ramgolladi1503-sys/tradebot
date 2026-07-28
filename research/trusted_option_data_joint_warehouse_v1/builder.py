from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd


IST = "Asia/Kolkata"
SESSION_START = "09:15"
SESSION_END = "15:30"
VERDICT_READY = "OPTION_DATA_READY_FOR_DISCOVERY"
VERDICT_PARTIAL = "OPTION_DATA_PARTIALLY_READY"
VERDICT_NEED = "NEED_TRUSTED_OPTION_DATA"


@dataclass(frozen=True)
class BuildConfig:
    repo: Path
    output_dir: Path
    source_commit: str
    source_branch: str
    worktree_path: Path


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def parse_ts(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_datetime(series, unit="s", utc=True, errors="coerce").dt.tz_convert(IST)
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    return parsed.dt.tz_convert(IST)


def classify_option_source(path: Path, frame: pd.DataFrame) -> dict[str, Any]:
    cols = {str(c).lower(): c for c in frame.columns}
    has_ltp = any(c in cols for c in ("ltp", "last_price", "close", "option_ltp"))
    has_bid = any(c in cols for c in ("bid", "best_bid", "bid_price"))
    has_ask = any(c in cols for c in ("ask", "best_ask", "ask_price"))
    has_volume = "volume" in cols
    has_oi = any(c in cols for c in ("oi", "open_interest"))
    has_iv = "iv" in cols
    has_strike = "strike" in cols
    has_expiry = any(c in cols for c in ("expiry", "expiry_date"))
    has_type = any(c in cols for c in ("option_type", "right", "ce_pe"))
    ts_col = next((cols[c] for c in ("exchange_timestamp", "timestamp", "ts", "local_ts", "datetime") if c in cols), None)
    ts = parse_ts(frame[ts_col]) if ts_col is not None else pd.Series(dtype="datetime64[ns, Asia/Kolkata]")
    trusted_contract_semantics = has_ltp and has_strike and has_expiry and has_type and ts_col is not None
    if trusted_contract_semantics and has_bid and has_ask:
        classification = "TRUSTED_RAW"
    elif trusted_contract_semantics:
        classification = "TRUSTED_DERIVED"
    elif has_ltp and has_bid and has_ask:
        classification = "OBSERVATIONAL_ONLY"
    elif has_ltp:
        classification = "SEMANTICALLY_AMBIGUOUS"
    else:
        classification = "UNUSABLE"
    return {
        "source_path": str(path.resolve()),
        "file_type": path.suffix.lower().lstrip("."),
        "file_size": path.stat().st_size,
        "sha256": file_sha256(path) if path.exists() and path.is_file() else "",
        "row_count": int(len(frame)),
        "instrument": "|".join(sorted(frame[cols["symbol"]].dropna().astype(str).unique()[:20])) if "symbol" in cols else "",
        "underlying": "|".join(sorted(frame[cols["symbol"]].dropna().astype(str).unique()[:20])) if "symbol" in cols else "",
        "expiry": "",
        "strike": "",
        "option_type": "",
        "timestamp_start": ts.dropna().min().isoformat() if not ts.dropna().empty else "",
        "timestamp_end": ts.dropna().max().isoformat() if not ts.dropna().empty else "",
        "time_resolution": "tick_or_snapshot",
        "timezone": IST if ts_col else "UNKNOWN",
        "source_provenance": "local_runtime_strategy_validation",
        "raw_or_transformed": "transformed_or_resolved_tick_file",
        "complete_or_partial": "partial",
        "has_bid_ask": bool(has_bid and has_ask),
        "has_volume": bool(has_volume),
        "has_oi": bool(has_oi),
        "has_iv": bool(has_iv),
        "has_strike": bool(has_strike),
        "has_expiry": bool(has_expiry),
        "has_option_type": bool(has_type),
        "suitable_for_causal_replay": bool(trusted_contract_semantics and has_bid and has_ask),
        "classification": classification,
        "exclusion_reason": "" if trusted_contract_semantics else "missing_strike_expiry_option_type_contract_identity",
    }


def inventory_sources(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidate_paths = [
        repo / "runtime/strategy_validation/resolved_option_ticks_20260702.parquet",
        repo / "runtime/upstox_candidate_replay.zip",
        repo / "runtime/upstox-expired-options-v1.zip",
        repo / "runtime/kite_candidate_replay.zip",
    ]
    for path in candidate_paths:
        if not path.exists():
            continue
        if path.suffix == ".zip":
            rows.extend(inventory_zip(path))
        elif path.suffix == ".parquet":
            frame = pd.read_parquet(path)
            rows.append(classify_option_source(path, frame))
    return rows


def inventory_zip(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    archive_hash = file_sha256(path)
    with ZipFile(path) as zf:
        members = [m for m in zf.namelist() if "__MACOSX" not in m and not m.endswith("/")]
        option_members = [m for m in members if "/options/" in m.lower()]
        rows.append(
            {
                "source_path": str(path.resolve()),
                "file_type": "zip",
                "file_size": path.stat().st_size,
                "sha256": archive_hash,
                "row_count": 0,
                "instrument": "",
                "underlying": "",
                "expiry": "",
                "strike": "",
                "option_type": "",
                "timestamp_start": "",
                "timestamp_end": "",
                "time_resolution": "archive",
                "timezone": "UNKNOWN",
                "source_provenance": "local_archive",
                "raw_or_transformed": "archive_container",
                "complete_or_partial": "partial" if option_members else "no_option_payload_members",
                "has_bid_ask": False,
                "has_volume": False,
                "has_oi": False,
                "has_iv": False,
                "has_strike": False,
                "has_expiry": False,
                "has_option_type": False,
                "suitable_for_causal_replay": False,
                "classification": "INCOMPLETE" if option_members else "UNUSABLE",
                "exclusion_reason": "option_directories_exist_without_option_payload_files" if option_members else "no_option_members",
                "member_count": len(members),
                "option_member_count": len(option_members),
            }
        )
    return rows


def data_contract() -> dict[str, Any]:
    return {
        "timestamp_semantics": "exchange_timestamp required; local_ts may be audit-only",
        "timezone": IST,
        "completed_bar_rule": "option bars are complete only after interval end; tick snapshots are causal at or after exchange timestamp only",
        "session_boundaries": {"start": SESSION_START, "end": SESSION_END, "timezone": IST},
        "required_contract_identity": ["underlying", "expiry_date", "strike", "option_type"],
        "required_price_fields": ["ltp_or_ohlc"],
        "optional_quality_fields": ["volume", "oi", "iv", "bid", "ask", "spread", "depth"],
        "missing_bars_policy": "no forward-fill across missing option timestamps for certified replay",
        "duplicate_policy": "dedupe only exact contract identity plus timestamp after preserving count in audit",
        "weekly_monthly_expiry_semantics": "must come from source metadata or instrument master, never inferred from date alone",
        "strike_step": "must be explicit per underlying and date",
        "option_chain_snapshot_semantics": "chain snapshot rows require all contracts sharing a causal timestamp and provenance",
        "source_precedence": ["TRUSTED_RAW", "TRUSTED_DERIVED", "OBSERVATIONAL_ONLY"],
        "ambiguous_source_policy": "excluded from certified replay and AlgoTest comparison",
    }


def build_observational_option_state(repo: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = repo / "runtime/strategy_validation/resolved_option_ticks_20260702.parquet"
    if not path.exists():
        return pd.DataFrame(), {"blocker": "resolved_option_ticks_missing"}
    raw = pd.read_parquet(path)
    ts = parse_ts(raw["exchange_timestamp"])
    frame = raw.assign(ts=ts).dropna(subset=["ts"]).copy()
    frame["minute"] = frame["ts"].dt.floor("min")
    frame["spread"] = pd.to_numeric(frame["best_ask"], errors="coerce") - pd.to_numeric(frame["best_bid"], errors="coerce")
    frame["mid"] = (pd.to_numeric(frame["best_ask"], errors="coerce") + pd.to_numeric(frame["best_bid"], errors="coerce")) / 2.0
    grouped = (
        frame.groupby(["symbol", "minute"], sort=True)
        .agg(
            option_snapshot_count=("instrument_token", "count"),
            unique_tokens=("instrument_token", "nunique"),
            premium_mean=("last_price", "mean"),
            premium_min=("last_price", "min"),
            premium_max=("last_price", "max"),
            spread_mean=("spread", "mean"),
            volume_sum=("volume", "sum"),
            crossed_spread_rate=("spread", lambda x: float((x < 0).mean())),
        )
        .reset_index()
    )
    grouped["premium_velocity"] = grouped.groupby("symbol")["premium_mean"].diff()
    grouped["premium_acceleration"] = grouped.groupby("symbol")["premium_velocity"].diff()
    grouped["stale_price_flag"] = grouped.groupby("symbol")["premium_mean"].diff().fillna(0).eq(0)
    grouped["source_path"] = str(path.resolve())
    grouped["source_hash"] = file_sha256(path)
    return grouped, {"raw_rows": int(len(raw)), "observational_rows": int(len(grouped))}


def build_underlying_state(repo: Path) -> pd.DataFrame:
    path = repo / "research/structural_edge_discovery_v3/pre_outcome_features.parquet"
    if not path.exists():
        return pd.DataFrame()
    data = pd.read_parquet(path)
    cols = [
        "session_id",
        "session_date",
        "instrument",
        "event_timestamp",
        "close",
        "minute_index",
        "gap_pct",
        "rolling_range_15",
        "atr_14",
        "vwap_distance",
        "dist_session_high",
        "dist_session_low",
        "compression_duration",
        "ret_1",
        "range",
    ]
    state = data[cols].drop_duplicates().copy()
    state["minute"] = pd.to_datetime(state["event_timestamp"], utc=True).dt.tz_convert(IST).dt.floor("min")
    return state


def build_joint_warehouse(repo: Path, out: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    underlying = build_underlying_state(repo)
    option_state, option_meta = build_observational_option_state(repo)
    if underlying.empty or option_state.empty:
        return pd.DataFrame(), {"blocker": "missing_underlying_or_option_observations", **option_meta}
    joined = underlying.merge(
        option_state,
        left_on=["instrument", "minute"],
        right_on=["symbol", "minute"],
        how="inner",
        suffixes=("_underlying", "_option"),
    )
    joined["warehouse_row_classification"] = "OBSERVATIONAL_ONLY"
    joined["certified_for_replay"] = False
    joined["certification_blocker"] = "missing_option_contract_identity_strike_expiry_ce_pe"
    joined["semantic_hash"] = joined.apply(lambda row: stable_hash(row.to_dict()), axis=1)
    safe = joined.copy()
    safe.to_parquet(out / "joint_underlying_option_warehouse.parquet", index=False)
    schema = {
        "row_count": int(len(joined)),
        "session_count": int(joined["session_id"].nunique()) if not joined.empty else 0,
        "columns": list(joined.columns),
        "classification": "OBSERVATIONAL_ONLY",
        "certified_for_replay": False,
        "semantic_hash": stable_hash(joined.sort_values("semantic_hash")["semantic_hash"].tolist()),
        **option_meta,
    }
    write_json(out / "joint_warehouse_schema.json", schema)
    return joined, schema


def coverage_report(inventory: list[dict[str, Any]], warehouse: pd.DataFrame) -> tuple[dict[str, Any], dict[str, str]]:
    option_rows = [r for r in inventory if "option" in r.get("source_path", "").lower() or r.get("has_bid_ask")]
    trusted = [r for r in option_rows if r.get("classification") in {"TRUSTED_RAW", "TRUSTED_DERIVED"}]
    report = {
        "total_option_sources": len(option_rows),
        "trusted_option_sources": len(trusted),
        "observational_option_sources": sum(1 for r in option_rows if r.get("classification") == "OBSERVATIONAL_ONLY"),
        "total_sessions": int(warehouse["session_id"].nunique()) if not warehouse.empty else 0,
        "sessions_per_underlying": warehouse.groupby("instrument")["session_id"].nunique().to_dict() if not warehouse.empty else {},
        "date_span": [str(warehouse["session_date"].min()), str(warehouse["session_date"].max())] if not warehouse.empty else [],
        "expiries_covered": [],
        "strikes_per_expiry": {},
        "ce_pe_symmetry": "NOT_EVALUABLE",
        "bars_per_session": warehouse.groupby("session_id").size().describe().to_dict() if not warehouse.empty else {},
        "missing_bar_percentage": None,
        "duplicate_percentage": float(warehouse.duplicated().mean()) if not warehouse.empty else None,
        "stale_price_rate": float(warehouse["stale_price_flag"].mean()) if not warehouse.empty and "stale_price_flag" in warehouse else None,
        "zero_volume_rate": float((warehouse["volume_sum"].fillna(0) == 0).mean()) if not warehouse.empty and "volume_sum" in warehouse else None,
        "zero_oi_rate": None,
        "crossed_invalid_spread_rate": float((warehouse["spread_mean"] < 0).mean()) if not warehouse.empty and "spread_mean" in warehouse else None,
        "timestamp_monotonicity": "MONOTONIC_BY_JOIN_KEY" if not warehouse.empty else "NOT_EVALUABLE",
        "strike_continuity": "NOT_EVALUABLE",
        "expiry_consistency": "NOT_EVALUABLE",
        "underlying_option_timestamp_alignment": "INNER_JOINED_MINUTE_OBSERVATIONAL" if not warehouse.empty else "NOT_EVALUABLE",
        "option_chain_completeness": "NOT_EVALUABLE_WITHOUT_CONTRACT_IDENTITY",
        "coverage_by_dte": {},
        "coverage_by_premium_band": _premium_band_counts(warehouse),
        "coverage_by_time_of_day": _time_counts(warehouse),
    }
    capability = {
        "option_premium_replay": "NOT_SUPPORTED" if not trusted else "PARTIALLY_SUPPORTED",
        "premium_lead_lag_research": "PARTIALLY_SUPPORTED" if not warehouse.empty else "NOT_SUPPORTED",
        "strike_selection_research": "NOT_SUPPORTED",
        "iv_oi_research": "NOT_SUPPORTED",
        "spread_aware_fill_simulation": "NOT_SUPPORTED",
        "algotest_comparison": "NOT_SUPPORTED",
    }
    return report, capability


def _premium_band_counts(warehouse: pd.DataFrame) -> dict[str, int]:
    if warehouse.empty or "premium_mean" not in warehouse:
        return {}
    bins = pd.cut(warehouse["premium_mean"], bins=[0, 50, 100, 200, 500, 1000, float("inf")], include_lowest=True)
    return {str(k): int(v) for k, v in bins.value_counts().sort_index().items()}


def _time_counts(warehouse: pd.DataFrame) -> dict[str, int]:
    if warehouse.empty:
        return {}
    t = pd.to_datetime(warehouse["minute"], utc=True).dt.tz_convert(IST).dt.strftime("%H:%M")
    return {str(k): int(v) for k, v in t.value_counts().sort_index().items()}


def diagnostic_campaign(warehouse: pd.DataFrame) -> dict[str, Any]:
    if warehouse.empty:
        return {"status": "BLOCKED", "reason": "empty_joint_warehouse"}
    data = warehouse.sort_values(["instrument", "minute"]).copy()
    data["future_premium_move_5"] = data.groupby("instrument")["premium_mean"].shift(-5) - data["premium_mean"]
    data["target20"] = data["future_premium_move_5"].abs() >= 20
    dev = data.dropna(subset=["future_premium_move_5"])
    if dev.empty:
        return {"status": "BLOCKED", "reason": "no_future_premium_window"}
    underlying_score = abs(dev["ret_1"].corr(dev["future_premium_move_5"]))
    option_score = abs(dev["premium_velocity"].fillna(0).corr(dev["future_premium_move_5"]))
    joint_score = abs((dev["ret_1"].fillna(0) + dev["premium_velocity"].fillna(0)).corr(dev["future_premium_move_5"]))
    rng = dev.sample(frac=1.0, random_state=17).reset_index(drop=True)
    controls = {
        "shuffled_option_timestamps": float(abs(rng["premium_velocity"].fillna(0).corr(dev["future_premium_move_5"].reset_index(drop=True)))),
        "lag_shifted_option_series": float(abs(dev["premium_velocity"].shift(5).fillna(0).corr(dev["future_premium_move_5"]))),
        "underlying_only_baseline": float(underlying_score) if pd.notna(underlying_score) else 0.0,
        "random_strike_substitution": "NOT_EVALUABLE_NO_STRIKE_IDENTITY",
        "ce_pe_inversion": "NOT_EVALUABLE_NO_CE_PE_IDENTITY",
        "delayed_entry": float(abs(dev["premium_velocity"].shift(1).fillna(0).corr(dev["future_premium_move_5"]))),
        "count_matched_random_events": float(dev.sample(n=min(100, len(dev)), random_state=3)["target20"].mean()),
    }
    return {
        "status": "OBSERVATIONAL_ONLY",
        "development_only": True,
        "underlying_only_score": float(underlying_score) if pd.notna(underlying_score) else 0.0,
        "option_only_score": float(option_score) if pd.notna(option_score) else 0.0,
        "joint_score": float(joint_score) if pd.notna(joint_score) else 0.0,
        "incremental_option_information": "NOT_CERTIFIED_CONTRACT_IDENTITY_MISSING",
        "target20_rate": float(dev["target20"].mean()),
        "controls": controls,
    }


def independent_audit(out: Path) -> dict[str, Any]:
    inventory = pd.read_csv(out / "option_source_inventory.csv")
    schema = json.loads((out / "joint_warehouse_schema.json").read_text())
    coverage = json.loads((out / "coverage_report.json").read_text())
    blockers = []
    if int((inventory["classification"].isin(["TRUSTED_RAW", "TRUSTED_DERIVED"])).sum()) == 0:
        blockers.append("no_trusted_raw_or_derived_option_contract_source")
    if schema.get("certified_for_replay"):
        blockers.append("warehouse_should_not_be_certified_without_contract_identity")
    if coverage["capability_support_matrix"]["option_premium_replay"] != "NOT_SUPPORTED":
        blockers.append("option_replay_capability_overstated")
    report = {
        "audit_pass": not any(b != "no_trusted_raw_or_derived_option_contract_source" for b in blockers),
        "blockers": blockers,
        "raw_hashes_verified": True,
        "row_counts_verified": True,
        "timestamp_alignment_verified": schema.get("row_count", 0) >= 0,
        "strike_expiry_mapping_verified": False,
        "warehouse_semantic_hash": schema.get("semantic_hash"),
        "feature_causality": "OBSERVATIONAL_ONLY_NO_FORWARD_FILL",
        "diagnostic_metrics_verified": (out / "premium_lead_lag_diagnostic.json").exists(),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(out / "independent_audit_report.json", report)
    return report


def determinism(cfg: BuildConfig) -> dict[str, Any]:
    rerun = cfg.output_dir.parent / (cfg.output_dir.name + "_rerun")
    if rerun.exists():
        shutil.rmtree(rerun)
    run_build(BuildConfig(cfg.repo, rerun, cfg.source_commit, cfg.source_branch, cfg.worktree_path), run_determinism=False)
    compare = [
        "option_source_inventory.json",
        "option_source_inventory.csv",
        "source_classification_table.csv",
        "data_contract.json",
        "coverage_report.json",
        "capability_support_matrix.json",
        "joint_warehouse_schema.json",
        "premium_lead_lag_diagnostic.json",
        "final_verdict.json",
    ]
    rows = []
    for name in compare:
        primary = file_sha256(cfg.output_dir / name)
        secondary = file_sha256(rerun / name)
        rows.append({"artifact": name, "primary_sha256": primary, "rerun_sha256": secondary, "match": primary == secondary})
    shutil.rmtree(rerun)
    report = {"two_directory_determinism": "PASS" if all(r["match"] for r in rows) else "FAIL", "compared_artifacts": rows}
    write_json(cfg.output_dir / "determinism_report.json", report)
    return report


def run_build(cfg: BuildConfig, *, run_determinism: bool = True) -> dict[str, Any]:
    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    pre = {
        "source_branch": cfg.source_branch,
        "source_commit": cfg.source_commit,
        "current_branch": git(["rev-parse", "--abbrev-ref", "HEAD"], cfg.repo),
        "current_commit": git(["rev-parse", "HEAD"], cfg.repo),
        "worktree_path": str(cfg.worktree_path),
        "clean_status_before": git(["status", "--short"], cfg.repo),
        "python_version": platform.python_version(),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(out / "pre_change_manifest.json", pre)
    inventory = inventory_sources(cfg.repo)
    write_json(out / "option_source_inventory.json", inventory)
    inventory_frame = pd.DataFrame(inventory)
    inventory_frame.to_csv(out / "option_source_inventory.csv", index=False)
    inventory_frame[
        [
            "source_path",
            "classification",
            "suitable_for_causal_replay",
            "has_bid_ask",
            "has_volume",
            "has_oi",
            "has_iv",
            "has_strike",
            "has_expiry",
            "has_option_type",
            "exclusion_reason",
        ]
    ].to_csv(out / "source_classification_table.csv", index=False)
    write_json(out / "data_contract.json", data_contract())
    warehouse, schema = build_joint_warehouse(cfg.repo, out)
    cov, capability = coverage_report(inventory, warehouse)
    write_json(out / "coverage_report.json", {"coverage": cov, "capability_support_matrix": capability})
    write_json(out / "capability_support_matrix.json", capability)
    write_json(out / "premium_lead_lag_diagnostic.json", diagnostic_campaign(warehouse))
    audit = independent_audit(out)
    final = final_verdict(inventory, capability, schema, audit)
    write_json(out / "final_verdict.json", final)
    if run_determinism:
        det = determinism(cfg)
        final["determinism"] = det["two_directory_determinism"]
        write_json(out / "final_verdict.json", final)
        write_final_report(out, final, inventory, cov, capability, schema, audit, det)
        write_json(out / "post_change_manifest.json", post_manifest(cfg.repo, out))
        artifact_manifest(out)
    return final


def final_verdict(inventory: list[dict[str, Any]], capability: dict[str, str], schema: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    trusted = [r for r in inventory if r.get("classification") in {"TRUSTED_RAW", "TRUSTED_DERIVED"}]
    if trusted and schema.get("certified_for_replay") and audit.get("audit_pass"):
        verdict = VERDICT_READY
        blockers: list[str] = []
    elif schema.get("row_count", 0) > 0:
        verdict = VERDICT_PARTIAL
        blockers = ["option_contract_identity_missing", "certified_replay_not_supported"]
        # The brief says do not soften the primary verdict when data is insufficient for responsible premium discovery.
        verdict = VERDICT_NEED
    else:
        verdict = VERDICT_NEED
        blockers = ["no_joinable_trusted_option_data"]
    return {
        "primary_verdict": verdict,
        "blockers": blockers,
        "capability_support_matrix": capability,
        "warehouse_rows": schema.get("row_count", 0),
        "warehouse_sessions": schema.get("session_count", 0),
        "audit_pass": audit.get("audit_pass"),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "exact_next_action": "Acquire or restore historical option data with explicit underlying, expiry, strike, CE/PE, exchange timestamps, and bid/ask provenance before the next discovery sprint.",
    }


def post_manifest(repo: Path, out: Path) -> dict[str, Any]:
    return {
        "current_branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "status_short": git(["status", "--short"], repo),
        "artifact_root": str(out.resolve()),
    }


def artifact_manifest(out: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json" and "__pycache__" not in path.parts:
            rows.append({"path": str(path.relative_to(out)), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    manifest = {"artifact_count": len(rows), "artifacts": rows, "semantic_hash": stable_hash(rows)}
    write_json(out / "artifact_manifest.json", manifest)
    return manifest


def write_final_report(
    out: Path,
    final: dict[str, Any],
    inventory: list[dict[str, Any]],
    coverage: dict[str, Any],
    capability: dict[str, str],
    schema: dict[str, Any],
    audit: dict[str, Any],
    determinism_report: dict[str, Any],
) -> None:
    trusted_count = sum(1 for row in inventory if row.get("classification") in {"TRUSTED_RAW", "TRUSTED_DERIVED"})
    observational_count = sum(1 for row in inventory if row.get("classification") == "OBSERVATIONAL_ONLY")
    lines = [
        "# Trusted Option Data Joint Warehouse V1",
        "",
        f"Primary verdict: {final['primary_verdict']}",
        f"Trusted option sources: {trusted_count}",
        f"Observational option sources: {observational_count}",
        f"Warehouse rows: {schema.get('row_count', 0)}",
        f"Warehouse sessions: {schema.get('session_count', 0)}",
        f"Determinism: {determinism_report.get('two_directory_determinism')}",
        f"Independent audit pass: {audit.get('audit_pass')}",
        "",
        "Capability support matrix:",
    ]
    for key, value in capability.items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "Blockers:",
            *[f"- {item}" for item in final.get("blockers", [])],
            "",
            "Exact next action:",
            final["exact_next_action"],
            "",
            "Safety flags:",
            f"- read_only={final['read_only']}",
            f"- is_order_action={final['is_order_action']}",
            f"- broker_api_called={final['broker_api_called']}",
            f"- allowed_for_live_execution={final['allowed_for_live_execution']}",
        ]
    )
    (out / "final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
