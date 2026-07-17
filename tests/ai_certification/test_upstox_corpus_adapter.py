from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd

from core.ai_certification.upstox_corpus import build_upstox_corpus_manifest


def _ohlcv(volume: list[float], *, symbol: str = "NIFTY_F1") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-10T09:15:00+05:30",
                periods=len(volume),
                freq="min",
            ),
            "symbol": [symbol] * len(volume),
            "open": [25000.0 + index for index in range(len(volume))],
            "high": [25001.0 + index for index in range(len(volume))],
            "low": [24999.0 + index for index in range(len(volume))],
            "close": [25000.5 + index for index in range(len(volume))],
            "volume": volume,
        }
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_volume_and_contract_identity_drive_three_distinct_evidence_lanes(
    tmp_path: Path,
):
    root = tmp_path / "corpus"
    root.mkdir()
    source = root / "NIFTY_20260710.parquet"

    _ohlcv([0, 0, 0], symbol="NIFTY").to_parquet(source)
    zero_volume = build_upstox_corpus_manifest(root).entries[0]

    _ohlcv([100, 120, 150], symbol="NIFTY").to_parquet(source)
    unconfirmed = build_upstox_corpus_manifest(root).entries[0]

    source.rename(root / "NIFTY_F1_20260710.parquet")
    confirmed = build_upstox_corpus_manifest(root).entries[0]

    assert zero_volume.eligibility == "PRICE_STRUCTURE_ONLY"
    assert zero_volume.volume_sum == 0.0
    assert "truthful_positive_volume_unavailable" in zero_volume.blockers
    assert unconfirmed.eligibility == "POSITIVE_VOLUME_IDENTITY_UNCONFIRMED"
    assert unconfirmed.volume_sum == 370.0
    assert "futures_identity_unconfirmed" in unconfirmed.blockers
    assert confirmed.eligibility == "FUTURES_VOLUME_ELIGIBLE"
    assert confirmed.volume_sum == 370.0
    assert confirmed.instrument_identity == "filename_future_marker"


def test_quote_completeness_changes_replay_eligibility(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    source = root / "NIFTY26JUL25000CE_quotes.parquet"
    incomplete = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-07-10T09:15:00+05:30",
                periods=3,
                freq="min",
            ),
            "ltp": [100.0, 101.0, 102.0],
            "bid": [99.5, 100.5, 101.5],
            "ask": [100.5, 101.5, 102.5],
            "bid_qty": [50, 50, 50],
        }
    )
    incomplete.to_parquet(source)
    before = build_upstox_corpus_manifest(root).entries[0]

    complete = incomplete.assign(ask_qty=[60, 60, 60])
    complete.to_parquet(source)
    after = build_upstox_corpus_manifest(root).entries[0]

    assert before.eligibility == "TICK_QUOTE_CONTROL"
    assert after.eligibility == "OPTION_QUOTE_REPLAY_CANDIDATE"
    assert before.sha256 != after.sha256
    assert "ask_qty" in after.columns


def test_zip_scan_is_deterministic_read_only_and_blocks_parent_traversal(
    tmp_path: Path,
):
    parquet = tmp_path / "future.parquet"
    _ohlcv([10, 20]).to_parquet(parquet)
    archive = tmp_path / "upstox.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(parquet, "NIFTY_F1_20260710.parquet")
        output.writestr("manifests/day.json", json.dumps({"provider": "upstox"}))
        output.writestr("../escape.json", "{}")
    archive_hash_before = _sha256(archive)

    first = build_upstox_corpus_manifest(archive)
    second = build_upstox_corpus_manifest(archive)

    invalid_entry = next(
        entry for entry in first.entries if entry.eligibility == "INVALID"
    )
    futures_entry = next(
        entry
        for entry in first.entries
        if entry.eligibility == "FUTURES_VOLUME_ELIGIBLE"
    )
    assert first.to_dict() == second.to_dict()
    assert first.source_sha256 == archive_hash_before
    assert _sha256(archive) == archive_hash_before
    assert not (tmp_path / "escape.json").exists()
    assert invalid_entry.path == "../escape.json"
    assert invalid_entry.blockers == ("unsafe_archive_path",)
    assert futures_entry.path == "NIFTY_F1_20260710.parquet"
    assert futures_entry.volume_sum == 30.0


def test_missing_timestamp_is_rejected_then_recovers_when_repaired(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    source = root / "NIFTY_F1_20260710.parquet"
    broken = _ohlcv([100, 120]).drop(columns=["timestamp"])
    broken.to_parquet(source)
    rejected = build_upstox_corpus_manifest(root).entries[0]

    _ohlcv([100, 120]).to_parquet(source)
    repaired = build_upstox_corpus_manifest(root).entries[0]

    assert rejected.eligibility == "INVALID"
    assert rejected.timestamp_column is None
    assert "timestamp_missing" in rejected.blockers
    assert repaired.eligibility == "FUTURES_VOLUME_ELIGIBLE"
    assert repaired.timestamp_column == "timestamp"
