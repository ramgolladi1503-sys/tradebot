import sys
from core.kite_client import kite_client

instruments = kite_client.instruments() or []
found = False
for i in instruments:
    if "BANKNIFTY" in i.get("tradingsymbol", "") and "PE" in i.get("tradingsymbol", ""):
        print("Found matching:", i.get("tradingsymbol"), i.get("instrument_token"))
        found = True
        break
if not found:
    print("No BANKNIFTY PE found in instruments!")
