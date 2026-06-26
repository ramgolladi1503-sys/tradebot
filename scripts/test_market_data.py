import sys
from core.market_data import get_token_for_symbol
from core.tick_store import get_last_tick
token = get_token_for_symbol("BANKNIFTY26JUN57900PE")
print("Token:", token)
if token:
    print("Last tick:", get_last_tick(token))
