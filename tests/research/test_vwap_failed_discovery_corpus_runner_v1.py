from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research.vwap_failed_discovery_hypothesis_v1.run_corpus import (
    load_sessions,
    run,
    sha256_file,
)

IST = ZoneInfo("Asia/Kolkata")


def _write_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("timestamp", "open", "high", "low", "close", "volume"),
        )
        writer.writeheader()
        for day_offset in range(2):
            start = datetime(2026, 1, 5 + day_offset, 9, 15, tzinfo=IST)
            for minute in range(40):
                close = 100.0 + 0.02 * minute + 0.01 * (minute % 3)
                writer.writerow(
                    {
                        "timestamp": (start + timedelta(minutes=minute)).isoformat(),
                        "open": close,
                        "high": close + 0.2,
                        "low": close - 0.2,
                        "close": close,
                        "volume": 1000 + minute,
                    }
                )


def test_csv_loader_preserves_two_sessions(tmp_path: Path) -> None:
    path = tmp_path / "futures.csv"
    _write_csv(path)
    sessions = load_sessions(path)
    assert len(sessions) == 2
    assert all(len(bars) == 40 for bars in sessions.values())


def test_runner_is_sha_bound_and_dev_only_in_claims(tmp_path: Path) -> None:
    path = tmp_path / "futures.csv"
    _write_csv(path)
    digest = sha256_file(path)
    report = run(
        path,
        expected_sha256=digest,
        partition="DEV",
        known_partial_corpus=False,
    )
    assert report["partition"] == "DEV"
    assert report["input"]["sha256"] == digest
    assert report["claim_boundary"] == {
        "strategy_tested": False,
        "option_data_used": False,
        "paper_eligibility": False,
        "live_eligibility": False,
        "robust_support_possible_from_this_run": False,
    }
    assert report["preliminary_hypothesis_verdict"] in {
        "REJECTED",
        "INCONCLUSIVE",
        "SUPPORTED",
    }


def test_runner_rejects_wrong_hash(tmp_path: Path) -> None:
    path = tmp_path / "futures.csv"
    _write_csv(path)
    with pytest.raises(ValueError, match="INPUT_SHA256_MISMATCH"):
        run(
            path,
            expected_sha256="0" * 64,
            partition="DEV",
            known_partial_corpus=False,
        )


def test_runner_rejects_symlink(tmp_path: Path) -> None:
    path = tmp_path / "futures.csv"
    _write_csv(path)
    link = tmp_path / "linked.csv"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="REGULAR_INPUT_FILE_REQUIRED"):
        run(
            link,
            expected_sha256=None,
            partition="DEV",
            known_partial_corpus=False,
        )
