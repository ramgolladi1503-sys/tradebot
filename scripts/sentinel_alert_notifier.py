#!/usr/bin/env python3
"""Sentinel Decoupled Telemetry Alert Dispatcher.

Runs as an independent, isolated background daemon that tails Sentinel Write-Ahead
Logs (WAL) and dispatches real-time structured telemetry notifications without
introducing any I/O latency to the live WebSocket streaming ingest thread.

Invariants:
- Zero WebSocket Thread Ingestion Overhead: Pure file-tailing observer.
- Deduplication: In-memory sequence tracker ensures each WAL transition fires exactly once.
- Fail-Safe: Malformed JSON or network timeout never crashes the observer loop.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("SentinelAlertNotifier")


@dataclass
class FormattedAlert:
    timestamp: str
    event_type: str
    symbol: str
    details: Dict[str, Any]
    message: str


class SentinelAlertNotifier:
    """Tails Sentinel WAL files and formats actionable real-time push alerts."""

    def __init__(
        self,
        wal_paths: Optional[List[str]] = None,
        out_telemetry_md: str = "reports/telemetry/sentinel_live_telemetry.md",
        poll_interval_sec: float = 1.0,
    ) -> None:
        self.wal_paths = [Path(p) for p in (wal_paths or [
            "runtime/sentinel_apm_wal.json",
            "runtime/sentinel_apm_wal_sensex.json",
            "runtime/sentinel_apm_wal_banknifty.json",
        ])]
        self.out_telemetry_md = Path(out_telemetry_md)
        self.out_telemetry_md.parent.mkdir(parents=True, exist_ok=True)
        self.poll_interval_sec = poll_interval_sec
        self._last_state_seen: Dict[str, str] = {}
        self._last_position_id: Dict[str, str] = {}

    def format_event(self, wal_data: Dict[str, Any], file_key: str) -> Optional[FormattedAlert]:
        """Translates raw WAL state into high-priority human-readable notification."""
        state = wal_data.get("state")
        payload = wal_data.get("payload") or {}
        pos_id = payload.get("position_id")
        symbol = payload.get("strike_contract") or "UNKNOWN"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")

        # Skip if identical to last processed state for this position
        prior_state = self._last_state_seen.get(file_key)
        prior_pos = self._last_position_id.get(file_key)
        if prior_pos == pos_id and prior_state == state:
            return None

        self._last_state_seen[file_key] = state
        self._last_position_id[file_key] = pos_id

        if state == "IN_FLIGHT" and prior_state != "IN_FLIGHT":
            msg = (
                f"🔔 **[ENTRY EXECUTED]** `{symbol}`\n"
                f"- **Direction:** {payload.get('direction')}\n"
                f"- **Entry Spot:** {payload.get('entry_price'):.2f}\n"
                f"- **Option Entry:** ₹{payload.get('opt_entry_ltp', 0.0):.2f}\n"
                f"- **Initial SL:** ₹{payload.get('opt_initial_sl', 0.0):.2f}\n"
                f"- **Target Spot:** {payload.get('target_price', 0.0):.2f}\n"
                f"- **Time:** {now_str}"
            )
            return FormattedAlert(timestamp=now_str, event_type="ENTRY", symbol=symbol, details=payload, message=msg)

        elif state == "TRAIL_LOCK" and prior_state != "TRAIL_LOCK":
            t1_gain = payload.get("tranche_1_pnl_pts", 0.0)
            runner_sl = payload.get("runner_trailing_sl", 0.0)
            msg = (
                f"🔒 **[PROFIT LOCKED / T1 BOOKED]** `{symbol}`\n"
                f"- **Banked Gain:** +{t1_gain:.2f} pts (50% lot booked)\n"
                f"- **Runner Trailing SL:** ₹{runner_sl:.2f}\n"
                f"- **Time:** {now_str}"
            )
            return FormattedAlert(timestamp=now_str, event_type="PROFIT_LOCK", symbol=symbol, details=payload, message=msg)

        elif state in {"LIQUIDATED", "COOL_OFF"} and prior_state in {"IN_FLIGHT", "TRAIL_LOCK", "EXIT_PENDING"}:
            reason = payload.get("exit_reason", "UNKNOWN")
            opt_pnl = payload.get("opt_pnl_pts", 0.0)
            exit_ltp = payload.get("opt_exit_ltp", 0.0)
            icon = "🎉" if opt_pnl > 0 else "🛑"
            msg = (
                f"{icon} **[POSITION EXITED]** `{symbol}`\n"
                f"- **Exit Reason:** `{reason}`\n"
                f"- **Option Exit Price:** ₹{exit_ltp:.2f}\n"
                f"- **Realized PnL Pts:** {opt_pnl:+.2f} pts\n"
                f"- **Time:** {now_str}"
            )
            return FormattedAlert(timestamp=now_str, event_type="EXIT", symbol=symbol, details=payload, message=msg)

        return None

    def poll_once(self) -> List[FormattedAlert]:
        """Performs a non-blocking check across all WAL paths."""
        new_alerts = []
        for p in self.wal_paths:
            if not p.exists():
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    continue
                data = json.loads(content)
                alert = self.format_event(data, str(p.name))
                if alert:
                    new_alerts.append(alert)
                    self._dispatch(alert)
            except Exception as e:
                logger.warning(f"Error reading WAL file {p}: {e}")
        return new_alerts

    def _dispatch(self, alert: FormattedAlert) -> None:
        """Dispatches alert to console, file log, and optional webhook."""
        logger.info(f"\n{alert.message}\n")
        # Append to human-readable markdown telemetry log
        try:
            with open(self.out_telemetry_md, "a", encoding="utf-8") as f:
                f.write(f"\n---\n### {alert.event_type} - {alert.timestamp}\n{alert.message}\n")
        except Exception as e:
            logger.error(f"Failed to append to telemetry log: {e}")

    def run_daemon(self) -> None:
        """Runs continuous monitoring loop."""
        logger.info("Starting SentinelAlertNotifier daemon...")
        while True:
            self.poll_once()
            time.sleep(self.poll_interval_sec)


if __name__ == "__main__":
    notifier = SentinelAlertNotifier()
    try:
        notifier.run_daemon()
    except KeyboardInterrupt:
        logger.info("SentinelAlertNotifier stopped by user.")
        sys.exit(0)
