from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import sys
from pathlib import Path

from core.kite_depth_ws import start_depth_ws
from core.kite_client import kite_client
from core.market_calendar import next_expiry_by_type
from config import config as cfg

if __name__ == "__main__":
    # debug: ensure instruments load
    try:
        data = kite_client.instruments_cached("NFO", ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
    except Exception as e:
        print(f"Live instruments fetch failed: {e}")
        # fallback to cached instruments
        data = kite_client.instruments_cached("NFO", ttl_sec=10**9)
    if not data:
        print("NFO instruments loaded: 0")
        print("No local instruments cache. Run scripts/download_instruments.py when network is available.")
        raise SystemExit(1)
    print(f"NFO instruments loaded: {len(data)}")
    # Resolve per-symbol expiries (NFO for NIFTY/BANKNIFTY, BFO for SENSEX)
    tokens = []
    resolution = []
    for sym in cfg.SYMBOLS:
        exchange = "BFO" if sym.upper() == "SENSEX" else "NFO"
        exp_primary = kite_client.next_available_expiry(sym, exchange=exchange)
        sym_tokens = []
        if exp_primary:
            sym_tokens = kite_client.resolve_option_tokens_exchange([sym], exp_primary, exchange=exchange)
        print(f"{sym} tokens ({exp_primary}) [{exchange}]: {len(sym_tokens)}")
        resolution.append({
            "symbol": sym,
            "exchange": exchange,
            "expiry": exp_primary,
            "tokens": sym_tokens,
            "count": len(sym_tokens),
        })
        tokens.extend(sym_tokens)
    tokens = list(set(tokens))
    try:
        import json
        from pathlib import Path
        out = Path("logs/token_resolution.json")
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(resolution, indent=2))
    except Exception:
        pass
    if not tokens:
        print("No option tokens resolved. Check SYMBOLS/expiry and Kite instruments access.")
        # fallback to futures tokens
        tokens = kite_client.resolve_tokens(cfg.SYMBOLS, exchange="NFO")
    if not tokens:
        print("No NFO tokens resolved. Check SYMBOLS and Kite instruments access.")
    else:
        start_depth_ws(tokens)
