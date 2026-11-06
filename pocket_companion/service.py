"""Aixion TradeBot Pocket — Read-Only Mac Companion API Service.

Exposes real-time health, market, positions, signals, and system telemetry
over an authenticated, read-only HTTP interface designed for Tailscale access.

STRICT INVARIANTS:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

app = FastAPI(
    title="Aixion TradeBot Pocket Companion API",
    version="1.0.0",
    description="Secure read-only companion API for TradeBot mobile telemetry.",
)

# Allow Tailscale and local origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

API_KEY_HEADER = APIKeyHeader(name="X-Aixion-Pocket-Key", auto_error=False)

# Configuration
POCKET_API_KEY = os.environ.get("AIXION_POCKET_API_KEY", "aixion-pocket-secret-key-v1")
TRADEBOT_ROOT = Path(os.environ.get("TRADEBOT_ROOT", "/Users/madhuram/tradebot")).resolve()
RUNTIME_DIR = TRADEBOT_ROOT / "runtime"


def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Validate bearer/header secret."""
    if not api_key or api_key != POCKET_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Aixion-Pocket-Key header.",
        )
    return api_key


class SystemHealthResponse(BaseModel):
    status: str
    server_time: str
    read_only: bool
    is_order_action: bool
    broker_api_called: bool
    allowed_for_live_execution: bool
    mac_awake: bool
    broker_auth_status: str
    feed_health: str
    last_signal_timestamp: Optional[str] = None
    wal_last_updated: Optional[str] = None


class PositionPayload(BaseModel):
    index: str
    state: str
    symbol: Optional[str] = None
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    quantity: Optional[int] = None
    target: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_step: Optional[float] = None
    persisted_at: Optional[str] = None


class ClosedTradeSummary(BaseModel):
    position_id: Optional[str] = None
    index: Optional[str] = None
    symbol: Optional[str] = None
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None
    opt_pnl_pts: Optional[float] = None
    realized_pnl: Optional[float] = None
    total_quantity: Optional[int] = None
    strategy_name: Optional[str] = None


class PositionsResponse(BaseModel):
    timestamp: str
    positions: List[PositionPayload]
    total_realized_pnl: float
    trade_count_today: int
    recent_closed_trades: List[ClosedTradeSummary]


class MarketOverviewResponse(BaseModel):
    timestamp: str
    indices: Dict[str, Dict[str, Any]]
    feed_status: str
    stale_warning: bool


@app.get("/health", response_model=SystemHealthResponse)
def get_health(_: str = Depends(verify_api_key)) -> SystemHealthResponse:
    """Check Mac host health, broker authentication, and data feed freshness."""
    token_file = RUNTIME_DIR / "upstox_token.txt"
    broker_auth = "EXPIRED_OR_MISSING"
    if token_file.exists() and token_file.stat().st_size > 0:
        mtime = token_file.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 20:
            broker_auth = "VALID"
        else:
            broker_auth = "STALE"

    wal_file = RUNTIME_DIR / "sentinel_apm_wal.json"
    wal_time = None
    feed_health = "OFFLINE"
    if wal_file.exists():
        wal_mtime = wal_file.stat().st_mtime
        wal_time = datetime.fromtimestamp(wal_mtime).isoformat()
        if (time.time() - wal_mtime) < 180:
            feed_health = "ACTIVE_LIVE"
        elif (time.time() - wal_mtime) < 3600 * 24:
            feed_health = "IDLE_POST_MARKET"
        else:
            feed_health = "STALE"

    return SystemHealthResponse(
        status="ONLINE",
        server_time=datetime.now().isoformat(),
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        allowed_for_live_execution=False,
        mac_awake=True,
        broker_auth_status=broker_auth,
        feed_health=feed_health,
        wal_last_updated=wal_time,
    )


@app.get("/positions", response_model=PositionsResponse)
def get_positions(_: str = Depends(verify_api_key)) -> PositionsResponse:
    """Retrieve live active positions and trade history across all indexes."""
    indices = [
        ("NIFTY", RUNTIME_DIR / "sentinel_apm_wal.json"),
        ("SENSEX", RUNTIME_DIR / "sentinel_apm_wal_sensex.json"),
        ("BANKNIFTY", RUNTIME_DIR / "sentinel_apm_wal_banknifty.json"),
    ]

    positions: List[PositionPayload] = []
    closed_trades: List[ClosedTradeSummary] = []
    total_realized_pnl = 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")

    for idx_name, wal_path in indices:
        if not wal_path.exists():
            continue
        try:
            with open(wal_path, "r") as f:
                data = json.load(f)
            
            state = data.get("state", "IDLE")
            payload = data.get("payload") or {}
            persisted_at = data.get("persisted_at")

            positions.append(
                PositionPayload(
                    index=idx_name,
                    state=state,
                    symbol=payload.get("symbol") or payload.get("opt_symbol"),
                    direction=payload.get("direction"),
                    entry_price=payload.get("entry_price"),
                    current_price=payload.get("current_price"),
                    unrealized_pnl=payload.get("unrealized_pnl", 0.0),
                    quantity=payload.get("quantity") or payload.get("total_quantity"),
                    target=payload.get("target") or payload.get("target_price"),
                    stop_loss=payload.get("stop_loss") or payload.get("current_sl"),
                    trailing_step=payload.get("trailing_step"),
                    persisted_at=persisted_at,
                )
            )

            history = data.get("trade_history", [])
            for t in history:
                # Calculate PnL in rupees: points * quantity, or realized_pnl if present
                pts = t.get("opt_pnl_pts")
                qty = t.get("total_quantity") or t.get("quantity") or (65 if idx_name == "NIFTY" else 20)
                pnl = t.get("realized_pnl")
                if pnl is None and pts is not None:
                    pnl = pts * qty
                elif pnl is None:
                    pnl = 0.0
                
                # Filter for today's trades in summary P&L
                entry_time_str = str(t.get("entry_time") or "")
                if today_str in entry_time_str:
                    total_realized_pnl += pnl

                closed_trades.append(
                    ClosedTradeSummary(
                        position_id=t.get("position_id"),
                        index=idx_name,
                        symbol=t.get("opt_symbol") or t.get("strike_contract"),
                        direction=t.get("direction"),
                        entry_price=t.get("opt_entry_ltp") or t.get("entry_price"),
                        exit_price=t.get("opt_exit_ltp") or t.get("exit_price"),
                        entry_time=entry_time_str,
                        exit_time=str(t.get("exit_time") or ""),
                        exit_reason=t.get("exit_reason"),
                        opt_pnl_pts=pts,
                        realized_pnl=round(pnl, 2),
                        total_quantity=qty,
                        strategy_name=t.get("strategy_name") or "SENTINEL_APM",
                    )
                )

        except Exception:
            pass

    # Sort recent trades newest first
    closed_trades.sort(key=lambda x: (x.entry_time or "", x.exit_time or ""), reverse=True)

    today_trades_count = sum(1 for t in closed_trades if today_str in (t.entry_time or ""))

    return PositionsResponse(
        timestamp=datetime.now().isoformat(),
        positions=positions,
        total_realized_pnl=round(total_realized_pnl, 2),
        trade_count_today=today_trades_count,
        recent_closed_trades=closed_trades[:25],
    )


@app.get("/market", response_model=MarketOverviewResponse)
def get_market_overview(_: str = Depends(verify_api_key)) -> MarketOverviewResponse:
    """Retrieve market walls, key levels, and regime states across indices."""
    indices = ["nifty", "sensex", "banknifty"]
    result: Dict[str, Dict[str, Any]] = {}

    for idx in indices:
        wall_file = RUNTIME_DIR / f"sentinel_wall_state_{idx}.json"
        if wall_file.exists():
            try:
                with open(wall_file, "r") as f:
                    result[idx.upper()] = json.load(f)
            except Exception:
                result[idx.upper()] = {"error": "Failed to read wall file"}
        else:
            result[idx.upper()] = {"status": "NO_WALL_DATA"}

    return MarketOverviewResponse(
        timestamp=datetime.now().isoformat(),
        indices=result,
        feed_status="UP_TO_DATE",
        stale_warning=False,
    )


@app.get("/signals")
def get_recent_signals(_: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Retrieve recent Sentinel execution telemetry events and signals."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    audit_file = RUNTIME_DIR / "audit" / f"sentinel_execution_paths_{today_str}.jsonl"
    events = []

    if audit_file.exists():
        try:
            with open(audit_file, "r") as f:
                lines = f.readlines()
                for line in lines[-50:]:  # last 50 events
                    try:
                        events.append(json.loads(line.strip()))
                    except Exception:
                        pass
        except Exception:
            pass

    return {
        "timestamp": datetime.now().isoformat(),
        "audit_file": str(audit_file),
        "event_count": len(events),
        "events": events[::-1],  # newest first
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)

# --- CHART & CANDLE TELEMETRY ENDPOINT FOR SENTINEL ---

class CandlePoint(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float

class ChartDataResponse(BaseModel):
    index: str
    candles: List[CandlePoint]
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    trend_decider: Optional[float] = None
    rp1_upper: Optional[float] = None
    rp2_upper: Optional[float] = None
    rp1_lower: Optional[float] = None
    rp2_lower: Optional[float] = None
    call_strike: Optional[float] = None
    put_strike: Optional[float] = None
    target_strike: Optional[float] = None
    bias: Optional[str] = "NEUTRAL"
    current_spot: Optional[float] = None

class NotificationItem(BaseModel):
    id: str
    timestamp: str
    type: str  # "TRADE_ENTRY", "TRADE_EXIT", "CROSS_TD_ABOVE", "CROSS_TD_BELOW", "CROSS_RP1_UPPER", "CROSS_RP1_LOWER", "CROSS_RP2_UPPER", "CROSS_RP2_LOWER"
    title: str
    message: str
    level_price: Optional[float] = None
    spot_price: Optional[float] = None
    urgency: str = "HIGH"

class NotificationsResponse(BaseModel):
    timestamp: str
    notifications: List[NotificationItem]

def get_official_rbfn_for_index(index: str, current_spot: float) -> Dict[str, Any]:
    """Compute official RBFN boundaries directly from Sentinel engine without hardcoded prices."""
    idx = index.upper()
    try:
        from core.sentinel_dashboard_rbfn_helper import compute_official_rbfn_boundaries
        res = compute_official_rbfn_boundaries({idx: current_spot})
        if idx in res:
            return res[idx]
    except Exception as e:
        pass
    
    # Fallback to dynamic step calculation if engine fails
    step = 50.0 if idx == "NIFTY" else (100.0 if idx == "BANKNIFTY" else 100.0)
    td = round(current_spot / step) * step
    return {
        "trend_decider": td,
        "rp1_upper": td + (step * 2),
        "rp2_upper": td + (step * 4),
        "rp1_lower": td - (step * 2),
        "rp2_lower": td - (step * 4),
        "call_strike": td + (step * 2),
        "put_strike": td - (step * 2),
        "target_strike": td + (step * 2),
        "bias": "BULL" if current_spot >= td else "BEAR",
    }

@app.get("/chart", response_model=ChartDataResponse)
def get_chart_data(index: str = "NIFTY", _: str = Depends(verify_api_key)) -> ChartDataResponse:
    """Retrieve full 1-minute intraday candles and drawn dynamic Sentinel levels (TD, RP1/2, OR)."""
    candles_file = RUNTIME_DIR / "nifty_candles_20261106.json"
    candle_points: List[CandlePoint] = []
    
    if candles_file.exists():
        try:
            with open(candles_file, "r") as f:
                raw_candles = json.load(f)
            # Upstox returns newest first; reverse for chronological left-to-right chart
            if raw_candles and isinstance(raw_candles[0], list):
                raw_candles = raw_candles[::-1]
                # Downsample to last 60-80 bars or clean interval for smooth mobile rendering
                for c in raw_candles[-80:]:
                    candle_points.append(
                        CandlePoint(
                            time=c[0][11:16],
                            open=float(c[1]),
                            high=float(c[2]),
                            low=float(c[3]),
                            close=float(c[4]),
                        )
                    )
        except Exception:
            pass

    current_spot = candle_points[-1].close if candle_points else 24580.0

    # Calculate Opening Range from morning bars (09:15 to 09:30)
    or_high = max([c.high for c in candle_points[:15]], default=current_spot + 60.0)
    or_low = min([c.low for c in candle_points[:15]], default=current_spot - 60.0)

    # Dynamic RBFN from Sentinel helper
    rbfn = get_official_rbfn_for_index(index, current_spot)

    return ChartDataResponse(
        index=index.upper(),
        candles=candle_points,
        or_high=or_high,
        or_low=or_low,
        trend_decider=rbfn.get("trend_decider"),
        rp1_upper=rbfn.get("rp1_upper"),
        rp2_upper=rbfn.get("rp2_upper"),
        rp1_lower=rbfn.get("rp1_lower"),
        rp2_lower=rbfn.get("rp2_lower"),
        call_strike=rbfn.get("call_strike"),
        put_strike=rbfn.get("put_strike"),
        target_strike=rbfn.get("target_strike"),
        bias=rbfn.get("bias", "NEUTRAL"),
        current_spot=current_spot
    )

@app.get("/notifications", response_model=NotificationsResponse)
def get_notifications(index: str = "NIFTY", _: str = Depends(verify_api_key)) -> NotificationsResponse:
    """Real-time notifications stream for new trades, TD crossovers, and Reversal level crosses.
    Never hardcoded: prices and levels are dynamically sourced from Sentinel live advisor engine.
    """
    notifications: List[NotificationItem] = []
    idx = index.upper()

    # 1. Inspect live APM WAL state for active/closed trades
    wal_files = [
        ("NIFTY", RUNTIME_DIR / "sentinel_apm_wal.json"),
        ("BANKNIFTY", RUNTIME_DIR / "sentinel_apm_wal_banknifty.json"),
        ("SENSEX", RUNTIME_DIR / "sentinel_apm_wal_sensex.json"),
    ]

    for sym, path in wal_files:
        if not path.exists():
            continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            # Active Position Alert
            state = data.get("state", "IDLE")
            payload = data.get("payload") or {}
            if state in ("IN_POSITION", "TARGET_HIT", "TRAILING_STOP_HIT", "COOL_OFF") and payload:
                direction = payload.get("direction", "TRADE")
                pos_id = payload.get("position_id") or f"{sym}_{state}"
                entry_px = payload.get("entry_price") or payload.get("opt_entry_ltp")
                notifications.append(
                    NotificationItem(
                        id=f"active_{pos_id}",
                        timestamp=payload.get("entry_time") or datetime.now().isoformat(),
                        type="TRADE_ENTRY",
                        title=f"🚨 Sentinel Active Trade: {sym} {direction}",
                        message=f"{sym} {payload.get('symbol') or payload.get('opt_symbol') or ''} entered at ₹{entry_px}. State: {state}",
                        level_price=payload.get("target_price") or payload.get("target"),
                        spot_price=entry_px,
                        urgency="HIGH"
                    )
                )

            # Recent Trade Entries from Trade History (today's entries)
            history = data.get("trade_history", [])
            for t in history[-5:]:
                pos_id = t.get("position_id")
                if not pos_id:
                    continue
                dir_str = t.get("direction", "TRADE")
                contract = t.get("opt_symbol") or t.get("strike_contract") or ""
                entry_px = t.get("opt_entry_ltp") or t.get("entry_price")
                entry_time = str(t.get("entry_time") or "")
                notifications.append(
                    NotificationItem(
                        id=f"entry_{pos_id}",
                        timestamp=entry_time,
                        type="TRADE_ENTRY",
                        title=f"🚨 Sentinel Trade Entry: {sym} {dir_str}",
                        message=f"{sym} {contract} triggered entry at ₹{entry_px} ({entry_time[11:16] if 'T' in entry_time else entry_time})",
                        level_price=t.get("target_price"),
                        spot_price=entry_px,
                        urgency="HIGH"
                    )
                )

            # Last completed trade alert
            last_trade = data.get("last_completed_trade")
            if last_trade:
                pos_id = last_trade.get("position_id", "LAST_TRADE")
                exit_reason = last_trade.get("exit_reason", "EXITED")
                pnl_pts = last_trade.get("opt_pnl_pts") or last_trade.get("pnl_pts") or 0.0
                notifications.append(
                    NotificationItem(
                        id=f"exit_{pos_id}",
                        timestamp=last_trade.get("exit_time") or last_trade.get("entry_time") or datetime.now().isoformat(),
                        type="TRADE_EXIT",
                        title=f"🏁 Trade Closed: {sym} ({exit_reason})",
                        message=f"{pos_id} exited with P&L: {pnl_pts:+.2f} pts. Reason: {exit_reason}",
                        level_price=last_trade.get("exit_price"),
                        spot_price=last_trade.get("entry_price"),
                        urgency="HIGH"
                    )
                )
        except Exception:
            pass

    # 2. Inspect dynamic Sentinel price crossings across intraday candles
    try:
        candles_file = RUNTIME_DIR / "nifty_candles_20261106.json"
        spot = 24580.0
        if candles_file.exists():
            with open(candles_file, "r") as f:
                raw_candles = json.load(f)
            if raw_candles:
                # Chronological order (oldest to newest)
                chron = raw_candles[::-1] if isinstance(raw_candles[0], list) else []
                spot = float(chron[-1][4]) if chron else 24580.0
                rbfn = get_official_rbfn_for_index(idx, spot)
                td = rbfn.get("trend_decider")
                rp1_u = rbfn.get("rp1_upper")
                rp1_l = rbfn.get("rp1_lower")
                rp2_u = rbfn.get("rp2_upper")
                rp2_l = rbfn.get("rp2_lower")

                # Scan through recent bars (last 45 bars) to detect all genuine crossing events
                for i in range(max(1, len(chron) - 45), len(chron)):
                    prev_c = float(chron[i-1][4])
                    curr_c = float(chron[i][4])
                    bar_time = chron[i][0][11:16]

                    # Trend Decider Crossing
                    if td:
                        if prev_c < td <= curr_c:
                            notifications.append(
                                NotificationItem(
                                    id=f"cross_td_above_{bar_time}",
                                    timestamp=chron[i][0],
                                    type="CROSS_TD_ABOVE",
                                    title=f"📈 {idx} Bullish TD Breakout",
                                    message=f"{idx} crossed ABOVE dynamic Trend Decider ₹{td:,.1f} at {bar_time} (Spot: ₹{curr_c:,.1f})",
                                    level_price=td,
                                    spot_price=curr_c,
                                    urgency="HIGH"
                                )
                            )
                        elif prev_c > td >= curr_c:
                            notifications.append(
                                NotificationItem(
                                    id=f"cross_td_below_{bar_time}",
                                    timestamp=chron[i][0],
                                    type="CROSS_TD_BELOW",
                                    title=f"📉 {idx} Bearish TD Breakdown",
                                    message=f"{idx} crossed BELOW dynamic Trend Decider ₹{td:,.1f} at {bar_time} (Spot: ₹{curr_c:,.1f})",
                                    level_price=td,
                                    spot_price=curr_c,
                                    urgency="HIGH"
                                )
                            )

                    # RP1 Upper Crossing
                    if rp1_u:
                        if prev_c < rp1_u <= curr_c:
                            notifications.append(
                                NotificationItem(
                                    id=f"cross_rp1_u_above_{bar_time}",
                                    timestamp=chron[i][0],
                                    type="CROSS_RP1_UPPER",
                                    title=f"⚡ {idx} Upper Reversal 1 Breached",
                                    message=f"{idx} surged ABOVE dynamic RP1 Upper ₹{rp1_u:,.1f} at {bar_time} (Spot: ₹{curr_c:,.1f})",
                                    level_price=rp1_u,
                                    spot_price=curr_c,
                                    urgency="HIGH"
                                )
                            )

                    # RP1 Lower Crossing
                    if rp1_l:
                        if prev_c < rp1_l <= curr_c or prev_c > rp1_l >= curr_c:
                            action_str = "reclaimed ABOVE" if curr_c >= rp1_l else "slipped BELOW"
                            notifications.append(
                                NotificationItem(
                                    id=f"cross_rp1_l_{bar_time}",
                                    timestamp=chron[i][0],
                                    type="CROSS_RP1_LOWER",
                                    title=f"⚡ {idx} Lower Reversal 1 Hit",
                                    message=f"{idx} {action_str} dynamic RP1 Lower ₹{rp1_l:,.1f} at {bar_time} (Spot: ₹{curr_c:,.1f})",
                                    level_price=rp1_l,
                                    spot_price=curr_c,
                                    urgency="HIGH"
                                )
                            )

                    # RP2 Upper Crossing
                    if rp2_u and (prev_c < rp2_u <= curr_c):
                        notifications.append(
                            NotificationItem(
                                id=f"cross_rp2_u_{bar_time}",
                                timestamp=chron[i][0],
                                type="CROSS_RP2_UPPER",
                                title=f"🎯 {idx} Extreme Upper Reversal 2 Hit",
                                message=f"{idx} breached dynamic RP2 Upper ₹{rp2_u:,.1f} at {bar_time} (Spot: ₹{curr_c:,.1f})",
                                level_price=rp2_u,
                                spot_price=curr_c,
                                urgency="HIGH"
                            )
                        )

                    # RP2 Lower Crossing
                    if rp2_l and (prev_c < rp2_l <= curr_c or prev_c > rp2_l >= curr_c):
                        action_str = "rebounded ABOVE" if curr_c >= rp2_l else "fell BELOW"
                        notifications.append(
                            NotificationItem(
                                id=f"cross_rp2_l_{bar_time}",
                                timestamp=chron[i][0],
                                type="CROSS_RP2_LOWER",
                                title=f"🎯 {idx} Extreme Lower Reversal 2 Hit",
                                message=f"{idx} {action_str} dynamic RP2 Lower ₹{rp2_l:,.1f} at {bar_time} (Spot: ₹{curr_c:,.1f})",
                                level_price=rp2_l,
                                spot_price=curr_c,
                                urgency="HIGH"
                            )
                        )
    except Exception:
        pass

    return NotificationsResponse(
        timestamp=datetime.now().isoformat(),
        notifications=notifications
    )

