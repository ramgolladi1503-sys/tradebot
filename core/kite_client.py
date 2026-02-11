import time
import json
import os
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
        self.last_init_error = None

    def ensure(self):
        self._ensure()

    @staticmethod
    def _looks_placeholder_secret(value: str) -> bool:
        token = str(value or "").strip().lower()
        if not token:
            return False
        if token.startswith("your_") or "placeholder" in token:
            return True
        return token in {
            "your_kiteconnect_api_key",
            "your_kite_api_key",
            "your_api_key",
            "changeme",
        }

    def _ensure(self):
        if self.kite or not KiteConnect:
            return
        api_key = (os.getenv("KITE_API_KEY") or str(getattr(cfg, "KITE_API_KEY", "") or "")).strip()
        if not api_key:
            self.last_init_error = "missing_api_key:KITE_API_KEY"
            return
        if self._looks_placeholder_secret(api_key):
            self.last_init_error = "invalid_api_key_placeholder:KITE_API_KEY"
            return
        token = ""
        try:
            from core.security_guard import resolve_kite_access_token
            repo_root = Path(__file__).resolve().parents[1]
            # Always resolve via security guard to avoid stale env/config token drift.
            token = resolve_kite_access_token(repo_root=repo_root, require_token=False).strip()
            if token:
                cfg.KITE_ACCESS_TOKEN = token
        except RuntimeError as exc:
            print(str(exc))
            self.last_init_error = str(exc)
            return
        if not token:
            self.last_init_error = "missing_access_token:~/.trading_bot/kite_access_token"
            return
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(token)
        print(
            f"KITE_REST api_key_tail4={api_key[-4:] if len(api_key) >= 4 else api_key} "
            f"access_token_tail4={token[-4:] if len(token) >= 4 else token} "
            f"kite_id={id(self.kite)}"
        )
        self.last_init_error = None

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

    def resolve_option_tokens_window(self, symbol, expiry_date, atm_strike, strikes_around, step, exchange="NFO"):
        seg = "NFO-OPT" if exchange == "NFO" else "BFO-OPT"
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        tokens = []
        if atm_strike is None or step is None or step <= 0:
            return []
        min_strike = atm_strike - (strikes_around * step)
        max_strike = atm_strike + (strikes_around * step)
        for inst in data:
            if inst.get("segment") != seg:
                continue
            if inst.get("name") != symbol:
                continue
            if inst.get("expiry") != expiry_date:
                continue
            strike = inst.get("strike")
            if strike is None:
                continue
            try:
                strike_val = float(strike)
            except Exception:
                continue
            if strike_val < min_strike or strike_val > max_strike:
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

    def historical_data(self, instrument_token, from_dt, to_dt, interval="minute"):
        self._ensure()
        if not self.kite:
            return []
        time.sleep(cfg.KITE_RATE_LIMIT_SLEEP)
        return self.kite.historical_data(instrument_token, from_dt, to_dt, interval)

    def resolve_index_token(self, symbol):
        sym = (symbol or "").upper()
        exchange = "BSE" if sym == "SENSEX" else "NSE"
        data = self.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
        if not data:
            return None
        name_map = {
            "NIFTY": ["NIFTY 50", "NIFTY"],
            "BANKNIFTY": ["NIFTY BANK", "BANKNIFTY"],
            "SENSEX": ["SENSEX"],
        }
        targets = set(name_map.get(sym, [sym]))
        for inst in data:
            ts = inst.get("tradingsymbol")
            nm = inst.get("name")
            seg = inst.get("segment", "")
            if ts in targets or nm in targets:
                if "INDICES" in str(seg) or exchange in str(inst.get("exchange", "")):
                    return inst.get("instrument_token")
        return None

kite_client = KiteClient()
