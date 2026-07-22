from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from research.structural_edge_campaign import (
    CampaignContract,
    CampaignContractError,
    HypothesisDevelopmentError,
    build_session_features,
    run_preregistered_development_screen,
)


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_ROOT = ROOT / "research" / "structural_edge_campaign"


def load_spec(name: str) -> tuple[dict, str]:
    path = CAMPAIGN_ROOT / "specs" / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    import hashlib

    return payload, hashlib.sha256(path.read_bytes()).hexdigest()


def make_bars(kind: str, sessions: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=sessions)
    rows: list[dict] = []
    previous_close = 10000.0
    for index, date in enumerate(dates):
        times = pd.date_range(
            f"{date.date()} 09:15",
            f"{date.date()} 15:29",
            freq="1min",
            tz="Asia/Kolkata",
        )
        signal = index >= 20 and index % 2 == 0
        direction = 1 if (index // 2) % 2 == 0 else -1
        if kind == "EOGF" and signal:
            session_open = previous_close + direction * 40.0
        else:
            session_open = previous_close + float(rng.normal(0.0, 2.0))
        prices = np.empty(len(times), dtype=float)
        prices[0] = session_open
        for minute in range(1, len(times)):
            prices[minute] = prices[minute - 1] + float(rng.normal(0.0, 0.7))

        if kind in {"HIM", "NOISE"} and signal:
            prices[:30] = np.linspace(
                session_open, session_open + direction * 35.0, 30
            )
            entry = (14 * 60 + 55) - (9 * 60 + 15)
            exit_ = (15 * 60 + 25) - (9 * 60 + 15)
            prices[30:entry] = np.linspace(
                prices[29], session_open + direction * 25.0, entry - 30
            )
            continuation = 15.0
            if kind == "NOISE" and (index // 2) % 2:
                continuation = -15.0
            prices[entry : exit_ + 1] = np.linspace(
                session_open + direction * 25.0,
                session_open + direction * (25.0 + continuation),
                exit_ - entry + 1,
            )
        elif kind == "EOGF" and signal:
            prices[:15] = np.linspace(
                session_open, session_open + direction * 12.0, 15
            )
            prices[15:30] = np.linspace(
                prices[14], session_open - direction * 5.0, 15
            )
            prices[30:61] = np.linspace(
                session_open - direction * 5.0,
                session_open - direction * 20.0,
                31,
            )
        else:
            for minute in range(1, 30):
                prices[minute] = session_open + float(rng.normal(0.0, 3.0))

        opens = prices
        closes = np.roll(prices, -1)
        closes[-1] = prices[-1]
        highs = np.maximum(opens, closes) + 0.2
        lows = np.minimum(opens, closes) - 0.2
        for timestamp, open_, high, low, close in zip(
            times, opens, highs, lows, closes, strict=True
        ):
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                }
            )
        previous_close = float(closes[-1])
    return pd.DataFrame(rows)


def run_screen(bars: pd.DataFrame, spec_name: str) -> dict:
    specification, spec_hash = load_spec(spec_name)
    return run_preregistered_development_screen(
        bars,
        specification=specification,
        frozen_spec_sha256=spec_hash,
        source_manifest_sha256="b" * 64,
        code_sha="c" * 40,
        bootstrap_iterations=200,
        permutation_iterations=200,
        seed=42,
    )


def test_campaign_contract_verifies_all_frozen_specs() -> None:
    contract = CampaignContract.load(
        CAMPAIGN_ROOT / "v1_campaign_contract.json"
    )
    assert [item.hypothesis_id for item in contract.hypotheses] == [
        "ML_V2_LONG",
        "ML_V2_SHORT",
        "HIM_30",
        "EOGF_30",
    ]


def test_campaign_contract_rejects_spec_byte_mutation(tmp_path: Path) -> None:
    copied = tmp_path / "campaign"
    shutil.copytree(CAMPAIGN_ROOT, copied)
    spec = copied / "specs" / "him_30.json"
    spec.write_text(spec.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(CampaignContractError, match="SHA-256 mismatch"):
        CampaignContract.load(copied / "v1_campaign_contract.json")


def test_him_pattern_can_freeze_only_through_registered_screen() -> None:
    result = run_screen(make_bars("HIM"), "him_30.json")
    assert result["verdict"] == "CANDIDATE_FROZEN"
    assert result["candidate_count"] == 1
    assert result["max_stat_fwer_pvalue"] <= 0.05
    assert result["future_mutation_oracle_passed"] is True


def test_eogf_pattern_can_freeze_only_through_registered_screen() -> None:
    result = run_screen(make_bars("EOGF"), "eogf_30.json")
    assert result["verdict"] == "CANDIDATE_FROZEN"
    assert result["candidate_count"] == 1
    assert result["max_stat_fwer_pvalue"] <= 0.05
    assert result["negative_controls_passed"] is True


def test_balanced_late_outcomes_do_not_freeze_him_candidate() -> None:
    result = run_screen(make_bars("NOISE"), "him_30.json")
    assert result["verdict"] == "NO_STABLE_CANDIDATE"
    assert result["candidate_count"] == 0
    assert result["candidate_bundle_hash"] is None


def test_post_outcome_mutation_cannot_change_signal_features() -> None:
    bars = make_bars("HIM", sessions=45)
    original = build_session_features(bars)
    mutated = bars.copy()
    final_date = mutated["timestamp"].dt.date.max()
    mask = (
        mutated["timestamp"].dt.date.eq(final_date)
        & (mutated["timestamp"].dt.time >= pd.Timestamp("15:26").time())
    )
    for column in ("open", "high", "low", "close"):
        mutated.loc[mask, column] = mutated.loc[mask, column] + 500.0
    changed = build_session_features(mutated)
    signal_columns = [
        "session_date",
        "opening_direction",
        "opening_move_prior_atr",
        "directional_efficiency",
        "gap_direction",
        "absolute_gap_prior_atr",
        "extension_prior_atr",
        "opening_reclaim_failure",
    ]
    pd.testing.assert_frame_equal(
        original[signal_columns],
        changed[signal_columns],
        check_exact=True,
    )


def test_duplicate_timestamps_fail_closed() -> None:
    bars = make_bars("HIM", sessions=20)
    duplicated = pd.concat([bars, bars.iloc[[0]]], ignore_index=True)
    with pytest.raises(HypothesisDevelopmentError, match="duplicate timestamps"):
        build_session_features(duplicated)
