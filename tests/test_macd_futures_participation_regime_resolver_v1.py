from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked
from research.macd_futures_participation_regime_v1.resolver import (
    EXPECTED_SIGNAL_MEAN_NET_6BPS,
    EXPECTED_SIGNAL_TRADES,
    resolve_canonical_macd_evidence,
)


def _write_root(base: Path, name: str, *, n: int = EXPECTED_SIGNAL_TRADES, mean: float = EXPECTED_SIGNAL_MEAN_NET_6BPS) -> Path:
    root = base / name
    root.mkdir(parents=True)
    signal = pd.DataFrame(
        {
            "trade_id": [f"T{i:03d}" for i in range(n)],
            "entry_timestamp": pd.date_range(
                "2024-08-01 10:00", periods=n, freq="D", tz="Asia/Kolkata"
            ),
            "net_6bps": [mean] * n,
        }
    )
    signal.to_csv(root / "MACD_SIGNAL_TRADE_PATH_DECOMPOSITION.csv", index=False)
    pd.DataFrame(
        {
            "replication_id": [1],
            "signal_trade_id": ["T000"],
            "signal_origin": ["2024-08-01 09:45:00+05:30"],
            "matched_placebo_origin": ["2024-08-01 11:00:00+05:30"],
        }
    ).to_csv(root / "MACD_MATCHED_PLACEBO_ASSIGNMENTS.csv", index=False)
    pd.DataFrame(
        {
            "replication_id": [1],
            "origin_timestamp": ["2024-08-01 11:00:00+05:30"],
            "net_6bps": [-1.0],
        }
    ).to_csv(root / "MACD_MATCHED_PLACEBO_PAYOFF_LEDGER.csv", index=False)
    return root


def test_resolver_accepts_exact_canonical_signature(tmp_path: Path):
    root = _write_root(
        tmp_path,
        "macd_path_dependent_matched_placebo_mechanism_test_v2_20260906T184607Z",
    )
    resolved = resolve_canonical_macd_evidence(tmp_path)
    assert resolved.root == root
    assert resolved.signal_trade_count == 148
    assert resolved.signal_mean_net_6bps == pytest.approx(8.0774)


def test_resolver_rejects_wrong_trade_count(tmp_path: Path):
    _write_root(
        tmp_path,
        "macd_path_dependent_matched_placebo_mechanism_test_v2_bad_count",
        n=147,
    )
    with pytest.raises(CampaignBlocked, match="CANONICAL_MACD_ROOT_NOT_RECONCILED"):
        resolve_canonical_macd_evidence(tmp_path)


def test_resolver_rejects_wrong_expectancy(tmp_path: Path):
    _write_root(
        tmp_path,
        "macd_path_dependent_matched_placebo_mechanism_test_v2_bad_mean",
        mean=8.50,
    )
    with pytest.raises(CampaignBlocked, match="CANONICAL_MACD_ROOT_NOT_RECONCILED"):
        resolve_canonical_macd_evidence(tmp_path)


def test_resolver_rejects_ambiguous_authority(tmp_path: Path):
    _write_root(
        tmp_path,
        "macd_path_dependent_matched_placebo_mechanism_test_v1_candidate_a",
    )
    _write_root(
        tmp_path,
        "macd_path_dependent_matched_placebo_mechanism_test_v2_candidate_b",
    )
    with pytest.raises(CampaignBlocked, match="CANONICAL_MACD_ROOT_AMBIGUOUS"):
        resolve_canonical_macd_evidence(tmp_path)


def test_resolver_rejects_missing_volume(tmp_path: Path):
    missing = tmp_path / "not-mounted"
    with pytest.raises(CampaignBlocked, match="VOLUMES_ROOT_MISSING"):
        resolve_canonical_macd_evidence(missing)
