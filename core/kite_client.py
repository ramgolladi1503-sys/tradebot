import time
import json
from pathlib import Path
from config import config as cfg

try:
    from kiteconnect import KiteConnect
except Exception:
    KiteConnect = None

class KiteClient:
    def __init__(self):
        self.kite = None
        self._instruments_cache = {}
        self._cache_ts = 0

    def ensure(self):
        self._ensure()

    def _ensure(self):
        if self.kite or not KiteConnect:
            return
        if not cfg.KITE_API_KEY or not cfg.KITE_ACCESS_TOKEN:
            return
        self.kite = KiteConnect(api_key=cfg.KITE_API_KEY)
        self.kite.set_access_token(cfg.KITE_ACCESS_TOKEN)

    def instruments(self, exchange=None):
        self._ensure()
        if not self.kite:
            return []
        time.sleep(cfg.KITE_RATE_LIMIT_SLEEP)
        return self.kite.instruments(exchange) if exchange else self.kite.instruments()

    def instruments_cached(self, exchange=None, ttl_sec=3600):
        cache_path = Path("data/kite_instruments.json")
        now = time.time()
        key = exchange or "ALL"

        if key in self._instruments_cache and (now - self._cache_ts) < ttl_sec:
            return self._instruments_cache[key]

        # Try disk cache
        if cache_path.exists() and (now - cache_path.stat().st_mtime) < ttl_sec:
            try:
                raw = json.loads(cache_path.read_text())
                self._instruments_cache = raw
                self._cache_ts = now
                if key in raw:
                    return raw[key]
            except Exception:
                pass

        data = None
        try:
            data = self.instruments(exchange)
        except Exception:
            data = None
        if not data:
            # fallback to local CSV
            csv_path = Path("data/kite_instruments.csv")
            if csv_path.exists():
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_path)
                    data = df.to_dict(orient="records")
                except Exception:
                    data = []
            # fallback to cache if it has data
            if not data and cache_path.exists():
                try:
                    raw = json.loads(cache_path.read_text())
                    cached = raw.get(key, [])
                    if cached:
                        data = cached
                except Exception:
                    pass
        if data:
            self._instruments_cache[key] = data
            self._cache_ts = now
            try:
                cache_path.parent.mkdir(exist_ok=True)
                cache_path.write_text(json.dumps(self._instruments_cache))
            except Exception:
                pass
        return data

    def resolve_tokens(self, symbols, exchange="NFO"):
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        tokens = []
        for inst in data:
            if inst.get("tradingsymbol") in symbols or inst.get("name") in symbols:
                tok = inst.get("instrument_token")
                if tok:
                    tokens.append(tok)
        return list(set(tokens))

    def resolve_option_tokens(self, symbols, expiry_date, strikes_around=2, step=50):
        data = self.instruments_cached("NFO", ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        tokens = []
        for inst in data:
            if inst.get("segment") != "NFO-OPT":
                continue
            if inst.get("name") not in symbols:
                continue
            if inst.get("expiry") != expiry_date:
                continue
            strike = inst.get("strike")
            if strike is None:
                continue
            tok = inst.get("instrument_token")
            if tok:
                tokens.append(tok)
        return list(set(tokens))

    def resolve_option_tokens_exchange(self, symbols, expiry_date, exchange="NFO"):
        seg = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        tokens = []
        for inst in data:
            if inst.get("segment") != seg:
                continue
            if inst.get("name") not in symbols:
                continue
            if inst.get("expiry") != expiry_date:
                continue
            tok = inst.get("instrument_token")
            if tok:
                tokens.append(tok)
        return list(set(tokens))

    def next_available_expiry(self, symbol, exchange="NFO"):
        seg = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        expiries = []
        for inst in data:
            if inst.get("segment") != seg:
                continue
            if inst.get("name") != symbol:
                continue
            exp = inst.get("expiry")
            if exp:
                expiries.append(exp)
        if not expiries:
            return None
        return sorted(expiries)[0]

    def token_symbol_map(self, exchange="NFO"):
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        m = {}
        for inst in data:
            tok = inst.get("instrument_token")
            sym = inst.get("tradingsymbol")
            if tok and sym:
                m[tok] = sym
        return m

    def find_option_symbol(self, symbol, strike, opt_type, exchange="NFO"):
        seg = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        strike_val = float(strike)
        for inst in data:
            if inst.get("segment") != seg:
                continue
            if inst.get("name") != symbol:
                continue
            if inst.get("strike") is None:
                continue
            if float(inst.get("strike")) != strike_val:
                continue
            if inst.get("instrument_type") != opt_type:
                continue
            ts = inst.get("tradingsymbol")
            if ts:
                return f"{exchange}:{ts}"
        return None

    def find_option_symbol_with_expiry(self, symbol, strike, opt_type, expiry, exchange="NFO"):
        seg = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        strike_val = float(strike)
        exp_str = str(expiry)
        for inst in data:
            if inst.get("segment") != seg:
                continue
            if inst.get("name") != symbol:
                continue
            if inst.get("strike") is None:
                continue
            if float(inst.get("strike")) != strike_val:
                continue
            if inst.get("instrument_type") != opt_type:
                continue
            if exp_str and str(inst.get("expiry")) != exp_str:
                continue
            ts = inst.get("tradingsymbol")
            if ts:
                return f"{exchange}:{ts}"
        return None

    def quote(self, symbols):
        self._ensure()
        if not self.kite:
            return {}
        time.sleep(cfg.KITE_RATE_LIMIT_SLEEP)
        return self.kite.quote(symbols)

    def ltp(self, symbols):
        self._ensure()
        if not self.kite:
            return {}
        time.sleep(cfg.KITE_RATE_LIMIT_SLEEP)
        return self.kite.ltp(symbols)

    def trades(self):
        self._ensure()
        if not self.kite:
            return []
        time.sleep(cfg.KITE_RATE_LIMIT_SLEEP)
        return self.kite.trades()

kite_client = KiteClient()
