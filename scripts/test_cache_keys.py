import sys
from core.market_data import fetch_live_market_data, _DATA_CACHE
res = fetch_live_market_data(allow_history_seed=False)
print("Data Cache Keys:")
for k in list(_DATA_CACHE.keys())[:10]:
    print(k)
