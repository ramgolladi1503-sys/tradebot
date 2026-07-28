#!/usr/bin/env python3
"""Independent signal-membership oracle for the late-day CE rebound candidate.

Reads only causal columns from the preserved event universe. Rebuilds surface
features, chronological folds, prior-only thresholds and candidate selection
without importing the discovery implementation, then compares exact signal
identities with the committed V3 primary ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PRIOR_REL = Path(
    "research/local_evidence_consolidation_v1/worktrees/"
    "reverse-causal-option-expansion-v1/runtime_research/"
    "reverse_causal_option_expansion_v1"
)
EVENT_FILE = "event_universe_5m.parquet"
V3_LEDGER_REL = Path(
    "runtime/research/late_day_ce_inventory_rebound_v3/trade_ledger.csv"
)
OUT_REL = Path(
    "runtime/research/late_day_ce_inventory_rebound_v5_signal_oracle"
)
RESEARCH_REL = Path(
    "research/late_day_ce_inventory_rebound_v5_signal_oracle"
)

CAUSAL_COLUMNS = [
    "expired_instrument_key",
    "expiry",
    "option_type",
    "strike",
    "timestamp",
    "session",
    "minute_of_day",
    "days_to_expiry",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
    "entry_price_next_open",
    "prior_5m_return_pct",
    "prior_10m_range_pct",
    "prior_5m_volume_ratio",
]


def finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_causal_frame(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=CAUSAL_COLUMNS)
    for column in [
        "strike",
        "minute_of_day",
        "days_to_expiry",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_interest",
        "entry_price_next_open",
        "prior_5m_return_pct",
        "prior_10m_range_pct",
        "prior_5m_volume_ratio",
    ]:
        frame[column] = finite(frame[column])
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], errors="raise", utc=True
    )
    frame["session_id"] = frame["session"].astype(str)
    frame["expiry_id"] = frame["expiry"].astype(str)
    frame["option_type"] = frame["option_type"].astype(str).str.upper()
    frame = frame.sort_values(
        ["expired_instrument_key", "timestamp"], kind="mergesort"
    )

    instrument = frame.groupby(
        "expired_instrument_key", sort=False, observed=True
    )
    frame["previous_return"] = instrument["prior_5m_return_pct"].shift(1)
    frame["previous_volume_ratio"] = instrument[
        "prior_5m_volume_ratio"
    ].shift(1)
    frame["previous_open_interest"] = instrument["open_interest"].shift(1)
    frame["return_acceleration"] = (
        frame["prior_5m_return_pct"] - frame["previous_return"]
    )
    frame["oi_change_ratio"] = (
        frame["open_interest"] - frame["previous_open_interest"]
    ) / frame["previous_open_interest"].abs().clip(lower=1.0)

    frame["positive_weight"] = (
        frame["prior_5m_return_pct"].clip(lower=0).fillna(0)
        * np.log1p(frame["volume"].clip(lower=0).fillna(0))
    )
    frame["weighted_strike_numerator"] = (
        frame["strike"] * frame["positive_weight"]
    )
    keys = ["session_id", "timestamp", "expiry_id", "option_type"]
    surface = (
        frame.groupby(keys, sort=False, observed=True)
        .agg(
            surface_count=("expired_instrument_key", "size"),
            positive_weight_sum=("positive_weight", "sum"),
            weighted_strike_sum=("weighted_strike_numerator", "sum"),
        )
        .reset_index()
    )
    surface["weighted_strike"] = (
        surface["weighted_strike_sum"]
        / surface["positive_weight_sum"].replace(0, np.nan)
    )
    surface = surface.sort_values(
        ["session_id", "expiry_id", "option_type", "timestamp"],
        kind="mergesort",
    )
    chain = surface.groupby(
        ["session_id", "expiry_id", "option_type"],
        sort=False,
        observed=True,
    )
    surface["weighted_strike_delta"] = (
        surface["weighted_strike"]
        - chain["weighted_strike"].shift(1)
    )
    direction = np.where(surface["option_type"].eq("CE"), 1.0, -1.0)
    surface["directional_mass_shift"] = (
        surface["weighted_strike_delta"] * direction
    )
    frame = frame.merge(
        surface[
            keys + ["surface_count", "directional_mass_shift"]
        ],
        on=keys,
        how="left",
        validate="many_to_one",
    )

    mirror = frame[
        [
            "session_id",
            "timestamp",
            "expiry_id",
            "strike",
            "option_type",
            "prior_5m_return_pct",
        ]
    ].copy()
    mirror["option_type"] = mirror["option_type"].map(
        {"CE": "PE", "PE": "CE"}
    )
    mirror = mirror.rename(
        columns={"prior_5m_return_pct": "mirror_return"}
    )
    mirror = mirror.drop_duplicates(
        ["session_id", "timestamp", "expiry_id", "strike", "option_type"]
    )
    frame = frame.merge(
        mirror,
        on=[
            "session_id",
            "timestamp",
            "expiry_id",
            "strike",
            "option_type",
        ],
        how="left",
        validate="many_to_one",
    )
    frame["option_asymmetry"] = (
        frame["prior_5m_return_pct"] - frame["mirror_return"]
    )
    return frame.loc[frame["minute_of_day"] >= 585].copy()


def split_sessions(
    frame: pd.DataFrame,
) -> tuple[list[str], list[str]]:
    sessions = sorted(frame["session_id"].dropna().unique().tolist())
    cut = int(math.floor(len(sessions) * 0.75))
    return sessions[:cut], sessions[cut:]


def expanding_folds(
    research_sessions: list[str],
) -> list[tuple[list[str], list[str], str]]:
    initial = int(math.floor(len(research_sessions) * 0.40))
    blocks = [
        list(block)
        for block in np.array_split(
            np.asarray(research_sessions[initial:], dtype=object), 4
        )
        if len(block)
    ]
    result: list[tuple[list[str], list[str], str]] = []
    train_end = initial
    for index, testing in enumerate(blocks, start=1):
        result.append(
            (
                research_sessions[:train_end],
                testing,
                f"fold_{index}",
            )
        )
        train_end += len(testing)
    return result


def quantile(
    frame: pd.DataFrame,
    column: str,
    value: float,
    default: float = 0.0,
) -> float:
    clean = finite(frame[column]).dropna()
    return float(clean.quantile(value)) if not clean.empty else default


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "ret_p10": quantile(training, "prior_5m_return_pct", 0.10),
        "ret_p80": quantile(training, "prior_5m_return_pct", 0.80),
        "volume_p90": quantile(
            training, "prior_5m_volume_ratio", 0.90, 1.0
        ),
        "accel_p10": quantile(training, "return_acceleration", 0.10),
        "asym_p10": quantile(training, "option_asymmetry", 0.10),
    }


def select(
    frame: pd.DataFrame,
    cut: dict[str, float],
    sessions: list[str],
) -> pd.DataFrame:
    mask = (
        frame["option_type"].eq("CE")
        & (frame["minute_of_day"] >= 780)
        & (frame["minute_of_day"] <= 890)
        & (frame["prior_5m_return_pct"] <= cut["ret_p10"])
        & (frame["prior_5m_volume_ratio"] >= cut["volume_p90"])
        & (frame["return_acceleration"] <= cut["accel_p10"])
        & (frame["mirror_return"] >= cut["ret_p80"])
        & (frame["option_asymmetry"] <= cut["asym_p10"])
        & frame["entry_price_next_open"].between(
            30.0, 150.0, inclusive="both"
        )
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["session_id"].isin(sessions)
    )
    candidates = frame.loc[mask].copy()
    if candidates.empty:
        return candidates
    candidates["premium_distance"] = (
        candidates["entry_price_next_open"] - 150.0
    ).abs()
    candidates["extremity_score"] = (
        candidates["prior_5m_return_pct"].abs().fillna(0)
        + candidates["return_acceleration"].abs().fillna(0)
        + candidates["option_asymmetry"].abs().fillna(0)
        + candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.02
        * candidates["directional_mass_shift"].abs().fillna(0)
    )
    earliest = candidates.groupby(
        "session_id", observed=True
    )["timestamp"].transform("min")
    candidates = candidates.loc[
        candidates["timestamp"].eq(earliest)
    ]
    candidates = candidates.sort_values(
        [
            "session_id",
            "extremity_score",
            "premium_distance",
            "expired_instrument_key",
        ],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    return candidates.drop_duplicates("session_id", keep="first")


def identities(
    frame: pd.DataFrame,
    role: str,
    fold_id: str,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "ledger_role",
                "fold_id",
                "session_id",
                "timestamp",
                "expired_instrument_key",
            ]
        )
    result = frame[
        [
            "session_id",
            "timestamp",
            "expired_instrument_key",
        ]
    ].copy()
    result["ledger_role"] = role
    result["fold_id"] = fold_id
    return result[
        [
            "ledger_role",
            "fold_id",
            "session_id",
            "timestamp",
            "expired_instrument_key",
        ]
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    ledger_path = root / V3_LEDGER_REL
    out = root / OUT_REL
    research_dir = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    causal = build_causal_frame(event_path)
    research_sessions, holdout_sessions = split_sessions(causal)
    generated: list[pd.DataFrame] = []
    fold_details: list[dict[str, Any]] = []
    for training_sessions, testing_sessions, fold_id in expanding_folds(
        research_sessions
    ):
        training = causal.loc[
            causal["session_id"].isin(training_sessions)
        ]
        testing = causal.loc[
            causal["session_id"].isin(testing_sessions)
        ]
        cut = thresholds(training)
        selected = select(testing, cut, testing_sessions)
        generated.append(
            identities(
                selected,
                "research_oof_primary",
                fold_id,
            )
        )
        fold_details.append(
            {
                "fold_id": fold_id,
                "training_sessions": len(training_sessions),
                "testing_sessions": len(testing_sessions),
                "selected": len(selected),
                "thresholds": cut,
            }
        )

    final_cut = thresholds(
        causal.loc[causal["session_id"].isin(research_sessions)]
    )
    holdout = causal.loc[
        causal["session_id"].isin(holdout_sessions)
    ]
    holdout_selected = select(
        holdout,
        final_cut,
        holdout_sessions,
    )
    generated.append(
        identities(
            holdout_selected,
            "holdout_primary",
            "holdout",
        )
    )
    oracle = pd.concat(
        generated,
        ignore_index=True,
        sort=False,
    )
    oracle["timestamp"] = pd.to_datetime(
        oracle["timestamp"], errors="raise", utc=True
    )
    oracle["session_id"] = oracle["session_id"].astype(str)
    oracle["fold_id"] = oracle["fold_id"].astype(str)
    oracle = oracle.sort_values(
        [
            "ledger_role",
            "fold_id",
            "session_id",
            "timestamp",
            "expired_instrument_key",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    published = pd.read_csv(
        ledger_path,
        usecols=[
            "ledger_role",
            "fold_id",
            "session_id",
            "timestamp",
            "expired_instrument_key",
        ],
    )
    published = published.loc[
        published["ledger_role"].isin(
            ["research_oof_primary", "holdout_primary"]
        )
    ].copy()
    published["timestamp"] = pd.to_datetime(
        published["timestamp"], errors="raise", utc=True
    )
    published["session_id"] = published["session_id"].astype(str)
    published["fold_id"] = published["fold_id"].astype(str)
    published = published.sort_values(
        [
            "ledger_role",
            "fold_id",
            "session_id",
            "timestamp",
            "expired_instrument_key",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    keys = [
        "ledger_role",
        "fold_id",
        "session_id",
        "timestamp",
        "expired_instrument_key",
    ]
    comparison = oracle.merge(
        published,
        on=keys,
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    missing = comparison.loc[comparison["_merge"].eq("right_only")]
    extra = comparison.loc[comparison["_merge"].eq("left_only")]
    ordered_values_equal = oracle[keys].astype(str).equals(
        published[keys].astype(str)
    )
    exact = bool(
        len(oracle) == len(published)
        and missing.empty
        and extra.empty
    )
    verdict = (
        "PASS_INDEPENDENT_SIGNAL_MEMBERSHIP_ORACLE"
        if exact
        else "FAIL_INDEPENDENT_SIGNAL_MEMBERSHIP_ORACLE"
    )
    payload = {
        "principal_verdict": verdict,
        "exact_membership_match": exact,
        "ordered_values_equal_after_normalization": ordered_values_equal,
        "oracle_signals": len(oracle),
        "published_primary_signals": len(published),
        "missing_from_oracle": len(missing),
        "extra_in_oracle": len(extra),
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "folds": fold_details,
        "final_thresholds": final_cut,
        "event_source_sha256": file_sha256(event_path),
        "published_ledger_sha256": file_sha256(ledger_path),
        "outcome_bearing_ledger_opened": True,
        "outcome_columns_requested": False,
        "pnl_columns_requested": False,
        "outcome_values_used": False,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    payload["semantic_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    stable_json(out / "signal_membership_oracle.json", payload)
    oracle.to_csv(out / "oracle_signal_ledger.csv", index=False)
    comparison.to_csv(
        out / "signal_membership_comparison.csv",
        index=False,
    )
    (research_dir / "RESULT.md").write_text(
        "# Late-Day CE Inventory Rebound V5 Signal Oracle\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Oracle signals: `{len(oracle)}`\n\n"
        f"Published primary signals: `{len(published)}`\n\n"
        f"Missing from oracle: `{len(missing)}`\n\n"
        f"Extra in oracle: `{len(extra)}`\n\n"
        "The oracle requested identity columns only and did not use outcome or "
        "P&L values. No paper or live trading is authorized.\n",
        encoding="utf-8",
    )
    return 0 if exact else 5


if __name__ == "__main__":
    raise SystemExit(main())
