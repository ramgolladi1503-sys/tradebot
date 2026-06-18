from dataclasses import dataclass

@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    exchange: float
    gst: float
    stamp: float
    sebi: float
    total: float

class IndianDerivativesCostModel:
    def __init__(self):
        pass

    def calculate_cost(self, entry_price: float, exit_price: float, lot_size: int, instrument: str, is_long: bool) -> CostBreakdown:
        if instrument not in ["INDEX_FUTURE", "INDEX_OPTION_BUY", "INDEX_OPTION_SELL"]:
            raise ValueError(f"Unknown instrument type: {instrument}")

        # Brokerage capped at 20 per order
        brokerage = 40.0
        
        # Calculate STT
        stt = 0.0
        if instrument == "INDEX_FUTURE":
            # 0.0125% on sell side notional
            sell_price = exit_price if is_long else entry_price
            stt = sell_price * lot_size * 0.000125
        elif instrument in ["INDEX_OPTION_BUY", "INDEX_OPTION_SELL"]:
            # 0.0625% on sell side premium
            sell_price = exit_price if is_long else entry_price
            stt = sell_price * lot_size * 0.000625

        # Exchange Transaction Charges (NSE)
        # NIFTY Futures: ~0.0019%
        # NIFTY Options: ~0.05% on premium
        exchange = 0.0
        if instrument == "INDEX_FUTURE":
            turnover = (entry_price + exit_price) * lot_size
            exchange = turnover * 0.000019
        else:
            premium_turnover = (entry_price + exit_price) * lot_size
            exchange = premium_turnover * 0.0005

        # SEBI Turnover fees
        turnover = (entry_price + exit_price) * lot_size
        sebi = turnover * 0.000001

        # Stamp Duty (Only on buy side)
        stamp = 0.0
        buy_price = entry_price if is_long else exit_price
        if instrument == "INDEX_FUTURE":
            # 0.002% on buy side
            stamp = buy_price * lot_size * 0.00002
        else:
            # 0.003% on buy side premium
            stamp = buy_price * lot_size * 0.00003

        # GST 18% on (brokerage + exchange + sebi)
        gst = (brokerage + exchange + sebi) * 0.18

        total = brokerage + stt + exchange + gst + stamp + sebi

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange=exchange,
            gst=gst,
            stamp=stamp,
            sebi=sebi,
            total=total
        )
