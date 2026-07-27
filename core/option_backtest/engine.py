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
from .models import OptionBacktestConfig, OptionBacktestResult, OptionBacktestTrade, ResearchMode
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


def _safe_timestamp(value: Any, timezone: str) -> pd.Timestamp | None:
    try:
        if value in (None, "", "None"):
            return None
        parsed = pd.Timestamp(value)
        if parsed.tzinfo is None:
            return parsed.tz_localize(timezone)
        return parsed.tz_convert(timezone)
    except Exception:
        return None


class OptionBacktestEngine:
    def __init__(self, cfg: OptionBacktestConfig):
        self.cfg = cfg
        self.fill_model = FillModel()

    def _strict_certification_mode(self) -> bool:
        return self.cfg.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH

    def _decision_rejection_reason(self, decision: dict[str, Any], candidate: dict[str, Any]) -> str:
        decision_reason = str(decision.get("decision_reason") or "").strip()
        execution_block_reason = str(candidate.get("execution_block_reason") or "").strip()
        if decision_reason in {"execution_not_ready", "execution_blocked"} and execution_block_reason:
            return execution_block_reason
        return decision_reason or "unknown"

    def _certification_blockers(
        self,
        *,
        candles: pd.DataFrame,
        trades: list[OptionBacktestTrade],
        summary: dict[str, Any],
        sampled_decisions: list[dict[str, Any]],
    ) -> list[str]:
        blockers: list[str] = []
        if not self._strict_certification_mode():
            return blockers
        if not trades:
            blockers.append("no_certifiable_trades")
        if len(sampled_decisions) != int(summary.get("signals_total", 0)):
            blockers.append("incomplete_decision_retention")
        if "setup_id" not in candles.columns:
            blockers.append("missing_setup_id_column")
        if "regime" not in candles.columns:
            blockers.append("missing_regime_column")
        if "is_oos" not in candles.columns:
            blockers.append("missing_oos_label_column")
        if any(str(trade.setup_id or "").strip().lower() in {"", "unknown"} for trade in trades):
            blockers.append("unknown_setup_id")
        if any(str(trade.regime or "").strip().lower() in {"", "unknown"} for trade in trades):
            blockers.append("unknown_regime")
        if any(not bool(getattr(trade, "oos_label_known", False)) for trade in trades):
            blockers.append("unknown_oos_label")
        required_trade_fields = (
            "source_symbol",
            "provider",
            "dataset_hash",
            "bar_interval",
            "feature_cutoff_ts",
            "signal_ts",
            "earliest_entry_ts",
            "entry_ts",
            "exit_ts",
            "entry_quote_side",
            "exit_quote_side",
            "entry_fill_price",
            "exit_price",
            "quantity",
            "gross_pnl_value",
            "entry_costs",
            "exit_costs",
            "total_costs",
            "net_pnl_value",
            "cost_model_version",
        )
        for trade in trades:
            for field_name in required_trade_fields:
                value = getattr(trade, field_name, None)
                if value is None or value == "":
                    blockers.append(f"missing_trade_field:{field_name}")
        if int(summary.get("ambiguity_count", 0)) != int(summary.get("diagnostics", {}).get("timing_ambiguity_count", 0)):
            blockers.append("ambiguity_summary_mismatch")
        return sorted(set(blockers))

    def _result_label(
        self,
        *,
        summary: dict[str, Any],
        trades: list[OptionBacktestTrade],
        certification_blockers: list[str],
    ) -> str:
        if not self._strict_certification_mode():
            return "PROXY_RESEARCH_ONLY"
        traded_path_proxy = bool(summary.get("diagnostics", {}).get("proxy_exit_mark_rows", 0)) or any(
            trade.exit_fill_source == "mark_fallback" or trade.geometry_source == "derived" for trade in trades
        )
        if traded_path_proxy:
            return "PROXY_RESEARCH_ONLY"
        if certification_blockers:
            return "OPTION_REPLAY_RESEARCH"
        return "CERTIFICATION_CANDIDATE"

    def _simulate_entry(self, candidate: dict[str, Any], row: pd.Series, row_index: int) -> dict[str, Any]:
        side = str(candidate.get("side") or "BUY").upper()
        symbol = str(candidate.get("symbol") or self.cfg.symbol)
        entry_ref = _safe_float(candidate.get("execution_entry"))
        if entry_ref is None:
            return {"status": "SKIPPED", "reason": "missing_execution_entry"}
        order = {"side": side, "symbol": symbol, "qty": int(self.cfg.quantity), "limit_price": float(entry_ref)}
        market_snapshot = {
            "bid": _safe_float(row.get("bid")),
            "ask": _safe_float(row.get("ask")),
            "bid_qty": _safe_float(row.get("bid_qty")) or 0.0,
            "ask_qty": _safe_float(row.get("ask_qty")) or 0.0,
            "volume": _safe_float(row.get("volume")) or 0.0,
            "oi": _safe_float(row.get("oi")) or 0.0,
            "allow_fallback_liquidity": not self._strict_certification_mode(),
        }
        return self.fill_model.simulate(order, market_snapshot, f"{self.cfg.fill_model_run_id}:{row_index}")

    def _compute_side_costs(self, quantity: int) -> float:
        return (
            float(self.cfg.cost_config.brokerage_per_order)
            + float(self.cfg.cost_config.other_fee_per_order)
            + float(self.cfg.cost_config.exchange_fee_per_contract) * float(quantity)
            + float(self.cfg.cost_config.tax_per_contract) * float(quantity)
        )

    def _exit_side_and_reference(
        self, entry_side: str, row: pd.Series, exit_reason: str, target_price: float, stop_price: float
    ) -> tuple[str, float | None]:
        if entry_side == "SELL":
            exit_side = "BUY"
            executable_quote = _safe_float(row.get("ask"))
        else:
            exit_side = "SELL"
            executable_quote = _safe_float(row.get("bid"))
        if exit_reason == "TARGET_HIT":
            trigger_reference = float(target_price)
        elif exit_reason == "STOP_HIT":
            trigger_reference = float(stop_price)
        else:
            trigger_reference = _safe_float(row.get("close"))
        return exit_side, executable_quote if executable_quote is not None else trigger_reference

    def _simulate_exit_fill(
        self,
        *,
        entry_side: str,
        quantity: int,
        row: pd.Series,
        row_index: int,
        exit_reason: str,
        target_price: float,
        stop_price: float,
    ) -> dict[str, Any]:
        exit_side, exit_reference = self._exit_side_and_reference(entry_side, row, exit_reason, target_price, stop_price)
        bid = _safe_float(row.get("bid"))
        ask = _safe_float(row.get("ask"))
        if self._strict_certification_mode() and (bid is None or ask is None or bid <= 0 or ask <= 0):
            return {"status": "NOFILL", "reason": "missing_exit_bid_ask", "fill_qty": 0, "fill_price": None, "used_mark_fallback": False}
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            fill_price = exit_reference if exit_reference is not None else _safe_float(row.get("close"))
            if fill_price is None:
                return {"status": "NOFILL", "reason": "missing_exit_reference", "fill_qty": 0, "fill_price": None, "used_mark_fallback": True}
            return {
                "status": "FILLED",
                "reason": None,
                "fill_qty": int(quantity),
                "fill_price": float(fill_price),
                "slippage_bp": 0.0,
                "used_mark_fallback": True,
                "used_fallback_liquidity": False,
            }
        order = {
            "side": exit_side,
            "symbol": self.cfg.symbol,
            "qty": int(quantity),
            "limit_price": float(bid if exit_side == "SELL" else ask),
        }
        market_snapshot = {
            "bid": bid,
            "ask": ask,
            "bid_qty": _safe_float(row.get("bid_qty")) or 0.0,
            "ask_qty": _safe_float(row.get("ask_qty")) or 0.0,
            "volume": _safe_float(row.get("volume")) or 0.0,
            "oi": _safe_float(row.get("oi")) or 0.0,
            "allow_fallback_liquidity": not self._strict_certification_mode(),
        }
        result = self.fill_model.simulate(order, market_snapshot, f"{self.cfg.fill_model_run_id}:exit:{row_index}")
        result["used_mark_fallback"] = False
        return result

    def _simulate_exit(
        self,
        *,
        side: str,
        target_price: float,
        stop_price: float,
        entry_index: int,
        entry_ts: pd.Timestamp,
        candles: pd.DataFrame,
    ) -> tuple[pd.Series, str, bool]:
        max_exit_ts = entry_ts + pd.Timedelta(minutes=int(self.cfg.max_hold_minutes))

        def _hit_target_or_stop(candle: pd.Series) -> tuple[bool, bool]:
            high = float(candle["high"])
            low = float(candle["low"])
            if side == "SELL":
                return low <= target_price, high >= stop_price
            return high >= target_price, low <= stop_price

        entry_candle = candles.iloc[entry_index]
        entry_tgt_hit, entry_stp_hit = _hit_target_or_stop(entry_candle)
        if entry_tgt_hit and entry_stp_hit:
            return entry_candle, "STOP_HIT", True
        if entry_stp_hit:
            return entry_candle, "STOP_HIT", True

        last_observed = entry_candle
        entry_candle_ambiguous = entry_tgt_hit
        for idx in range(entry_index + 1, len(candles)):
            candle = candles.iloc[idx]
            candle_ts = candle["timestamp"]
            if candle_ts > max_exit_ts:
                break
            last_observed = candle
            tgt_hit, stp_hit = _hit_target_or_stop(candle)
            if tgt_hit and stp_hit:
                return candle, "STOP_HIT", True
            if stp_hit:
                return candle, "STOP_HIT", False
            if tgt_hit:
                return candle, "TARGET_HIT", entry_candle_ambiguous

        timeout_candle = last_observed.copy()
        timeout_candle["timestamp"] = max_exit_ts
        return timeout_candle, "TIME_EXIT", entry_candle_ambiguous

    def _write_artifacts(self, result: OptionBacktestResult) -> None:
        if self.cfg.output_dir is None:
            return
        output_dir = Path(self.cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text(json.dumps(result.summary, indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "trade_journal.json").write_text(json.dumps([trade.__dict__ for trade in result.trades], indent=2), encoding="utf-8")
        (output_dir / "decision_samples.json").write_text(json.dumps(result.sampled_decisions, indent=2), encoding="utf-8")

    def run(self) -> OptionBacktestResult:
        candles = load_option_symbol_csv(
            data_path=self.cfg.data_path,
            symbol=self.cfg.symbol,
            date_from=self.cfg.date_from,
            date_to=self.cfg.date_to,
            timezone=self.cfg.timezone,
            config=self.cfg,
        )
        signals_total = 0
        executable_signals = 0
        rejected_reasons: Counter[str] = Counter()
        diagnostics = {
            "fallback_rows": 0,
            "derived_geometry_rows": 0,
            "derived_timing_rows": 0,
            "missing_signal_rows": 0,
            "missing_bid_ask_rows": int((~candles["has_bid_ask"]).sum()),
            "missing_timing_rows": 0,
            "timing_ambiguity_count": 0,
            "proxy_exit_mark_rows": 0,
            "strict_exit_quote_rejections": 0,
            "late_entries": 0,
            "chop_losses": 0,
            "confidence_buckets": {"high": {"wins": 0, "losses": 0}, "low": {"wins": 0, "losses": 0}},
        }
        trades: list[OptionBacktestTrade] = []
        sampled_decisions: list[dict[str, Any]] = []
        open_until_index = -1
        candle_epochs = candles["timestamp"].map(lambda ts: float(ts.timestamp()))
        replay_contract = candles.attrs.get("replay_contract", {})

        for row_index, row in candles.iterrows():
            candidate = build_candidate_from_candle(row.to_dict(), self.cfg)
            signals_total += 1
            if candidate.get("truth_quality") == "FALLBACK":
                diagnostics["fallback_rows"] += 1
            if candidate.get("source_flags", {}).get("backtest_geometry_source") == "derived":
                diagnostics["derived_geometry_rows"] += 1
            if candidate.get("source_flags", {}).get("backtest_timing_source") == "derived":
                diagnostics["derived_timing_rows"] += 1
            if candidate.get("confidence_raw") is None and candidate.get("confidence_final") is None:
                diagnostics["missing_signal_rows"] += 1
            if candidate.get("feature_cutoff_ts") is None or candidate.get("signal_ts") is None or candidate.get("earliest_entry_ts") is None:
                diagnostics["missing_timing_rows"] += 1

            decision = evaluate_candidate_decision(candidate)
            rejection_reason = self._decision_rejection_reason(decision, candidate)
            sampled_decisions.append(
                {
                    "decision_index": int(row_index),
                    "timestamp": candidate["timestamp"],
                    "symbol": candidate["symbol"],
                    "truth_quality": decision.get("truth_quality"),
                    "decision_reason": decision.get("decision_reason"),
                    "rejection_reason": rejection_reason if decision.get("execution_status") != "executable" else None,
                    "execution_block_reason": candidate.get("execution_block_reason"),
                    "permission": decision.get("permission"),
                    "execution_status": decision.get("execution_status"),
                    "selected_for_execution": bool(candidate.get("selected_for_execution")),
                    "confidence_raw": candidate.get("confidence_raw"),
                    "confidence_final": candidate.get("confidence_final"),
                    "feature_cutoff_ts": candidate.get("feature_cutoff_ts"),
                    "signal_ts": candidate.get("signal_ts"),
                    "earliest_entry_ts": candidate.get("earliest_entry_ts"),
                }
            )
            if decision.get("execution_status") == "executable":
                executable_signals += 1
            else:
                rejected_reasons[rejection_reason] += 1

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
            earliest_entry_epoch = _safe_float(candidate.get("earliest_entry_ts_epoch"))
            if earliest_entry_epoch is None:
                rejected_reasons["missing_signal_timing_provenance"] += 1
                continue
            eligible_indexes = candle_epochs[candle_epochs >= float(earliest_entry_epoch)].index
            if len(eligible_indexes) == 0:
                rejected_reasons["no_eligible_entry_candle"] += 1
                continue
            entry_index = int(eligible_indexes[0])
            if entry_index <= row_index:
                rejected_reasons["ambiguous_signal_timing"] += 1
                continue
            if entry_index <= open_until_index:
                continue
            entry_row = candles.iloc[entry_index]
            if self._strict_certification_mode():
                entry_quote_ts = _safe_timestamp(entry_row.get("quote_timestamp"), self.cfg.timezone)
                signal_ts = _safe_timestamp(candidate.get("signal_ts"), self.cfg.timezone)
                if entry_quote_ts is None:
                    rejected_reasons["missing_entry_quote_timestamp"] += 1
                    continue
                if signal_ts is None:
                    rejected_reasons["missing_signal_timing_provenance"] += 1
                    continue
                if entry_quote_ts <= signal_ts:
                    rejected_reasons["entry_quote_before_signal"] += 1
                    continue

            fill = self._simulate_entry(candidate, entry_row, entry_index)
            if fill.get("status") not in {"FILLED", "PARTIAL"}:
                rejected_reasons[str(fill.get("reason") or "entry_not_filled")] += 1
                continue

            side = str(candidate.get("side") or "BUY").upper()
            entry_fill_price = float(fill["fill_price"])
            entry_ref = float(candidate["execution_entry"])
            entry_fill_qty = int(fill.get("fill_qty", self.cfg.quantity))
            exit_row, exit_reason, timing_ambiguity = self._simulate_exit(
                side=side,
                target_price=target_price,
                stop_price=stop_price,
                entry_index=entry_index,
                entry_ts=entry_row["timestamp"],
                candles=candles,
            )
            exit_fill = self._simulate_exit_fill(
                entry_side=side,
                quantity=entry_fill_qty,
                row=exit_row,
                row_index=int(getattr(exit_row, "name", entry_index)),
                exit_reason=exit_reason,
                target_price=target_price,
                stop_price=stop_price,
            )
            if exit_fill.get("status") not in {"FILLED", "PARTIAL"}:
                rejected_reasons[str(exit_fill.get("reason") or "exit_not_filled")] += 1
                if str(exit_fill.get("reason") or "") == "missing_exit_bid_ask":
                    diagnostics["strict_exit_quote_rejections"] += 1
                continue
            exit_fill_qty = int(exit_fill.get("fill_qty", entry_fill_qty))
            closed_qty = int(min(entry_fill_qty, exit_fill_qty))
            if closed_qty <= 0:
                rejected_reasons["exit_zero_fill_qty"] += 1
                continue
            exit_price = float(exit_fill["fill_price"])
            exit_ref = _safe_float(exit_row.get("bid")) if side != "SELL" else _safe_float(exit_row.get("ask"))
            exit_ts = exit_row["timestamp"]
            pnl_points = entry_fill_price - exit_price if side == "SELL" else exit_price - entry_fill_price
            hold_minutes = max((exit_ts - entry_row["timestamp"]).total_seconds() / 60.0, 0.0)
            entry_slippage_points = abs(entry_fill_price - entry_ref)
            exit_slippage_points = abs(exit_price - (exit_ref if exit_ref is not None else exit_price))
            gross_pnl_value = float(pnl_points) * float(closed_qty)
            entry_costs = self._compute_side_costs(closed_qty)
            exit_costs = self._compute_side_costs(closed_qty)
            total_costs = entry_costs + exit_costs
            net_pnl_value = gross_pnl_value - total_costs
            trade = OptionBacktestTrade(
                symbol=str(candidate["symbol"]),
                source_symbol=str(candidate.get("source_symbol") or candidate["symbol"]),
                underlying=str(candidate.get("underlying") or replay_contract.get("underlying") or ""),
                option_type=str(candidate.get("option_type") or replay_contract.get("option_type") or ""),
                strike=float(candidate.get("strike") or replay_contract.get("strike") or 0.0),
                expiry=str(candidate.get("expiry") or replay_contract.get("expiry") or ""),
                provider=str(candidate.get("provider") or replay_contract.get("provider") or ""),
                dataset_hash=str(candidate.get("dataset_hash") or replay_contract.get("dataset_hash") or ""),
                bar_interval=str(candidate.get("bar_interval") or replay_contract.get("bar_interval") or ""),
                side=side,
                entry_ts=entry_row["timestamp"].isoformat(),
                exit_ts=exit_ts.isoformat(),
                entry_reference_price=entry_ref,
                entry_fill_price=entry_fill_price,
                exit_reference_price=float(exit_ref if exit_ref is not None else exit_price),
                exit_price=float(exit_price),
                entry_bid=_safe_float(entry_row.get("bid")),
                entry_ask=_safe_float(entry_row.get("ask")),
                exit_bid=_safe_float(exit_row.get("bid")),
                exit_ask=_safe_float(exit_row.get("ask")),
                entry_quote_side="ask" if side == "BUY" else "bid",
                exit_quote_side="ask" if side == "SELL" else "bid",
                quantity=closed_qty,
                entry_fill_qty=entry_fill_qty,
                exit_fill_qty=exit_fill_qty,
                target_price=float(target_price),
                stop_price=float(stop_price),
                exit_reason=exit_reason,
                pnl_points=float(pnl_points),
                gross_pnl_value=float(gross_pnl_value),
                total_costs=float(total_costs),
                net_pnl_value=float(net_pnl_value),
                entry_costs=float(entry_costs),
                exit_costs=float(exit_costs),
                entry_slippage_points=float(entry_slippage_points),
                exit_slippage_points=float(exit_slippage_points),
                hold_minutes=float(hold_minutes),
                truth_quality=str(candidate.get("truth_quality") or ""),
                geometry_source=str(candidate.get("source_flags", {}).get("backtest_geometry_source") or ""),
                confidence_raw=_safe_float(candidate.get("confidence_raw")),
                confidence_final=_safe_float(candidate.get("confidence_final")),
                decision_reason=str(decision.get("decision_reason") or ""),
                feature_cutoff_ts=str(candidate.get("feature_cutoff_ts") or ""),
                signal_ts=str(candidate.get("signal_ts") or ""),
                earliest_entry_ts=str(candidate.get("earliest_entry_ts") or ""),
                timing_ambiguity=bool(timing_ambiguity),
                ambiguity_count=1 if timing_ambiguity else 0,
                exit_fill_source="mark_fallback" if exit_fill.get("used_mark_fallback") else "quote_side",
                cost_model_version=self.cfg.cost_config.version,
                fill_model_run_id=self.cfg.fill_model_run_id,
                setup_id=str(candidate.get("setup_id") or "unknown"),
                regime=str(candidate.get("regime") or "unknown"),
                is_oos=bool(candidate.get("is_oos")),
                oos_label_known="is_oos" in candles.columns,
            )
            if exit_reason == "TIME_EXIT":
                diagnostics["late_entries"] += 1
            if exit_reason == "STOP_HIT":
                diagnostics["chop_losses"] += 1
            if timing_ambiguity:
                diagnostics["timing_ambiguity_count"] += 1
            if exit_fill.get("used_mark_fallback"):
                diagnostics["proxy_exit_mark_rows"] += 1
            confidence_key = "high" if (trade.confidence_final or 0.0) >= 0.7 else "low"
            if trade.net_pnl_value > 0:
                diagnostics["confidence_buckets"][confidence_key]["wins"] += 1
            elif trade.net_pnl_value < 0:
                diagnostics["confidence_buckets"][confidence_key]["losses"] += 1
            trades.append(trade)
            consumed_indexes = candles.index[candles["timestamp"] <= exit_ts]
            open_until_index = int(consumed_indexes[-1]) if len(consumed_indexes) else entry_index

        summary = summarize_backtest(
            signals_total=signals_total,
            executable_signals=executable_signals,
            trades=trades,
            rejected_reasons=rejected_reasons,
            diagnostics=diagnostics,
        )
        summary["reconciliation"]["decision_rows"] = len(sampled_decisions)
        summary["decision_rows"] = len(sampled_decisions)
        summary["trade_rows"] = len(trades)
        summary["decision_artifact"] = "decision_samples.json" if self.cfg.output_dir is not None else None
        summary["append"] = False
        summary["read_only"] = True
        summary["is_order_action"] = False
        summary["broker_api_called"] = False
        summary["allowed_for_live_execution"] = False
        certification_blockers = self._certification_blockers(
            candles=candles,
            trades=trades,
            summary=summary,
            sampled_decisions=sampled_decisions,
        )
        summary["certification_blockers"] = certification_blockers
        summary["certifiable"] = not certification_blockers
        summary["result_label"] = self._result_label(
            summary=summary,
            trades=trades,
            certification_blockers=certification_blockers,
        )
        result = OptionBacktestResult(
            config=self.cfg,
            summary=summary,
            trades=trades,
            diagnostics=diagnostics,
            sampled_decisions=sampled_decisions,
        )
        self._write_artifacts(result)
        return result


def run_option_symbol_backtest(cfg: OptionBacktestConfig) -> OptionBacktestResult:
    return OptionBacktestEngine(cfg).run()
