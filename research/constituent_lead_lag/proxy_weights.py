"""Community proxy-weight validation for constituent lead-lag research."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .model import DataContractError

COMMUNITY_PROXY_LICENSE = "CC BY-NC-SA 4.0"
EXPECTED_DATASET_NAME = "Historical Nifty 50 Constituent Weights"
EXPECTED_DOI = "10.6084/m9.figshare.30217915"


def hash_file_full(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_and_validate_source_manifest(path: Path | str, *, raw_weights_path: Path | str | None = None) -> dict[str, Any]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text())
    dataset_name = str(payload.get("dataset_name") or payload.get("name") or "")
    doi = str(payload.get("doi") or "")
    license_value = str(payload.get("license") or payload.get("licence") or "")
    version = str(payload.get("version") or payload.get("version_or_updated_date") or payload.get("latest_reported_snapshot") or "")
    hashes = payload.get("sha256_by_file") or {}
    raw_hash = str(payload.get("raw_weights_sha256") or hashes.get("weights.csv") or "")
    if EXPECTED_DATASET_NAME not in dataset_name:
        raise DataContractError("proxy source manifest dataset name mismatch")
    if doi != EXPECTED_DOI:
        raise DataContractError("proxy source manifest DOI mismatch")
    if not version:
        raise DataContractError("proxy source manifest missing version")
    if COMMUNITY_PROXY_LICENSE not in license_value:
        raise DataContractError("proxy source manifest must declare CC BY-NC-SA 4.0")
    if raw_weights_path is not None:
        actual_hash = hash_file_full(raw_weights_path)
        if raw_hash != actual_hash:
            raise DataContractError("proxy source manifest raw weights hash mismatch")
        payload["validated_raw_weights_sha256"] = actual_hash
    elif not raw_hash:
        raise DataContractError("proxy source manifest missing raw weights hash")
    payload["source_manifest_sha256"] = hash_file_full(manifest_path)
    payload["validated_dataset_name"] = dataset_name
    payload["validated_doi"] = doi
    payload["validated_license"] = license_value
    payload["validated_version"] = version
    return payload


def audit_proxy_dataset(weights_path: Path | str, *, evaluation_end: str,
                        source_manifest_path: Path | str, raw_weights_path: Path | str) -> dict[str, Any]:
    weights = normalize_proxy_weights(pd.read_csv(weights_path))
    latest_snapshot = derive_latest_snapshot(weights)
    end = pd.Timestamp(evaluation_end).date()
    if end > latest_snapshot:
        raise DataContractError("evaluation end exceeds latest supported proxy snapshot")
    manifest = load_and_validate_source_manifest(source_manifest_path, raw_weights_path=raw_weights_path)
    return {
        "weights_path": str(weights_path),
        "weights_sha256": hash_file_full(weights_path),
        "raw_weights_path": str(raw_weights_path),
        "raw_weights_sha256": hash_file_full(raw_weights_path),
        "latest_raw_snapshot": latest_snapshot.isoformat(),
        "evaluation_end": end.isoformat(),
        "official_weight_gate_passed": False,
        "commercial_use_allowed": False,
        "allowed_for_live_execution": False,
        "source_manifest": manifest,
    }


def normalize_proxy_weights(raw: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "ticker": "constituent_symbol",
        "symbol": "constituent_symbol",
        "stock": "constituent_symbol",
        "date": "effective_from",
        "snapshot_date": "effective_from",
        "weight_pct": "weight",
        "percentage": "weight",
    }
    frame = raw.rename(columns={k: v for k, v in aliases.items() if k in raw.columns}).copy()
    if "index_symbol" not in frame:
        frame["index_symbol"] = "NIFTY"
    required = {"index_symbol", "constituent_symbol", "effective_from", "weight"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise DataContractError(f"proxy weights missing columns: {missing}")
    frame["index_symbol"] = frame["index_symbol"].astype(str).str.upper().str.strip()
    frame["constituent_symbol"] = frame["constituent_symbol"].astype(str).str.upper().str.strip()
    frame["effective_from"] = pd.to_datetime(frame["effective_from"], errors="coerce").dt.date
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce")
    if frame["effective_from"].isna().any() or frame["weight"].isna().any():
        raise DataContractError("proxy weights contain invalid dates or weights")
    if frame["weight"].max() > 1.02:
        frame["weight"] = frame["weight"] / 100.0
    if (frame["weight"] <= 0).any():
        raise DataContractError("proxy weights must be positive")
    return frame.sort_values(["index_symbol", "effective_from", "constituent_symbol"]).reset_index(drop=True)


def derive_latest_snapshot(weights: pd.DataFrame):
    return normalize_proxy_weights(weights)["effective_from"].max()


def derive_effective_intervals(weights: pd.DataFrame) -> pd.DataFrame:
    frame = normalize_proxy_weights(weights)
    rows: list[pd.DataFrame] = []
    for _, group in frame.groupby("index_symbol", sort=False):
        ordered = group.sort_values(["effective_from", "constituent_symbol"]).copy()
        snapshot_dates = sorted(ordered["effective_from"].unique())
        effective_to_by_snapshot = {
            snapshot_date: ((pd.Timestamp(snapshot_dates[index + 1]) - pd.Timedelta(days=1)).date()
                            if index + 1 < len(snapshot_dates) else None)
            for index, snapshot_date in enumerate(snapshot_dates)
        }
        ordered["effective_to"] = ordered["effective_from"].map(effective_to_by_snapshot)
        rows.append(ordered)
    out = pd.concat(rows, ignore_index=True) if rows else frame
    return out.sort_values(["index_symbol", "effective_from", "constituent_symbol"]).reset_index(drop=True)


def validate_normalized_proxy(weights: pd.DataFrame, *, evaluation_start: str, evaluation_end: str,
                              allow_community_reconstructed_proxy: bool = False) -> pd.DataFrame:
    if not allow_community_reconstructed_proxy:
        raise DataContractError("explicit community reconstructed proxy flag is required")
    start = pd.Timestamp(evaluation_start).date()
    end = pd.Timestamp(evaluation_end).date()
    latest_snapshot = derive_latest_snapshot(weights)
    if end > latest_snapshot:
        raise DataContractError("evaluation end exceeds latest supported proxy snapshot")
    frame = derive_effective_intervals(weights)
    if (frame["index_symbol"] != "NIFTY").any():
        raise DataContractError("community reconstructed proxy is NIFTY-only")
    active_to = frame["effective_to"].apply(
        lambda value: pd.isna(value) or pd.Timestamp(value).date() >= start
    )
    active = frame[(frame["effective_from"] <= end) & active_to]
    if active.empty:
        raise DataContractError("proxy has no active rows for evaluation window")
    return frame
