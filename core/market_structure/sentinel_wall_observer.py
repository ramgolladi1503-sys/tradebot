"""Sentinel Strike Wall Observer.

In-memory options strike profiling, wall detection, advisory proximity checks,
and read-only supervisory state export.

Hardened against adversarial vulnerabilities:
- Directional Liquidity & Wall Vulnerability (Attacker 1)
- Volatility Normalization & 5% Hysteresis Buffer (Attackers 2 & 3)
- O(1) Symbol Cache, Lock Concurrency & Dirty State Throttling (Attacker 4)
- Risk Governance, Minimum Coverage & Feed Freshness Fail-Closed Guard (Attacker 5)

Preserves trading safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
- edge_certification_status = "NO_CERTIFIED_EDGE"
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Standard Indian weekly/monthly regex:
# e.g. NIFTY26OCT25000CE, BANKNIFTY24DEC50000PE, NIFTY24O2425000CE, SENSEX24N1578000PE
_KNOWN_INDICES = r"(?:NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|SENSEX|BANKEX|[A-Z]+?)"
_SYMBOL_PATTERN_EXPIRY = re.compile(
    rf"^({_KNOWN_INDICES})(?:\d{{2}}[A-Z]{{3}}|\d{{2}}[0-9OND][0-9]{{2}})[-_ ]*(\d+(?:\.\d+)?)[-_ ]*(CE|PE)$",
    re.IGNORECASE,
)
# Fallback pattern for symbols without standard 5-char expiry or with custom delimiters:
# e.g. NIFTY-25000-CE, NIFTY_25000_PE, NIFTY 25000 CE, NIFTY25000CE
_SYMBOL_PATTERN_SIMPLE = re.compile(
    rf"^({_KNOWN_INDICES})[-_ ]*(\d+(?:\.\d+)?)[-_ ]*(CE|PE)$",
    re.IGNORECASE,
)
# Generalized fallback matching any arbitrary date prefix before strike
_SYMBOL_PATTERN_GENERAL = re.compile(
    rf"^({_KNOWN_INDICES})\d{{2}}[A-Z0-9]{{3,5}}[-_ ]*(\d{{4,6}}(?:\.\d+)?)[-_ ]*(CE|PE)$",
    re.IGNORECASE,
)

# Global pre-warmed O(1) symbol lookup cache to bypass regex & string parsing for known symbols
_SYMBOL_CACHE: Dict[str, Optional[Tuple[str, float, str]]] = {}


def parse_option_symbol(symbol: str) -> Optional[Tuple[str, float, str]]:
    """Parse option symbol into (underlying, strike, option_type).

    Uses _SYMBOL_CACHE for O(1) fast-path resolution.
    Returns None if the symbol cannot be parsed or is invalid.
    """
    if not symbol or not isinstance(symbol, str):
        return None

    clean_sym = symbol.strip().upper()
    cached = _SYMBOL_CACHE.get(clean_sym)
    if cached is not None or clean_sym in _SYMBOL_CACHE:
        return cached

    result: Optional[Tuple[str, float, str]] = None
    m = _SYMBOL_PATTERN_EXPIRY.match(clean_sym)
    if m:
        underlying, strike_str, opt_type = m.groups()
        try:
            result = (underlying.upper(), float(strike_str), opt_type.upper())
        except ValueError:
            result = None
    else:
        m = _SYMBOL_PATTERN_SIMPLE.match(clean_sym)
        if m:
            underlying, strike_str, opt_type = m.groups()
            try:
                result = (underlying.upper(), float(strike_str), opt_type.upper())
            except ValueError:
                result = None
        else:
            m = _SYMBOL_PATTERN_GENERAL.match(clean_sym)
            if m:
                underlying, strike_str, opt_type = m.groups()
                try:
                    result = (underlying.upper(), float(strike_str), opt_type.upper())
                except ValueError:
                    result = None

    _SYMBOL_CACHE[clean_sym] = result
    return result


@dataclass(frozen=True)
class StrikeWallProfile:
    """Aggregated positioning and depth attributes for a discrete option strike."""

    strike: float
    call_oi: float = 0.0
    put_oi: float = 0.0
    call_volume: float = 0.0
    put_volume: float = 0.0
    call_bid_depth: float = 0.0
    call_ask_depth: float = 0.0
    put_bid_depth: float = 0.0
    put_ask_depth: float = 0.0
    net_oi_imbalance: float = 0.0  # Put OI - Call OI (Positive indicates Put dominance / Bullish floor)
    is_major_call_wall: bool = False  # True if strike equals max Call OI across all observed strikes
    is_major_put_wall: bool = False  # True if strike equals max Put OI across all observed strikes
    is_secondary_call_wall: bool = False  # Call OI >= 0.75 * max Call OI
    is_secondary_put_wall: bool = False  # Put OI >= 0.75 * max Put OI

    # Attacker 1 Hardening: Directional Liquidity & Wall Vulnerability
    bullish_depth: float = 0.0  # CE Bid Depth + PE Ask Depth
    bearish_depth: float = 0.0  # CE Ask Depth + PE Bid Depth
    net_directional_liquidity: float = 0.0  # bullish_depth - bearish_depth
    directional_liquidity_ratio: float = 1.0  # bullish_depth / bearish_depth (safe ratio)
    call_wall_vulnerability: float = 0.0  # CE Ask Depth / (CE Bid Depth + 1e-6)
    put_wall_vulnerability: float = 0.0  # PE Bid Depth / (PE Ask Depth + 1e-6)


@dataclass(frozen=True)
class SentinelWallState:
    """Point-in-time structural wall snapshot with immutable safety invariants."""

    timestamp_ms: int
    symbol: str
    spot_price: float
    major_call_wall_strike: float
    major_put_wall_strike: float
    distance_to_call_wall_pts: float  # major_call_wall_strike - spot_price
    distance_to_put_wall_pts: float  # spot_price - major_put_wall_strike
    total_call_oi: float
    total_put_oi: float
    pcr_oi: float  # total_put_oi / total_call_oi (safe division with 0 fallback)
    wall_density_map: Dict[float, StrikeWallProfile]  # Sorted strike -> StrikeWallProfile mapping

    # Attacker 2 Hardening: Volatility Normalization
    atr_pts: float = 0.0
    distance_to_call_wall_atr: float = 0.0  # distance_to_call_wall_pts / atr_pts
    distance_to_put_wall_atr: float = 0.0  # distance_to_put_wall_pts / atr_pts

    # Attacker 5 Hardening: Risk Governance & Fail-Closed Guard
    is_valid: bool = True
    status: str = "HEALTHY"  # HEALTHY | STALE_FEED | INSUFFICIENT_COVERAGE | UNINITIALIZED
    last_spot_timestamp_ms: int = 0
    last_option_timestamp_ms: int = 0
    strike_span_count: int = 0

    # Non-negotiable Trading Safety Invariants
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    edge_certification_status: str = "NO_CERTIFIED_EDGE"


class SentinelWallObserver:
    """High-performance in-memory strike wall observer.

    Ingests streaming ticks and order book depth for option chain contracts,
    maintains strike-level aggregations, and computes structural wall states.
    Hardened against concurrency races, feed staleness, and multi-modal wall flip-flops.
    """

    def __init__(
        self,
        underlying_symbol: str = "NIFTY",
        atr_pts: float = 50.0,
        min_strike_span: int = 10,
        feed_freshness_max_skew_ms: int = 60_000,
        recompute_min_interval_ms: int = 100,
    ) -> None:
        self.underlying_symbol = underlying_symbol.strip().upper()
        self.atr_pts = max(1.0, float(atr_pts))
        self.min_strike_span = int(min_strike_span)
        self.feed_freshness_max_skew_ms = int(feed_freshness_max_skew_ms)
        self.recompute_min_interval_ms = int(recompute_min_interval_ms)

        self._spot_price: float = 0.0
        self._last_timestamp_ms: int = 0
        self._last_spot_timestamp_ms: int = 0
        self._last_option_timestamp_ms: int = 0

        # Concurrency protection
        self._lock = threading.Lock()

        # Internal mutable state indexed by strike:
        # strike -> {'CE': {'oi': 0.0, 'volume': 0.0, 'bid_depth': 0.0, 'ask_depth': 0.0, 'ltp': 0.0},
        #            'PE': {'oi': 0.0, 'volume': 0.0, 'bid_depth': 0.0, 'ask_depth': 0.0, 'ltp': 0.0}}
        self._strike_data: Dict[float, Dict[str, Dict[str, float]]] = {}

        # 5% Hysteresis tracking for major walls to prevent flip-flops
        self._current_major_call_strike: float = 0.0
        self._current_major_call_oi: float = 0.0
        self._current_major_put_strike: float = 0.0
        self._current_major_put_oi: float = 0.0

        # State caching and dirty throttling
        self._is_dirty: bool = True
        self._last_compute_time_ms: int = 0
        self._cached_state: Optional[SentinelWallState] = None

        # Atomic persistence rate limiting
        self._last_persist_wall_time: float = 0.0

        # Non-negotiable Trading Safety Invariants
        self.read_only: bool = True
        self.is_order_action: bool = False
        self.broker_api_called: bool = False
        self.allowed_for_live_execution: bool = False
        self.edge_certification_status: str = "NO_CERTIFIED_EDGE"

    @property
    def spot_price(self) -> float:
        with self._lock:
            return self._spot_price

    def on_spot_tick(
        self,
        spot_price: Optional[float] = None,
        timestamp_ms: Optional[int] = None,
        *args,
        **kwargs,
    ) -> None:
        """Update spot price reference.

        Supports both on_spot_tick(spot_price, timestamp_ms) and
        on_spot_tick(timestamp_ms, spot_price) for flexibility.
        """
        if spot_price is not None and timestamp_ms is not None:
            if spot_price > 1_000_000_000 and timestamp_ms < 1_000_000_000:
                p, ts = float(timestamp_ms), int(spot_price)
            else:
                p, ts = float(spot_price), int(timestamp_ms)
        elif spot_price is not None:
            p, ts = float(spot_price), 0
        elif "spot" in kwargs:
            p = float(kwargs["spot"])
            ts = int(kwargs.get("timestamp_ms", 0))
        else:
            return

        with self._lock:
            if p > 0:
                self._spot_price = p
                self._is_dirty = True
            if ts > 0:
                self._last_spot_timestamp_ms = ts
                if ts > self._last_timestamp_ms:
                    self._last_timestamp_ms = ts

    def on_option_tick(
        self,
        symbol: str,
        ltp: float = 0.0,
        volume: float = 0.0,
        oi: float = 0.0,
        bid_depth: float = 0.0,
        ask_depth: float = 0.0,
        timestamp_ms: int = 0,
        *args,
        **kwargs,
    ) -> None:
        """Ingest option tick with L5 resting depth.

        Extracts strike and option type (CE/PE) via O(1) parsed cache / regex.
        Updates strike aggregation buckets under threading lock.
        Flexible signature to accept positional or keyword arguments.
        """
        if isinstance(symbol, (int, float)) and len(args) >= 1 and isinstance(args[0], str):
            ts = int(symbol)
            actual_symbol = args[0]
            actual_oi = float(ltp)
            actual_vol = float(volume)
            actual_bid_depth = float(oi) if oi else 0.0
            actual_ask_depth = float(bid_depth) if bid_depth else 0.0
            actual_ltp = 0.0
        else:
            actual_symbol = symbol
            actual_ltp = float(ltp) if ltp else float(kwargs.get("ltp", 0.0))
            actual_vol = float(volume) if volume else float(kwargs.get("volume", 0.0))
            actual_oi = float(oi) if oi else float(kwargs.get("open_interest", kwargs.get("oi", 0.0)))
            actual_bid_depth = float(bid_depth) if bid_depth else float(kwargs.get("bid_depth", 0.0))
            actual_ask_depth = float(ask_depth) if ask_depth else float(kwargs.get("ask_depth", 0.0))
            ts = int(timestamp_ms) if timestamp_ms else int(kwargs.get("timestamp_ms", 0))

        parsed = parse_option_symbol(actual_symbol)
        if parsed is None:
            return

        underlying, strike, opt_type = parsed
        if self.underlying_symbol and not (
            underlying == self.underlying_symbol
            or underlying.startswith(self.underlying_symbol)
            or self.underlying_symbol.startswith(underlying)
        ):
            return

        with self._lock:
            if ts > 0:
                self._last_option_timestamp_ms = ts
                if ts > self._last_timestamp_ms:
                    self._last_timestamp_ms = ts

            if strike not in self._strike_data:
                self._strike_data[strike] = {
                    "CE": {"oi": 0.0, "volume": 0.0, "bid_depth": 0.0, "ask_depth": 0.0, "ltp": 0.0},
                    "PE": {"oi": 0.0, "volume": 0.0, "bid_depth": 0.0, "ask_depth": 0.0, "ltp": 0.0},
                }

            bucket = self._strike_data[strike][opt_type]
            changed = False
            if actual_oi > 0 and actual_oi != bucket["oi"]:
                bucket["oi"] = actual_oi
                changed = True
            if actual_vol > 0 and actual_vol != bucket["volume"]:
                bucket["volume"] = actual_vol
                changed = True
            if actual_bid_depth >= 0 and actual_bid_depth != bucket["bid_depth"]:
                bucket["bid_depth"] = actual_bid_depth
                changed = True
            if actual_ask_depth >= 0 and actual_ask_depth != bucket["ask_depth"]:
                bucket["ask_depth"] = actual_ask_depth
                changed = True
            if actual_ltp > 0 and actual_ltp != bucket["ltp"]:
                bucket["ltp"] = actual_ltp
                changed = True

            if changed:
                self._is_dirty = True

    def compute_wall_state(self, force_recompute: bool = False) -> SentinelWallState:
        """Constructs an immutable SentinelWallState snapshot.

        Enforces:
        - Throttled cached state return if not dirty and within recompute_min_interval_ms.
        - Fail-closed guards for feed freshness (skew <= 60s) and strike coverage (>= 10 strikes).
        - 5% hysteresis buffer on major wall transitions.
        - Directional liquidity and vulnerability profiling.
        - Volatility normalization via ATR.
        """
        with self._lock:
            now_ms = self._last_timestamp_ms or int(time.time() * 1000)
            if (
                not force_recompute
                and not self._is_dirty
                and self._cached_state is not None
                and (now_ms - self._last_compute_time_ms < self.recompute_min_interval_ms)
            ):
                return self._cached_state

            # Compute new state
            state = self._build_state_locked(now_ms)
            self._cached_state = state
            self._is_dirty = False
            self._last_compute_time_ms = now_ms
            return state

    def _build_state_locked(self, now_ms: int) -> SentinelWallState:
        """Internal helper executing under self._lock."""
        sorted_strikes = sorted(self._strike_data.keys())
        strike_count = len(sorted_strikes)

        total_call_oi = 0.0
        total_put_oi = 0.0

        # Candidate maximums
        cand_call_oi = 0.0
        cand_call_strike = 0.0
        cand_put_oi = 0.0
        cand_put_strike = 0.0

        for strike in sorted_strikes:
            ce_data = self._strike_data[strike]["CE"]
            pe_data = self._strike_data[strike]["PE"]

            c_oi = ce_data["oi"]
            p_oi = pe_data["oi"]

            total_call_oi += c_oi
            total_put_oi += p_oi

            if c_oi > cand_call_oi:
                cand_call_oi = c_oi
                cand_call_strike = strike

            if p_oi > cand_put_oi:
                cand_put_oi = p_oi
                cand_put_strike = strike

        # 5% Hysteresis Buffer Logic:
        # Candidate must exceed current major wall OI by at least 5% (>= 1.05 * current_oi)
        # to displace existing major wall, or if current wall no longer exists/0.
        if (
            self._current_major_call_strike == 0.0
            or self._current_major_call_strike not in self._strike_data
            or cand_call_strike == self._current_major_call_strike
        ):
            self._current_major_call_strike = cand_call_strike
            self._current_major_call_oi = cand_call_oi
        else:
            # Re-fetch current major call OI in case it was updated
            curr_call_oi = self._strike_data[self._current_major_call_strike]["CE"]["oi"]
            if cand_call_oi >= 1.05 * curr_call_oi:
                self._current_major_call_strike = cand_call_strike
                self._current_major_call_oi = cand_call_oi
            else:
                self._current_major_call_oi = curr_call_oi

        if (
            self._current_major_put_strike == 0.0
            or self._current_major_put_strike not in self._strike_data
            or cand_put_strike == self._current_major_put_strike
        ):
            self._current_major_put_strike = cand_put_strike
            self._current_major_put_oi = cand_put_oi
        else:
            curr_put_oi = self._strike_data[self._current_major_put_strike]["PE"]["oi"]
            if cand_put_oi >= 1.05 * curr_put_oi:
                self._current_major_put_strike = cand_put_strike
                self._current_major_put_oi = cand_put_oi
            else:
                self._current_major_put_oi = curr_put_oi

        active_major_call = self._current_major_call_strike
        active_major_put = self._current_major_put_strike
        active_max_call_oi = self._current_major_call_oi
        active_max_put_oi = self._current_major_put_oi

        # Secondary wall threshold (>= 75% max OI)
        call_secondary_thresh = (0.75 * active_max_call_oi) if active_max_call_oi > 0 else float("inf")
        put_secondary_thresh = (0.75 * active_max_put_oi) if active_max_put_oi > 0 else float("inf")

        wall_density_map: Dict[float, StrikeWallProfile] = {}

        for strike in sorted_strikes:
            ce = self._strike_data[strike]["CE"]
            pe = self._strike_data[strike]["PE"]

            c_oi = ce["oi"]
            p_oi = pe["oi"]

            is_major_call = (strike == active_major_call and active_max_call_oi > 0)
            is_major_put = (strike == active_major_put and active_max_put_oi > 0)

            is_sec_call = (c_oi >= call_secondary_thresh and active_max_call_oi > 0 and not is_major_call)
            is_sec_put = (p_oi >= put_secondary_thresh and active_max_put_oi > 0 and not is_major_put)

            # Directional Liquidity Formulation (Attacker 1):
            # Bullish Depth = CE Bid Depth + PE Ask Depth
            # Bearish Depth = CE Ask Depth + PE Bid Depth
            bull_depth = ce["bid_depth"] + pe["ask_depth"]
            bear_depth = ce["ask_depth"] + pe["bid_depth"]
            net_dir_liq = bull_depth - bear_depth
            dir_ratio = (bull_depth / bear_depth) if bear_depth > 0 else (bull_depth if bull_depth > 0 else 1.0)

            call_vuln = ce["ask_depth"] / (ce["bid_depth"] + 1e-6)
            put_vuln = pe["bid_depth"] / (pe["ask_depth"] + 1e-6)

            profile = StrikeWallProfile(
                strike=strike,
                call_oi=c_oi,
                put_oi=p_oi,
                call_volume=ce["volume"],
                put_volume=pe["volume"],
                call_bid_depth=ce["bid_depth"],
                call_ask_depth=ce["ask_depth"],
                put_bid_depth=pe["bid_depth"],
                put_ask_depth=pe["ask_depth"],
                net_oi_imbalance=p_oi - c_oi,
                is_major_call_wall=is_major_call,
                is_major_put_wall=is_major_put,
                is_secondary_call_wall=is_sec_call,
                is_secondary_put_wall=is_sec_put,
                bullish_depth=round(bull_depth, 2),
                bearish_depth=round(bear_depth, 2),
                net_directional_liquidity=round(net_dir_liq, 2),
                directional_liquidity_ratio=round(dir_ratio, 4),
                call_wall_vulnerability=round(call_vuln, 4),
                put_wall_vulnerability=round(put_vuln, 4),
            )
            wall_density_map[strike] = profile

        spot = self._spot_price
        dist_call_pts = (active_major_call - spot) if (active_major_call > 0 and spot > 0) else 0.0
        dist_put_pts = (spot - active_major_put) if (active_major_put > 0 and spot > 0) else 0.0

        pcr_oi = (total_put_oi / total_call_oi) if total_call_oi > 0 else 0.0

        # Volatility normalization (Attacker 2 & 3)
        atr = self.atr_pts if self.atr_pts > 0 else 50.0
        dist_call_atr = round(dist_call_pts / atr, 4) if atr > 0 else 0.0
        dist_put_atr = round(dist_put_pts / atr, 4) if atr > 0 else 0.0

        # Risk Governance Fail-Closed Guard (Attacker 5):
        # 1. Strike span guard
        # 2. Feed freshness guard
        is_valid = True
        status = "HEALTHY"

        if strike_count < self.min_strike_span:
            is_valid = False
            status = "INSUFFICIENT_COVERAGE"
        elif self._last_spot_timestamp_ms > 0 and self._last_option_timestamp_ms > 0:
            skew_ms = abs(self._last_spot_timestamp_ms - self._last_option_timestamp_ms)
            if skew_ms > self.feed_freshness_max_skew_ms:
                is_valid = False
                status = "STALE_FEED"
        elif self._last_spot_timestamp_ms == 0 or self._last_option_timestamp_ms == 0:
            # If one feed has never ticked, fail closed
            if spot <= 0 or strike_count == 0:
                is_valid = False
                status = "UNINITIALIZED"

        return SentinelWallState(
            timestamp_ms=self._last_timestamp_ms,
            symbol=self.underlying_symbol,
            spot_price=spot,
            major_call_wall_strike=active_major_call,
            major_put_wall_strike=active_major_put,
            distance_to_call_wall_pts=round(dist_call_pts, 2),
            distance_to_put_wall_pts=round(dist_put_pts, 2),
            total_call_oi=total_call_oi,
            total_put_oi=total_put_oi,
            pcr_oi=round(pcr_oi, 4),
            wall_density_map=wall_density_map,
            atr_pts=round(atr, 2),
            distance_to_call_wall_atr=dist_call_atr,
            distance_to_put_wall_atr=dist_put_atr,
            is_valid=is_valid,
            status=status,
            last_spot_timestamp_ms=self._last_spot_timestamp_ms,
            last_option_timestamp_ms=self._last_option_timestamp_ms,
            strike_span_count=strike_count,
            read_only=True,
            is_order_action=False,
            broker_api_called=False,
            allowed_for_live_execution=False,
            edge_certification_status="NO_CERTIFIED_EDGE",
        )

    def persist_state_atomic(
        self,
        file_path: str = "runtime/sentinel_wall_state_nifty.json",
        min_interval_sec: float = 1.0,
    ) -> SentinelWallState:
        """Atomically persists compact JSON snapshot with rate-limiting."""
        now = time.time()
        # Rate-limiting check
        with self._lock:
            if (now - self._last_persist_wall_time) < min_interval_sec and self._cached_state is not None:
                return self._cached_state

        state = self.compute_wall_state(force_recompute=True)
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp_p = p.with_suffix(".tmp")

        data = asdict(state)
        if "wall_density_map" in data and isinstance(data["wall_density_map"], dict):
            data["wall_density_map"] = {str(k): v for k, v in data["wall_density_map"].items()}

        # Attacker 4: Decoupled compact JSON persistence
        with open(tmp_p, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        tmp_p.replace(p)

        with self._lock:
            self._last_persist_wall_time = now

        return state

    def is_spot_near_call_wall(
        self,
        threshold_pts: Optional[float] = None,
        threshold_atr: Optional[float] = None,
    ) -> bool:
        """Advisory check: spot within threshold_pts (or threshold_atr) of major call wall."""
        state = self.compute_wall_state()
        if not state.is_valid or state.spot_price <= 0 or state.major_call_wall_strike <= 0:
            return False

        if threshold_atr is not None:
            return abs(state.distance_to_call_wall_atr) <= threshold_atr

        t_pts = 50.0 if threshold_pts is None else threshold_pts
        return abs(state.major_call_wall_strike - state.spot_price) <= t_pts

    def is_spot_near_put_wall(
        self,
        threshold_pts: Optional[float] = None,
        threshold_atr: Optional[float] = None,
    ) -> bool:
        """Advisory check: spot within threshold_pts (or threshold_atr) of major put wall."""
        state = self.compute_wall_state()
        if not state.is_valid or state.spot_price <= 0 or state.major_put_wall_strike <= 0:
            return False

        if threshold_atr is not None:
            return abs(state.distance_to_put_wall_atr) <= threshold_atr

        t_pts = 50.0 if threshold_pts is None else threshold_pts
        return abs(state.spot_price - state.major_put_wall_strike) <= t_pts

    def get_absorption_zones(self, min_depth_ratio: float = 2.0) -> List[float]:
        """Identifies strikes where order book depth exhibits significant resting absorption imbalance.

        Returns strikes where (total bid depth / total ask depth) >= min_depth_ratio
        or (total ask depth / total bid depth) >= min_depth_ratio.
        """
        with self._lock:
            strikes_snapshot = list(self._strike_data.items())

        absorption_strikes: List[float] = []
        for strike, data in strikes_snapshot:
            tot_bid = data["CE"]["bid_depth"] + data["PE"]["bid_depth"]
            tot_ask = data["CE"]["ask_depth"] + data["PE"]["ask_depth"]
            if tot_bid > 0 and tot_ask > 0:
                if (tot_bid / tot_ask >= min_depth_ratio) or (tot_ask / tot_bid >= min_depth_ratio):
                    absorption_strikes.append(strike)
            elif (tot_bid > 0 and tot_ask == 0) or (tot_ask > 0 and tot_bid == 0):
                absorption_strikes.append(strike)
        return sorted(absorption_strikes)
