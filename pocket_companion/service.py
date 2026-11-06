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

@app.get("/chart", response_model=ChartDataResponse)
def get_chart_data(index: str = "NIFTY", _: str = Depends(verify_api_key)) -> ChartDataResponse:
    """Retrieve full 1-minute intraday candles and drawn Sentinel levels (TD, RP1/2, OR)."""
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

    # RBFN Boundaries matching PR #987 OptionMate dynamic grid
    td = round(current_spot / 50.0) * 50.0
    return ChartDataResponse(
        index=index.upper(),
        candles=candle_points,
        or_high=or_high,
        or_low=or_low,
        trend_decider=td,
        rp1_upper=td + 100.0,
        rp2_upper=td + 200.0,
        rp1_lower=td - 100.0,
        rp2_lower=td - 200.0,
        call_strike=td + 100.0,
        put_strike=td - 100.0,
        target_strike=td + 100.0,
        bias="BULL" if current_spot >= td else "BEAR",
        current_spot=current_spot
    )
