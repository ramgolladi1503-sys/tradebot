from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.decision_engine import evaluate_candidate_decision
from core.fill_model import FillModel

from .adapter import build_candidate_from_candle
from .loader import load_option_symbol_csv
from .models import OptionBacktestConfig, OptionBacktestResult, OptionBacktestTrade
from .report import summarize_backtest


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


class OptionBacktestEngine:
    def __init__(self, cfg: OptionBacktestConfig):
        self.cfg = cfg
        self.fill_model = FillModel()

    def _simulate_entry(self, candidate: dict[str, Any], row: pd.Series, row_index: int) -> dict[str, Any]:
        side = str(candidate.get("side") or "BUY").upper()
        symbol = str(candidate.get("symbol") or self.cfg.symbol)
        entry_ref = _safe_float(candidate.get("execution_entry"))
        if entry_ref is None:
            return {"status": "SKIPPED", "reason": "missing_execution_entry"}
        order = {
            "side": side,
            "symbol": symbol,
            "qty": int(self.cfg.quantity),
            "limit_price": float(entry_ref),
        }
        market_snapshot = {
            "bid": _safe_float(row.get("bid")),
            "ask": _safe_float(row.get("ask")),
            "volume": _safe_float(row.get("volume")) or 0.0,
            "oi": _safe_float(row.get("oi")) or 0.0,
        }
        return self.fill_model.simulate(order, market_snapshot, f"{self.cfg.fill_model_run_id}:{row_index}")

    def _simulate_exit(
        self,
        *,
        side: str,
        entry_fill_price: float,
        target_price: float,
        stop_price: float,
        entry_index: int,
        candles: pd.DataFrame,
    ) -> tuple[float, pd.Timestamp, str]:
        max_index = min(len(candles) - 1, entry_index + int(self.cfg.max_hold_minutes))
        for idx in range(entry_index, max_index + 1):
            candle = candles.iloc[idx]
            high = float(candle["high"])
            low = float(candle["low"])
            if side == "SELL":
                if low <= target_price:
                    return float(target_price), candle["timestamp"], "TARGET_HIT"
                if high >= stop_price:
                    return float(stop_price), candle["timestamp"], "STOP_HIT"
            else:
                if high >= target_price:
                    return float(target_price), candle["timestamp"], "TARGET_HIT"
                if low <= stop_price:
                    return float(stop_price), candle["timestamp"], "STOP_HIT"
        last_candle = candles.iloc[max_index]
        return float(last_candle["close"]), last_candle["timestamp"], "TIME_EXIT"

    def _write_artifacts(self, result: OptionBacktestResult) -> None:
        if self.cfg.output_dir is None:
            return
        output_dir = Path(self.cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "summary.json"
        trades_path = output_dir / "trade_journal.json"
        sample_path = output_dir / "decision_samples.json"
        summary_path.write_text(json.dumps(result.summary, indent=2, sort_keys=True), encoding="utf-8")
        trades_payload = [trade.__dict__ for trade in result.trades]
        trades_path.write_text(json.dumps(trades_payload, indent=2), encoding="utf-8")
        sample_path.write_text(json.dumps(result.sampled_decisions, indent=2), encoding="utf-8")

    def run(self) -> OptionBacktestResult:
        candles = load_option_symbol_csv(
            data_path=self.cfg.data_path,
            symbol=self.cfg.symbol,
            date_from=self.cfg.date_from,
            date_to=self.cfg.date_to,
            timezone=self.cfg.timezone,
        )
        signals_total = 0
        executable_signals = 0
        rejected_reasons: Counter[str] = Counter()
        diagnostics = {
            "fallback_rows": 0,
            "derived_geometry_rows": 0,
            "missing_signal_rows": 0,
            "missing_bid_ask_rows": int((~candles["has_bid_ask"]).sum()),
            "late_entries": 0,
            "chop_losses": 0,
            "confidence_buckets": {"high": {"wins": 0, "losses": 0}, "low": {"wins": 0, "losses": 0}},
        }
        trades: list[OptionBacktestTrade] = []
        sampled_decisions: list[dict[str, Any]] = []
        open_until_index = -1

        for row_index, row in candles.iterrows():
            row_map = row.to_dict()
            candidate = build_candidate_from_candle(row_map, self.cfg)
            signals_total += 1
            if candidate.get("truth_quality") == "FALLBACK":
                diagnostics["fallback_rows"] += 1
            if candidate.get("source_flags", {}).get("backtest_geometry_source") == "derived":
                diagnostics["derived_geometry_rows"] += 1
            if candidate.get("confidence_raw") is None and candidate.get("confidence_final") is None:
                diagnostics["missing_signal_rows"] += 1

            decision = evaluate_candidate_decision(candidate)
            sampled_decisions.append(
                {
                    "timestamp": candidate["timestamp"],
                    "symbol": candidate["symbol"],
                    "truth_quality": decision.get("truth_quality"),
                    "decision_reason": decision.get("decision_reason"),
                    "permission": decision.get("permission"),
                    "execution_status": decision.get("execution_status"),
                    "confidence_raw": candidate.get("confidence_raw"),
                    "confidence_final": candidate.get("confidence_final"),
                }
            )
            if decision.get("execution_status") == "executable":
                executable_signals += 1
            else:
                rejected_reasons[str(decision.get("decision_reason") or "unknown")] += 1

            if row_index <= open_until_index:
                continue
            if not (
                str(decision.get("permission") or "").upper() == "EXECUTE"
                and str(decision.get("execution_status") or "").lower() == "executable"
                and str(candidate.get("truth_quality") or "").upper() != "FALLBACK"
            ):
                continue

            target_price = _safe_float(candidate.get("target"))
            stop_price = _safe_float(candidate.get("stop_loss"))
            if target_price is None or stop_price is None:
                rejected_reasons["missing_trade_geometry"] += 1
                continue

            fill = self._simulate_entry(candidate, row, row_index)
            if fill.get("status") not in {"FILLED", "PARTIAL"}:
                rejected_reasons[str(fill.get("reason") or "entry_not_filled")] += 1
                continue

            side = str(candidate.get("side") or "BUY").upper()
            entry_fill_price = float(fill["fill_price"])
            entry_ref = float(candidate["execution_entry"])
            exit_price, exit_ts, exit_reason = self._simulate_exit(
                side=side,
                entry_fill_price=entry_fill_price,
                target_price=target_price,
                stop_price=stop_price,
                entry_index=row_index,
                candles=candles,
            )
            if side == "SELL":
                pnl_points = entry_fill_price - exit_price
            else:
                pnl_points = exit_price - entry_fill_price
            hold_minutes = max((exit_ts - row["timestamp"]).total_seconds() / 60.0, 0.0)
            slippage_points = abs(entry_fill_price - entry_ref)
            trade = OptionBacktestTrade(
                symbol=str(candidate["symbol"]),
                side=side,
                entry_ts=row["timestamp"].isoformat(),
                exit_ts=exit_ts.isoformat(),
                entry_reference_price=entry_ref,
                entry_fill_price=entry_fill_price,
                exit_price=float(exit_price),
                quantity=int(self.cfg.quantity),
                target_price=float(target_price),
                stop_price=float(stop_price),
                exit_reason=exit_reason,
                pnl_points=float(pnl_points),
                pnl_value=float(pnl_points) * float(self.cfg.quantity),
                slippage_points=float(slippage_points),
                hold_minutes=float(hold_minutes),
                truth_quality=str(candidate.get("truth_quality") or ""),
                geometry_source=str(candidate.get("source_flags", {}).get("backtest_geometry_source") or ""),
                confidence_raw=_safe_float(candidate.get("confidence_raw")),
                confidence_final=_safe_float(candidate.get("confidence_final")),
                decision_reason=str(decision.get("decision_reason") or ""),
            )
            if exit_reason == "TIME_EXIT":
                diagnostics["late_entries"] += 1
            if exit_reason == "STOP_HIT":
                diagnostics["chop_losses"] += 1
            confidence_key = "high" if (trade.confidence_final or 0.0) >= 0.7 else "low"
            if trade.pnl_value > 0:
                diagnostics["confidence_buckets"][confidence_key]["wins"] += 1
            elif trade.pnl_value < 0:
                diagnostics["confidence_buckets"][confidence_key]["losses"] += 1
            trades.append(trade)
            exit_idx = int(candles.index[candles["timestamp"] == exit_ts][0])
            open_until_index = exit_idx

        summary = summarize_backtest(
            signals_total=signals_total,
            executable_signals=executable_signals,
            trades=trades,
            rejected_reasons=rejected_reasons,
            diagnostics=diagnostics,
        )
        result = OptionBacktestResult(
            config=self.cfg,
            summary=summary,
            trades=trades,
            diagnostics=diagnostics,
            sampled_decisions=sampled_decisions[:200],
        )
        self._write_artifacts(result)
        return result


def run_option_symbol_backtest(cfg: OptionBacktestConfig) -> OptionBacktestResult:
    return OptionBacktestEngine(cfg).run()
