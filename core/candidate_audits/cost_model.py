"""Indian derivatives statutory and transaction cost model.

Supports effective-date aware rates for both Futures and Options:
- STT on equity futures:
    - Pre-2024-10-01: 0.0125% on sell side notional
    - 2024-10-01 to 2026-03-31: 0.02% on sell side notional
    - Post-2026-04-01: 0.05% on sell side notional
- STT on equity options:
    - Pre-2024-10-01: 0.0625% on sell side premium
    - 2024-10-01 to 2026-03-31: 0.10% on sell side premium
    - Post-2026-04-01: 0.15% on sell side premium
- Exchange transaction fees (NSE circular FA73061):
    - Futures: 0.0019% on total turnover
    - Options: 0.035% on total premium turnover (post-Oct-2024 revised schedule)
- Stamp duty:
    - Futures: 0.002% on buy side notional
    - Options: 0.003% on buy side premium
- SEBI turnover charges: ₹10 per crore (0.0001% = 0.000001) on total turnover
- Brokerage: ₹20 per executed leg (₹40 round-trip for 1 leg in/out; ₹80 for 2-leg spread)
- GST: 18% on (brokerage + exchange + sebi)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Union

@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange: float
    gst: float
    stamp: float
    sebi: float
    total: float
    effective_stt_rate: float
    effective_exchange_rate: float

class IndianDerivativesCostModel:
    def __init__(self):
        pass

    @staticmethod
    def parse_trade_date(trade_date: Optional[Union[date, datetime, str]] = None) -> date:
        if trade_date is None:
            return date(2026, 9, 21)
        if isinstance(trade_date, str):
            return datetime.fromisoformat(trade_date.split()[0]).date()
        if isinstance(trade_date, datetime):
            return trade_date.date()
        return trade_date

    @classmethod
    def get_stt_rate_futures(cls, trade_date: Optional[Union[date, datetime, str]] = None) -> float:
        dt = cls.parse_trade_date(trade_date)
        if dt >= date(2026, 4, 1):
            return 0.0005   # 0.05%
        elif dt >= date(2024, 10, 1):
            return 0.0002   # 0.02%
        else:
            return 0.000125 # 0.0125%

    @classmethod
    def get_stt_rate_options(cls, trade_date: Optional[Union[date, datetime, str]] = None) -> float:
        dt = cls.parse_trade_date(trade_date)
        if dt >= date(2026, 4, 1):
            return 0.0015   # 0.15% on premium sale (Budget/NSE 2026)
        elif dt >= date(2024, 10, 1):
            return 0.0010   # 0.10% on premium sale (Budget 2024)
        else:
            return 0.000625 # 0.0625%

    @classmethod
    def get_exchange_rate(cls, instrument: str, trade_date: Optional[Union[date, datetime, str]] = None) -> float:
        dt = cls.parse_trade_date(trade_date)
        if instrument == "INDEX_FUTURE":
            return 0.000019 # 0.0019%
        else:  # Options
            if dt >= date(2024, 10, 1):
                return 0.00035 # 0.035% on premium (NSE Circular FA73061)
            else:
                return 0.00050 # 0.05% historical schedule

    def calculate_cost(
        self,
        entry_price: float,
        exit_price: float,
        lot_size: int,
        instrument: str,
        is_long: bool,
        trade_date: Optional[Union[date, datetime, str]] = None,
        legs_count: int = 2
    ) -> CostBreakdown:
        if instrument not in ["INDEX_FUTURE", "INDEX_OPTION_BUY", "INDEX_OPTION_SELL"]:
            raise ValueError(f"Unknown instrument type: {instrument}")

        if lot_size <= 0:
            raise ValueError(f"Invalid lot size: {lot_size}. Must be positive.")

        # 1. Brokerage: ₹20 per executed order leg
        brokerage = 20.0 * legs_count

        # 2. STT Calculation (Sell side only)
        stt = 0.0
        stt_rate = 0.0
        if instrument == "INDEX_FUTURE":
            stt_rate = self.get_stt_rate_futures(trade_date)
            sell_price = exit_price if is_long else entry_price
            sell_turnover = sell_price * lot_size
            stt = sell_turnover * stt_rate
        else:
            stt_rate = self.get_stt_rate_options(trade_date)
            # In options, STT applies strictly on sell transactions
            sell_price = exit_price if is_long else entry_price
            sell_turnover = sell_price * lot_size
            stt = sell_turnover * stt_rate

        # 3. Exchange Transaction Charges
        exchange_rate = self.get_exchange_rate(instrument, trade_date)
        turnover = (entry_price + exit_price) * lot_size
        exchange = turnover * exchange_rate

        # 4. SEBI Turnover Fees: ₹10 / crore (0.000001)
        sebi = turnover * 0.000001

        # 5. Stamp Duty (Buy side only)
        buy_price = entry_price if is_long else exit_price
        buy_turnover = buy_price * lot_size
        stamp = 0.0
        if instrument == "INDEX_FUTURE":
            stamp = buy_turnover * 0.00002 # 0.002%
        else:
            stamp = buy_turnover * 0.00003 # 0.003% on premium

        # 6. GST: 18% on (brokerage + exchange + sebi)
        gst = (brokerage + exchange + sebi) * 0.18

        total = brokerage + stt + exchange + gst + stamp + sebi

        return CostBreakdown(
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange=round(exchange, 2),
            gst=round(gst, 2),
            stamp=round(stamp, 2),
            sebi=round(sebi, 2),
            total=round(total, 2),
            effective_stt_rate=stt_rate,
            effective_exchange_rate=exchange_rate
        )
