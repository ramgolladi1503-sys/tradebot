#!/usr/bin/env python3
"""Validate option hypotheses derived only from frozen outcome-blind transitions.

Discovery authority is the outcome-blind campaign. This script does not search
thresholds, states, directions, or holding horizons. It validates five fixed
prefix -> next-state hypotheses on the first half of previously unopened
sessions and opens the final holdout only for at most one gated survivor.
Research-only; no paper or live authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_outcome_blind_pattern_observation_stage_v1 as observe

CAMPAIGN = "observed_transition_option_validation_v1"
OBSERVATION_SEMANTIC_SHA256 = "2667991a5880f5be826412478da6b870d417378442907b6f470f28723db84a44"
PRIMARY_HORIZON_MINUTES = 10
STRESS_FRICTION = 0.010
SEVERE_FRICTION = 0.015
COOLDOWN_MINUTES = 20
MAX_SIGNALS_PER_HYPOTHESIS_SESSION = 2
RANDOM_STATE = 20260730

HYPOTHESES: dict[str, dict[str, Any]] = {
    "negative_persistence_to_pe_shock": {
        "prefix": ("S0", "S0"),
        "expected_next_state": "S1",
        "option_type": "PE",
        "frozen_full_motif": "S0>S0>S1",
    },
    "positive_persistence_to_ce_shock": {
        "prefix": ("S3", "S3"),
        "expected_next_state": "S2",
        "option_type": "CE",
        "frozen_full_motif": "S3>S3>S2",
    },
    "bearish_shock_to_negative_persistence": {
        "prefix": ("S1", "S0"),
        "expected_next_state": "S0",
        "option_type": "PE",
        "frozen_full_motif": "S1>S0>S0",
    },
    "bullish_shock_to_positive_persistence": {
        "prefix": ("S2", "S3"),
        "expected_next_state": "S3",
        "option_type": "CE",
        "frozen_full_motif": "S2>S3>S3",
    },
    "failed_positive_interrupt_in_negative_regime": {
        "prefix": ("S0", "S3"),
        "expected_next_state": "S0",
        "option_type": "PE",
        "frozen_full_motif": "S0>S3>S0",
    },
}
NEGATIVE_CONTROLS = {
    "wing_flip_after_bearish_shock": {"prefix": ("S1", "S2"), "option_type": "CE"},
    "wing_flip_after_bullish_shock": {"prefix": ("S2", "S1"), "option_type": "PE"},
}


class CampaignError(RuntimeError):
    pass


@dataclass(frozen=True)
class Metrics:
    trades: int
    sessions: int
    mean_return: float | None
    median_return: float | None
    profit_factor: float | None
    bootstrap_ci_low: float | None
    remove_top_five_mean: float | None
    remove_top_five_profit_factor: float | None
    largest_winner_share: float | None
    largest_session_share: float | None
    positive_halves: int
    total_halves: int


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def semantic_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_timestamp(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        raise CampaignError(f"invalid timestamps: {int(parsed.isna().sum())}")
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise")
    return parsed.dt.tz_convert("Asia/Kolkata")


def priority(paths: list[Path], tokens: tuple[str, ...]) -> Path:
    candidates = sorted(set(path.resolve() for path in paths))
    if not candidates:
        raise CampaignError(f"no source candidates for {tokens}")
    return sorted(
        candidates,
        key=lambda path: (-sum(token in str(path) for token in tokens), len(str(path)), str(path)),
    )[0]


def resolve_option_sources(repo: Path) -> tuple[Path, Path]:
    root = repo / "research" / "local_evidence_consolidation_v1"
    inventory = priority(
        list(root.rglob("contract_inventory.parquet")),
        ("external_local_dirs", "tradebot-ml-evidence", "upstox-expired-options-v1", "manifests"),
    )
    return inventory, inventory.parent.parent


def resolve_contract_path(root: Path, relative: Any) -> Path:
    value = str(relative or "").strip()
    if not value:
        raise CampaignError("empty normalized option path")
    direct = root / value
    if direct.exists():
        return direct
    parts = Path(value).parts
    for position in range(len(parts)):
        candidate = root.joinpath(*parts[position:])
        if candidate.exists():
            return candidate
    matches = list(root.rglob(Path(value).name))
    if len(matches) == 1:
        return matches[0]
    raise CampaignError(f"cannot resolve option path: {value}")


class OptionPairStore:
    def __init__(self, inventory_path: Path, option_root: Path):
        inventory = pd.read_parquet(inventory_path).copy()
        required = {"expiry", "strike", "option_type", "normalized_1m_path"}
        missing = sorted(required - set(inventory.columns))
        if missing:
            raise CampaignError(f"contract inventory missing: {missing}")
        inventory["expiry"] = pd.to_datetime(inventory["expiry"], errors="coerce").dt.date
        inventory["strike"] = pd.to_numeric(inventory["strike"], errors="coerce")
        inventory["option_type"] = inventory["option_type"].astype(str).str.upper()
        inventory = inventory.dropna(subset=["expiry", "strike", "normalized_1m_path"])
        if "final_status" in inventory.columns:
            inventory = inventory[inventory["final_status"].isin(["VALID_COMPLETE", "VALID_1M_ONLY"])]
        pairs = inventory.pivot_table(
            index=["expiry", "strike"],
            columns="option_type",
            values="normalized_1m_path",
            aggfunc="first",
        ).reset_index()
        if "CE" not in pairs.columns or "PE" not in pairs.columns:
            raise CampaignError("no same-strike CE/PE pairs")
        self.pairs = pairs.dropna(subset=["CE", "PE"]).sort_values(
            ["expiry", "strike"], kind="mergesort"
        )
        self.option_root = option_root
        self.cache: dict[Path, pd.DataFrame] = {}

    def load(self, relative: str) -> pd.DataFrame:
        path = resolve_contract_path(self.option_root, relative)
        if path not in self.cache:
            frame = pd.read_parquet(path).copy()
            required = {"timestamp", "open", "high", "low", "close"}
            missing = sorted(required - set(frame.columns))
            if missing:
                raise CampaignError(f"{path} missing: {missing}")
            frame["timestamp"] = normalize_timestamp(frame["timestamp"])
            for column in ("open", "high", "low", "close", "volume", "open_interest"):
                if column not in frame.columns:
                    frame[column] = 0.0
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
            frame = frame.sort_values("timestamp", kind="mergesort").drop_duplicates(
                "timestamp", keep="last"
            )
            self.cache[path] = frame.set_index("timestamp", drop=False)
        return self.cache[path]

    def select(self, session: str, signal_timestamp: pd.Timestamp, spot: float) -> dict[str, Any] | None:
        session_date = pd.Timestamp(session).date()
        eligible = self.pairs[self.pairs["expiry"] >= session_date]
        if eligible.empty:
            return None
        expiry = eligible["expiry"].min()
        eligible = eligible[eligible["expiry"] == expiry].copy()
        eligible["distance"] = (eligible["strike"] - float(spot)).abs()
        eligible = eligible[eligible["distance"] <= 100.0]
        if eligible.empty:
            return None
        row = eligible.sort_values(["distance", "strike"], kind="mergesort").iloc[0]
        ce, pe = self.load(str(row["CE"])), self.load(str(row["PE"]))
        prior = signal_timestamp - pd.Timedelta(minutes=1)
        if prior not in ce.index or prior not in pe.index:
            return None
        return {
            "expiry": str(expiry),
            "strike": float(row["strike"]),
            "ce": ce,
            "pe": pe,
            "prior": prior,
        }


def stale_at_signal(frame: pd.DataFrame, timestamp: pd.Timestamp) -> bool:
    if "stale_price_flag" in frame.columns and timestamp in frame.index:
        value = frame.loc[timestamp, "stale_price_flag"]
        if isinstance(value, pd.Series):
            value = value.iloc[-1]
        if pd.notna(value) and bool(value):
            return True
    window = frame.loc[:timestamp].tail(3)
    return bool(
        len(window) == 3
        and window["close"].nunique() == 1
        and window["volume"].fillna(0).sum() == 0
    )


def load_observation_freeze(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("semantic_sha256") != OBSERVATION_SEMANTIC_SHA256:
        raise CampaignError(
            f"observation semantic hash mismatch: {payload.get('semantic_sha256')} != "
            f"{OBSERVATION_SEMANTIC_SHA256}"
        )
    if payload.get("principal_verdict") != "OUTCOME_BLIND_PATTERNS_FROZEN_FOR_HYPOTHESIS_FORMATION":
        raise CampaignError(f"unexpected observation verdict: {payload.get('principal_verdict')}")
    frozen = {record["motif"] for record in payload.get("frozen_patterns", [])}
    required = {spec["frozen_full_motif"] for spec in HYPOTHESES.values()}
    missing = sorted(required - frozen)
    if missing:
        raise CampaignError(f"hypotheses not grounded in frozen patterns: {missing}")
    return payload


def build_labeled_state(repo: Path, observation_payload: dict[str, Any]) -> pd.DataFrame:
    joint_path = observe.locate_by_sha(
        repo,
        "repaired_joint_underlying_option_warehouse.parquet",
        observe.JOINT_SHA256,
    )
    constituent_path = observe.locate_by_sha(
        repo,
        "constituent_index_5m.parquet",
        observe.CONSTITUENT_SHA256,
    )
    joint_state, _ = observe.load_joint_state(joint_path)
    constituent_state, _ = observe.load_constituent_state(constituent_path)
    state, _ = observe.join_states(joint_state, constituent_state)
    sessions = sorted(state["session_id"].unique().tolist())
    expected_unopened = list(observation_payload["unopened_sessions"])
    if not set(expected_unopened).issubset(set(sessions)):
        raise CampaignError("unopened session set is not contained in reconstructed state")

    observation_count = max(70, int(len(sessions) * 0.40))
    observation_sessions = sessions[:observation_count]
    observation = state[state["session_id"].isin(observation_sessions)].copy()

    surface_features = [
        "ce_velocity_median",
        "pe_velocity_median",
        "ce_acceleration_median",
        "pe_acceleration_median",
        "ce_positive_share",
        "pe_positive_share",
        "ce_velocity_iqr",
        "pe_velocity_iqr",
        "ce_volume_top3_share",
        "pe_volume_top3_share",
        "ce_oi_top3_share",
        "pe_oi_top3_share",
        "ce_log_volume",
        "pe_log_volume",
        "ce_log_oi",
        "pe_log_oi",
        "ce_log_premium",
        "pe_log_premium",
        "wing_velocity_gap",
        "joint_abs_velocity",
        "wing_acceleration_gap",
        "wing_breadth_gap",
        "ce_volume_share",
        "surface_joint_positive",
        "surface_joint_negative",
    ]
    constituent_features = [
        "index_ret1",
        "constituent_ret_median",
        "constituent_ret_mean",
        "constituent_ret_iqr",
        "constituent_up_share",
        "constituent_down_share",
        "constituent_abs_breadth",
        "constituent_top5_abs_share",
        "index_constituent_gap",
        "constituent_count",
    ]
    candidate_features = (
        observe.UNDERLYING_NUMERIC
        + observe.UNDERLYING_BOOL
        + surface_features
        + constituent_features
    )
    features, medians, scales = observe.robust_fit(observation, candidate_features)
    x_observation = observe.robust_transform(observation, features, medians, scales)
    model = KMeans(
        n_clusters=5,
        random_state=observe.RANDOM_STATE,
        n_init=20,
        max_iter=500,
    )
    model.fit(x_observation)
    state["state_id"] = [
        f"S{value}"
        for value in model.predict(observe.robust_transform(state, features, medians, scales))
    ]

    close_frame = pd.read_parquet(
        joint_path,
        columns=["session_id", "event_timestamp", "close"],
    )
    close_frame["session_id"] = close_frame["session_id"].astype(str)
    close_frame["event_timestamp"] = pd.to_datetime(
        close_frame["event_timestamp"], errors="coerce"
    )
    close_frame["close"] = pd.to_numeric(close_frame["close"], errors="coerce")
    close_consistency = close_frame.groupby(
        ["session_id", "event_timestamp"], observed=True
    )["close"].nunique(dropna=False)
    if int((close_consistency > 1).sum()) > 0:
        raise CampaignError("underlying close inconsistent across option rows")
    close_frame = (
        close_frame.groupby(["session_id", "event_timestamp"], observed=True)["close"]
        .first()
        .rename("index_close")
        .reset_index()
    )
    state = state.merge(
        close_frame,
        on=["session_id", "event_timestamp"],
        how="left",
        validate="one_to_one",
    )
    state = state[state["index_close"].gt(0)].copy()
    return state.sort_values(
        ["session_id", "event_timestamp"], kind="mergesort"
    ).reset_index(drop=True)


def split_unopened(sessions: list[str]) -> tuple[list[str], list[str]]:
    if len(sessions) < 60:
        raise CampaignError(f"insufficient unopened sessions: {len(sessions)}")
    cut = len(sessions) // 2
    return sessions[:cut], sessions[cut:]


def generate_signals(
    state: pd.DataFrame,
    sessions: list[str],
    hypotheses: dict[str, dict[str, Any]],
    split_name: str,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for session, group in (
        state[state["session_id"].isin(sessions)]
        .sort_values(["session_id", "event_timestamp"], kind="mergesort")
        .groupby("session_id", sort=False)
    ):
        group = group.reset_index(drop=True)
        for hypothesis_id, spec in hypotheses.items():
            prefix = tuple(spec["prefix"])
            emitted = 0
            last_signal: pd.Timestamp | None = None
            for position in range(len(prefix) - 1, len(group)):
                window = group.iloc[position - len(prefix) + 1 : position + 1]
                if tuple(window["state_id"].astype(str)) != prefix:
                    continue
                timestamps = pd.to_datetime(window["event_timestamp"]).tolist()
                gaps = [
                    (timestamps[index + 1] - timestamps[index]).total_seconds() / 60.0
                    for index in range(len(timestamps) - 1)
                ]
                if not all(0.0 < gap <= 6.0 for gap in gaps):
                    continue
                event_timestamp = pd.Timestamp(group.iloc[position]["event_timestamp"])
                if (
                    last_signal is not None
                    and (event_timestamp - last_signal).total_seconds() / 60.0
                    < COOLDOWN_MINUTES
                ):
                    continue
                next_state = None
                next_state_timestamp = None
                if position + 1 < len(group):
                    next_row = group.iloc[position + 1]
                    next_gap = (
                        pd.Timestamp(next_row["event_timestamp"]) - event_timestamp
                    ).total_seconds() / 60.0
                    if 0.0 < next_gap <= 6.0:
                        next_state = str(next_row["state_id"])
                        next_state_timestamp = pd.Timestamp(next_row["event_timestamp"])
                records.append(
                    {
                        "split": split_name,
                        "session": str(session),
                        "hypothesis_id": hypothesis_id,
                        "prefix": ">".join(prefix),
                        "expected_next_state": spec.get("expected_next_state"),
                        "actual_next_state": next_state,
                        "event_timestamp": event_timestamp,
                        "signal_timestamp": event_timestamp + pd.Timedelta(minutes=1),
                        "next_state_timestamp": next_state_timestamp,
                        "option_type": str(spec["option_type"]),
                        "index_close": float(group.iloc[position]["index_close"]),
                    }
                )
                last_signal = event_timestamp
                emitted += 1
                if emitted >= MAX_SIGNALS_PER_HYPOTHESIS_SESSION:
                    break
    return pd.DataFrame(records)


def replay_signals(
    store: OptionPairStore,
    signals: pd.DataFrame,
    delay_minutes: int = 0,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    if signals.empty:
        return pd.DataFrame()
    for _, signal in signals.sort_values(
        ["session", "signal_timestamp", "hypothesis_id"], kind="mergesort"
    ).iterrows():
        pair = store.select(
            str(signal["session"]),
            signal["signal_timestamp"],
            float(signal["index_close"]),
        )
        if pair is None:
            continue
        ce, pe, prior = pair["ce"], pair["pe"], pair["prior"]
        if stale_at_signal(ce, prior) or stale_at_signal(pe, prior):
            continue
        selected_type = str(signal["option_type"]).upper()
        selected = ce if selected_type == "CE" else pe
        mirror = pe if selected_type == "CE" else ce
        entry_timestamp = signal["signal_timestamp"] + pd.Timedelta(minutes=delay_minutes)
        exit_timestamp = entry_timestamp + pd.Timedelta(
            minutes=PRIMARY_HORIZON_MINUTES - 1
        )
        if entry_timestamp not in selected.index or entry_timestamp not in mirror.index:
            continue
        if exit_timestamp not in selected.index or exit_timestamp not in mirror.index:
            continue
        selected_entry = float(selected.loc[entry_timestamp, "open"])
        selected_exit = float(selected.loc[exit_timestamp, "close"])
        mirror_entry = float(mirror.loc[entry_timestamp, "open"])
        mirror_exit = float(mirror.loc[exit_timestamp, "close"])
        if min(selected_entry, selected_exit, mirror_entry, mirror_exit) <= 0:
            continue
        gross = selected_exit / selected_entry - 1.0
        mirror_gross = mirror_exit / mirror_entry - 1.0
        prior_zero_volume = bool(
            float(ce.loc[prior, "volume"]) <= 0
            or float(pe.loc[prior, "volume"]) <= 0
        )
        if prior_zero_volume:
            continue
        records.append(
            {
                **signal.to_dict(),
                "expiry": pair["expiry"],
                "strike": float(pair["strike"]),
                "entry_timestamp": entry_timestamp,
                "exit_timestamp": exit_timestamp,
                "selected_entry": selected_entry,
                "selected_exit": selected_exit,
                "mirror_entry": mirror_entry,
                "mirror_exit": mirror_exit,
                "gross_return": gross,
                "stress_return": gross - STRESS_FRICTION,
                "severe_return": gross - SEVERE_FRICTION,
                "mirror_gross_return": mirror_gross,
                "mirror_stress_return": mirror_gross - STRESS_FRICTION,
                "extra_entry_delay": delay_minutes,
                "prior_zero_volume": prior_zero_volume,
            }
        )
    return pd.DataFrame(records)


def profit_factor(values: np.ndarray) -> float | None:
    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()
    if losses > 0:
        return float(gains / losses)
    if gains > 0:
        return math.inf
    return None


def calculate_metrics(
    ledger: pd.DataFrame,
    column: str = "stress_return",
    trim: int = 5,
) -> Metrics:
    if ledger.empty or column not in ledger.columns:
        return Metrics(0, 0, None, None, None, None, None, None, None, None, 0, 0)
    working = ledger.copy()
    working["_return"] = pd.to_numeric(working[column], errors="coerce")
    working = working[working["_return"].notna()].copy()
    values = working["_return"].to_numpy(float)
    if len(values) == 0:
        return Metrics(0, 0, None, None, None, None, None, None, None, None, 0, 0)
    ordered = np.sort(values)
    trimmed = ordered[:-trim] if len(ordered) > trim else np.array([], dtype=float)
    samples = np.random.default_rng(RANDOM_STATE).choice(
        values, size=(5000, len(values)), replace=True
    ).mean(axis=1)
    positive = values[values > 0]
    winner_share = (
        float(positive.max() / positive.sum())
        if len(positive) and positive.sum() > 0
        else None
    )
    session_returns = working.groupby("session", observed=True)["_return"].sum()
    positive_sessions = session_returns[session_returns > 0]
    session_share = (
        float(positive_sessions.max() / positive_sessions.sum())
        if len(positive_sessions) and positive_sessions.sum() > 0
        else None
    )
    ordered_sessions = sorted(working["session"].astype(str).unique().tolist())
    halves = np.array_split(np.asarray(ordered_sessions, dtype=object), 2)
    half_means = [
        float(
            working[
                working["session"].astype(str).isin(part.tolist())
            ]["_return"].mean()
        )
        for part in halves
        if len(part)
    ]
    return Metrics(
        trades=len(values),
        sessions=int(working["session"].nunique()),
        mean_return=float(values.mean()),
        median_return=float(np.median(values)),
        profit_factor=profit_factor(values),
        bootstrap_ci_low=float(np.quantile(samples, 0.025)),
        remove_top_five_mean=float(trimmed.mean()) if len(trimmed) else None,
        remove_top_five_profit_factor=profit_factor(trimmed) if len(trimmed) else None,
        largest_winner_share=winner_share,
        largest_session_share=session_share,
        positive_halves=int(sum(value > 0 for value in half_means)),
        total_halves=len(half_means),
    )


def transition_evidence(
    signals: pd.DataFrame,
    state: pd.DataFrame,
    expected_state: str,
) -> dict[str, Any]:
    if signals.empty:
        return {
            "signals": 0,
            "evaluable_transitions": 0,
            "observed_transition_rate": None,
            "unconditional_next_state_rate": None,
            "transition_lift": None,
        }
    evaluable = signals[signals["actual_next_state"].notna()].copy()
    if evaluable.empty:
        return {
            "signals": len(signals),
            "evaluable_transitions": 0,
            "observed_transition_rate": None,
            "unconditional_next_state_rate": None,
            "transition_lift": None,
        }
    observed_rate = float((evaluable["actual_next_state"] == expected_state).mean())
    sessions = signals["session"].astype(str).unique().tolist()
    baseline_frame = state[state["session_id"].isin(sessions)].sort_values(
        ["session_id", "event_timestamp"], kind="mergesort"
    ).copy()
    baseline_frame["next_state"] = baseline_frame.groupby(
        "session_id", observed=True
    )["state_id"].shift(-1)
    baseline = baseline_frame["next_state"].dropna()
    baseline_rate = float((baseline == expected_state).mean()) if len(baseline) else None
    lift = observed_rate / baseline_rate if baseline_rate and baseline_rate > 0 else None
    return {
        "signals": len(signals),
        "evaluable_transitions": len(evaluable),
        "observed_transition_rate": observed_rate,
        "unconditional_next_state_rate": baseline_rate,
        "transition_lift": lift,
    }


def screen_hypothesis(
    hypothesis_id: str,
    signals: pd.DataFrame,
    primary: pd.DataFrame,
    delayed: pd.DataFrame,
    state: pd.DataFrame,
    forward: bool,
) -> dict[str, Any]:
    spec = HYPOTHESES[hypothesis_id]
    primary = primary[primary["hypothesis_id"] == hypothesis_id].copy()
    delayed = delayed[delayed["hypothesis_id"] == hypothesis_id].copy()
    metrics = calculate_metrics(primary, trim=3 if forward else 5)
    mirror = calculate_metrics(
        primary,
        column="mirror_stress_return",
        trim=3 if forward else 5,
    )
    delayed_metrics = calculate_metrics(delayed, trim=3 if forward else 5)
    transition = transition_evidence(
        signals[signals["hypothesis_id"] == hypothesis_id],
        state,
        str(spec["expected_next_state"]),
    )
    passed = bool(
        metrics.trades >= 20
        and metrics.sessions >= 15
        and (transition["transition_lift"] or 0.0) >= (1.10 if forward else 1.15)
        and (metrics.mean_return or 0.0) > 0.0
        and (metrics.median_return or -1.0) >= 0.0
        and (metrics.profit_factor or 0.0) >= (1.15 if forward else 1.20)
        and (metrics.bootstrap_ci_low or -1.0) > 0.0
        and (metrics.remove_top_five_mean or -1.0) > 0.0
        and (metrics.remove_top_five_profit_factor or 0.0)
        >= (1.00 if forward else 1.05)
        and metrics.positive_halves == 2
        and metrics.total_halves == 2
        and (
            metrics.largest_winner_share is None
            or metrics.largest_winner_share <= (0.30 if forward else 0.25)
        )
        and (
            metrics.largest_session_share is None
            or metrics.largest_session_share <= (0.30 if forward else 0.25)
        )
        and metrics.mean_return is not None
        and mirror.mean_return is not None
        and metrics.mean_return > mirror.mean_return
        and delayed_metrics.mean_return is not None
        and metrics.mean_return > delayed_metrics.mean_return
        and metrics.profit_factor is not None
        and delayed_metrics.profit_factor is not None
        and metrics.profit_factor >= delayed_metrics.profit_factor
    )
    return {
        "hypothesis_id": hypothesis_id,
        "spec": spec,
        "metrics": asdict(metrics),
        "mirror_metrics": asdict(mirror),
        "delayed_metrics": asdict(delayed_metrics),
        "transition_evidence": transition,
        "passed": passed,
    }


def select_survivor(records: list[dict[str, Any]]) -> str | None:
    passed = [record for record in records if record["passed"]]
    if not passed:
        return None
    ordered = sorted(
        passed,
        key=lambda record: (
            record["metrics"]["bootstrap_ci_low"] or -math.inf,
            record["metrics"]["profit_factor"] or -math.inf,
            record["transition_evidence"]["transition_lift"] or -math.inf,
            record["metrics"]["trades"],
            record["hypothesis_id"],
        ),
        reverse=True,
    )
    return str(ordered[0]["hypothesis_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--observation-dir",
        type=Path,
        default=Path("runtime/research/outcome_blind_pattern_observation_v1"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runtime/research/observed_transition_option_validation_v1"),
    )
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    observation_dir = (
        args.observation_dir
        if args.observation_dir.is_absolute()
        else repo / args.observation_dir
    )
    output = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    observation_payload = load_observation_freeze(
        observation_dir / "frozen_observed_patterns.json"
    )
    state = build_labeled_state(repo, observation_payload)
    unopened = list(observation_payload["unopened_sessions"])
    validation_sessions, holdout_sessions = split_unopened(unopened)
    inventory, option_root = resolve_option_sources(repo)
    store = OptionPairStore(inventory, option_root)

    contract = {
        "schema_version": 1,
        "campaign": CAMPAIGN,
        "observation_semantic_sha256": OBSERVATION_SEMANTIC_SHA256,
        "hypotheses": HYPOTHESES,
        "negative_controls": NEGATIVE_CONTROLS,
        "primary_horizon_minutes": PRIMARY_HORIZON_MINUTES,
        "stress_friction": STRESS_FRICTION,
        "severe_friction": SEVERE_FRICTION,
        "cooldown_minutes": COOLDOWN_MINUTES,
        "max_signals_per_hypothesis_session": MAX_SIGNALS_PER_HYPOTHESIS_SESSION,
        "validation_sessions": validation_sessions,
        "holdout_sessions": holdout_sessions,
        "selection_policy": (
            "at most one validation survivor selected by bootstrap lower bound, "
            "PF, structural lift, then count"
        ),
        "holdout_policy": "sealed unless a validation survivor passes every gate",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(output / "research_contract.json", contract)

    validation_signals = generate_signals(
        state,
        validation_sessions,
        HYPOTHESES,
        "validation",
    )
    validation_signals.to_csv(output / "validation_signal_ledger.csv", index=False)
    validation_primary = replay_signals(store, validation_signals, delay_minutes=0)
    validation_delayed = replay_signals(store, validation_signals, delay_minutes=1)
    validation_primary.to_csv(output / "validation_trade_ledger.csv", index=False)
    validation_delayed.to_csv(
        output / "validation_delayed_trade_ledger.csv", index=False
    )

    validation_records = [
        screen_hypothesis(
            hypothesis_id,
            validation_signals,
            validation_primary,
            validation_delayed,
            state,
            forward=False,
        )
        for hypothesis_id in HYPOTHESES
    ]
    selected = select_survivor(validation_records)
    stable_json(
        output / "validation_results.json",
        {
            "records": validation_records,
            "selected_survivor": selected,
            "holdout_authorized": selected is not None,
        },
    )

    control_signals = generate_signals(
        state,
        validation_sessions,
        NEGATIVE_CONTROLS,
        "validation_control",
    )
    control_ledger = replay_signals(store, control_signals, delay_minutes=0)
    control_ledger.to_csv(output / "negative_control_trade_ledger.csv", index=False)
    control_records = {
        control_id: asdict(
            calculate_metrics(
                control_ledger[control_ledger["hypothesis_id"] == control_id]
            )
        )
        for control_id in NEGATIVE_CONTROLS
    }
    stable_json(output / "negative_control_results.json", control_records)

    holdout_opened = False
    holdout_record: dict[str, Any] | None = None
    if selected is not None:
        holdout_opened = True
        selected_spec = {selected: HYPOTHESES[selected]}
        holdout_signals = generate_signals(
            state,
            holdout_sessions,
            selected_spec,
            "holdout",
        )
        holdout_primary = replay_signals(store, holdout_signals, delay_minutes=0)
        holdout_delayed = replay_signals(store, holdout_signals, delay_minutes=1)
        holdout_signals.to_csv(output / "holdout_signal_ledger.csv", index=False)
        holdout_primary.to_csv(output / "holdout_trade_ledger.csv", index=False)
        holdout_delayed.to_csv(
            output / "holdout_delayed_trade_ledger.csv", index=False
        )
        holdout_record = screen_hypothesis(
            selected,
            holdout_signals,
            holdout_primary,
            holdout_delayed,
            state,
            forward=True,
        )
        stable_json(output / "holdout_results.json", holdout_record)

    validation_pass_count = sum(int(record["passed"]) for record in validation_records)
    validation_trade_count = int(len(validation_primary))
    if selected is None:
        if validation_trade_count < 20:
            verdict = "INSUFFICIENT_TRANSITION_OCCURRENCE"
        else:
            verdict = "NO_OBSERVED_TRANSITION_OPTION_EDGE"
    elif holdout_record and holdout_record["passed"]:
        verdict = "VALIDATED_OBSERVED_TRANSITION_OPTION_EDGE"
    else:
        verdict = "OBSERVED_PATTERN_OPTION_TRANSLATION_FAILED"

    decision = {
        "principal_verdict": verdict,
        "validation_pass_count": validation_pass_count,
        "selected_survivor": selected,
        "holdout_opened": holdout_opened,
        "holdout_passed": bool(holdout_record and holdout_record["passed"]),
        "validation_sessions": len(validation_sessions),
        "holdout_sessions": len(holdout_sessions),
        "research_only": True,
        "allowed_for_live_execution": False,
        "claim_boundary": (
            "historical one-minute OHLC proxy with 1% premium-return friction; "
            "no bid/ask or live execution certification"
        ),
    }
    decision["semantic_sha256"] = semantic_hash(decision)
    stable_json(output / "final_decision.json", decision)

    lines = [
        "# Observed Transition Option Validation V1",
        "",
        f"Principal verdict: `{verdict}`",
        "",
        "The hypotheses were formed only after outcome-blind state transitions were frozen.",
        "",
        "## Validation",
        "",
    ]
    for record in validation_records:
        metrics = record["metrics"]
        transition = record["transition_evidence"]
        lines.append(
            f"- `{record['hypothesis_id']}`: passed={record['passed']}, "
            f"trades={metrics['trades']}, sessions={metrics['sessions']}, "
            f"mean_after_1pct={metrics['mean_return']}, PF={metrics['profit_factor']}, "
            f"transition_lift={transition['transition_lift']}."
        )
    lines.extend(
        [
            "",
            f"Selected survivor: `{selected}`.",
            f"Holdout opened: `{holdout_opened}`.",
            "",
            "Research only. No paper or live authorization.",
            "",
        ]
    )
    (output / "RESULT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
