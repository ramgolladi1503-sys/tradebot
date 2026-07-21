from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


WILDER_RSI_2 = "WILDER_RSI_2"
SIMPLE_RSI_2 = "SIMPLE_RSI_2"
NEXT_OPEN = "NEXT_OPEN_EXECUTABLE"
SAME_CLOSE = "SAME_CLOSE_THEORETICAL_PROXY"


@dataclass(frozen=True)
class CostModel:
    name: str
    spread_bps_round_trip: float
    slippage_bps_round_trip: float
    fees_taxes_bps_round_trip: float
    adverse_entry_slippage_bps: float = 0.0

    @property
    def total_bps(self) -> float:
        return (
            self.spread_bps_round_trip
            + self.slippage_bps_round_trip
            + self.fees_taxes_bps_round_trip
            + self.adverse_entry_slippage_bps
        )


BASE_COST = CostModel(
    name="base_index_proxy_costs",
    spread_bps_round_trip=1.0,
    slippage_bps_round_trip=2.0,
    fees_taxes_bps_round_trip=3.0,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def worktree_record(cwd: Path, output_dir: Path | None = None) -> dict[str, str]:
    if output_dir is not None:
        recorded = output_dir / "worktree_start_record.json"
        if recorded.exists():
            return json.loads(recorded.read_text(encoding="utf-8"))
    return {
        "source_branch": "origin/main",
        "source_commit": _git_value(["rev-parse", "HEAD"], cwd),
        "worktree_path": str(cwd),
        "branch": _git_value(["branch", "--show-current"], cwd),
        "initial_worktree_status": _git_value(["status", "--short", "--branch"], cwd),
    }


def simple_rsi(close: pd.Series, period: int = 2) -> pd.Series:
    delta = close.astype(float).diff()
    gains = delta.clip(lower=0.0).rolling(period, min_periods=period).mean()
    losses = (-delta.clip(upper=0.0)).rolling(period, min_periods=period).mean()
    rs = gains / losses.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask((losses == 0.0) & (gains > 0.0), 100.0)
    rsi = rsi.mask((gains == 0.0) & (losses > 0.0), 0.0)
    rsi = rsi.mask((gains == 0.0) & (losses == 0.0), 50.0)
    return rsi


def wilder_rsi(close: pd.Series, period: int = 2) -> pd.Series:
    delta = close.astype(float).diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) <= period:
        return out
    avg_gain = gains.iloc[1 : period + 1].mean()
    avg_loss = losses.iloc[1 : period + 1].mean()
    out.iloc[period] = _rsi_from_avgs(avg_gain, avg_loss)
    for i in range(period + 1, len(close)):
        avg_gain = ((avg_gain * (period - 1)) + gains.iloc[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses.iloc[i]) / period
        out.iloc[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def independent_wilder_oracle(values: Iterable[float], period: int = 2) -> list[float | None]:
    prices = [float(v) for v in values]
    result: list[float | None] = [None] * len(prices)
    if len(prices) <= period:
        return result
    moves = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    avg_gain = sum(max(x, 0.0) for x in moves[:period]) / period
    avg_loss = sum(max(-x, 0.0) for x in moves[:period]) / period
    result[period] = _rsi_from_avgs(avg_gain, avg_loss)
    for price_index in range(period + 1, len(prices)):
        move = prices[price_index] - prices[price_index - 1]
        avg_gain = ((avg_gain * (period - 1)) + max(move, 0.0)) / period
        avg_loss = ((avg_loss * (period - 1)) + max(-move, 0.0)) / period
        result[price_index] = _rsi_from_avgs(avg_gain, avg_loss)
    return result


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0 and avg_gain == 0.0:
        return 50.0
    if avg_loss == 0.0:
        return 100.0
    if avg_gain == 0.0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def load_ohlc(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        raw = pd.read_parquet(path)
    else:
        raw = pd.read_csv(path)
    frame = raw.copy()
    lowered = {str(c).lower(): c for c in frame.columns}
    date_col = lowered.get("date") or lowered.get("timestamp") or lowered.get("datetime")
    if date_col is None:
        if isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.reset_index(names="date")
            date_col = "date"
        else:
            raise ValueError("OHLC input must include date, timestamp, or datetime")
    rename = {lowered[k]: k for k in ("open", "high", "low", "close") if k in lowered}
    frame = frame.rename(columns=rename)
    missing = {"open", "high", "low", "close"} - set(frame.columns)
    if missing:
        raise ValueError(f"OHLC input missing columns: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame[date_col]).dt.tz_localize(None).dt.normalize()
    frame = frame[["date", "open", "high", "low", "close"]].sort_values("date")
    frame = frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["open", "high", "low", "close"])


def validate_ohlc(frame: pd.DataFrame) -> dict[str, object]:
    duplicate_dates = int(frame["date"].duplicated().sum())
    non_positive = int((frame[["open", "high", "low", "close"]] <= 0.0).any(axis=1).sum())
    missing_sessions = int((frame["date"].diff().dt.days.fillna(1) > 5).sum())
    return {
        "rows": int(len(frame)),
        "start": frame["date"].min().date().isoformat() if len(frame) else None,
        "end": frame["date"].max().date().isoformat() if len(frame) else None,
        "duplicate_dates": duplicate_dates,
        "non_positive_ohlc_rows": non_positive,
        "large_calendar_gaps_gt_5d": missing_sessions,
        "status": "PASS" if duplicate_dates == 0 and non_positive == 0 else "FAIL",
    }


def download_yfinance(output_dir: Path, start: str, end: str, auto_adjust: bool) -> tuple[Path, dict[str, object]]:
    import yfinance as yf

    output_dir.mkdir(parents=True, exist_ok=True)
    ticker = "^NSEI"
    raw = yf.download(
        tickers=ticker,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=auto_adjust,
        actions=False,
        progress=False,
        threads=False,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("yfinance returned no NIFTY rows")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [str(c[0]).lower() for c in raw.columns]
    else:
        raw.columns = [str(c).lower() for c in raw.columns]
    raw = raw.reset_index().rename(columns={"Date": "date", "date": "date"})
    frozen = output_dir / f"nifty50_yfinance_{start}_{end}_auto_adjust_{str(auto_adjust).lower()}.csv"
    raw.to_csv(frozen, index=False)
    meta = {
        "source": "yfinance_secondary_smoke_test",
        "yfinance_version": getattr(yf, "__version__", "UNKNOWN"),
        "ticker": ticker,
        "start_date": start,
        "exclusive_end_date": end,
        "timezone": "Yahoo Finance exchange daily calendar, normalized to naive session dates",
        "auto_adjust": auto_adjust,
        "raw_sha256": sha256_file(frozen),
    }
    return frozen, meta


def prepare_features(frame: pd.DataFrame, rsi_variant: str, rsi_period: int, sma_period: int) -> pd.DataFrame:
    data = frame.copy().reset_index(drop=True)
    if rsi_variant == WILDER_RSI_2:
        data["rsi"] = wilder_rsi(data["close"], rsi_period)
    elif rsi_variant == SIMPLE_RSI_2:
        data["rsi"] = simple_rsi(data["close"], rsi_period)
    else:
        raise ValueError(f"Unknown RSI variant: {rsi_variant}")
    data["sma"] = data["close"].rolling(sma_period, min_periods=sma_period).mean()
    data["trend_ok"] = data["close"] > data["sma"]
    data["ret_cc_fwd_1"] = data["close"].shift(-1) / data["close"] - 1.0
    data["ret_oc_next"] = data["close"].shift(-1) / data["open"].shift(-1) - 1.0
    return data


def build_trade_ledger(
    data: pd.DataFrame,
    *,
    lane: str,
    rsi_variant: str,
    entry_threshold: float,
    exit_threshold: float,
    sma_period: int,
    use_trend_filter: bool,
    cost: CostModel,
) -> tuple[pd.DataFrame, pd.Series]:
    rows: list[dict[str, object]] = []
    equity = pd.Series(1.0, index=data["date"])
    in_trade = False
    entry_i = -1
    entry_price = math.nan
    signal_i = -1
    for i in range(len(data) - 1):
        row = data.iloc[i]
        if not in_trade:
            trend_ok = bool(row["trend_ok"]) if use_trend_filter else True
            if trend_ok and float(row["rsi"]) < entry_threshold:
                if lane == NEXT_OPEN:
                    entry_i = i + 1
                    entry_price = float(data.iloc[entry_i]["open"])
                elif lane == SAME_CLOSE:
                    entry_i = i
                    entry_price = float(row["close"])
                else:
                    raise ValueError(f"Unknown lane: {lane}")
                signal_i = i
                in_trade = True
        elif float(row["rsi"]) > exit_threshold:
            exit_i = i + 1 if lane == NEXT_OPEN and i + 1 < len(data) else i
            if exit_i <= entry_i:
                continue
            exit_price = float(data.iloc[exit_i]["open"] if lane == NEXT_OPEN else data.iloc[exit_i]["close"])
            trade_slice = data.iloc[entry_i : exit_i + 1]
            gross = exit_price / entry_price - 1.0
            net = gross - cost.total_bps / 10000.0
            rows.append(
                {
                    "strategy_variant": "RSI2_MEAN_REVERSION_LONG_ONLY",
                    "rsi_variant": rsi_variant,
                    "parameter_set": json.dumps(
                        {
                            "rsi_period": 2,
                            "entry_threshold": entry_threshold,
                            "exit_threshold": exit_threshold,
                            "sma_period": sma_period,
                            "use_trend_filter": use_trend_filter,
                            "lane": lane,
                            "cost_model": cost.name,
                        },
                        sort_keys=True,
                    ),
                    "signal_timestamp": data.iloc[signal_i]["date"].date().isoformat(),
                    "entry_timestamp": data.iloc[entry_i]["date"].date().isoformat(),
                    "entry_price": entry_price,
                    "exit_timestamp": data.iloc[exit_i]["date"].date().isoformat(),
                    "exit_price": exit_price,
                    "holding_sessions": int(exit_i - entry_i),
                    "gross_return": gross,
                    "estimated_spread": cost.spread_bps_round_trip / 10000.0,
                    "slippage": (cost.slippage_bps_round_trip + cost.adverse_entry_slippage_bps) / 10000.0,
                    "fees_and_taxes": cost.fees_taxes_bps_round_trip / 10000.0,
                    "net_return": net,
                    "MAE": float((trade_slice["low"] / entry_price - 1.0).min()),
                    "MFE": float((trade_slice["high"] / entry_price - 1.0).max()),
                    "regime_label": _regime_label(data, signal_i),
                    "calendar_year": int(data.iloc[entry_i]["date"].year),
                    "WFA_fold": _fold_label(data.iloc[entry_i]["date"]),
                    "exit_reason": "RSI_EXIT_THRESHOLD_OBSERVED",
                }
            )
            equity.loc[data.iloc[exit_i]["date"] :] *= 1.0 + net
            in_trade = False
    return pd.DataFrame(rows), equity


def _regime_label(data: pd.DataFrame, i: int) -> str:
    trailing = data["close"].pct_change(63).iloc[i]
    if pd.isna(trailing):
        return "UNKNOWN"
    if trailing > 0.05:
        return "UP_STRONG"
    if trailing > 0.0:
        return "UP_WEAK"
    return "DOWN_OR_SIDEWAYS"


def _fold_label(date: pd.Timestamp) -> str:
    year = int(date.year)
    return f"{year - (year % 3)}_{year - (year % 3) + 2}"


def metrics(ledger: pd.DataFrame, equity: pd.Series, data: pd.DataFrame) -> dict[str, object]:
    returns = equity.pct_change().fillna(0.0)
    years = max((data["date"].max() - data["date"].min()).days / 365.25, 1e-9)
    completed = int(len(ledger))
    wins = ledger[ledger["net_return"] > 0.0]["net_return"] if completed else pd.Series(dtype=float)
    losses = ledger[ledger["net_return"] <= 0.0]["net_return"] if completed else pd.Series(dtype=float)
    total_net = float(equity.iloc[-1] - 1.0)
    yearly = ledger.groupby("calendar_year")["net_return"].sum().to_dict() if completed else {}
    return {
        "completed_trades": completed,
        "exposure_percentage": float(ledger["holding_sessions"].sum() / max(len(data), 1) * 100.0) if completed else 0.0,
        "average_holding_period": float(ledger["holding_sessions"].mean()) if completed else 0.0,
        "median_holding_period": float(ledger["holding_sessions"].median()) if completed else 0.0,
        "win_rate": float((ledger["net_return"] > 0.0).mean()) if completed else 0.0,
        "average_win": float(wins.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.mean()) if len(losses) else 0.0,
        "payoff_ratio": float(abs(wins.mean() / losses.mean())) if len(wins) and len(losses) and losses.mean() else 0.0,
        "expectancy_per_trade": float(ledger["net_return"].mean()) if completed else 0.0,
        "median_trade": float(ledger["net_return"].median()) if completed else 0.0,
        "gross_profit_factor": _profit_factor(ledger["gross_return"]) if completed else 0.0,
        "net_profit_factor": _profit_factor(ledger["net_return"]) if completed else 0.0,
        "CAGR": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "annualized_volatility": float(returns.std(ddof=0) * math.sqrt(252.0)),
        "Sharpe": _ratio(returns.mean() * 252.0, returns.std(ddof=0) * math.sqrt(252.0)),
        "Sortino": _ratio(returns.mean() * 252.0, returns[returns < 0.0].std(ddof=0) * math.sqrt(252.0)),
        "maximum_drawdown": _max_drawdown(equity),
        "Calmar": _ratio(float(equity.iloc[-1] ** (1.0 / years) - 1.0), abs(_max_drawdown(equity))),
        "worst_trade": float(ledger["net_return"].min()) if completed else 0.0,
        "worst_five_trade_sequence": _worst_n_sequence(ledger["net_return"], 5) if completed else 0.0,
        "longest_losing_sequence": _longest_losing_sequence(ledger["net_return"]) if completed else 0,
        "yearly_return_matrix": {str(k): float(v) for k, v in yearly.items()},
        "yearly_trade_count_matrix": {str(k): int(v) for k, v in ledger.groupby("calendar_year").size().to_dict().items()} if completed else {},
        "fold_level_metrics": _fold_metrics(ledger),
        "largest_year_pnl_contribution_pct": _largest_year_contribution(yearly, total_net),
        "five_best_trades_pnl_contribution_pct": _five_best_contribution(ledger, total_net),
    }


def _profit_factor(series: pd.Series) -> float:
    gains = float(series[series > 0.0].sum())
    losses = abs(float(series[series <= 0.0].sum()))
    return gains / losses if losses else float("inf") if gains else 0.0


def _ratio(num: float, den: float) -> float:
    return float(num / den) if den and not pd.isna(den) else 0.0


def _max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1.0).min())


def _worst_n_sequence(series: pd.Series, n: int) -> float:
    if len(series) < n:
        return float(series.sum()) if len(series) else 0.0
    return float(series.rolling(n).sum().min())


def _longest_losing_sequence(series: pd.Series) -> int:
    longest = current = 0
    for value in series:
        if value <= 0.0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _fold_metrics(ledger: pd.DataFrame) -> dict[str, dict[str, float]]:
    if ledger.empty:
        return {}
    return {
        str(fold): {
            "trades": int(len(group)),
            "expectancy": float(group["net_return"].mean()),
            "win_rate": float((group["net_return"] > 0.0).mean()),
            "net_return_sum": float(group["net_return"].sum()),
        }
        for fold, group in ledger.groupby("WFA_fold")
    }


def _largest_year_contribution(yearly: dict[int, float], total_net: float) -> float:
    positive = [v for v in yearly.values() if v > 0.0]
    return float(max(positive) / total_net * 100.0) if total_net > 0.0 and positive else 0.0


def _five_best_contribution(ledger: pd.DataFrame, total_net: float) -> float:
    if total_net <= 0.0 or ledger.empty:
        return 0.0
    return float(ledger["net_return"].nlargest(5).sum() / total_net * 100.0)


def forward_return_study(data: pd.DataFrame) -> dict[str, object]:
    signal = data["trend_ok"] & (data["rsi"] < 15.0)
    horizons = {}
    for h in [1, 2, 5, 10]:
        fwd = data["close"].shift(-h) / data["close"] - 1.0
        baseline = fwd[~signal]
        selected = fwd[signal]
        horizons[str(h)] = {
            "signal_count": int(selected.count()),
            "signal_mean": float(selected.mean()) if selected.count() else 0.0,
            "baseline_mean": float(baseline.mean()) if baseline.count() else 0.0,
            "signal_median": float(selected.median()) if selected.count() else 0.0,
        }
    return horizons


def baseline_entries(data: pd.DataFrame, name: str, cost: CostModel) -> tuple[pd.DataFrame, pd.Series]:
    synthetic = data.copy()
    if name == "one_day_dip":
        synthetic["rsi"] = np.where(synthetic["close"].pct_change() < 0.0, 0.0, 100.0)
    elif name == "two_day_dip":
        dip = (synthetic["close"].pct_change() < 0.0) & (synthetic["close"].pct_change().shift(1) < 0.0)
        synthetic["rsi"] = np.where(dip, 0.0, 100.0)
    elif name == "random_equal_exposure":
        rng = random.Random(20260721)
        trigger_count = int(((synthetic["trend_ok"]) & (synthetic["rsi"] < 15.0)).sum())
        idx = set(rng.sample(range(len(synthetic)), min(trigger_count, len(synthetic))))
        synthetic["rsi"] = [0.0 if i in idx else 100.0 for i in range(len(synthetic))]
    else:
        raise ValueError(name)
    return build_trade_ledger(
        synthetic,
        lane=NEXT_OPEN,
        rsi_variant=name,
        entry_threshold=15.0,
        exit_threshold=85.0,
        sma_period=200,
        use_trend_filter=True,
        cost=cost,
    )


def buy_and_hold_metrics(data: pd.DataFrame) -> dict[str, float]:
    equity = data["close"] / float(data["close"].iloc[0])
    returns = equity.pct_change().fillna(0.0)
    years = max((data["date"].max() - data["date"].min()).days / 365.25, 1e-9)
    return {
        "total_return": float(equity.iloc[-1] - 1.0),
        "CAGR": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "annualized_volatility": float(returns.std(ddof=0) * math.sqrt(252.0)),
        "maximum_drawdown": _max_drawdown(equity),
        "Sharpe": _ratio(returns.mean() * 252.0, returns.std(ddof=0) * math.sqrt(252.0)),
    }


def run_research(input_path: Path, output_dir: Path, source_meta: dict[str, object], cwd: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = load_ohlc(input_path)
    frame = frame[frame["date"] <= pd.Timestamp("2025-12-31")]
    qc = validate_ohlc(frame)
    if qc["status"] != "PASS":
        raise ValueError(f"Input data QC failed: {qc}")

    costs = [
        CostModel("zero_cost_diagnostic", 0.0, 0.0, 0.0),
        BASE_COST,
        CostModel("cost_stress_1_5x", 1.5, 3.0, 4.5),
        CostModel("cost_stress_2x", 2.0, 4.0, 6.0),
        CostModel("adverse_next_open_slippage_stress", 1.0, 2.0, 3.0, adverse_entry_slippage_bps=5.0),
    ]
    ledgers = []
    result_metrics: dict[str, object] = {}
    for rsi_variant in [WILDER_RSI_2, SIMPLE_RSI_2]:
        featured = prepare_features(frame, rsi_variant, 2, 200)
        result_metrics[f"forward_returns_{rsi_variant}"] = forward_return_study(featured)
        for lane in [NEXT_OPEN, SAME_CLOSE]:
            for cost in costs:
                ledger, equity = build_trade_ledger(
                    featured,
                    lane=lane,
                    rsi_variant=rsi_variant,
                    entry_threshold=15.0,
                    exit_threshold=85.0,
                    sma_period=200,
                    use_trend_filter=True,
                    cost=cost,
                )
                key = f"{rsi_variant}|{lane}|{cost.name}|trend_filter"
                result_metrics[key] = metrics(ledger, equity, featured)
                if cost.name == BASE_COST.name and lane == NEXT_OPEN:
                    ledgers.append(ledger)
                if rsi_variant == WILDER_RSI_2 and lane == NEXT_OPEN and cost.name == BASE_COST.name:
                    result_metrics["ledger_equity_reconciliation"] = {
                        "ledger_compounded_net": float((1.0 + ledger["net_return"]).prod() - 1.0) if not ledger.empty else 0.0,
                        "equity_curve_net": float(equity.iloc[-1] - 1.0),
                        "absolute_difference": abs(
                            (float((1.0 + ledger["net_return"]).prod() - 1.0) if not ledger.empty else 0.0)
                            - float(equity.iloc[-1] - 1.0)
                        ),
                        "tolerance": 1e-12,
                    }
        no_filter_ledger, no_filter_equity = build_trade_ledger(
            featured,
            lane=NEXT_OPEN,
            rsi_variant=rsi_variant,
            entry_threshold=15.0,
            exit_threshold=85.0,
            sma_period=200,
            use_trend_filter=False,
            cost=BASE_COST,
        )
        result_metrics[f"{rsi_variant}|{NEXT_OPEN}|{BASE_COST.name}|no_trend_filter"] = metrics(
            no_filter_ledger, no_filter_equity, featured
        )

        for entry in [10.0, 15.0, 20.0]:
            for exit_ in [80.0, 85.0, 90.0]:
                ledger, equity = build_trade_ledger(
                    featured,
                    lane=NEXT_OPEN,
                    rsi_variant=rsi_variant,
                    entry_threshold=entry,
                    exit_threshold=exit_,
                    sma_period=200,
                    use_trend_filter=True,
                    cost=BASE_COST,
                )
                result_metrics[f"param_stability|{rsi_variant}|entry_{entry}|exit_{exit_}"] = metrics(ledger, equity, featured)

    featured = prepare_features(frame, WILDER_RSI_2, 2, 200)
    for baseline in ["random_equal_exposure", "one_day_dip", "two_day_dip"]:
        ledger, equity = baseline_entries(featured, baseline, BASE_COST)
        result_metrics[f"baseline|{baseline}|{NEXT_OPEN}|{BASE_COST.name}"] = metrics(ledger, equity, featured)

    combined_ledger = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()
    ledger_path = output_dir / "completed_trade_ledger.csv"
    combined_ledger.to_csv(ledger_path, index=False)

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "worktree": worktree_record(cwd, output_dir),
        "safety_contract": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
        },
        "data_contract": {
            **source_meta,
            "frozen_input_path": str(input_path),
            "frozen_input_sha256": sha256_file(input_path),
            "use_through_date": "2025-12-31",
            "qc": qc,
            "independent_reconciliation": "NOT_AVAILABLE_IN_REPOSITORY",
        },
        "cost_model_declared_before_result_review": [cost.__dict__ for cost in costs],
        "tradability": {
            "index_signal_study": "COMPLETE",
            "tradable_instrument_study": "INSUFFICIENT_TRADABLE_DATA",
            "reason": "No frozen authoritative multi-year NIFTY futures or NIFTYBEES daily instrument dataset was found in this worktree.",
            "options_translation": "NOT_EVALUATED_OPTIONS_REQUIRE_SEPARATE_PATH_DEPENDENT_REPLAY",
        },
        "buy_and_hold": buy_and_hold_metrics(frame),
        "cash_risk_free": "NOT_EVALUATED_NO_FROZEN_RISK_FREE_SERIES_FOUND",
        "metrics": result_metrics,
        "ledger_path": str(ledger_path),
        "research_verdict": _verdict(result_metrics),
    }
    report_path = output_dir / "rsi2_mean_reversion_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary_path = output_dir / "rsi2_mean_reversion_summary.md"
    summary_path.write_text(render_summary(report), encoding="utf-8")
    return report


def _verdict(result_metrics: dict[str, object]) -> str:
    key = f"{WILDER_RSI_2}|{NEXT_OPEN}|{BASE_COST.name}|trend_filter"
    primary = result_metrics.get(key, {})
    if not isinstance(primary, dict) or primary.get("completed_trades", 0) < 30:
        return "NO_STRUCTURAL_EDGE_PROVEN_INSUFFICIENT_COMPLETED_TRADES"
    if primary.get("expectancy_per_trade", 0.0) <= 0.0 or primary.get("net_profit_factor", 0.0) <= 1.0:
        return "NO_STRUCTURAL_EDGE_PROVEN_NEGATIVE_OR_WEAK_COST_ADJUSTED_EXPECTANCY"
    if primary.get("five_best_trades_pnl_contribution_pct", 100.0) > 50.0:
        return "NO_DURABLE_STRUCTURAL_EDGE_PROVEN_CONCENTRATED_PNL"
    return "CANDIDATE_EDGE_REQUIRES_TRADABLE_INSTRUMENT_CONFIRMATION"


def render_summary(report: dict[str, object]) -> str:
    key = f"{WILDER_RSI_2}|{NEXT_OPEN}|{BASE_COST.name}|trend_filter"
    primary = report["metrics"][key]
    no_filter = report["metrics"][f"{WILDER_RSI_2}|{NEXT_OPEN}|{BASE_COST.name}|no_trend_filter"]
    random_base = report["metrics"][f"baseline|random_equal_exposure|{NEXT_OPEN}|{BASE_COST.name}"]
    return "\n".join(
        [
            "# RSI(2) NIFTY 50 Mean-Reversion Research",
            "",
            f"Verdict: `{report['research_verdict']}`.",
            "",
            "Primary executable lane: WILDER_RSI_2, next-open entry/exit, 200-session trend filter, base costs.",
            "",
            f"- Completed trades: {primary['completed_trades']}",
            f"- Win rate: {primary['win_rate']:.4f}",
            f"- Expectancy per trade: {primary['expectancy_per_trade']:.6f}",
            f"- CAGR: {primary['CAGR']:.6f}",
            f"- Max drawdown: {primary['maximum_drawdown']:.6f}",
            f"- Net profit factor: {primary['net_profit_factor']:.6f}",
            f"- Five best trades PnL contribution pct: {primary['five_best_trades_pnl_contribution_pct']:.2f}",
            "",
            f"No-trend-filter completed trades: {no_filter['completed_trades']}; expectancy: {no_filter['expectancy_per_trade']:.6f}.",
            f"Matched random completed trades: {random_base['completed_trades']}; expectancy: {random_base['expectancy_per_trade']:.6f}.",
            "",
            "The same-close lane is reported only as a non-executable theoretical proxy.",
            "Tradable-instrument translation is `INSUFFICIENT_TRADABLE_DATA`; index returns are not options P&L.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/research/rsi2_mean_reversion"))
    parser.add_argument("--download-yfinance", action="store_true")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default="2026-01-01")
    parser.add_argument("--auto-adjust", action="store_true")
    args = parser.parse_args(argv)
    source_meta: dict[str, object] = {"source": "user_supplied_or_repo_frozen"}
    input_path = args.input
    if args.download_yfinance:
        input_path, source_meta = download_yfinance(args.output_dir / "frozen_data", args.start, args.end, args.auto_adjust)
    if input_path is None:
        raise SystemExit("--input is required unless --download-yfinance is set")
    report = run_research(input_path, args.output_dir, source_meta, Path.cwd())
    print(json.dumps({"report": str(args.output_dir / "rsi2_mean_reversion_report.json"), "verdict": report["research_verdict"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
