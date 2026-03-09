import os
import sys
import json
import time
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import config as cfg
from core.auth_manager import access_token_path, resolve_access_token
from core.paths import data_root

try:
    from kiteconnect import KiteConnect
except Exception:
    KiteConnect = None

logger = logging.getLogger(__name__)


class KiteClient:
    def __init__(self):
        self.kite = None
        self._instruments_cache: Dict[str, Dict[str, Any]] = {}
        self._last_instruments_fetch: Optional[str] = None
        self._historical_auth_cooldown_until = 0.0
        self._historical_auth_cooldown_reason = ""

    # ---------------------------
    # Logging (atomic write)
    # ---------------------------
    def _log_atomic(self, msg: str) -> None:
        try:
            sys.stdout.write(str(msg) + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    # ---------------------------
    # Kite session
    # ---------------------------
    def _create_kite(self, api_key: str, access_token: str):
        if KiteConnect is None:
            raise RuntimeError("kiteconnect_not_installed")
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        return kite

    def ensure(self):
        if self.kite is not None:
            return self.kite

        api_key = (getattr(cfg, "KITE_API_KEY", "") or "").strip()
        api_secret = (getattr(cfg, "KITE_API_SECRET", "") or "").strip()  # may be used elsewhere

        access_token = (os.getenv("KITE_ACCESS_TOKEN") or "").strip()
        if not access_token:
            access_token = resolve_access_token()

        if not api_key:
            raise RuntimeError("kite_api_key_missing")
        if not access_token:
            raise RuntimeError("kite_access_token_missing")

        kite = self._create_kite(api_key=api_key, access_token=access_token)

        # Single atomic line to avoid glued logs
        self._log_atomic(
            "KITE_REST "
            f"api_key_tail4={api_key[-4:] if len(api_key) >= 4 else api_key} "
            f"access_token_tail4={access_token[-4:] if len(access_token) >= 4 else access_token} "
            f"kite_id={id(kite)}"
        )

        self.kite = kite
        return self.kite

    # ---------------------------
    # Basic wrappers
    # ---------------------------
    def profile(self):
        return self.ensure().profile()

    def margins(self):
        return self.ensure().margins()

    def instruments(self, exchange: Optional[str] = None, force: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch instruments list from Kite (heavy). Cache per exchange per day.
        """
        kite = self.ensure()
        key = (exchange or "ALL").upper()
        today = date.today().isoformat()

        cached = self._instruments_cache.get(key)
        if not force and cached and cached.get("date") == today:
            return cached.get("data", [])

        try:
            data = kite.instruments(exchange) if exchange else kite.instruments()
            self._instruments_cache[key] = {"date": today, "data": data}
            self._last_instruments_fetch = datetime.now().isoformat()
            return data
        except Exception as e:
            logger.exception("instruments_fetch_failed exchange=%s err=%s", exchange, e)
            if cached:
                return cached.get("data", [])
            return []

    # Compatibility (some modules may call this)
    def get_instruments_cached(self, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.instruments(exchange=exchange)

    # Legacy compatibility used by tests and older callers.
    def instruments_cached(self, exchange: Optional[str] = None, ttl_sec: int = 3600) -> List[Dict[str, Any]]:
        _ = int(ttl_sec or 3600)
        return self.instruments(exchange=exchange)

    def ltp(self, instruments):
        return self.ensure().ltp(instruments)

    def quote(self, instruments):
        return self.ensure().quote(instruments)

    # ---------------------------
    # Historical (telemetry-enabled)
    # ---------------------------
    def _is_historical_auth_error(self, exc: Exception) -> bool:
        text = str(exc or "").strip().lower()
        if not text:
            return False
        markers = (
            "tokenexception",
            "access_token",
            "api_key",
            "incorrect api_key",
            "incorrect api key",
            "invalid api key",
            "invalid session",
            "session expired",
            "unauthorized",
            "forbidden",
        )
        return any(marker in text for marker in markers)

    def _historical_auth_cooldown_remaining(self) -> float:
        now_ts = float(time.time())
        remaining = float(self._historical_auth_cooldown_until or 0.0) - now_ts
        return max(0.0, remaining)

    def historical(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
        _symbol: Optional[str] = None,
        _exchange: Optional[str] = None,
        _caller: Optional[str] = None,
    ):
        cooldown_remaining = self._historical_auth_cooldown_remaining()
        if cooldown_remaining > 0.0:
            self._log_atomic(
                "[HIST_SUPPRESSED] "
                f"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} "
                f"interval={interval} from={from_date} to={to_date} "
                f"continuous={continuous} oi={oi} cooldown_remaining_sec={cooldown_remaining:.2f} "
                f"reason={self._historical_auth_cooldown_reason or 'auth_cooldown'}"
            )
            return []
        kite = self.ensure()
        try:
            bars = kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )
            if not bars:
                self._log_atomic(
                    "[HIST_EMPTY] "
                    f"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} "
                    f"interval={interval} from={from_date} to={to_date} "
                    f"continuous={continuous} oi={oi}"
                )
            return bars
        except Exception as e:
            if self._is_historical_auth_error(e):
                cooldown_sec = max(1.0, float(getattr(cfg, "KITE_HIST_AUTH_ERROR_COOLDOWN_SEC", 45.0)))
                self._historical_auth_cooldown_until = float(time.time()) + cooldown_sec
                self._historical_auth_cooldown_reason = repr(e)
                self._log_atomic(
                    "[HIST_AUTH_COOLDOWN] "
                    f"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} "
                    f"interval={interval} cooldown_sec={cooldown_sec:.2f} reason={repr(e)}"
                )
            self._log_atomic(
                "[HIST_ERROR] "
                f"caller={_caller} symbol={_symbol} exchange={_exchange} token={instrument_token} "
                f"interval={interval} from={from_date} to={to_date} "
                f"continuous={continuous} oi={oi} err={repr(e)}"
            )
            raise

    def _normalize_interval(self, interval: str) -> str:
        """
        Normalize common interval aliases into Kite values:
        Kite expects: minute, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute, day
        """
        iv = (interval or "").strip().lower()
        mapping = {
            "1m": "minute",
            "1min": "minute",
            "min": "minute",
            "minute": "minute",
            "3m": "3minute",
            "3min": "3minute",
            "3minute": "3minute",
            "5m": "5minute",
            "5min": "5minute",
            "5minute": "5minute",
            "10m": "10minute",
            "10min": "10minute",
            "10minute": "10minute",
            "15m": "15minute",
            "15min": "15minute",
            "15minute": "15minute",
            "30m": "30minute",
            "30min": "30minute",
            "30minute": "30minute",
            "60m": "60minute",
            "60min": "60minute",
            "60minute": "60minute",
            "1h": "60minute",
            "hour": "60minute",
            "1d": "day",
            "day": "day",
            "daily": "day",
        }
        return mapping.get(iv, interval)

    def historical_data(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str = "minute",
        continuous: bool = False,
        oi: bool = False,
        **kwargs,
    ):
        """
        Backward-compatible wrapper: lots of modules call kite_client.historical_data(...)
        Routes through telemetry-enabled `historical()`.
        """
        interval_norm = self._normalize_interval(interval)

        # Kite can be picky about tz-aware datetimes; strip tzinfo if present.
        def _naive_dt(x: Any) -> Any:
            try:
                if isinstance(x, datetime) and x.tzinfo is not None:
                    return x.replace(tzinfo=None)
            except Exception:
                pass
            return x

        fdt = _naive_dt(from_date)
        tdt = _naive_dt(to_date)

        return self.historical(
            instrument_token=instrument_token,
            from_date=fdt,
            to_date=tdt,
            interval=interval_norm,
            continuous=continuous,
            oi=oi,
            _symbol=kwargs.get("_symbol"),
            _exchange=kwargs.get("_exchange"),
            _caller=kwargs.get("_caller"),
        )

    # ---------------------------
    # Orders / Portfolio
    # ---------------------------
    def orders(self):
        return self.ensure().orders()

    def positions(self):
        return self.ensure().positions()

    def holdings(self):
        return self.ensure().holdings()

    def place_order(self, **kwargs):
        return self.ensure().place_order(**kwargs)

    def modify_order(self, **kwargs):
        return self.ensure().modify_order(**kwargs)

    def cancel_order(self, **kwargs):
        return self.ensure().cancel_order(**kwargs)

    def order_history(self, order_id):
        return self.ensure().order_history(order_id)

    def trades(self):
        return self.ensure().trades()

    def convert_position(self, **kwargs):
        return self.ensure().convert_position(**kwargs)

    # ---------------------------
    # Auth helpers
    # ---------------------------
    def generate_session(self, request_token, api_secret):
        if KiteConnect is None:
            raise RuntimeError("kiteconnect_not_installed")
        api_key = (getattr(cfg, "KITE_API_KEY", "") or "").strip()
        kite = KiteConnect(api_key=api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)
        kite.set_access_token(data.get("access_token"))
        return data

    def set_access_token(self, token: str):
        token = (token or "").strip()
        if not token:
            raise RuntimeError("empty_access_token")
        os.environ["KITE_ACCESS_TOKEN"] = token
        try:
            p = Path(access_token_path())
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(token)
        except Exception:
            pass
        self.kite = None  # force re-create

    # ---------------------------
    # Helper converters
    # ---------------------------
    def _to_date(self, d: Any) -> Optional[date]:
        if d is None:
            return None
        if isinstance(d, date) and not isinstance(d, datetime):
            return d
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, str):
            s = d.strip()
            for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y"):
                try:
                    return datetime.strptime(s, fmt).date()
                except Exception:
                    pass
        return None

    # ---------------------------
    # Instrument lookup helpers
    # ---------------------------
    def _find_instrument(self, exchange: Optional[str], tradingsymbol: str) -> Optional[Dict[str, Any]]:
        ts = (tradingsymbol or "").strip().upper()
        if not ts:
            return None

        data = self.instruments(exchange=exchange) if exchange else self.instruments()
        for r in data:
            if (r.get("tradingsymbol") or "").upper() == ts:
                return r
        return None

    def _instrument_row_belongs_to_symbol(self, symbol: str, row: Dict[str, Any]) -> bool:
        sym = (symbol or "").strip().upper()
        if not sym:
            return False
        name = str(row.get("name") or "").strip().upper()
        if name == sym:
            return True
        tradingsymbol = str(row.get("tradingsymbol") or "").strip().upper()
        if not tradingsymbol.startswith(sym):
            return False
        if len(tradingsymbol) == len(sym):
            return True
        next_char = tradingsymbol[len(sym)]
        return not next_char.isalpha()

    def _normalize_option_instrument_types(
        self,
        instrument_types: Optional[Tuple[str, ...]] = None,
    ) -> set[str]:
        source = ("OPTIDX", "OPTSTK", "CE", "PE") if instrument_types is None else instrument_types
        return {
            str(value or "").strip().upper()
            for value in source
            if str(value or "").strip()
        }

    def _is_option_instrument_row(
        self,
        row: Dict[str, Any],
        instrument_types: Optional[Tuple[str, ...]] = None,
    ) -> bool:
        seg = str(row.get("segment") or "").strip().upper()
        inst_type = str(row.get("instrument_type") or "").strip().upper()
        tradingsymbol = str(row.get("tradingsymbol") or "").strip().upper()
        normalized_instrument_types = self._normalize_option_instrument_types(instrument_types)
        has_suffix_option_shape = (
            (tradingsymbol.endswith("CE") or tradingsymbol.endswith("PE"))
            and self._to_date(row.get("expiry")) is not None
            and any(ch.isdigit() for ch in tradingsymbol[:-2])
        )
        return bool(
            ("OPT" in seg)
            or (inst_type in normalized_instrument_types)
            or has_suffix_option_shape
        )

    def _log_option_window_resolution(
        self,
        *,
        exchange: str,
        symbol: str,
        expiry: Any,
        strikes_around: int,
        spot: Optional[float],
        total_rows_scanned: int,
        option_rows_matched: int,
        expiry_matched_rows: int,
        strike_window_matched_rows: int,
        final_token_count: int,
        failure_reason: str,
    ) -> None:
        try:
            self._log_atomic(
                json.dumps(
                    {
                        "event": "KITE_OPTION_WINDOW_RESOLUTION",
                        "exchange": exchange,
                        "expiry": "none" if expiry is None else str(expiry),
                        "failure_reason": str(failure_reason or ""),
                        "final_token_count": int(final_token_count),
                        "option_rows_matched": int(option_rows_matched),
                        "spot": spot,
                        "strike_window_matched_rows": int(strike_window_matched_rows),
                        "strikes_around": int(strikes_around),
                        "symbol": symbol,
                        "total_rows_scanned": int(total_rows_scanned),
                        "expiry_matched_rows": int(expiry_matched_rows),
                    },
                    default=str,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        except Exception:
            pass

    def resolve_index_token(self, symbol: str) -> Optional[int]:
        """
        Resolve index spot instrument_token deterministically.

        Canonical mapping:
          NIFTY     -> NSE / "NIFTY 50"
          BANKNIFTY -> NSE / "NIFTY BANK"
          SENSEX    -> BSE / "SENSEX"
        """
        sym = (symbol or "").strip().upper()
        if not sym:
            return None

        canonical = {
            "NIFTY": ("NSE", "NIFTY 50"),
            "BANKNIFTY": ("NSE", "NIFTY BANK"),
            "SENSEX": ("BSE", "SENSEX"),
        }

        if sym in canonical:
            exch, ts = canonical[sym]
            inst = self._find_instrument(exchange=exch, tradingsymbol=ts)
            if inst:
                tok = inst.get("instrument_token")
                return tok if isinstance(tok, int) else None

        # Fallback attempts
        for exch in ("NSE", "BSE"):
            inst = self._find_instrument(exchange=exch, tradingsymbol=sym)
            if inst:
                tok = inst.get("instrument_token")
                return tok if isinstance(tok, int) else None

        inst = self._find_instrument(exchange=None, tradingsymbol=sym)
        if inst:
            tok = inst.get("instrument_token")
            return tok if isinstance(tok, int) else None

        return None

    def next_available_expiry(self, symbol: str, exchange: str = "NFO") -> Optional[date]:
        """
        Returns soonest available expiry date for options for given underlying (name field).
        Expects NFO instruments by default.
        """
        sym = (symbol or "").strip().upper()
        exch = (exchange or "NFO").strip().upper()
        if not sym:
            return None

        data = self.instruments(exchange=exch)
        expiries: List[date] = []
        matched_tradingsymbols: List[str] = []
        total_option_candidates_scanned = 0
        sample_segments: List[str] = []
        sample_instrument_types: List[str] = []
        candidate_tradingsymbols: List[str] = []

        for r in data:
            try:
                inst_type = (r.get("instrument_type") or "").strip().upper()
                seg = (r.get("segment") or "").strip().upper()
                tradingsymbol = str(r.get("tradingsymbol") or "").strip().upper()
                if seg and seg not in sample_segments and len(sample_segments) < 5:
                    sample_segments.append(seg)
                if inst_type and inst_type not in sample_instrument_types and len(sample_instrument_types) < 5:
                    sample_instrument_types.append(inst_type)
                if not self._is_option_instrument_row(r):
                    continue
                if tradingsymbol and len(candidate_tradingsymbols) < 5:
                    candidate_tradingsymbols.append(tradingsymbol)

                exp = self._to_date(r.get("expiry"))
                if not exp:
                    continue
                total_option_candidates_scanned += 1
                if not self._instrument_row_belongs_to_symbol(sym, r):
                    continue
                expiries.append(exp)
                if tradingsymbol and len(matched_tradingsymbols) < 5:
                    matched_tradingsymbols.append(tradingsymbol)
            except Exception:
                continue

        resolved_expiry = "none"
        if not expiries:
            resolved = None
        else:
            expiries.sort()
            resolved = expiries[0]
            resolved_expiry = resolved.isoformat()

        try:
            self._log_atomic(
                json.dumps(
                    {
                        "event": "KITE_NEXT_AVAILABLE_EXPIRY",
                        "exchange": exch,
                        "symbol": sym,
                        "total_option_candidates_scanned": int(total_option_candidates_scanned),
                        "matched_candidates_count": int(len(expiries)),
                        "sample_segments": list(sample_segments),
                        "sample_instrument_types": list(sample_instrument_types),
                        "candidate_tradingsymbols": list(candidate_tradingsymbols),
                        "matched_tradingsymbols": list(matched_tradingsymbols),
                        "resolved_expiry": resolved_expiry,
                    },
                    default=str,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        except Exception:
            pass

        return resolved

    # ---------------------------
    # Options token window resolver (for WS subscriptions)
    # ---------------------------
    def resolve_option_tokens_window(
        self,
        symbol: str,
        expiry: Any = None,
        strikes_around: int = 6,
        exchange: str = "NFO",
        include_ce: bool = True,
        include_pe: bool = True,
        segment: Optional[str] = None,
        instrument_types: Tuple[str, ...] = ("CE", "PE", "OPTIDX", "OPTSTK"),
        spot: Optional[float] = None,
        **kwargs,
    ) -> List[int]:
        """
        Resolve a window of option instrument tokens around ATM.
        Returns list[int] instrument_token for WS subscribe.

        NOTE: This is best-effort without live spot; if spot not supplied,
        it uses median strike as ATM proxy (still good enough to subscribe a chain window).
        """
        sym = (symbol or "").strip().upper()
        if not sym:
            return []

        exch = (exchange or "NFO").strip().upper()
        seg_filter = (segment or "").strip().upper() or None
        allowed_instrument_types = self._normalize_option_instrument_types(instrument_types)

        inst = self.instruments(exchange=exch)
        total_rows_scanned = 0
        option_rows_matched = 0
        expiry_matched_rows = 0
        strike_window_matched_rows = 0
        failure_reason = ""

        exp = self._to_date(expiry)
        if exp is None:
            exp = self.next_available_expiry(sym, exchange=exch)
        if exp is None:
            self._log_option_window_resolution(
                exchange=exch,
                symbol=sym,
                expiry=None,
                strikes_around=int(strikes_around),
                spot=spot,
                total_rows_scanned=int(len(inst or [])),
                option_rows_matched=0,
                expiry_matched_rows=0,
                strike_window_matched_rows=0,
                final_token_count=0,
                failure_reason="expiry_unavailable",
            )
            return []

        if instrument_types is not None and not allowed_instrument_types:
            self._log_option_window_resolution(
                exchange=exch,
                symbol=sym,
                expiry=exp.isoformat(),
                strikes_around=int(strikes_around),
                spot=spot,
                total_rows_scanned=int(len(inst or [])),
                option_rows_matched=0,
                expiry_matched_rows=0,
                strike_window_matched_rows=0,
                final_token_count=0,
                failure_reason="instrument_types_empty",
            )
            return []

        candidates: List[Dict[str, Any]] = []
        for row in inst:
            try:
                total_rows_scanned += 1
                if (row.get("exchange") or "").upper() != exch:
                    continue
                if seg_filter and (row.get("segment") or "").upper() != seg_filter:
                    continue
                if not self._is_option_instrument_row(row, instrument_types=instrument_types):
                    continue
                option_rows_matched += 1
                row_inst_type = str(row.get("instrument_type") or "").strip().upper()
                row_tradingsymbol = str(row.get("tradingsymbol") or "").strip().upper()
                if allowed_instrument_types:
                    type_allowed = row_inst_type in allowed_instrument_types
                    suffix_allowed = (
                        (row_tradingsymbol.endswith("CE") and "CE" in allowed_instrument_types)
                        or (row_tradingsymbol.endswith("PE") and "PE" in allowed_instrument_types)
                    )
                    if not type_allowed and not suffix_allowed:
                        continue
                if not self._instrument_row_belongs_to_symbol(sym, row):
                    continue
                row_exp = self._to_date(row.get("expiry"))
                if row_exp != exp:
                    continue
                expiry_matched_rows += 1
                candidates.append(row)
            except Exception:
                continue

        if not candidates:
            failure_reason = "no_expiry_matched_rows"
            self._log_option_window_resolution(
                exchange=exch,
                symbol=sym,
                expiry=exp.isoformat(),
                strikes_around=int(strikes_around),
                spot=spot,
                total_rows_scanned=int(total_rows_scanned),
                option_rows_matched=int(option_rows_matched),
                expiry_matched_rows=int(expiry_matched_rows),
                strike_window_matched_rows=0,
                final_token_count=0,
                failure_reason=failure_reason,
            )
            return []

        strikes = sorted(
            {float(r.get("strike") or 0.0) for r in candidates if float(r.get("strike") or 0.0) > 0.0}
        )
        if not strikes:
            failure_reason = "no_strikes"
            self._log_option_window_resolution(
                exchange=exch,
                symbol=sym,
                expiry=exp.isoformat(),
                strikes_around=int(strikes_around),
                spot=spot,
                total_rows_scanned=int(total_rows_scanned),
                option_rows_matched=int(option_rows_matched),
                expiry_matched_rows=int(expiry_matched_rows),
                strike_window_matched_rows=0,
                final_token_count=0,
                failure_reason=failure_reason,
            )
            return []

        diffs = [round(strikes[i + 1] - strikes[i], 6) for i in range(len(strikes) - 1)]
        diffs = [d for d in diffs if d > 0]
        strike_step = min(diffs) if diffs else None

        # Determine ATM strike
        if spot is None:
            atm = strikes[len(strikes) // 2]
        else:
            try:
                s = float(spot)
                if strike_step:
                    atm = round(round(s / strike_step) * strike_step, 6)
                else:
                    atm = min(strikes, key=lambda x: abs(x - s))
            except Exception:
                atm = strikes[len(strikes) // 2]

        if atm not in strikes:
            atm = min(strikes, key=lambda x: abs(x - atm))

        atm_idx = strikes.index(atm)
        lo = max(0, atm_idx - int(strikes_around))
        hi = min(len(strikes) - 1, atm_idx + int(strikes_around))
        target_strikes = set(strikes[lo : hi + 1])

        tokens: List[int] = []
        for row in candidates:
            try:
                strike = float(row.get("strike") or 0.0)
                if strike not in target_strikes:
                    continue
                strike_window_matched_rows += 1

                ts = (row.get("tradingsymbol") or "").upper()
                is_ce = ts.endswith("CE")
                is_pe = ts.endswith("PE")
                if is_ce and not include_ce:
                    continue
                if is_pe and not include_pe:
                    continue

                tok = row.get("instrument_token")
                if isinstance(tok, int):
                    tokens.append(tok)
            except Exception:
                continue

        resolved_tokens = sorted(set(tokens))
        if not resolved_tokens:
            if strike_window_matched_rows == 0:
                failure_reason = "no_strike_window_matches"
            else:
                failure_reason = "no_tokens_after_leg_filter"
            self._log_option_window_resolution(
                exchange=exch,
                symbol=sym,
                expiry=exp.isoformat(),
                strikes_around=int(strikes_around),
                spot=spot,
                total_rows_scanned=int(total_rows_scanned),
                option_rows_matched=int(option_rows_matched),
                expiry_matched_rows=int(expiry_matched_rows),
                strike_window_matched_rows=int(strike_window_matched_rows),
                final_token_count=0,
                failure_reason=failure_reason,
            )

        return resolved_tokens


kite_client = KiteClient()
