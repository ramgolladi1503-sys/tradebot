from __future__ import annotations

STOCK_OPTION_CONTEXT_MAP: dict[str, dict[str, str]] = {
    "RELIANCE": {"index_symbol": "NIFTY", "sector_symbol": "NIFTY", "sector": "energy"},
    "HDFCBANK": {"index_symbol": "BANKNIFTY", "sector_symbol": "BANKNIFTY", "sector": "banking"},
    "ICICIBANK": {"index_symbol": "BANKNIFTY", "sector_symbol": "BANKNIFTY", "sector": "banking"},
    "SBIN": {"index_symbol": "BANKNIFTY", "sector_symbol": "BANKNIFTY", "sector": "banking"},
    "TCS": {"index_symbol": "NIFTY", "sector_symbol": "NIFTY", "sector": "it"},
}
