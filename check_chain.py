import json
import config as cfg
from core.market_data import fetch_live_market_data
import logging

logging.basicConfig(level=logging.INFO)

res = fetch_live_market_data()
for item in res:
    if item.get("symbol") == "SENSEX":
        chain = item.get("option_chain", [])
        for opt in chain:
            if opt.get("strike") in [77600.0, 76800.0]:
                print(opt.get("strike"), opt.get("type"), opt.get("ltp"), opt.get("last_price"), opt.get("tradingsymbol"))
