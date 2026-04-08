from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
import os
from typing import Any


DEFAULT_STOCK_OPTION_SYMBOLS = (
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "INFY",
    "TCS",
)


@dataclass(frozen=True)
class StockOptionSubsystemConfig:
    enabled: bool = False
    whitelisted_symbols: tuple[str, ...] = DEFAULT_STOCK_OPTION_SYMBOLS
    max_symbols_per_cycle: int = 4
    max_expiries_per_symbol: int = 1
    strikes_around_atm: int = 2
    min_open_interest: float = 1500.0
    min_volume: float = 500.0
    max_spread_pct: float = 0.60
    max_quote_age_sec: float = 3.0
    min_signal_strength: float = 0.55
    require_tradingsymbol: bool = True
    require_instrument_token: bool = True


@dataclass(frozen=True)
class StockOptionCandidate:
    symbol: str
    underlying: str
    instrument: str
    instrument_type: str
    expiry: str
    strike: float
    option_type: str
    tradingsymbol: str | None
    instrument_token: int | None
    ltp: float
    best_bid: float
    best_ask: float
    volume: float
    oi: float
    quote_age_sec: float
    spread_pct: float
    moneyness_abs: float
    liquidity_score: float
    execution_score: float
    score: float
    candidate_status: str
    rejection_reason: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_trade_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "instrument": self.instrument,
            "instrument_type": self.instrument_type,
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type,
            "right": self.option_type,
            "tradingsymbol": self.tradingsymbol,
            "instrument_token": self.instrument_token,
            "entry_price": self.best_ask,
            "signal_price": self.ltp,
            "opt_ltp": self.ltp,
            "opt_bid": self.best_bid,
            "opt_ask": self.best_ask,
            "volume": self.volume,
            "oi": self.oi,
            "quote_age_sec": self.quote_age_sec,
            "spread_pct": self.spread_pct,
            "liquidity_score": self.liquidity_score,
            "execution_score": self.execution_score,
            "final_score": self.score,
            "opportunity_score": self.score,
            "candidate_status": self.candidate_status,
            "candidate_type": "stock_option",
            "strategy_family": "stock_options",
            "permission": "EXECUTE" if self.candidate_status == "executable" else "ADVISORY_ONLY",
            "tradable": self.candidate_status == "executable",
            "planning_only": self.candidate_status != "executable",
            "execution_allowed": self.candidate_status == "executable",
            "reason": self.rejection_reason,
            "source_flags": {
                "stock_option_subsystem": True,
                "liquidity_score": self.liquidity_score,
                "execution_score": self.execution_score,
                "notes": list(self.notes),
            },
        }


@dataclass(frozen=True)
class StockOptionEvaluation:
    candidates: tuple[StockOptionCandidate, ...]
    blocked_symbols: dict[str, str]
    scanned_symbols: tuple[str, ...]



def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}



def build_default_stock_option_config() -> StockOptionSubsystemConfig:
    raw_symbols = os.getenv("STOCK_OPTION_SYMBOLS", ",".join(DEFAULT_STOCK_OPTION_SYMBOLS))
    symbols = tuple(str(s).strip().upper() for s in raw_symbols.split(",") if str(s).strip())
    return StockOptionSubsystemConfig(
        enabled=_env_flag("ENABLE_STOCK_OPTIONS", False),
        whitelisted_symbols=symbols or DEFAULT_STOCK_OPTION_SYMBOLS,
        max_symbols_per_cycle=max(1, int(os.getenv("STOCK_OPTION_MAX_SYMBOLS_PER_CYCLE", "4"))),
        max_expiries_per_symbol=max(1, int(os.getenv("STOCK_OPTION_MAX_EXPIRIES_PER_SYMBOL", "1"))),
        strikes_around_atm=max(0, int(os.getenv("STOCK_OPTION_STRIKES_AROUND_ATM", "2"))),
        min_open_interest=float(os.getenv("STOCK_OPTION_MIN_OI", "1500")),
        min_volume=float(os.getenv("STOCK_OPTION_MIN_VOLUME", "500")),
        max_spread_pct=float(os.getenv("STOCK_OPTION_MAX_SPREAD_PCT", "0.60")),
        max_quote_age_sec=float(os.getenv("STOCK_OPTION_MAX_QUOTE_AGE_SEC", "3.0")),
        min_signal_strength=float(os.getenv("STOCK_OPTION_MIN_SIGNAL_STRENGTH", "0.55")),
        require_tradingsymbol=_env_flag("STOCK_OPTION_REQUIRE_TRADINGSYMBOL", True),
        require_instrument_token=_env_flag("STOCK_OPTION_REQUIRE_INSTRUMENT_TOKEN", True),
    )



def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default



def _norm_symbol(value: Any) -> str:
    return str(value or "").strip().upper()



def _parse_expiry(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("missing_expiry")
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    return datetime.fromisoformat(text)



def _spread_pct(best_bid: float, best_ask: float) -> float:
    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        return 999.0
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0:
        return 999.0
    return ((best_ask - best_bid) / mid) * 100.0



def _liquidity_score(volume: float, oi: float, spread_pct: float, quote_age_sec: float, cfg: StockOptionSubsystemConfig) -> float:
    volume_component = min(1.0, volume / max(cfg.min_volume, 1.0))
    oi_component = min(1.0, oi / max(cfg.min_open_interest, 1.0))
    spread_component = max(0.0, 1.0 - (spread_pct / max(cfg.max_spread_pct, 1e-6)))
    freshness_component = max(0.0, 1.0 - (quote_age_sec / max(cfg.max_quote_age_sec, 1e-6)))
    return round((0.30 * volume_component) + (0.30 * oi_component) + (0.25 * spread_component) + (0.15 * freshness_component), 4)



def _execution_score(liquidity_score: float, moneyness_abs: float, strikes_around_atm: int) -> float:
    denominator = max(1.0, float(max(strikes_around_atm, 1)))
    atm_component = max(0.0, 1.0 - (moneyness_abs / denominator))
    return round((0.65 * liquidity_score) + (0.35 * atm_component), 4)



def _candidate_status(contract: dict[str, Any], cfg: StockOptionSubsystemConfig) -> tuple[str, str | None, tuple[str, ...]]:
    notes: list[str] = []
    symbol = _norm_symbol(contract.get("underlying") or contract.get("symbol"))
    if symbol not in set(cfg.whitelisted_symbols):
        return "blocked", "symbol_not_whitelisted", tuple(notes)
    if cfg.require_tradingsymbol and not contract.get("tradingsymbol"):
        return "blocked", "missing_tradingsymbol", tuple(notes)
    if cfg.require_instrument_token and contract.get("instrument_token") in (None, "", 0):
        return "blocked", "missing_instrument_token", tuple(notes)

    oi = _safe_float(contract.get("oi"), 0.0) or 0.0
    volume = _safe_float(contract.get("volume"), 0.0) or 0.0
    quote_age_sec = _safe_float(contract.get("quote_age_sec"), 999.0) or 999.0
    bid = _safe_float(contract.get("best_bid", contract.get("bid")), 0.0) or 0.0
    ask = _safe_float(contract.get("best_ask", contract.get("ask")), 0.0) or 0.0
    spread_pct = _spread_pct(bid, ask)

    if oi < cfg.min_open_interest:
        return "blocked", "oi_below_threshold", tuple(notes)
    if volume < cfg.min_volume:
        return "blocked", "volume_below_threshold", tuple(notes)
    if quote_age_sec > cfg.max_quote_age_sec:
        return "blocked", "quote_stale", tuple(notes)
    if spread_pct > cfg.max_spread_pct:
        return "blocked", "spread_too_wide", tuple(notes)

    if spread_pct > (cfg.max_spread_pct * 0.75):
        notes.append("spread_near_limit")
    if quote_age_sec > (cfg.max_quote_age_sec * 0.75):
        notes.append("quote_age_near_limit")
    if oi < (cfg.min_open_interest * 1.25):
        notes.append("oi_only_marginal")
    if volume < (cfg.min_volume * 1.25):
        notes.append("volume_only_marginal")

    if notes:
        return "advisory_only", None, tuple(notes)
    return "executable", None, tuple(notes)



def _select_contracts_for_symbol(symbol_snapshot: dict[str, Any], cfg: StockOptionSubsystemConfig) -> tuple[list[dict[str, Any]], str | None]:
    symbol = _norm_symbol(symbol_snapshot.get("symbol"))
    if symbol not in set(cfg.whitelisted_symbols):
        return [], "symbol_not_whitelisted"
    spot = _safe_float(symbol_snapshot.get("spot") or symbol_snapshot.get("ltp"))
    if spot is None or spot <= 0:
        return [], "missing_spot"
    chain = symbol_snapshot.get("option_chain")
    if not isinstance(chain, list) or not chain:
        return [], "missing_option_chain"

    rows: list[dict[str, Any]] = []
    for raw in chain:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["underlying"] = symbol
        strike = _safe_float(row.get("strike"))
        expiry = row.get("expiry") or row.get("expiry_date")
        option_type = _norm_symbol(row.get("option_type") or row.get("type") or row.get("right"))
        if strike is None or not expiry or option_type not in {"CE", "PE"}:
            continue
        row["strike"] = strike
        row["expiry"] = str(expiry)
        row["option_type"] = option_type
        row["moneyness_abs"] = abs(strike - spot)
        rows.append(row)

    if not rows:
        return [], "no_valid_contracts"

    try:
        expiries = sorted({_parse_expiry(row["expiry"]).date().isoformat() for row in rows})
    except Exception:
        expiries = sorted({str(row["expiry"]) for row in rows})
    allowed_expiries = set(expiries[: cfg.max_expiries_per_symbol])
    rows = [row for row in rows if str(row["expiry"]) in allowed_expiries]
    rows.sort(key=lambda row: (row["moneyness_abs"], str(row["expiry"]), str(row["option_type"])))

    if cfg.strikes_around_atm <= 0:
        return rows, None

    unique_strikes = sorted({float(row["strike"]) for row in rows}, key=lambda value: abs(value - spot))
    allowed_strikes = set(unique_strikes[: (cfg.strikes_around_atm * 2) + 1])
    rows = [row for row in rows if float(row["strike"]) in allowed_strikes]
    rows.sort(key=lambda row: (row["moneyness_abs"], str(row["expiry"]), str(row["option_type"])))
    return rows, None



def evaluate_stock_option_subsystem(
    market_data_list: list[dict[str, Any]] | None,
    config: StockOptionSubsystemConfig | None = None,
    signal_strength_by_symbol: dict[str, float] | None = None,
) -> StockOptionEvaluation:
    cfg = config or build_default_stock_option_config()
    if not cfg.enabled:
        return StockOptionEvaluation(candidates=tuple(), blocked_symbols={}, scanned_symbols=tuple())

    signal_strength_by_symbol = {
        _norm_symbol(k): float(v) for k, v in dict(signal_strength_by_symbol or {}).items()
    }
    blocked_symbols: dict[str, str] = {}
    scanned_symbols: list[str] = []
    candidates: list[StockOptionCandidate] = []

    for snapshot in list(market_data_list or []):
        if not isinstance(snapshot, dict):
            continue
        symbol = _norm_symbol(snapshot.get("symbol"))
        if not symbol:
            continue
        if len(scanned_symbols) >= cfg.max_symbols_per_cycle and symbol not in scanned_symbols:
            break
        if symbol not in scanned_symbols:
            scanned_symbols.append(symbol)
        strength = float(signal_strength_by_symbol.get(symbol, 1.0))
        if strength < cfg.min_signal_strength:
            blocked_symbols[symbol] = "signal_below_threshold"
            continue
        selected_rows, selection_reason = _select_contracts_for_symbol(snapshot, cfg)
        if selection_reason:
            blocked_symbols[symbol] = selection_reason
            continue
        for row in selected_rows:
            status, rejection_reason, notes = _candidate_status(row, cfg)
            bid = _safe_float(row.get("best_bid", row.get("bid")), 0.0) or 0.0
            ask = _safe_float(row.get("best_ask", row.get("ask")), 0.0) or 0.0
            ltp = _safe_float(row.get("ltp"), ask or bid or 0.0) or 0.0
            spread_pct = _spread_pct(bid, ask)
            quote_age_sec = _safe_float(row.get("quote_age_sec"), 999.0) or 999.0
            volume = _safe_float(row.get("volume"), 0.0) or 0.0
            oi = _safe_float(row.get("oi"), 0.0) or 0.0
            strike = _safe_float(row.get("strike"), 0.0) or 0.0
            moneyness_abs = _safe_float(row.get("moneyness_abs"), 999999.0) or 999999.0
            liquidity_score = _liquidity_score(volume, oi, spread_pct, quote_age_sec, cfg)
            execution_score = _execution_score(liquidity_score, moneyness_abs, cfg.strikes_around_atm)
            final_score = round((0.55 * execution_score) + (0.35 * liquidity_score) + (0.10 * min(1.0, strength)), 4)
            candidates.append(
                StockOptionCandidate(
                    symbol=symbol,
                    underlying=symbol,
                    instrument="OPT",
                    instrument_type="OPT",
                    expiry=str(row.get("expiry")),
                    strike=strike,
                    option_type=_norm_symbol(row.get("option_type")),
                    tradingsymbol=row.get("tradingsymbol"),
                    instrument_token=int(row.get("instrument_token")) if row.get("instrument_token") not in (None, "", 0) else None,
                    ltp=ltp,
                    best_bid=bid,
                    best_ask=ask,
                    volume=volume,
                    oi=oi,
                    quote_age_sec=quote_age_sec,
                    spread_pct=spread_pct,
                    moneyness_abs=moneyness_abs,
                    liquidity_score=liquidity_score,
                    execution_score=execution_score,
                    score=final_score,
                    candidate_status=status,
                    rejection_reason=rejection_reason,
                    notes=notes,
                )
            )

    candidates.sort(
        key=lambda row: (
            0 if row.candidate_status == "executable" else 1,
            -row.score,
            row.quote_age_sec,
            row.spread_pct,
        )
    )
    return StockOptionEvaluation(
        candidates=tuple(candidates),
        blocked_symbols=blocked_symbols,
        scanned_symbols=tuple(scanned_symbols),
    )
