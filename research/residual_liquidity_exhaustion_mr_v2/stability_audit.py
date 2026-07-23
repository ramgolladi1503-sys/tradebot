from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

import numpy as np
import pandas as pd


DIMENSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overall", ()),
    ("symbol", ("target_symbol",)),
    ("symbol_side", ("target_symbol", "event_side")),
    ("symbol_time", ("target_symbol", "time_bucket")),
    ("symbol_magnitude", ("target_symbol", "magnitude_bucket")),
    ("symbol_volatility", ("target_symbol", "volatility_bucket")),
)

MAGNITUDE_ORDER = ("RZ_2_2P5", "RZ_2P5_3", "RZ_3_PLUS")
VOLATILITY_ORDER = ("VOL_LT_5BPS", "VOL_5_10BPS", "VOL_10_20BPS", "VOL_20BPS_PLUS")


@dataclass(frozen=True)
class StabilityAuditContract:
    horizons_minutes: tuple[int, ...] = (5, 15, 30, 60)
    primary_horizons_minutes: tuple[int, ...] = (15, 30)
    minimum_events: int = 40
    minimum_sessions: int = 30
    minimum_calendar_periods: int = 3
    minimum_events_per_calendar_period: int = 12
    sign_flip_permutations: int = 2000
    false_discovery_rate: float = 0.05
    random_seed: int = 20260723

    def validate(self) -> None:
        if not self.horizons_minutes:
            raise ValueError("at least one horizon is required")
        if not set(self.primary_horizons_minutes).issubset(self.horizons_minutes):
            raise ValueError("primary horizons must be included in horizons")
        if self.minimum_events <= 0 or self.minimum_sessions <= 0:
            raise ValueError("minimum counts must be positive")
        if self.minimum_calendar_periods <= 1:
            raise ValueError("minimum_calendar_periods must exceed one")
        if self.minimum_events_per_calendar_period <= 0:
            raise ValueError("minimum_events_per_calendar_period must be positive")
        if self.sign_flip_permutations <= 0:
            raise ValueError("sign_flip_permutations must be positive")
        if not 0 < self.false_discovery_rate < 1:
            raise ValueError("false_discovery_rate must be between zero and one")


def _required_columns(contract: StabilityAuditContract) -> set[str]:
    columns = {
        "event_time",
        "calendar_period",
        "target_symbol",
        "event_side",
        "time_bucket",
        "magnitude_bucket",
        "volatility_bucket",
        "exhaustion_confirmed",
    }
    for horizon in contract.horizons_minutes:
        columns.add(f"raw_reversion_bps_{horizon}m")
        columns.add(f"confirmed_reversion_bps_{horizon}m")
    return columns


def validate_event_ledger(
    events: pd.DataFrame,
    *,
    contract: StabilityAuditContract = StabilityAuditContract(),
) -> pd.DataFrame:
    contract.validate()
    missing = sorted(_required_columns(contract).difference(events.columns))
    if missing:
        raise ValueError(f"event ledger missing required columns: {missing}")
    if events.empty:
        raise ValueError("event ledger is empty")

    normalized = events.copy()
    normalized["event_time"] = pd.to_datetime(normalized["event_time"], errors="raise")
    if normalized["event_time"].isna().any():
        raise ValueError("event ledger contains null event_time")
    normalized["session_date"] = normalized["event_time"].dt.strftime("%Y-%m-%d")
    normalized["exhaustion_confirmed"] = normalized["exhaustion_confirmed"].astype(bool)

    metric_columns = [
        f"{mode}_reversion_bps_{horizon}m"
        for mode in ("raw", "confirmed")
        for horizon in contract.horizons_minutes
    ]
    for column in metric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized.sort_values(["event_time", "target_symbol"], kind="mergesort").reset_index(drop=True)


def _candidate_key(mode: str, dimension: str, columns: tuple[str, ...], values: tuple[object, ...]) -> str:
    parts = [mode, dimension]
    parts.extend(f"{column}={value}" for column, value in zip(columns, values))
    return "|".join(parts)


def _seed_for_key(base_seed: int, key: str, horizon: int) -> int:
    digest = hashlib.sha256(f"{base_seed}|{key}|{horizon}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def _session_sign_flip_p_value(
    frame: pd.DataFrame,
    *,
    metric: str,
    permutations: int,
    seed: int,
) -> tuple[float, float, int]:
    session_means = frame.groupby("session_date", sort=True)[metric].mean().dropna().to_numpy(float)
    if session_means.size == 0:
        return float("nan"), float("nan"), 0
    observed = float(session_means.mean())
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(permutations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=session_means.size, replace=True)
        null_mean = float(np.mean(session_means * signs))
        if null_mean >= observed:
            exceed += 1
    p_value = float((1 + exceed) / (1 + permutations))
    return observed, p_value, int(session_means.size)


def _bh_adjust(p_values: pd.Series) -> pd.Series:
    valid = p_values.dropna().astype(float)
    adjusted = pd.Series(np.nan, index=p_values.index, dtype=float)
    if valid.empty:
        return adjusted
    order = valid.sort_values(kind="mergesort").index.tolist()
    count = len(order)
    running = 1.0
    for reverse_rank, index in enumerate(reversed(order), start=1):
        rank = count - reverse_rank + 1
        value = min(running, float(valid.loc[index]) * count / rank)
        running = value
        adjusted.loc[index] = value
    return adjusted


def _period_stability(
    frame: pd.DataFrame,
    *,
    mode: str,
    contract: StabilityAuditContract,
) -> tuple[int, bool, dict[str, object]]:
    eligible: dict[str, object] = {}
    for period, period_frame in frame.groupby("calendar_period", sort=True):
        if len(period_frame) < contract.minimum_events_per_calendar_period:
            continue
        period_result: dict[str, object] = {"event_count": int(len(period_frame))}
        passes = True
        for horizon in contract.primary_horizons_minutes:
            metric = f"{mode}_reversion_bps_{horizon}m"
            values = period_frame[metric].dropna()
            mean = float(values.mean()) if not values.empty else float("nan")
            median = float(values.median()) if not values.empty else float("nan")
            positive_rate = float((values > 0).mean()) if not values.empty else float("nan")
            period_result[f"mean_{horizon}m"] = mean
            period_result[f"median_{horizon}m"] = median
            period_result[f"positive_rate_{horizon}m"] = positive_rate
            passes = passes and bool(mean > 0 and median > 0 and positive_rate > 0.5)
        period_result["passes"] = bool(passes)
        eligible[str(period)] = period_result
    period_count = len(eligible)
    stable = period_count >= contract.minimum_calendar_periods and all(
        bool(item["passes"]) for item in eligible.values()
    )
    return period_count, bool(stable), eligible


def build_stability_screen(
    events: pd.DataFrame,
    *,
    contract: StabilityAuditContract = StabilityAuditContract(),
) -> pd.DataFrame:
    ledger = validate_event_ledger(events, contract=contract)
    rows: list[dict[str, object]] = []

    for mode in ("raw", "confirmed"):
        mode_frame = ledger if mode == "raw" else ledger.loc[ledger["exhaustion_confirmed"]].copy()
        for dimension, columns in DIMENSIONS:
            if not columns:
                groups: Iterable[tuple[object, pd.DataFrame]] = [((), mode_frame)]
            else:
                groups = mode_frame.groupby(list(columns), dropna=False, sort=True)
            for raw_key, frame in groups:
                values = raw_key if isinstance(raw_key, tuple) else (raw_key,)
                key = _candidate_key(mode, dimension, columns, values)
                row: dict[str, object] = {
                    "candidate_key": key,
                    "mode": mode,
                    "dimension": dimension,
                    "event_count": int(len(frame)),
                    "session_count": int(frame["session_date"].nunique()),
                }
                for column, value in zip(columns, values):
                    row[column] = value

                descriptive_pass = True
                for horizon in contract.horizons_minutes:
                    metric = f"{mode}_reversion_bps_{horizon}m"
                    values_series = frame[metric].dropna()
                    mean = float(values_series.mean()) if not values_series.empty else float("nan")
                    median = float(values_series.median()) if not values_series.empty else float("nan")
                    positive_rate = (
                        float((values_series > 0).mean()) if not values_series.empty else float("nan")
                    )
                    row[f"mean_reversion_bps_{horizon}m"] = mean
                    row[f"median_reversion_bps_{horizon}m"] = median
                    row[f"positive_rate_{horizon}m"] = positive_rate
                    descriptive_pass = descriptive_pass and bool(
                        mean > 0 and median > 0 and positive_rate > 0.5
                    )

                count_pass = bool(
                    row["event_count"] >= contract.minimum_events
                    and row["session_count"] >= contract.minimum_sessions
                )
                row["count_gate_pass"] = count_pass
                row["all_horizon_descriptive_gate_pass"] = bool(descriptive_pass)

                period_count, calendar_pass, period_evidence = _period_stability(
                    frame,
                    mode=mode,
                    contract=contract,
                )
                row["eligible_calendar_period_count"] = period_count
                row["calendar_stability_gate_pass"] = calendar_pass
                row["calendar_period_evidence"] = period_evidence

                for horizon in contract.primary_horizons_minutes:
                    metric = f"{mode}_reversion_bps_{horizon}m"
                    observed, p_value, tested_sessions = _session_sign_flip_p_value(
                        frame,
                        metric=metric,
                        permutations=contract.sign_flip_permutations,
                        seed=_seed_for_key(contract.random_seed, key, horizon),
                    )
                    row[f"session_equal_weight_mean_{horizon}m"] = observed
                    row[f"sign_flip_p_value_{horizon}m"] = p_value
                    row[f"tested_session_count_{horizon}m"] = tested_sessions
                rows.append(row)

    screen = pd.DataFrame(rows)
    if screen.empty:
        return screen

    for horizon in contract.primary_horizons_minutes:
        p_column = f"sign_flip_p_value_{horizon}m"
        q_column = f"bh_q_value_{horizon}m"
        screen[q_column] = _bh_adjust(screen[p_column])

    return _apply_final_gates(screen, contract=contract)


def _adjacent_bucket(bucket: str, order: tuple[str, ...]) -> set[str]:
    if bucket not in order:
        return set()
    index = order.index(bucket)
    neighbors: set[str] = set()
    if index > 0:
        neighbors.add(order[index - 1])
    if index + 1 < len(order):
        neighbors.add(order[index + 1])
    return neighbors


def _apply_neighbor_gate(
    screen: pd.DataFrame,
    index: int,
    *,
    contract: StabilityAuditContract,
) -> bool:
    row = screen.loc[index]
    dimension = row["dimension"]
    if dimension not in {"symbol_magnitude", "symbol_volatility"}:
        return True
    bucket_column = "magnitude_bucket" if dimension == "symbol_magnitude" else "volatility_bucket"
    order = MAGNITUDE_ORDER if dimension == "symbol_magnitude" else VOLATILITY_ORDER
    neighbors = _adjacent_bucket(str(row[bucket_column]), order)
    if not neighbors:
        return False
    mask = (
        (screen["mode"] == row["mode"])
        & (screen["dimension"] == dimension)
        & (screen["target_symbol"] == row["target_symbol"])
        & (screen[bucket_column].isin(neighbors))
        & (screen["count_gate_pass"])
    )
    adjacent = screen.loc[mask]
    if adjacent.empty:
        return False
    for _, neighbor in adjacent.iterrows():
        if all(
            neighbor[f"mean_reversion_bps_{horizon}m"] > 0
            and neighbor[f"median_reversion_bps_{horizon}m"] > 0
            and neighbor[f"positive_rate_{horizon}m"] > 0.5
            for horizon in contract.primary_horizons_minutes
        ):
            return True
    return False


def _apply_final_gates(
    screen: pd.DataFrame,
    *,
    contract: StabilityAuditContract,
) -> pd.DataFrame:
    result = screen.copy()
    result["multiple_testing_gate_pass"] = True
    for horizon in contract.primary_horizons_minutes:
        result["multiple_testing_gate_pass"] &= (
            result[f"bh_q_value_{horizon}m"] <= contract.false_discovery_rate
        )
    result["neighbor_stability_gate_pass"] = [
        _apply_neighbor_gate(result, int(index), contract=contract) for index in result.index
    ]
    result["stable_candidate"] = (
        result["count_gate_pass"]
        & result["all_horizon_descriptive_gate_pass"]
        & result["calendar_stability_gate_pass"]
        & result["multiple_testing_gate_pass"]
        & result["neighbor_stability_gate_pass"]
    )
    return result.sort_values(
        ["stable_candidate", "dimension", "event_count", "candidate_key"],
        ascending=[False, True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def summarize_stability_screen(
    screen: pd.DataFrame,
    *,
    contract: StabilityAuditContract = StabilityAuditContract(),
) -> dict[str, object]:
    contract.validate()
    stable = screen.loc[screen["stable_candidate"]].copy() if not screen.empty else screen
    classification = (
        "DIAGNOSTIC_SEGMENTS_FOUND_REQUIRES_NEW_PREREGISTRATION_AND_UNSEEN_DATA"
        if not stable.empty
        else "NO_STABLE_RESIDUAL_MEAN_REVERSION_SEGMENT_FOUND"
    )
    return {
        "campaign_id": "RESIDUAL_LIQUIDITY_EXHAUSTION_MR_V2",
        "stage": "B_PATTERN_STABILITY_AUDIT",
        "classification": classification,
        "candidate_count_tested": int(len(screen)),
        "stable_candidate_count": int(len(stable)),
        "stable_candidate_keys": stable["candidate_key"].tolist() if not stable.empty else [],
        "strategy_created": False,
        "structural_edge_claim_allowed": False,
        "profitability_claim_allowed": False,
        "paper_live_allowed": False,
        "execution_allowed": False,
        "next_gate": (
            "FREEZE_A_NEW_CANDIDATE_EQUATION_ON_NEW_DATA_ONLY"
            if not stable.empty
            else "CLOSE_CANDLE_RESIDUAL_FORMULATION_AND_CONTINUE_DEPTH_DATA_ACQUISITION"
        ),
    }
