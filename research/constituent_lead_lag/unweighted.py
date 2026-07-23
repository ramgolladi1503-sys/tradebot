"""Research-only unweighted constituent-breadth lead-lag lane."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .bar_grid import exact_bar_window, symbols_with_exact_window
from .model import (
    DataContractError,
    TradeOutcome,
    evaluate_signals_with_entry_delay,
    summarize_outcomes,
    validate_bars,
)

REQUIRED_UNIVERSE_COLUMNS = {"index_symbol", "constituent_symbol", "effective_from"}
DEFAULT_DECISION_TIMES = ("10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:15")


@dataclass(frozen=True)
class UnweightedThresholds:
    z_entry: float = 2.0
    participation_min: float = 0.70
    breadth_abs_min: float = 0.40
    catch_up_ratio_max: float = 0.60
    dispersion_percentile_max: float = 0.80
    range_consumed_max: float = 0.60
    minimum_constituent_coverage: float = 0.80
    minimum_constituent_count: int = 5
    minimum_history_sessions: int = 20
    assumed_round_trip_cost_bps: float = 5.0
    max_hold_minutes: int = 20
    stop_fraction_of_median_30m_move: float = 0.35
    reward_risk: float = 1.50


@dataclass(frozen=True)
class UnweightedSignalState:
    index_symbol: str
    session: str
    decision_time: str
    decision_timestamp: str
    side: str
    reason: str
    basket_return_5m_bps: float
    basket_return_10m_bps: float
    median_constituent_return_5m_bps: float
    median_constituent_return_10m_bps: float
    index_return_5m_bps: float
    index_return_10m_bps: float
    lead_gap_bps: float
    lead_gap_z: float
    participation: float
    breadth: float
    dispersion_bps: float
    dispersion_percentile: float
    catch_up_ratio: float
    range_consumed: float
    constituents_expected: int
    constituents_available: int
    constituent_coverage: float
    rolling_median_30m_move_bps: float
    missing_constituents: tuple[str, ...] = ()
    research_lane: str = "UNWEIGHTED_CONSTITUENT_BREADTH"
    research_only: bool = True
    allowed_for_live_execution: bool = False
    broker_api_called: bool = False
    is_order_action: bool = False

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["missing_constituents"] = list(self.missing_constituents)
        return payload


def _to_session_date(value: object) -> date:
    return pd.Timestamp(value).date()


def validate_universe(universe: pd.DataFrame, minimum_constituent_count: int = 5) -> pd.DataFrame:
    missing = sorted(REQUIRED_UNIVERSE_COLUMNS - set(universe.columns))
    if missing:
        raise DataContractError(f"universe missing columns: {missing}")
    out = universe.copy()
    out["index_symbol"] = out["index_symbol"].astype(str).str.upper().str.strip()
    out["constituent_symbol"] = out["constituent_symbol"].astype(str).str.upper().str.strip()
    out["effective_from"] = pd.to_datetime(out["effective_from"], errors="coerce").dt.date
    if out["effective_from"].isna().any():
        raise DataContractError("universe contains invalid effective_from values")
    out["effective_to"] = pd.to_datetime(out.get("effective_to"), errors="coerce").dt.date if "effective_to" in out else pd.NaT
    if (out["index_symbol"] == out["constituent_symbol"]).any():
        raise DataContractError("index symbol cannot be a constituent of itself")
    if out.duplicated(["index_symbol", "constituent_symbol", "effective_from"], keep=False).any():
        raise DataContractError("duplicate point-in-time constituent-universe keys")
    counts = out.groupby(["index_symbol", "effective_from"])["constituent_symbol"].nunique()
    too_small = counts[counts < minimum_constituent_count]
    if len(too_small):
        raise DataContractError(f"universe snapshots below minimum constituent count {minimum_constituent_count}: {too_small.to_dict()}")
    return out.sort_values(["index_symbol", "effective_from", "constituent_symbol"]).reset_index(drop=True)


def select_universe_snapshot(universe: pd.DataFrame, index_symbol: str, session: object) -> pd.DataFrame:
    session_date = _to_session_date(session)
    candidates = universe[(universe["index_symbol"] == index_symbol.upper()) & (universe["effective_from"] <= session_date)]
    if candidates.empty:
        raise DataContractError(f"no point-in-time constituent universe for {index_symbol} on {session_date}")
    effective = candidates["effective_from"].max()
    snapshot = candidates[candidates["effective_from"] == effective].copy()
    snapshot = snapshot[snapshot["effective_to"].apply(lambda value: pd.isna(value) or value >= session_date)]
    if snapshot.empty:
        raise DataContractError(f"constituent universe snapshot expired for {index_symbol} on {session_date}")
    return snapshot


def classify_unweighted_state(*, basket_return_5m_bps: float, basket_return_10m_bps: float,
                              lead_gap_z: float, participation: float, breadth: float,
                              dispersion_percentile: float, catch_up_ratio: float,
                              range_consumed: float, constituent_coverage: float,
                              thresholds: UnweightedThresholds) -> tuple[str, str]:
    if constituent_coverage < thresholds.minimum_constituent_coverage:
        return "NONE", "insufficient_constituent_coverage"
    if dispersion_percentile > thresholds.dispersion_percentile_max:
        return "NONE", "dispersion_too_high"
    if catch_up_ratio > thresholds.catch_up_ratio_max:
        return "NONE", "index_already_caught_up"
    if range_consumed > thresholds.range_consumed_max:
        return "NONE", "index_range_already_consumed"
    if (lead_gap_z >= thresholds.z_entry and basket_return_5m_bps > 0 and basket_return_10m_bps > 0
            and participation >= thresholds.participation_min and breadth >= thresholds.breadth_abs_min):
        return "LONG", "unweighted_constituents_lead_index_up"
    if (lead_gap_z <= -thresholds.z_entry and basket_return_5m_bps < 0 and basket_return_10m_bps < 0
            and participation >= thresholds.participation_min and breadth <= -thresholds.breadth_abs_min):
        return "SHORT", "unweighted_constituents_lead_index_down"
    return "NONE", "frozen_unweighted_entry_conditions_not_met"


def _percentile_rank(history: Sequence[float], value: float) -> float:
    if not history:
        return 0.5
    array = np.asarray(history, dtype=float)
    return float((np.sum(array <= value) + 1) / (len(array) + 1))


def _session_median_abs_30m_move(index_day: pd.DataFrame) -> float | None:
    closes = index_day.set_index("timestamp")["close"].sort_index()
    values = [abs((float(closes.loc[ts + pd.Timedelta(minutes=30)]) / float(start) - 1.0) * 10_000.0)
              for ts, start in closes.items() if ts + pd.Timedelta(minutes=30) in closes.index]
    return float(np.median(values)) if values else None


def generate_unweighted_signal_states(bars: pd.DataFrame, universe: pd.DataFrame, index_symbol: str,
                                      decision_times: Iterable[str] = DEFAULT_DECISION_TIMES,
                                      thresholds: UnweightedThresholds = UnweightedThresholds()) -> list[UnweightedSignalState]:
    clean_bars = validate_bars(bars)
    clean_universe = validate_universe(universe, thresholds.minimum_constituent_count)
    index_symbol = index_symbol.upper()
    decision_times = tuple(decision_times)
    history_gap = {t: [] for t in decision_times}
    history_dispersion = {t: [] for t in decision_times}
    prior_30m_moves: list[float] = []
    results: list[UnweightedSignalState] = []

    for session, day in clean_bars.groupby("session", sort=True):
        day_by_symbol = {symbol: group.sort_values("timestamp") for symbol, group in day.groupby("symbol", sort=False)}
        index_day = day_by_symbol.get(index_symbol, pd.DataFrame())
        if index_day.empty:
            raise DataContractError(f"missing index bars for {index_symbol} on {session}")
        snapshot = select_universe_snapshot(clean_universe, index_symbol, session)
        expected_symbols = tuple(snapshot["constituent_symbol"].astype(str))
        expected_count = len(expected_symbols)

        for decision_time in decision_times:
            cutoff = pd.Timestamp(f"{session} {decision_time}", tz="Asia/Kolkata").tz_convert("UTC")
            index_window, index_missing = exact_bar_window(index_day, cutoff)
            if index_window is None:
                raise DataContractError(f"index exact return grid missing for {session} {decision_time}: {list(index_missing)}")
            available, missing = symbols_with_exact_window(day_by_symbol, expected_symbols, cutoff)
            r5s = np.asarray([window.return_5m_bps for window in available.values()], dtype=float)
            r10s = np.asarray([window.return_10m_bps for window in available.values()], dtype=float)
            available_count = len(available)
            coverage = available_count / expected_count if expected_count else 0.0
            history_ready = len(history_gap[decision_time]) >= thresholds.minimum_history_sessions
            median_30m = float(np.median(prior_30m_moves[-20:])) if prior_30m_moves else 0.0
            open_price = float(index_day.iloc[0]["open"])
            open_move = abs((index_window.close_t / open_price - 1.0) * 10_000.0)
            range_consumed = open_move / median_30m if median_30m > 1e-9 else 0.0

            if available_count == 0:
                basket5 = basket10 = median5 = median10 = gap = z = participation = breadth = dispersion = 0.0
                dispersion_pct = 0.5
                catch_up = float("inf")
                side, reason = "NONE", "insufficient_constituent_coverage"
            else:
                basket5, basket10 = float(np.mean(r5s)), float(np.mean(r10s))
                median5, median10 = float(np.median(r5s)), float(np.median(r10s))
                gap = basket5 - index_window.return_5m_bps
                if history_ready:
                    hist = np.asarray(history_gap[decision_time][-thresholds.minimum_history_sessions:], dtype=float)
                    std = float(np.std(hist, ddof=1))
                    z = (gap - float(np.mean(hist))) / std if std > 1e-9 else 0.0
                else:
                    z = 0.0
                direction = 1.0 if basket5 > 0 else -1.0 if basket5 < 0 else 0.0
                participation = float(np.mean(np.sign(r5s) == direction)) if direction else 0.0
                breadth = float(np.mean(np.sign(r5s)))
                dispersion = float(np.std(r5s, ddof=0))
                dispersion_pct = _percentile_rank(history_dispersion[decision_time], dispersion)
                catch_up = abs(index_window.return_10m_bps) / max(abs(basket10), 1e-9)
                side, reason = classify_unweighted_state(
                    basket_return_5m_bps=basket5, basket_return_10m_bps=basket10, lead_gap_z=z,
                    participation=participation, breadth=breadth, dispersion_percentile=dispersion_pct,
                    catch_up_ratio=catch_up, range_consumed=range_consumed,
                    constituent_coverage=coverage, thresholds=thresholds,
                )
                if coverage >= thresholds.minimum_constituent_coverage and not history_ready:
                    side, reason = "NONE", "insufficient_lead_gap_history"

            results.append(UnweightedSignalState(
                index_symbol=index_symbol, session=session, decision_time=decision_time,
                decision_timestamp=cutoff.isoformat(), side=side, reason=reason,
                basket_return_5m_bps=basket5, basket_return_10m_bps=basket10,
                median_constituent_return_5m_bps=median5, median_constituent_return_10m_bps=median10,
                index_return_5m_bps=index_window.return_5m_bps, index_return_10m_bps=index_window.return_10m_bps,
                lead_gap_bps=gap, lead_gap_z=z, participation=participation, breadth=breadth,
                dispersion_bps=dispersion, dispersion_percentile=dispersion_pct, catch_up_ratio=catch_up,
                range_consumed=range_consumed, constituents_expected=expected_count,
                constituents_available=available_count, constituent_coverage=coverage,
                rolling_median_30m_move_bps=median_30m, missing_constituents=tuple(sorted(missing)),
            ))
            if coverage >= thresholds.minimum_constituent_coverage and available_count > 0:
                history_gap[decision_time].append(gap)
                history_dispersion[decision_time].append(dispersion)

        session_move = _session_median_abs_30m_move(index_day)
        if session_move is not None:
            prior_30m_moves.append(session_move)
    return results


def evaluate_unweighted_first_signal_per_session(states: Sequence[UnweightedSignalState], bars: pd.DataFrame,
                                                 thresholds: UnweightedThresholds = UnweightedThresholds()) -> list[TradeOutcome]:
    return evaluate_signals_with_entry_delay(states, bars, thresholds, entry_delay_bars=1)  # type: ignore[arg-type]


def chronological_fold_summary(outcomes: Sequence[TradeOutcome], folds: int = 5) -> dict[str, object]:
    valid = [o for o in outcomes if o.exit_reason != "AMBIGUOUS_SAME_BAR"]
    sessions = sorted({o.session for o in valid})
    if not sessions:
        return {"folds": [], "positive_mean_folds": 0, "positive_median_folds": 0}
    split_sessions = np.array_split(np.asarray(sessions, dtype=object), folds)
    rows = []
    for number, fold_sessions in enumerate(split_sessions, start=1):
        if not len(fold_sessions):
            continue
        allowed = set(str(x) for x in fold_sessions)
        values = np.asarray([o.net_return_bps for o in valid if o.session in allowed], dtype=float)
        rows.append({
            "fold": number, "session_start": str(fold_sessions[0]), "session_end": str(fold_sessions[-1]),
            "sessions": len(fold_sessions), "signals": len(values),
            "net_mean_bps": float(np.mean(values)) if len(values) else None,
            "net_median_bps": float(np.median(values)) if len(values) else None,
            "positive_rate": float(np.mean(values > 0)) if len(values) else None,
        })
    return {
        "folds": rows,
        "positive_mean_folds": sum(1 for row in rows if row["net_mean_bps"] is not None and row["net_mean_bps"] > 0),
        "positive_median_folds": sum(1 for row in rows if row["net_median_bps"] is not None and row["net_median_bps"] > 0),
    }


def summarize_unweighted_outcomes(outcomes: Sequence[TradeOutcome]) -> dict[str, object]:
    summary = summarize_outcomes(outcomes)
    summary["chronological_fold_summary"] = chronological_fold_summary(outcomes)
    summary["research_lane"] = "UNWEIGHTED_CONSTITUENT_BREADTH"
    return summary
