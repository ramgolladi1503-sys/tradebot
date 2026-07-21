from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.ml_strategy_discovery.contracts import DiscoveryConfig
from research.ml_strategy_discovery.dataset import build_discovery_dataset
from research.ml_strategy_discovery.upstox_source import (
    load_certified_upstox_underlying,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_certified_session(
    root: Path,
    *,
    session_date: str = "2026-01-05",
    declared_sha: str | None = None,
    logical_path: str | None = None,
) -> tuple[Path, Path]:
    logical = logical_path or (
        f"runtime/upstox_candidate_replay/{session_date.replace('-', '')}/"
        f"underlying/NIFTY_{session_date.replace('-', '')}.parquet"
    )
    source = root / logical
    source.parent.mkdir(parents=True, exist_ok=True)

    timestamps = pd.date_range(
        f"{session_date} 09:15:00",
        periods=375,
        freq="1min",
    )
    base = 22000.0 + np.linspace(0.0, 90.0, timestamps.size)
    close = base + np.sin(np.arange(timestamps.size) / 7.0)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": "NSE_INDEX|Nifty 50",
            "open": base,
            "high": np.maximum(base, close) + 2.0,
            "low": np.minimum(base, close) - 2.0,
            "close": close,
            "volume": np.zeros(timestamps.size, dtype=float),
        }
    )
    frame.to_parquet(source, index=False)
    actual_sha = _sha256(source)

    manifest = {
        "source_manifest_version": "v2",
        "record_count": 1,
        "records": [
            {
                "source_manifest_version": "v2",
                "source_record_id": "record-nifty-20260105",
                "record_index": 0,
                "session_date": session_date,
                "symbol": "NIFTY",
                "logical_path": logical,
                "actual_sha256": declared_sha or actual_sha,
                "byte_size": source.stat().st_size,
                "row_count": frame.shape[0],
            }
        ],
    }
    manifest_path = root / "docs/agent_reviews/source_manifest_v2.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    return source, manifest_path


def test_certified_adapter_reopens_hashes_and_conserves_rows(tmp_path: Path) -> None:
    _, manifest_path = _write_certified_session(tmp_path)
    bundle = load_certified_upstox_underlying(
        source_project_root=tmp_path,
        source_manifest_path=manifest_path,
        instrument="NIFTY",
    )

    assert bundle.bars.shape[0] == 375
    assert bundle.bars["timestamp"].iloc[0] == pd.Timestamp(
        "2026-01-05 09:15:00+05:30"
    )
    assert bundle.bars["timestamp"].iloc[-1] == pd.Timestamp(
        "2026-01-05 15:29:00+05:30"
    )
    assert bundle.manifest["record_count"] == 1
    assert bundle.manifest["row_count"] == 375
    assert bundle.manifest["timestamp_semantics"] == "START"
    assert bundle.manifest["read_only"] is True
    assert bundle.manifest["is_order_action"] is False
    assert bundle.manifest["broker_api_called"] is False


def test_certified_start_timestamp_becomes_bar_end_decision(tmp_path: Path) -> None:
    _, manifest_path = _write_certified_session(tmp_path)
    bundle = load_certified_upstox_underlying(
        source_project_root=tmp_path,
        source_manifest_path=manifest_path,
        instrument="NIFTY",
    )
    dataset = build_discovery_dataset(
        bundle.bars,
        config=DiscoveryConfig(
            instrument="NIFTY",
            timestamp_semantics="START",
            source_timezone="Asia/Kolkata",
            bar_interval_minutes=1,
            strict_bar_cadence=True,
            minimum_history_bars=40,
            barrier_horizon_bars=12,
            source_kind="CERTIFIED_UPSTOX_CANDIDATE_REPLAY_V2",
        ),
    )

    first = dataset.iloc[0]
    assert first["decision_timestamp"] == first["bar_end_timestamp"]
    assert first["decision_timestamp"] == first["bar_start_timestamp"] + pd.Timedelta(
        minutes=1
    )
    assert first["label_entry_timestamp"] == first["decision_timestamp"]
    assert first["label_terminal_timestamp"] > first["label_entry_timestamp"]
    assert first["source_logical_path"].startswith(
        "runtime/upstox_candidate_replay/"
    )
    assert first["source_sha256"]
    assert first["source_manifest_record_id"] == "record-nifty-20260105"


def test_certified_adapter_rejects_sha_mismatch(tmp_path: Path) -> None:
    _, manifest_path = _write_certified_session(
        tmp_path,
        declared_sha="0" * 64,
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_certified_upstox_underlying(
            source_project_root=tmp_path,
            source_manifest_path=manifest_path,
            instrument="NIFTY",
        )


def test_certified_adapter_rejects_path_escape_before_file_read(tmp_path: Path) -> None:
    _, manifest_path = _write_certified_session(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["logical_path"] = "../outside.parquet"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe source logical path"):
        load_certified_upstox_underlying(
            source_project_root=tmp_path,
            source_manifest_path=manifest_path,
            instrument="NIFTY",
        )


def test_certified_adapter_rejects_incomplete_session(tmp_path: Path) -> None:
    source, manifest_path = _write_certified_session(tmp_path)
    frame = pd.read_parquet(source).iloc[:-1]
    frame.to_parquet(source, index=False)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["actual_sha256"] = _sha256(source)
    payload["records"][0]["byte_size"] = source.stat().st_size
    payload["records"][0]["row_count"] = frame.shape[0]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="session is incomplete"):
        load_certified_upstox_underlying(
            source_project_root=tmp_path,
            source_manifest_path=manifest_path,
            instrument="NIFTY",
        )
