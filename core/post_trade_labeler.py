from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.time_utils import now_ist


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _parse_iso_to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _outcome_from_pnl(realized_pnl: float, epsilon: float = 1e-6) -> str:
    if realized_pnl > epsilon:
        return "WIN"
    if realized_pnl < -epsilon:
        return "LOSS"
    return "BREAKEVEN"


@dataclass
class PostTradeLabeler:
    output_dir: str = "data/training"

    def _date_tag_from_epoch(self, ts_epoch: float | None) -> str:
        if ts_epoch is None:
            return now_ist().date().isoformat()
        try:
            return datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc).astimezone(
                timezone.utc
            ).date().isoformat()
        except Exception:
            return now_ist().date().isoformat()

    def _output_path(self, ts_epoch: float | None) -> Path:
        date_tag = self._date_tag_from_epoch(ts_epoch)
        root = Path(self.output_dir)
        root.mkdir(parents=True, exist_ok=True)
        return root / f"trade_labels_{date_tag}.jsonl"

    def build_label(
        self,
        trade_row: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
        decision_trace_id: str | None = None,
        features_snapshot: dict[str, Any] | None = None,
        regime_at_entry: str | None = None,
    ) -> dict[str, Any]:
        meta = dict(meta or {})
        trade_id = str(trade_row.get("trade_id") or "")
        if not trade_id:
            raise ValueError("label_error:missing_trade_id")

        entry_epoch = trade_row.get("timestamp_epoch")
        if entry_epoch is None:
            entry_epoch = _parse_iso_to_epoch(trade_row.get("timestamp"))
        if entry_epoch is None:
            entry_epoch = meta.get("entry_time")
        if entry_epoch is not None:
            entry_epoch = _safe_float(entry_epoch, default=0.0)

        exit_epoch = _parse_iso_to_epoch(trade_row.get("exit_time"))
        if exit_epoch is None:
            exit_epoch = time.time()

        entry_price = _safe_float(trade_row.get("entry"))
        exit_price = _safe_float(trade_row.get("exit_price"))
        stop_price = _safe_float(trade_row.get("stop_loss"))
        target_price = _safe_float(trade_row.get("target"))
        side = str(trade_row.get("side") or "BUY").upper()
        qty_units = int(trade_row.get("qty_units") or 0)
        if qty_units <= 0:
            qty_units = int(trade_row.get("qty") or 0)

        realized_pnl = trade_row.get("realized_pnl")
        if realized_pnl is None:
            direction_mult = 1.0 if side == "BUY" else -1.0
            realized_pnl = (exit_price - entry_price) * qty_units * direction_mult
        realized_pnl = _safe_float(realized_pnl)

        initial_risk_rupees = abs(entry_price - stop_price) * max(qty_units, 0)
        if initial_risk_rupees > 0:
            r_multiple = realized_pnl / initial_risk_rupees
        else:
            r_multiple = _safe_float(trade_row.get("r_multiple_realized"), default=0.0)

        hold_time_sec = None
        if entry_epoch is not None:
            hold_time_sec = max(0.0, float(exit_epoch) - float(entry_epoch))

        mae = meta.get("mae_15m")
        if mae is None:
            mae = meta.get("mae")
        mfe = meta.get("mfe_15m")
        if mfe is None:
            mfe = meta.get("mfe")

        label = {
            "trade_id": trade_id,
            "trace_id": trade_id,
            "decision_trace_id": decision_trace_id or trade_row.get("decision_trace_id") or trade_id,
            "timestamp_epoch": float(exit_epoch),
            "timestamp_iso": datetime.fromtimestamp(float(exit_epoch), tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "entry_timestamp_epoch": float(entry_epoch) if entry_epoch is not None else None,
            "symbol": trade_row.get("symbol"),
            "strategy": trade_row.get("strategy"),
            "regime_at_entry": regime_at_entry or meta.get("regime_at_entry") or trade_row.get("regime"),
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "stop_loss": stop_price,
            "target": target_price,
            "qty_units": qty_units,
            "qty_lots": trade_row.get("qty_lots"),
            "hold_time_sec": hold_time_sec,
            "pnl": realized_pnl,
            "r_multiple": float(r_multiple),
            "mae": _safe_float(mae, default=0.0),
            "mfe": _safe_float(mfe, default=0.0),
            "label": _outcome_from_pnl(realized_pnl),
            "features_snapshot": features_snapshot
            if features_snapshot is not None
            else dict(meta.get("features_snapshot") or {}),
        }
        return label

    def label_and_persist(
        self,
        trade_row: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
        decision_trace_id: str | None = None,
        features_snapshot: dict[str, Any] | None = None,
        regime_at_entry: str | None = None,
    ) -> dict[str, Any]:
        label = self.build_label(
            trade_row,
            meta=meta,
            decision_trace_id=decision_trace_id,
            features_snapshot=features_snapshot,
            regime_at_entry=regime_at_entry,
        )
        out_path = self._output_path(label.get("timestamp_epoch"))
        with out_path.open("a") as handle:
            handle.write(json.dumps(label, default=str) + "\n")
        return label

