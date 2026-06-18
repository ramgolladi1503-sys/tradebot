from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float

@dataclass
class Signal:
    symbol: str
    setup_name: str
    regime: str
    signal_time: datetime
    entry_price: float
    stop_loss: float
    target: float
    risk_points: float

@dataclass
class Rejection:
    symbol: str
    setup_name: str
    signal_time: datetime
    reason: str

@dataclass
class Trade:
    signal: Signal
    entry_time: datetime
    exit_time: Optional[datetime] = None
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_points: float = 0.0
    pnl_r: float = 0.0
    
    # Costs
    gross_rupees: float = 0.0
    costs_rupees: float = 0.0
    net_rupees: float = 0.0
    
    # Tracking for MAE / MFE
    highest_price_during_trade: float = 0.0
    lowest_price_during_trade: float = float('inf')
    mae_points: float = 0.0
    mfe_points: float = 0.0
    
    is_random_baseline: bool = False
