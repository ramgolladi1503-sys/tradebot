from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from research.constituent_lead_lag.model import DataContractError, StrategyThresholds, classify_state
from research.constituent_lead_lag.proxy_weights import (
    derive_effective_intervals,
    load_and_validate_source_manifest,
    hash_file_full,
    validate_normalized_proxy,
)
from scripts.audit_reconstructed_proxy_evidence import audit as oracle_audit
from scripts.build_proxy_fetch_campaign_manifest import build as build_manifest
from scripts.build_proxy_ticker_resolution import build as build_resolution
from scripts.normalize_upstox_v3_candles import normalize


def _raw(path: Path, symbol: str, start: str, candles: list[list[object]]) -> Path:
    payload = {"status": "success", "data": {"candles": candles}}
    out = path / f"{symbol}_{start}_{start}.json.gz"
    with gzip.open(out, "wt") as handle:
        json.dump(payload, handle)
    return out


def test_full_file_hash_changes_with_content(tmp_path: Path):
    p = tmp_path / "x.txt"
    p.write_text("a")
    first = hash_file_full(p)
    p.write_text("b")
    assert hash_file_full(p) != first


def test_campaign_allowlist_excludes_stale_files(tmp_path: Path):
    _raw(tmp_path, "NIFTY", "2024-01-02", [["2024-01-02T09:15:00+05:30", 1, 1, 1, 1, 0, 0]])
    _raw(tmp_path, "NIFTY", "2026-01-02", [["2026-01-02T09:15:00+05:30", 1, 1, 1, 1, 0, 0]])
    manifest = tmp_path / "fetch_manifest.json"
    rows = []
    for p in sorted(tmp_path.glob("*.json.gz")):
        parts = p.name.removesuffix(".json.gz").split("_")
        rows.append({"symbol": parts[0], "from_date": parts[1], "to_date": parts[2], "stored_file_sha256": hash_file_full(p), "instrument_key": "NSE_INDEX|Nifty 50"})
    manifest.write_text(json.dumps(rows))
    summary = build_manifest(tmp_path, tmp_path / "campaign", "2024-01-01", "2025-08-29", manifest)
    assert summary["raw_files_accepted"] == 1
    assert summary["raw_files_rejected"] == 1


def test_filename_is_not_symbol_authority_without_manifest(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    campaign = tmp_path / "campaign"
    _raw(raw, "NIFTY", "2024-01-02", [["2024-01-02T09:15:00+05:30", 10, 11, 9, 10, 0, 0]])
    manifest = tmp_path / "fetch_manifest.json"
    manifest.write_text(json.dumps([{
        "symbol": "NIFTY",
        "from_date": "2024-01-02",
        "to_date": "2024-01-02",
        "stored_file_sha256": hash_file_full(next(raw.glob("*.json.gz"))),
        "instrument_key": "NSE_INDEX|Nifty 50",
    }]))
    build_manifest(raw, campaign, "2024-01-01", "2025-08-29", manifest)
    accepted = json.loads((campaign / "manifests/accepted_raw_files.json").read_text())
    accepted[0]["symbol"] = "VERIFIED"
    (campaign / "manifests/accepted_raw_files.json").write_text(json.dumps(accepted))
    pd.DataFrame([{"proxy_ticker": "VERIFIED", "instrument_key": "NSE_EQ|X"}]).to_csv(campaign / "manifests/ticker_resolution.csv", index=False)
    report = normalize(campaign / "manifests/accepted_raw_files.json", campaign / "manifests/ticker_resolution.csv", "2024-01-01", "2025-08-29", campaign / "normalized")
    bars = pd.read_parquet(report["output_path"])
    assert set(bars["symbol"]) == {"VERIFIED"}


def test_raw_candle_shape_and_timezone_window_enforced(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    campaign = tmp_path / "campaign"
    raw_file = _raw(raw, "NIFTY", "2024-01-02", [
        ["2024-01-02T09:15:00+05:30", 10, 11, 9, 10, 0, 0],
        ["2024-01-02T09:17:00+05:30", 10, 11, 9, 10, 0, 0],
        ["2024-01-02T09:20:00+05:30", 10, 8, 9, 10, 0, 0],
        ["2024-01-02T09:25:00+05:30", 10, 11, 9],
    ])
    campaign.joinpath("manifests").mkdir(parents=True)
    accepted = [{
        "stored_path": str(raw_file),
        "sha256": hash_file_full(raw_file),
        "symbol": "NIFTY",
        "from_date": "2024-01-02",
        "to_date": "2024-01-02",
        "instrument_key": "NSE_INDEX|Nifty 50",
        "candle_count": 4,
    }]
    (campaign / "manifests/accepted_raw_files.json").write_text(json.dumps(accepted))
    pd.DataFrame([{"proxy_ticker": "NIFTY", "instrument_key": "NSE_INDEX|Nifty 50"}]).to_csv(campaign / "manifests/ticker_resolution.csv", index=False)
    report = normalize(campaign / "manifests/accepted_raw_files.json", campaign / "manifests/ticker_resolution.csv", "2024-01-01", "2025-08-29", campaign / "normalized")
    assert report["normalized_accepted"] == 1
    assert report["malformed"] == 2
    assert report["invalid_ohlc_quarantined"] == 1
    assert report["row_conservation_passed"] is True
    bars = pd.read_parquet(report["output_path"])
    assert str(bars.iloc[0]["timestamp"]).endswith("+00:00")
    assert bars.iloc[0]["session"] == "2024-01-02"


def test_proxy_flag_required_and_nifty_only():
    weights = pd.DataFrame([
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2024-01-01", "effective_to": None, "weight": 1.0},
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2025-08-31", "effective_to": None, "weight": 1.0},
    ])
    with pytest.raises(DataContractError, match="explicit community"):
        validate_normalized_proxy(weights, evaluation_start="2024-01-01", evaluation_end="2025-08-29")
    validated = validate_normalized_proxy(weights, evaluation_start="2024-01-01", evaluation_end="2025-08-29", allow_community_reconstructed_proxy=True)
    assert len(validated) == 2
    assert pd.isna(validated.iloc[-1]["effective_to"])
    bad = weights.assign(index_symbol="BANKNIFTY")
    with pytest.raises(DataContractError, match="NIFTY-only"):
        validate_normalized_proxy(bad, evaluation_start="2024-01-01", evaluation_end="2025-08-29", allow_community_reconstructed_proxy=True)


def test_global_snapshot_intervals_departure_reentry_and_absence():
    raw = pd.DataFrame([
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2024-01-01", "weight": 0.5},
        {"index_symbol": "NIFTY", "constituent_symbol": "B", "effective_from": "2024-01-01", "weight": 0.5},
        {"index_symbol": "NIFTY", "constituent_symbol": "B", "effective_from": "2024-02-01", "weight": 1.0},
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2024-03-01", "weight": 0.4},
        {"index_symbol": "NIFTY", "constituent_symbol": "B", "effective_from": "2024-03-01", "weight": 0.6},
    ])
    intervals = derive_effective_intervals(raw)
    jan_a = intervals[(intervals["constituent_symbol"] == "A") & (intervals["effective_from"].astype(str) == "2024-01-01")].iloc[0]
    mar_a = intervals[(intervals["constituent_symbol"] == "A") & (intervals["effective_from"].astype(str) == "2024-03-01")].iloc[0]
    assert str(jan_a["effective_to"]) == "2024-01-31"
    assert pd.isna(mar_a["effective_to"])
    assert "A" not in set(intervals[intervals["effective_from"].astype(str).eq("2024-02-01")]["constituent_symbol"])
    assert intervals.groupby("effective_from")["constituent_symbol"].nunique().to_dict() == {
        pd.Timestamp("2024-01-01").date(): 2,
        pd.Timestamp("2024-02-01").date(): 1,
        pd.Timestamp("2024-03-01").date(): 2,
    }


def test_source_manifest_required_wrong_doi_and_raw_hash(tmp_path: Path):
    raw_weights = tmp_path / "weights.csv"
    raw_weights.write_text("x\n")
    manifest = tmp_path / "manifest.json"
    payload = {
        "dataset_name": "Historical Nifty 50 Constituent Weights (20Y)",
        "doi": "wrong",
        "version_or_updated_date": "2025-08-31",
        "license": "CC BY-NC-SA 4.0",
        "sha256_by_file": {"weights.csv": hash_file_full(raw_weights)},
    }
    manifest.write_text(json.dumps(payload))
    with pytest.raises(DataContractError, match="DOI"):
        load_and_validate_source_manifest(manifest, raw_weights_path=raw_weights)
    payload["doi"] = "10.6084/m9.figshare.30217915"
    payload["sha256_by_file"]["weights.csv"] = "bad"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(DataContractError, match="raw weights hash"):
        load_and_validate_source_manifest(manifest, raw_weights_path=raw_weights)
    payload["sha256_by_file"]["weights.csv"] = hash_file_full(raw_weights)
    manifest.write_text(json.dumps(payload))
    assert load_and_validate_source_manifest(manifest, raw_weights_path=raw_weights)["validated_doi"] == "10.6084/m9.figshare.30217915"


def test_post_latest_snapshot_rejected():
    weights = pd.DataFrame([
        {"index_symbol": "NIFTY", "constituent_symbol": "A", "effective_from": "2024-01-01", "effective_to": None, "weight": 1.0},
    ])
    with pytest.raises(DataContractError, match="latest supported"):
        validate_normalized_proxy(weights, evaluation_start="2024-01-01", evaluation_end="2025-09-01", allow_community_reconstructed_proxy=True)


def test_state_reason_ownership_and_predicates():
    side, reason = classify_state(
        basket_return_5m_bps=10,
        basket_return_10m_bps=10,
        lead_gap_z=1.0,
        participation=0.9,
        weighted_breadth=0.9,
        dispersion_percentile=0.1,
        catch_up_ratio=0.1,
        range_consumed=0.1,
        weight_coverage=1.0,
        thresholds=StrategyThresholds(),
    )
    assert side == "NONE"
    assert reason == "frozen_entry_conditions_not_met"


def test_theoretical_state_bound_and_oracle_tamper_detection(tmp_path: Path):
    bars = pd.DataFrame([
        {"timestamp": "2024-01-02T03:45:00Z", "session": "2024-01-02", "symbol": "NIFTY", "open": 1, "high": 1, "low": 1, "close": 1},
    ])
    bars_path = tmp_path / "bars.parquet"
    bars.to_parquet(bars_path, index=False)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    pd.DataFrame([{"session": "2024-01-02", "side": "NONE", "reason": "insufficient_lead_gap_history"}]).to_parquet(eval_dir / "signal_states_weighted.parquet", index=False)
    pd.DataFrame().to_parquet(eval_dir / "signal_states_unweighted.parquet", index=False)
    pd.DataFrame().to_parquet(eval_dir / "matched_control.parquet", index=False)
    report = oracle_audit(eval_dir, bars_path, tmp_path / "oracle")
    assert report["verdict"] == "FAIL"
    assert report["state_rows"] <= report["sessions"] * 10


def test_filename_only_authority_fails(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _raw(raw, "NIFTY", "2024-01-02", [["2024-01-02T09:15:00+05:30", 1, 1, 1, 1, 0, 0]])
    manifest = tmp_path / "fetch_manifest.json"
    manifest.write_text("[]")
    summary = build_manifest(raw, tmp_path / "campaign", "2024-01-01", "2025-08-29", manifest)
    assert summary["raw_files_accepted"] == 0
    rejected = json.loads((tmp_path / "campaign/manifests/rejected_raw_files.json").read_text())
    assert "missing_authoritative_ownership" in rejected[0]["reject_reasons"]


def test_master_missing_fails(tmp_path: Path):
    accepted = tmp_path / "accepted.json"
    accepted.write_text("[]")
    with pytest.raises(FileNotFoundError):
        build_resolution(accepted, tmp_path / "missing.json.gz", tmp_path)
