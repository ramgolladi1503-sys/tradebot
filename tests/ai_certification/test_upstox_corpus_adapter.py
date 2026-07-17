from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from core.ai_certification.upstox_corpus import build_upstox_corpus_manifest


def _ohlcv(volume: list[float], *, symbol: str = "NIFTY_F1") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-10T09:15:00+05:30", periods=len(volume), freq="min"),
            "symbol": [symbol] * len(volume),
            "open": [25000.0 + index for index in range(len(volume))],
            "high": [25001.0 + index for index in range(len(volume))],
            "low": [24999.0 + index for index in range(len(volume))],
            "close": [25000.5 + index for index in range(len(volume))],
            "volume": volume,
        }
    )


def test_positive_volume_future_is_vwap_eligible(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    _ohlcv([100, 120, 150]).to_parquet(root / "NIFTY_F1_20260710.parquet")

    manifest = build_upstox_corpus_manifest(root)

    assert manifest.summary["FUTURES_VOLUME_ELIGIBLE"] == 1
    assert manifest.entries[0].volume_sum == 370.0


def test_zero_volume_underlying_is_price_structure_only(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    _ohlcv([0, 0, 0], symbol="NIFTY").to_parquet(root / "underlying_NIFTY_20260710.parquet")

    manifest = build_upstox_corpus_manifest(root)

    entry = manifest.entries[0]
    assert entry.eligibility == "PRICE_STRUCTURE_ONLY"
    assert "truthful_positive_volume_unavailable" in entry.blockers


def test_quote_rows_are_option_replay_candidates(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-10T09:15:00+05:30", periods=3, freq="min"),
            "ltp": [100.0, 101.0, 102.0],
            "bid": [99.5, 100.5, 101.5],
            "ask": [100.5, 101.5, 102.5],
            "bid_qty": [50, 50, 50],
            "ask_qty": [60, 60, 60],
        }
    ).to_parquet(root / "NIFTY26JUL25000CE_quotes.parquet")

    manifest = build_upstox_corpus_manifest(root)

    assert manifest.entries[0].eligibility == "OPTION_QUOTE_REPLAY_CANDIDATE"


def test_zip_manifest_is_deterministic_and_rejects_traversal(tmp_path: Path):
    parquet = tmp_path / "future.parquet"
    _ohlcv([10, 20]).to_parquet(parquet)
    archive = tmp_path / "upstox.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(parquet, "NIFTY_F1_20260710.parquet")
        output.writestr("manifests/day.json", json.dumps({"provider": "upstox"}))
        output.writestr("../escape.json", "{}")

    first = build_upstox_corpus_manifest(archive)
    second = build_upstox_corpus_manifest(archive)

    assert first.to_dict() == second.to_dict()
    assert first.source_sha256
    invalid = [entry for entry in first.entries if entry.eligibility == "INVALID"]
    assert invalid and invalid[0].blockers == ("unsafe_archive_path",)


def test_positive_volume_without_future_identity_is_not_promoted(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    _ohlcv([10, 20], symbol="NIFTY").to_parquet(root / "NIFTY_20260710.parquet")

    manifest = build_upstox_corpus_manifest(root)

    entry = manifest.entries[0]
    assert entry.eligibility == "POSITIVE_VOLUME_IDENTITY_UNCONFIRMED"
    assert "futures_identity_unconfirmed" in entry.blockers
