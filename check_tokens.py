import json
import os
import sys

from core.kite_client import KiteClient

# Initialize Kite Client
kc = KiteClient()

try:
    data = kc.instruments_cached("BFO")
    for inst in data:
        if "SENSEX" in inst.get("name", "") and inst.get("strike") in [77600, 76800] and "25" in str(inst.get("expiry")):
            print(inst.get("tradingsymbol"), inst.get("instrument_token"), inst.get("instrument_type"), inst.get("strike"))
except Exception as e:
    print(f"Error fetching BFO instruments: {e}")
