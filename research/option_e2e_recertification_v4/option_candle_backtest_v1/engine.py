from __future__ import annotations

from collections import Counter
import hashlib
from typing import Any

import pandas as pd

from .fills import entry_fill, exit_fill, long_exit_trigger, validate_ohlcv_bar
from .models import CandleBacktestConfig, CandleBacktestResult, CandleTrade
from .selector import ContractSelectionError, select_contract


_REQUIRED_SIGNAL_COLUMNS = {"signal_ts", "direction", "underlying", "underlying_price"}
_REQUIRED_BAR_COLUMNS = {"contract_symbol", "timestamp", "open", "high", "low", "close", "volume"}


def _timestamp(value: Any, timezone: str) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed.tz_localize(timezone)
    return parsed.tz_convert(timezone)


def _bool(value: Any, default: bool = True) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _signal_id(row: pd.Series) -> str:
    explicit = str(row.get("signal_id") or "").strip()
    if explicit:
        return explicit
    payload = "|".join(
        str(row.get(name) or "")
        for name in ("signal_ts", "underlying", "direction", "underlying_price", "strategy_id")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _money_cost(*, price: float, quantity: int, fixed: float, bps: float) -> float:
    return float(fixed) + float(price) * float(quantity) * float(bps) / 10_000.0


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return float(drawdown)


def _breakdown(trades: list[CandleTrade], option_type: str) -> dict[str, Any]:
    rows = [trade for trade in trades if trade.option_type == option_type]
    wins = sum(1 for trade in rows if trade.net_pnl > 0)
    return {
        "trades": len(rows),
        "wins": wins,
        "win_rate": wins / len(rows) if rows else None,
        "net_pnl": float(sum(trade.net_pnl for trade in rows)),
    }


def _summary(
    *,
    config: CandleBacktestConfig,
    total_signals: int,
    selected_signals: int,
    trades: list[CandleTrade],
    rejections: list[dict[str, Any]],
) -> dict[str, Any]:
    net_values = [trade.net_pnl for trade in trades]
    gross_profit = sum(value for value in net_values if value > 0)
    gross_loss = abs(sum(value for value in net_values if value < 0))
    wins = sum(1 for value in net_values if value > 0)
    rejection_counts = Counter(str(row["reason"]) for row in rejections)
    static_catalog_count = sum(
        1 for trade in trades if trade.catalog_time_authority == "STATIC_CATALOG_LIMITATION"
    )
    return {
        "schema_version": "option_candle_backtest_summary_v1",
        "result_label": "CANDLE_PROXY_ECONOMICS_ONLY",
        "evidence_level": "CANDLE_PROXY_ECONOMICS",
        "fill_model_version": config.fill_model_version,
        "signals_total": int(total_signals),
        "signals_selected": int(selected_signals),
        "trades": len(trades),
        "wins": wins,
        "losses": sum(1 for value in net_values if value < 0),
        "flat": sum(1 for value in net_values if value == 0),
        "win_rate": wins / len(trades) if trades else None,
        "gross_profit": float(gross_profit),
        "gross_loss": float(gross_loss),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else None,
        "net_pnl": float(sum(net_values)),
        "average_net_pnl": float(sum(net_values) / len(net_values)) if net_values else None,
        "max_drawdown": _max_drawdown(net_values),
        "total_costs": float(sum(trade.total_costs for trade in trades)),
        "same_bar_ambiguities": sum(1 for trade in trades if trade.same_bar_ambiguity),
        "static_catalog_limitation_trades": static_catalog_count,
        "ce": _breakdown(trades, "CE"),
        "pe": _breakdown(trades, "PE"),
        "rejections": dict(sorted(rejection_counts.items())),
        "assumptions": {
            "signal_confirmation": "completed_signal_candle",
            "entry": "first_option_bar_strictly_after_signal_at_bar_open",
            "intrabar_conflict": "stop_first",
            "favourable_target_gap_improvement": False,
            "entry_slippage_bps": config.entry_slippage_bps,
            "exit_slippage_bps": config.exit_slippage_bps,
            "fixed_cost_per_order": config.fixed_cost_per_order,
            "entry_cost_bps": config.entry_cost_bps,
            "exit_cost_bps": config.exit_cost_bps,
            "max_volume_participation": config.max_volume_participation,
        },
        "historical_strategy_research_authorized": True,
        "executable_option_pnl_certified": False,
        "certifiable": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "next_gate": "FORWARD_BID_ASK_VALIDATION",
    }


def run_option_candle_backtest(
    *,
    signals: pd.DataFrame,
    contract_catalog: pd.DataFrame,
    option_bars: pd.DataFrame,
    config: CandleBacktestConfig | None = None,
) -> CandleBacktestResult:
    config = config or CandleBacktestConfig()
    missing_signals = sorted(_REQUIRED_SIGNAL_COLUMNS - set(signals.columns))
    missing_bars = sorted(_REQUIRED_BAR_COLUMNS - set(option_bars.columns))
    if missing_signals:
        raise ValueError(f"missing_signal_columns:{','.join(missing_signals)}")
    if missing_bars:
        raise ValueError(f"missing_option_bar_columns:{','.join(missing_bars)}")

    signal_rows = signals.copy()
    signal_rows["signal_ts"] = signal_rows["signal_ts"].map(
        lambda value: _timestamp(value, config.timezone)
    )
    if "signal_id" in signal_rows.columns:
        explicit_ids = signal_rows["signal_id"].astype(str).str.strip()
        nonblank_ids = explicit_ids.loc[explicit_ids != ""]
        if nonblank_ids.duplicated().any():
            raise ValueError("duplicate_signal_ids")
    signal_rows = signal_rows.sort_values("signal_ts", kind="mergesort").reset_index(drop=True)

    bars = option_bars.copy()
    bars["contract_symbol"] = bars["contract_symbol"].astype(str)
    bars["timestamp"] = bars["timestamp"].map(lambda value: _timestamp(value, config.timezone))
    duplicate_mask = bars.duplicated(["contract_symbol", "timestamp"], keep=False)
    if duplicate_mask.any():
        raise ValueError("duplicate_contract_timestamp_rows")
    bars = bars.sort_values(["contract_symbol", "timestamp"], kind="mergesort").reset_index(drop=True)

    trades: list[CandleTrade] = []
    rejections: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    selected_signals = 0

    for _, signal in signal_rows.iterrows():
        signal_id = _signal_id(signal)
        if not _bool(signal.get("selected_for_execution"), default=True):
            rejections.append({"signal_id": signal_id, "reason": "not_selected_for_research"})
            continue
        selected_signals += 1
        try:
            selection = select_contract(
                signal=signal,
                catalog=contract_catalog,
                timezone=config.timezone,
                require_session_catalog=config.require_session_catalog,
            )
        except ContractSelectionError as exc:
            rejections.append({"signal_id": signal_id, "reason": str(exc)})
            continue
        if selection is None:
            rejections.append({"signal_id": signal_id, "reason": "neutral_no_trade"})
            continue

        selection_record = {"signal_id": signal_id, **selection.to_dict()}
        selections.append(selection_record)
        signal_ts = signal["signal_ts"]
        contract_rows = bars.loc[
            (bars["contract_symbol"] == selection.contract_symbol)
            & (bars["timestamp"] > signal_ts)
            & (bars["timestamp"].dt.date == signal_ts.date())
        ].copy()
        if contract_rows.empty:
            rejections.append({"signal_id": signal_id, "reason": "no_next_option_bar"})
            continue

        entry_row = contract_rows.iloc[0]
        try:
            entry = entry_fill(entry_row, config)
        except ValueError as exc:
            rejections.append({"signal_id": signal_id, "reason": str(exc)})
            continue
        if entry.status not in {"FILLED", "PARTIAL"} or entry.fill_price is None:
            rejections.append({"signal_id": signal_id, "reason": entry.reason or "entry_not_filled"})
            continue

        explicit_stop = pd.to_numeric(pd.Series([signal.get("option_stop_price")]), errors="coerce").iloc[0]
        explicit_target = pd.to_numeric(pd.Series([signal.get("option_target_price")]), errors="coerce").iloc[0]
        risk_distance = float(entry.fill_price) * float(config.stop_pct)
        stop_price = float(explicit_stop) if not pd.isna(explicit_stop) else float(entry.fill_price) - risk_distance
        target_price = (
            float(explicit_target)
            if not pd.isna(explicit_target)
            else float(entry.fill_price) + risk_distance * float(config.target_rr)
        )
        if not (0 < stop_price < float(entry.fill_price) < target_price):
            rejections.append({"signal_id": signal_id, "reason": "invalid_option_trade_geometry"})
            continue

        max_exit_ts = entry_row["timestamp"] + pd.Timedelta(minutes=config.max_hold_minutes)
        eligible_exit_rows = contract_rows.loc[contract_rows["timestamp"] <= max_exit_ts].copy()
        if eligible_exit_rows.empty:
            rejections.append({"signal_id": signal_id, "reason": "no_exit_bar"})
            continue

        exit_row: pd.Series | None = None
        exit_reason = "TIME_EXIT"
        exit_reference: float | None = None
        same_bar_ambiguity = False
        exit_validation_reason: str | None = None
        for _, candidate_bar in eligible_exit_rows.iterrows():
            try:
                reason, reference, ambiguous = long_exit_trigger(
                    candidate_bar,
                    target_price=target_price,
                    stop_price=stop_price,
                    config=config,
                )
            except ValueError as exc:
                exit_validation_reason = str(exc)
                break
            if reason is not None:
                exit_row = candidate_bar
                exit_reason = reason
                exit_reference = reference
                same_bar_ambiguity = ambiguous
                break
        if exit_validation_reason is not None:
            rejections.append({"signal_id": signal_id, "reason": exit_validation_reason})
            continue
        if exit_row is None:
            exit_row = eligible_exit_rows.iloc[-1]
            try:
                validate_ohlcv_bar(exit_row)
            except ValueError as exc:
                rejections.append({"signal_id": signal_id, "reason": str(exc)})
                continue
            exit_reference = float(exit_row["close"])
        if exit_reference is None:
            rejections.append({"signal_id": signal_id, "reason": "missing_exit_reference"})
            continue

        exit_result = exit_fill(
            exit_row,
            reference_price=exit_reference,
            quantity=entry.quantity,
            reason=exit_reason,
            config=config,
        )
        if exit_result.fill_price is None:
            rejections.append({"signal_id": signal_id, "reason": exit_result.reason or "exit_not_filled"})
            continue

        entry_cost = _money_cost(
            price=float(entry.fill_price),
            quantity=entry.quantity,
            fixed=config.fixed_cost_per_order,
            bps=config.entry_cost_bps,
        )
        exit_cost = _money_cost(
            price=float(exit_result.fill_price),
            quantity=entry.quantity,
            fixed=config.fixed_cost_per_order,
            bps=config.exit_cost_bps,
        )
        gross_pnl = (float(exit_result.fill_price) - float(entry.fill_price)) * entry.quantity
        total_costs = entry_cost + exit_cost
        net_pnl = gross_pnl - total_costs
        hold_minutes = max(
            (exit_row["timestamp"] - entry_row["timestamp"]).total_seconds() / 60.0,
            0.0,
        )
        trades.append(
            CandleTrade(
                signal_id=signal_id,
                underlying=selection.underlying,
                direction=str(signal.get("direction") or "").upper(),
                contract_symbol=selection.contract_symbol,
                option_type=selection.option_type,
                strike=selection.strike,
                expiry=selection.expiry,
                signal_ts=signal_ts.isoformat(),
                entry_ts=entry_row["timestamp"].isoformat(),
                exit_ts=exit_row["timestamp"].isoformat(),
                entry_reference_price=float(entry.reference_price),
                entry_fill_price=float(entry.fill_price),
                exit_reference_price=float(exit_result.reference_price),
                exit_fill_price=float(exit_result.fill_price),
                target_price=float(target_price),
                stop_price=float(stop_price),
                exit_reason=exit_reason,
                quantity=entry.quantity,
                gross_pnl=float(gross_pnl),
                entry_cost=float(entry_cost),
                exit_cost=float(exit_cost),
                total_costs=float(total_costs),
                net_pnl=float(net_pnl),
                hold_minutes=float(hold_minutes),
                entry_fill_source=entry.source,
                exit_fill_source=exit_result.source,
                entry_slippage_bps=config.entry_slippage_bps,
                exit_slippage_bps=config.exit_slippage_bps,
                same_bar_ambiguity=bool(same_bar_ambiguity),
                catalog_time_authority=selection.catalog_time_authority,
            )
        )

    summary = _summary(
        config=config,
        total_signals=len(signal_rows),
        selected_signals=selected_signals,
        trades=trades,
        rejections=rejections,
    )
    return CandleBacktestResult(
        config=config,
        summary=summary,
        trades=trades,
        rejections=rejections,
        selections=selections,
    )
