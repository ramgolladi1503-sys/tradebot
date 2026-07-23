"""Research-only weighted constituent lead-lag strategy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .bar_grid import exact_bar_window, symbols_with_exact_window

REQUIRED_BAR_COLUMNS = {"timestamp", "session", "symbol", "open", "high", "low", "close"}
REQUIRED_WEIGHT_COLUMNS = {"index_symbol", "constituent_symbol", "effective_from", "weight"}
DEFAULT_DECISION_TIMES = ("10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:15")


class DataContractError(ValueError):
    """Raised when research inputs are not authoritative enough to evaluate."""


@dataclass(frozen=True)
class StrategyThresholds:
    z_entry: float = 2.0
    participation_min: float = 0.70
    breadth_abs_min: float = 0.40
    catch_up_ratio_max: float = 0.60
    dispersion_percentile_max: float = 0.80
    range_consumed_max: float = 0.60
    minimum_weight_coverage: float = 0.80
    minimum_history_sessions: int = 20
    assumed_round_trip_cost_bps: float = 5.0
    max_hold_minutes: int = 20
    stop_fraction_of_median_30m_move: float = 0.35
    reward_risk: float = 1.50


@dataclass(frozen=True)
class SignalState:
    index_symbol: str
    session: str
    decision_time: str
    decision_timestamp: str
    side: str
    reason: str
    basket_return_5m_bps: float
    basket_return_10m_bps: float
    index_return_5m_bps: float
    index_return_10m_bps: float
    lead_gap_bps: float
    lead_gap_z: float
    participation: float
    weighted_breadth: float
    dispersion_bps: float
    dispersion_percentile: float
    catch_up_ratio: float
    range_consumed: float
    weight_coverage: float
    rolling_median_30m_move_bps: float
    constituents_expected: int = 0
    constituents_available: int = 0
    count_coverage: float = 0.0
    missing_constituents: tuple[str, ...] = ()
    research_only: bool = True
    allowed_for_live_execution: bool = False
    broker_api_called: bool = False  # broker_api_called=false
    is_order_action: bool = False  # is_order_action=false

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["missing_constituents"] = list(self.missing_constituents)
        return payload


@dataclass(frozen=True)
class TradeOutcome:
    index_symbol: str
    session: str
    decision_time: str
    side: str
    entry_timestamp: str
    exit_timestamp: str
    entry_price: float
    exit_price: float
    stop_bps: float
    target_bps: float
    gross_return_bps: float
    net_return_bps: float
    exit_reason: str
    research_only: bool = True
    allowed_for_live_execution: bool = False
    broker_api_called: bool = False  # broker_api_called=false
    is_order_action: bool = False  # is_order_action=false

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def _to_session_date(value: object) -> date:
    return pd.Timestamp(value).date()


def validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_BAR_COLUMNS - set(bars.columns))
    if missing:
        raise DataContractError(f"bars missing columns: {missing}")
    out = bars.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["session"] = out["session"].astype(str)
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    numeric = ["open", "high", "low", "close"]
    out[numeric] = out[numeric].apply(pd.to_numeric, errors="coerce")
    invalid = (
        out[numeric].isna().any(axis=1)
        | (out[numeric] <= 0).any(axis=1)
        | (out["high"] < out[["open", "close"]].max(axis=1))
        | (out["low"] > out[["open", "close"]].min(axis=1))
        | (out["high"] < out["low"])
    )
    if invalid.any():
        raise DataContractError(f"bars contain {int(invalid.sum())} invalid OHLC rows")
    duplicate = out.duplicated(["symbol", "timestamp"], keep=False)
    if duplicate.any():
        keys = out.loc[duplicate, ["symbol", "timestamp"]].drop_duplicates().head(5)
        raise DataContractError(f"bars contain duplicate symbol/timestamp keys: {keys.to_dict('records')}")
    return out.sort_values(["session", "symbol", "timestamp"]).reset_index(drop=True)


def validate_weights(weights: pd.DataFrame, minimum_snapshot_coverage: float = 0.80) -> pd.DataFrame:
    missing = sorted(REQUIRED_WEIGHT_COLUMNS - set(weights.columns))
    if missing:
        raise DataContractError(f"weights missing columns: {missing}")
    out = weights.copy()
    out["index_symbol"] = out["index_symbol"].astype(str).str.upper().str.strip()
    out["constituent_symbol"] = out["constituent_symbol"].astype(str).str.upper().str.strip()
    out["effective_from"] = pd.to_datetime(out["effective_from"], errors="raise").dt.date
    out["effective_to"] = pd.to_datetime(out.get("effective_to"), errors="coerce").dt.date if "effective_to" in out else pd.NaT
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce")
    if out["weight"].isna().any() or (out["weight"] <= 0).any():
        raise DataContractError("weights must be positive numeric values")
    if out.duplicated(["index_symbol", "constituent_symbol", "effective_from"], keep=False).any():
        raise DataContractError("duplicate point-in-time constituent-weight keys")
    sums = out.groupby(["index_symbol", "effective_from"])["weight"].sum()
    if len(sums[sums < minimum_snapshot_coverage]):
        raise DataContractError(f"weight snapshots below {minimum_snapshot_coverage:.0%}: {sums[sums < minimum_snapshot_coverage].to_dict()}")
    if len(sums[sums > 1.02]):
        raise DataContractError(f"weight snapshots above 102%: {sums[sums > 1.02].to_dict()}")
    return out.sort_values(["index_symbol", "effective_from", "constituent_symbol"]).reset_index(drop=True)


def select_weight_snapshot(weights: pd.DataFrame, index_symbol: str, session: object) -> pd.DataFrame:
    session_date = _to_session_date(session)
    active_to = weights["effective_to"].apply(
        lambda value: pd.isna(value) or pd.Timestamp(value).date() >= session_date
    )
    subset = weights[
        (weights["index_symbol"] == index_symbol.upper())
        & (weights["effective_from"] <= session_date)
        & active_to
    ]
    if subset.empty:
        raise DataContractError(f"no point-in-time weights for {index_symbol} on {session_date}")
    effective = subset["effective_from"].max()
    snapshot = subset[subset["effective_from"] == effective].copy()
    if snapshot.empty:
        raise DataContractError(f"empty weight snapshot for {index_symbol} on {session_date}")
    return snapshot


def classify_state(*, basket_return_5m_bps: float, basket_return_10m_bps: float, lead_gap_z: float,
                   participation: float, weighted_breadth: float, dispersion_percentile: float,
                   catch_up_ratio: float, range_consumed: float, weight_coverage: float,
                   thresholds: StrategyThresholds) -> tuple[str, str]:
    if weight_coverage < thresholds.minimum_weight_coverage:
        return "NONE", "insufficient_weight_coverage"
    if dispersion_percentile > thresholds.dispersion_percentile_max:
        return "NONE", "dispersion_too_high"
    if catch_up_ratio > thresholds.catch_up_ratio_max:
        return "NONE", "index_already_caught_up"
    if range_consumed > thresholds.range_consumed_max:
        return "NONE", "index_range_already_consumed"
    if (lead_gap_z >= thresholds.z_entry and basket_return_5m_bps > 0 and basket_return_10m_bps > 0
            and participation >= thresholds.participation_min and weighted_breadth >= thresholds.breadth_abs_min):
        return "LONG", "constituents_lead_index_up"
    if (lead_gap_z <= -thresholds.z_entry and basket_return_5m_bps < 0 and basket_return_10m_bps < 0
            and participation >= thresholds.participation_min and weighted_breadth <= -thresholds.breadth_abs_min):
        return "SHORT", "constituents_lead_index_down"
    return "NONE", "frozen_entry_conditions_not_met"


def _weighted_std(values: np.ndarray, weights: np.ndarray, mean: float) -> float:
    return float(np.sqrt(np.sum(weights * np.square(values - mean))))


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


def generate_signal_states(bars: pd.DataFrame, weights: pd.DataFrame, index_symbol: str,
                           decision_times: Iterable[str] = DEFAULT_DECISION_TIMES,
                           thresholds: StrategyThresholds = StrategyThresholds()) -> list[SignalState]:
    clean_bars = validate_bars(bars)
    clean_weights = validate_weights(weights, thresholds.minimum_weight_coverage)
    index_symbol = index_symbol.upper()
    decision_times = tuple(decision_times)
    history_gap = {t: [] for t in decision_times}
    history_dispersion = {t: [] for t in decision_times}
    prior_30m_moves: list[float] = []
    results: list[SignalState] = []

    for session, day in clean_bars.groupby("session", sort=True):
        day_by_symbol = {symbol: group.sort_values("timestamp") for symbol, group in day.groupby("symbol", sort=False)}
        index_day = day_by_symbol.get(index_symbol, pd.DataFrame())
        if index_day.empty:
            raise DataContractError(f"missing index bars for {index_symbol} on {session}")
        snapshot = select_weight_snapshot(clean_weights, index_symbol, session)
        snapshot_weight = float(snapshot["weight"].sum())
        expected_symbols = tuple(snapshot["constituent_symbol"].astype(str))

        for decision_time in decision_times:
            cutoff = pd.Timestamp(f"{session} {decision_time}", tz="Asia/Kolkata").tz_convert("UTC")
            index_window, index_missing = exact_bar_window(index_day, cutoff)
            if index_window is None:
                raise DataContractError(f"index exact return grid missing for {session} {decision_time}: {list(index_missing)}")
            available, missing = symbols_with_exact_window(day_by_symbol, expected_symbols, cutoff)
            component_returns: list[tuple[float, float, float, str]] = []
            weight_by_symbol = snapshot.set_index("constituent_symbol")["weight"].to_dict()
            for symbol, window in available.items():
                component_returns.append((float(weight_by_symbol[symbol]), window.return_5m_bps, window.return_10m_bps, symbol))

            valid_weight = float(sum(row[0] for row in component_returns))
            count_coverage = len(component_returns) / len(expected_symbols) if expected_symbols else 0.0
            weight_coverage = valid_weight / snapshot_weight if snapshot_weight else 0.0
            history_ready = len(history_gap[decision_time]) >= thresholds.minimum_history_sessions
            median_30m = float(np.median(prior_30m_moves[-20:])) if prior_30m_moves else 0.0
            current_price = index_window.close_t
            open_price = float(index_day.iloc[0]["open"])
            open_move = abs((current_price / open_price - 1.0) * 10_000.0)
            range_consumed = open_move / median_30m if median_30m > 1e-9 else 0.0

            if valid_weight <= 0:
                basket5 = basket10 = gap = z = participation = breadth = dispersion = 0.0
                dispersion_pct = 0.5
                catch_up = float("inf")
                side, reason = "NONE", "insufficient_weight_coverage"
            else:
                normalized = np.asarray([row[0] / valid_weight for row in component_returns], dtype=float)
                r5s = np.asarray([row[1] for row in component_returns], dtype=float)
                r10s = np.asarray([row[2] for row in component_returns], dtype=float)
                basket5 = float(np.sum(normalized * r5s))
                basket10 = float(np.sum(normalized * r10s))
                gap = basket5 - index_window.return_5m_bps
                if history_ready:
                    hist = np.asarray(history_gap[decision_time][-thresholds.minimum_history_sessions:], dtype=float)
                    std = float(np.std(hist, ddof=1))
                    z = (gap - float(np.mean(hist))) / std if std > 1e-9 else 0.0
                else:
                    z = 0.0
                direction = 1.0 if basket5 > 0 else -1.0 if basket5 < 0 else 0.0
                participation = float(np.sum(normalized[np.sign(r5s) == direction])) if direction else 0.0
                breadth = float(np.sum(normalized * np.sign(r5s)))
                dispersion = _weighted_std(r5s, normalized, basket5)
                dispersion_pct = _percentile_rank(history_dispersion[decision_time], dispersion)
                catch_up = abs(index_window.return_10m_bps) / max(abs(basket10), 1e-9)
                side, reason = classify_state(
                    basket_return_5m_bps=basket5, basket_return_10m_bps=basket10, lead_gap_z=z,
                    participation=participation, weighted_breadth=breadth,
                    dispersion_percentile=dispersion_pct, catch_up_ratio=catch_up,
                    range_consumed=range_consumed, weight_coverage=weight_coverage, thresholds=thresholds,
                )
                if weight_coverage >= thresholds.minimum_weight_coverage and not history_ready:
                    side, reason = "NONE", "insufficient_lead_gap_history"

            results.append(SignalState(
                index_symbol=index_symbol, session=session, decision_time=decision_time,
                decision_timestamp=cutoff.isoformat(), side=side, reason=reason,
                basket_return_5m_bps=basket5, basket_return_10m_bps=basket10,
                index_return_5m_bps=index_window.return_5m_bps, index_return_10m_bps=index_window.return_10m_bps,
                lead_gap_bps=gap, lead_gap_z=z, participation=participation, weighted_breadth=breadth,
                dispersion_bps=dispersion, dispersion_percentile=dispersion_pct, catch_up_ratio=catch_up,
                range_consumed=range_consumed, weight_coverage=weight_coverage,
                rolling_median_30m_move_bps=median_30m,
                constituents_expected=len(expected_symbols), constituents_available=len(component_returns),
                count_coverage=count_coverage, missing_constituents=tuple(sorted(missing)),
            ))
            if weight_coverage >= thresholds.minimum_weight_coverage and valid_weight > 0:
                history_gap[decision_time].append(gap)
                history_dispersion[decision_time].append(dispersion)

        session_move = _session_median_abs_30m_move(index_day)
        if session_move is not None:
            prior_30m_moves.append(session_move)
    return results


def evaluate_signals_with_entry_delay(states: Sequence[SignalState], bars: pd.DataFrame,
                                      thresholds: StrategyThresholds = StrategyThresholds(),
                                      entry_delay_bars: int = 1) -> list[TradeOutcome]:
    if entry_delay_bars < 1:
        raise ValueError("entry_delay_bars must be at least one")
    clean_bars = validate_bars(bars)
    candidates = [s for s in states if s.side in {"LONG", "SHORT"}]
    first: dict[tuple[str, str], SignalState] = {}
    for state in sorted(candidates, key=lambda s: (s.session, s.index_symbol, s.decision_timestamp)):
        first.setdefault((state.session, state.index_symbol), state)
    outcomes: list[TradeOutcome] = []
    for state in first.values():
        day = clean_bars[(clean_bars["session"] == state.session) & (clean_bars["symbol"] == state.index_symbol)].sort_values("timestamp")
        decision_ts = pd.Timestamp(state.decision_timestamp)
        expected_entry_ts = decision_ts + pd.Timedelta(minutes=5 * entry_delay_bars)
        entry_rows = day[day["timestamp"] == expected_entry_ts]
        if entry_rows.empty:
            continue
        entry = entry_rows.iloc[0]
        hold_timestamps = [expected_entry_ts + pd.Timedelta(minutes=5 * offset) for offset in range(thresholds.max_hold_minutes // 5)]
        future = day[day["timestamp"].isin(hold_timestamps)].sort_values("timestamp")
        if future.empty or future.iloc[0]["timestamp"] != expected_entry_ts:
            continue
        entry_price = float(entry["open"])
        stop_bps = max(5.0, thresholds.stop_fraction_of_median_30m_move * state.rolling_median_30m_move_bps)
        target_bps = stop_bps * thresholds.reward_risk
        side_mult = 1.0 if state.side == "LONG" else -1.0
        exit_price = float(future.iloc[-1]["close"])
        exit_ts = future.iloc[-1]["timestamp"]
        exit_reason = "MAX_HOLD"
        target_price = entry_price * (1.0 + side_mult * target_bps / 10_000.0)
        stop_price = entry_price * (1.0 - side_mult * stop_bps / 10_000.0)
        for bar in future.itertuples(index=False):
            if state.side == "LONG":
                target_hit, stop_hit = float(bar.high) >= target_price, float(bar.low) <= stop_price
            else:
                target_hit, stop_hit = float(bar.low) <= target_price, float(bar.high) >= stop_price
            if target_hit and stop_hit:
                exit_price, exit_ts, exit_reason = float(bar.close), bar.timestamp, "AMBIGUOUS_SAME_BAR"
                break
            if target_hit:
                exit_price, exit_ts, exit_reason = target_price, bar.timestamp, "TARGET"
                break
            if stop_hit:
                exit_price, exit_ts, exit_reason = stop_price, bar.timestamp, "STOP"
                break
        gross = side_mult * (exit_price / entry_price - 1.0) * 10_000.0
        outcomes.append(TradeOutcome(
            index_symbol=state.index_symbol, session=state.session, decision_time=state.decision_time,
            side=state.side, entry_timestamp=pd.Timestamp(entry["timestamp"]).isoformat(),
            exit_timestamp=pd.Timestamp(exit_ts).isoformat(), entry_price=entry_price, exit_price=exit_price,
            stop_bps=stop_bps, target_bps=target_bps, gross_return_bps=gross,
            net_return_bps=gross - thresholds.assumed_round_trip_cost_bps, exit_reason=exit_reason,
        ))
    return outcomes


def evaluate_first_signal_per_session(states: Sequence[SignalState], bars: pd.DataFrame,
                                      thresholds: StrategyThresholds = StrategyThresholds()) -> list[TradeOutcome]:
    return evaluate_signals_with_entry_delay(states, bars, thresholds, entry_delay_bars=1)


def summarize_outcomes(outcomes: Sequence[TradeOutcome]) -> dict[str, object]:
    valid = [o for o in outcomes if o.exit_reason != "AMBIGUOUS_SAME_BAR"]
    values = np.asarray([o.net_return_bps for o in valid], dtype=float)
    return {
        "signals_total": len(outcomes), "signals_evaluable": len(valid),
        "ambiguous_same_bar": len(outcomes) - len(valid),
        "net_mean_bps": float(np.mean(values)) if len(values) else None,
        "net_median_bps": float(np.median(values)) if len(values) else None,
        "positive_rate": float(np.mean(values > 0)) if len(values) else None,
        "research_only": True, "allowed_for_live_execution": False,
        "broker_api_called": False, "is_order_action": False,
    }
