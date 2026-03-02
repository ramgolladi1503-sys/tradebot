# config/config.py
# Migration note:
# Added market-context/depth-policy config keys for deterministic LIVE vs OFFHOURS behavior.

# -------------------------------
# Env loader (optional)
# -------------------------------
import os
import json
import csv
from pathlib import Path
from core.paths import db_dir as canonical_db_dir, desk_logs_dir as canonical_desk_logs_dir, desks_dir as canonical_desks_dir, ensure_dir as canonical_ensure_dir, trade_db_path as canonical_trade_db_path
from core.runtime_paths import (
    DATA_ROOT as _DATA_ROOT,
    DESKS_ROOT as _DESKS_ROOT,
    LOGS_ROOT as _LOGS_ROOT,
    REPORTS_ROOT as _REPORTS_ROOT,
    LOCKS_ROOT as _LOCKS_ROOT,
    DB_ROOT as _DB_ROOT,
)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

DATA_ROOT = os.getenv("DATA_ROOT", str(_DATA_ROOT))
DESKS_ROOT = os.getenv("DESKS_ROOT", str(_DESKS_ROOT))
LOGS_ROOT = os.getenv("LOGS_ROOT", str(_LOGS_ROOT))
REPORTS_ROOT = os.getenv("REPORTS_ROOT", str(_REPORTS_ROOT))
LOCKS_ROOT = os.getenv("LOCKS_ROOT", str(_LOCKS_ROOT))
DB_ROOT = os.getenv("DB_ROOT", str(_DB_ROOT))

# -------------------------------
# Kite / broker API credentials
# -------------------------------
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")

# -------------------------------
# Telegram bot credentials
# -------------------------------
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "true").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ONLY_TRADES = os.getenv("TELEGRAM_ONLY_TRADES", "true").lower() == "true"
TELEGRAM_ALLOW_NON_TRADE_ALERTS = os.getenv("TELEGRAM_ALLOW_NON_TRADE_ALERTS", "false").lower() == "true"
TELEGRAM_TRADE_VALIDITY_SEC = int(os.getenv("TELEGRAM_TRADE_VALIDITY_SEC", "180"))

# -------------------------------
# Capital & Risk Configuration
# -------------------------------
CAPITAL = 100000
# Canonical risk limits (percent as decimal)
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.004"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "-0.06"))
MAX_OPEN_RISK_PCT = float(os.getenv("MAX_OPEN_RISK_PCT", "0.02"))
# Portfolio exposure concentration limits
MAX_UNDERLYING_EXPOSURE_PCT = float(os.getenv("MAX_UNDERLYING_EXPOSURE_PCT", "0.40"))
MAX_POSITIONS_PER_UNDERLYING = int(os.getenv("MAX_POSITIONS_PER_UNDERLYING", "3"))
MAX_EXPIRY_CONCENTRATION_PCT = float(os.getenv("MAX_EXPIRY_CONCENTRATION_PCT", "0.65"))
MAX_NET_DELTA = float(os.getenv("MAX_NET_DELTA", "200"))
MAX_NET_VEGA = float(os.getenv("MAX_NET_VEGA", "120"))
EVENT_NET_DELTA_MULT = float(os.getenv("EVENT_NET_DELTA_MULT", "0.5"))
EVENT_NET_VEGA_MULT = float(os.getenv("EVENT_NET_VEGA_MULT", "0.5"))
# Backward-compatible aliases (deprecated)
MAX_RISK_PER_TRADE = MAX_RISK_PER_TRADE_PCT
MAX_DAILY_LOSS = MAX_DAILY_LOSS_PCT
MAX_TRADES_PER_DAY = 5
MAX_RISK_PER_TRADE_EQ = float(os.getenv("MAX_RISK_PER_TRADE_EQ", "0.02"))
MAX_RISK_PER_TRADE_FUT = float(os.getenv("MAX_RISK_PER_TRADE_FUT", "0.03"))
MAX_RISK_PER_TRADE_OPT = float(os.getenv("MAX_RISK_PER_TRADE_OPT", "0.03"))

# Portfolio allocator
PORTFOLIO_ALLOCATOR_ENABLE = True
PORTFOLIO_MAX_DELTA_PCT = float(os.getenv("PORTFOLIO_MAX_DELTA_PCT", "0.25"))
PORTFOLIO_MAX_GAMMA_PCT = float(os.getenv("PORTFOLIO_MAX_GAMMA_PCT", "0.10"))
PORTFOLIO_MAX_VEGA_PCT = float(os.getenv("PORTFOLIO_MAX_VEGA_PCT", "0.12"))
CORR_PENALTY = float(os.getenv("CORR_PENALTY", "0.2"))
STRESS_MOVE_PCT = float(os.getenv("STRESS_MOVE_PCT", "0.02"))
STRESS_VOL_PCT = float(os.getenv("STRESS_VOL_PCT", "0.3"))
MAX_STRESS_LOSS_PCT = float(os.getenv("MAX_STRESS_LOSS_PCT", "0.03"))

# Correlation map for symbol pairs (ordered tuple)
SYMBOL_CORRELATIONS = {
    tuple(sorted(("NIFTY", "BANKNIFTY"))): 0.85,
    tuple(sorted(("NIFTY", "SENSEX"))): 0.90,
    tuple(sorted(("BANKNIFTY", "SENSEX"))): 0.80,
}

# Regime-aware exposure multipliers
REGIME_EXPOSURE_MULT = {
    "TREND": {"delta": 1.1, "gamma": 0.9, "vega": 0.9},
    "RANGE": {"delta": 0.9, "gamma": 1.0, "vega": 1.0},
    "RANGE_VOLATILE": {"delta": 0.8, "gamma": 0.8, "vega": 0.8},
    "EVENT": {"delta": 0.5, "gamma": 0.4, "vega": 0.4},
    "PANIC": {"delta": 0.4, "gamma": 0.4, "vega": 0.4},
    "NEUTRAL": {"delta": 0.0, "gamma": 0.0, "vega": 0.0},
}

# Risk profiles (override defaults when selected)
RISK_PROFILE = os.getenv("RISK_PROFILE", "PILOT").upper()
RISK_PROFILE_LIMITS = {
    "PILOT": {
        "MAX_DAILY_LOSS_PCT": float(os.getenv("PILOT_MAX_DAILY_LOSS_PCT", "0.015")),
        "MAX_DRAWDOWN_PCT": float(os.getenv("PILOT_MAX_DRAWDOWN_PCT", "-0.04")),
        "MAX_RISK_PER_TRADE_PCT": float(os.getenv("PILOT_MAX_RISK_PER_TRADE_PCT", "0.0035")),
        "MAX_OPEN_RISK_PCT": float(os.getenv("PILOT_MAX_OPEN_RISK_PCT", "0.015")),
        "MAX_TRADES_PER_DAY": int(os.getenv("PILOT_MAX_TRADES_PER_DAY", "2")),
        "LOSS_STREAK_DOWNSIZE": int(os.getenv("PILOT_LOSS_STREAK_DOWNSIZE", "3")),
        "EVENT_REGIME_RISK_MULT": float(os.getenv("PILOT_EVENT_REGIME_RISK_MULT", "0.5")),
        "HIGH_ENTROPY_RISK_MULT": float(os.getenv("PILOT_HIGH_ENTROPY_RISK_MULT", "0.6")),
        "RECOVERY_MODE_MULT": float(os.getenv("PILOT_RECOVERY_MODE_MULT", "0.4")),
    },
    "NORMAL": {
        "MAX_DAILY_LOSS_PCT": float(os.getenv("NORMAL_MAX_DAILY_LOSS_PCT", "0.025")),
        "MAX_DRAWDOWN_PCT": float(os.getenv("NORMAL_MAX_DRAWDOWN_PCT", "-0.08")),
        "MAX_RISK_PER_TRADE_PCT": float(os.getenv("NORMAL_MAX_RISK_PER_TRADE_PCT", "0.005")),
        "MAX_OPEN_RISK_PCT": float(os.getenv("NORMAL_MAX_OPEN_RISK_PCT", "0.03")),
        "MAX_TRADES_PER_DAY": int(os.getenv("NORMAL_MAX_TRADES_PER_DAY", "4")),
        "LOSS_STREAK_DOWNSIZE": int(os.getenv("NORMAL_LOSS_STREAK_DOWNSIZE", "3")),
        "EVENT_REGIME_RISK_MULT": float(os.getenv("NORMAL_EVENT_REGIME_RISK_MULT", "0.6")),
        "HIGH_ENTROPY_RISK_MULT": float(os.getenv("NORMAL_HIGH_ENTROPY_RISK_MULT", "0.7")),
        "RECOVERY_MODE_MULT": float(os.getenv("NORMAL_RECOVERY_MODE_MULT", "0.5")),
    },
    "AGGRESSIVE": {
        "MAX_DAILY_LOSS_PCT": float(os.getenv("AGGRESSIVE_MAX_DAILY_LOSS_PCT", "0.04")),
        "MAX_DRAWDOWN_PCT": float(os.getenv("AGGRESSIVE_MAX_DRAWDOWN_PCT", "-0.12")),
        "MAX_RISK_PER_TRADE_PCT": float(os.getenv("AGGRESSIVE_MAX_RISK_PER_TRADE_PCT", "0.0075")),
        "MAX_OPEN_RISK_PCT": float(os.getenv("AGGRESSIVE_MAX_OPEN_RISK_PCT", "0.05")),
        "MAX_TRADES_PER_DAY": int(os.getenv("AGGRESSIVE_MAX_TRADES_PER_DAY", "6")),
        "LOSS_STREAK_DOWNSIZE": int(os.getenv("AGGRESSIVE_LOSS_STREAK_DOWNSIZE", "4")),
        "EVENT_REGIME_RISK_MULT": float(os.getenv("AGGRESSIVE_EVENT_REGIME_RISK_MULT", "0.7")),
        "HIGH_ENTROPY_RISK_MULT": float(os.getenv("AGGRESSIVE_HIGH_ENTROPY_RISK_MULT", "0.75")),
        "RECOVERY_MODE_MULT": float(os.getenv("AGGRESSIVE_RECOVERY_MODE_MULT", "0.6")),
    },
}
if RISK_PROFILE not in RISK_PROFILE_LIMITS:
    RISK_PROFILE = "PILOT"
_active_risk_limits = dict(RISK_PROFILE_LIMITS[RISK_PROFILE])
# Hard guard: pilot must remain conservative regardless of env overrides.
if _active_risk_limits["MAX_DAILY_LOSS_PCT"] > 0.02:
    _active_risk_limits["MAX_DAILY_LOSS_PCT"] = 0.02
MAX_DAILY_LOSS_PCT = float(_active_risk_limits["MAX_DAILY_LOSS_PCT"])
MAX_DRAWDOWN_PCT = float(_active_risk_limits["MAX_DRAWDOWN_PCT"])
MAX_RISK_PER_TRADE_PCT = float(_active_risk_limits["MAX_RISK_PER_TRADE_PCT"])
MAX_OPEN_RISK_PCT = float(_active_risk_limits["MAX_OPEN_RISK_PCT"])
MAX_TRADES_PER_DAY = int(_active_risk_limits["MAX_TRADES_PER_DAY"])
LOSS_STREAK_DOWNSIZE = int(_active_risk_limits["LOSS_STREAK_DOWNSIZE"])
EVENT_REGIME_RISK_MULT = float(_active_risk_limits["EVENT_REGIME_RISK_MULT"])
HIGH_ENTROPY_RISK_MULT = float(_active_risk_limits["HIGH_ENTROPY_RISK_MULT"])
RECOVERY_MODE_MULT = float(_active_risk_limits["RECOVERY_MODE_MULT"])
# Deterministic regime-aware risk clamps (used by RiskEngine)
REGIME_EVENT_DAILY_LOSS_MULT = float(os.getenv("REGIME_EVENT_DAILY_LOSS_MULT", "0.5"))
REGIME_EVENT_OPEN_RISK_MULT = float(os.getenv("REGIME_EVENT_OPEN_RISK_MULT", "0.6"))
REGIME_EVENT_MAX_TRADES_MULT = float(os.getenv("REGIME_EVENT_MAX_TRADES_MULT", "0.6"))
REGIME_EVENT_SIZE_MULT = float(os.getenv("REGIME_EVENT_SIZE_MULT", "0.6"))
REGIME_TREND_DAILY_LOSS_MULT = float(os.getenv("REGIME_TREND_DAILY_LOSS_MULT", "1.0"))
REGIME_TREND_OPEN_RISK_MULT = float(os.getenv("REGIME_TREND_OPEN_RISK_MULT", "1.0"))
REGIME_TREND_MAX_TRADES_MULT = float(os.getenv("REGIME_TREND_MAX_TRADES_MULT", "1.0"))
REGIME_TREND_SIZE_MULT = float(os.getenv("REGIME_TREND_SIZE_MULT", "1.0"))
REGIME_RANGE_DAILY_LOSS_MULT = float(os.getenv("REGIME_RANGE_DAILY_LOSS_MULT", "1.0"))
REGIME_RANGE_OPEN_RISK_MULT = float(os.getenv("REGIME_RANGE_OPEN_RISK_MULT", "1.0"))
REGIME_RANGE_MAX_TRADES_MULT = float(os.getenv("REGIME_RANGE_MAX_TRADES_MULT", "1.0"))
REGIME_RANGE_SIZE_MULT = float(os.getenv("REGIME_RANGE_SIZE_MULT", "1.0"))
RISK_SOFT_HALT_FRACTION = float(os.getenv("RISK_SOFT_HALT_FRACTION", "0.7"))
RISK_SHOCK_SCORE_SOFT = float(os.getenv("RISK_SHOCK_SCORE_SOFT", "0.65"))
RISK_ENTROPY_SOFT = float(os.getenv("RISK_ENTROPY_SOFT", "1.3"))

# -------------------------------
# Live Pilot Governance
# -------------------------------
LIVE_PILOT_MODE = os.getenv("LIVE_PILOT_MODE", "false").lower() == "true"
LIVE_STRATEGY_WHITELIST = [s.strip() for s in os.getenv("LIVE_STRATEGY_WHITELIST", "").split(",") if s.strip()]
LIVE_MAX_LOTS = int(os.getenv("LIVE_MAX_LOTS", "1"))
LIVE_MAX_TRADES_PER_DAY = int(os.getenv("LIVE_MAX_TRADES_PER_DAY", "2"))
LIVE_MAX_SPREAD_PCT = float(os.getenv("LIVE_MAX_SPREAD_PCT", "0.02"))
LIVE_MAX_QUOTE_AGE_SEC = float(os.getenv("LIVE_MAX_QUOTE_AGE_SEC", "2.0"))
LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION = (
    os.getenv("LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", "false").lower() == "true"
)
AUDIT_REQUIRED_TO_TRADE = os.getenv("AUDIT_REQUIRED_TO_TRADE", "true").lower() == "true"
EXEC_DEGRADATION_MAX_MISSED_FILL_RATE = float(os.getenv("EXEC_DEGRADATION_MAX_MISSED_FILL_RATE", "0.5"))
EXEC_DEGRADATION_MAX_SLIPPAGE_MULT = float(os.getenv("EXEC_DEGRADATION_MAX_SLIPPAGE_MULT", "2.0"))
# Baseline slippage (price units) for degradation checks. If zero/unknown, pilot mode halts.
EXEC_BASELINE_SLIPPAGE = float(os.getenv("EXEC_BASELINE_SLIPPAGE", "0.0"))
PAPER_PILOT_UNLOCK_ENABLE = os.getenv("PAPER_PILOT_UNLOCK_ENABLE", "true").lower() == "true"
PAPER_PILOT_UNLOCK_CLEAN_CYCLES = int(os.getenv("PAPER_PILOT_UNLOCK_CLEAN_CYCLES", "3"))
PAPER_PILOT_UNLOCK_MAX_RISK = float(os.getenv("PAPER_PILOT_UNLOCK_MAX_RISK", "150.0"))
# Execution guard policy
LIVE_FAIL_CLOSED_ON_MARKET_CLOSED = os.getenv("LIVE_FAIL_CLOSED_ON_MARKET_CLOSED", "true").lower() == "true"
ENFORCE_EXECUTION_ALLOWED_FLAG = os.getenv("ENFORCE_EXECUTION_ALLOWED_FLAG", "true").lower() == "true"
EXECUTION_GUARD_ALLOW_PLANNING = os.getenv("EXECUTION_GUARD_ALLOW_PLANNING", "true").lower() == "true"
ACTIVATE_SELL_RULE = os.getenv("ACTIVATE_SELL_RULE", "LE").upper()

# -------------------------------
# Suggested trade target fallback
# -------------------------------
TARGET_RR_DEFAULT = float(os.getenv("TARGET_RR_DEFAULT", "1.5"))

# -------------------------------
# Option entry validation
# -------------------------------
OPTION_LTP_SLA_SEC = float(os.getenv("OPTION_LTP_SLA_SEC", "2.0"))
LTP_SLA_SECONDS = float(os.getenv("LTP_SLA_SECONDS", str(OPTION_LTP_SLA_SEC)))
OPTION_ENTRY_MISMATCH_PCT = float(os.getenv("OPTION_ENTRY_MISMATCH_PCT", "0.03"))
OPTION_ENTRY_REQUIRE_LIVE = os.getenv("OPTION_ENTRY_REQUIRE_LIVE", "true").lower() == "true"

# -------------------------------
# Trade deduplication controls
# -------------------------------
TRADE_DEDUP_WINDOW_SEC = int(os.getenv("TRADE_DEDUP_WINDOW_SEC", "600"))
TRADE_DEDUP_PRICE_TOL = float(os.getenv("TRADE_DEDUP_PRICE_TOL", "0.05"))

# -------------------------------
# Trade permission / confidence dampening
# -------------------------------
PERMISSION_IMPULSE_ENABLE = os.getenv("PERMISSION_IMPULSE_ENABLE", "true").lower() == "true"
PERMISSION_IMPULSE_BODY_PCT = float(os.getenv("PERMISSION_IMPULSE_BODY_PCT", "0.006"))
PERMISSION_IMPULSE_ATR_MULT = float(os.getenv("PERMISSION_IMPULSE_ATR_MULT", "1.0"))
PERMISSION_UNKNOWN_REGIME_MAX_PER_SYMBOL = int(
    os.getenv("PERMISSION_UNKNOWN_REGIME_MAX_PER_SYMBOL", "2")
)
PERMISSION_UNKNOWN_REGIME_MAX_TOTAL = int(
    os.getenv("PERMISSION_UNKNOWN_REGIME_MAX_TOTAL", "6")
)

# -------------------------------
# Upstox deep-linking (manual confirmation only)
# -------------------------------
UPSTOX_ENABLE_DEEPLINK = os.getenv("UPSTOX_ENABLE_DEEPLINK", "false").lower() == "true"
UPSTOX_CONTRACT_URL_TEMPLATE = os.getenv(
    "UPSTOX_CONTRACT_URL_TEMPLATE",
    "https://pro.upstox.com/instruments/{instrument_key}",
)
UPSTOX_SEARCH_URL_TEMPLATE = os.getenv(
    "UPSTOX_SEARCH_URL_TEMPLATE",
    "https://pro.upstox.com/search?query={query}",
)
UPSTOX_INSTRUMENTS_PATH = os.getenv("UPSTOX_INSTRUMENTS_PATH", f"{DATA_ROOT}/upstox_instruments.json.gz")

# -------------------------------
# Strategy lifecycle governance
# -------------------------------
STRATEGY_LIFECYCLE_PATH = os.getenv("STRATEGY_LIFECYCLE_PATH", f"{LOGS_ROOT}/strategy_lifecycle.json")
STRATEGY_LIFECYCLE_DEFAULT_STATE = os.getenv("STRATEGY_LIFECYCLE_DEFAULT_STATE", "PAPER")
ALLOW_RESEARCH_STRATEGIES = os.getenv("ALLOW_RESEARCH_STRATEGIES", "false").lower() == "true"
PROMOTION_PILOT_DAYS_REQUIRED = int(os.getenv("PROMOTION_PILOT_DAYS_REQUIRED", "3"))
PROMOTION_REQUIRE_STRESS = os.getenv("PROMOTION_REQUIRE_STRESS", "true").lower() == "true"
PROMOTION_REQUIRE_BACKTEST = os.getenv("PROMOTION_REQUIRE_BACKTEST", "true").lower() == "true"

# -------------------------------
# Symbols to monitor
# -------------------------------
SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
ENABLE_FUTURES = os.getenv("ENABLE_FUTURES", "false").lower() == "true"
ENABLE_EQUITIES = os.getenv("ENABLE_EQUITIES", "false").lower() == "true"
FUTURES_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
EQUITY_SYMBOLS = ["NIFTY 50", "BANKNIFTY", "SENSEX"]

# -------------------------------
# Session calendar (IST)
# -------------------------------
DEFAULT_SEGMENT = os.getenv("DEFAULT_SEGMENT", "NSE_FNO")
try:
    SESSION_OVERRIDES = json.loads(os.getenv("SESSION_OVERRIDES", "{}"))
except Exception:
    SESSION_OVERRIDES = {}

# -------------------------------
# Expiry configuration
# -------------------------------
# 0 = Monday, 1 = Tuesday, ..., 4 = Friday
# Legacy fallback only. Ignored when EXPIRY_WEEKDAY_BY_SYMBOL is set.
EXPIRY_DAY = 1

# -------------------------------
# Option quote freshness
# -------------------------------
MAX_OPTION_QUOTE_AGE_SEC = float(os.getenv("MAX_OPTION_QUOTE_AGE_SEC", "8"))
STRICT_LIVE_QUOTES = os.getenv("STRICT_LIVE_QUOTES", "true").lower() == "true"
PAPER_STRICT_QUOTES = os.getenv("PAPER_STRICT_QUOTES", "true").lower() == "true"
MAX_LTP_AGE_SEC = float(os.getenv("MAX_LTP_AGE_SEC", "8"))
MAX_CANDLE_AGE_SEC = float(os.getenv("MAX_CANDLE_AGE_SEC", "120"))
OPTION_LAST_OUTSIDE_BAND_PCT = float(os.getenv("OPTION_LAST_OUTSIDE_BAND_PCT", "0.01"))
OFFHOURS_MAX_OPTION_QUOTE_AGE_SEC = float(
    os.getenv("OFFHOURS_MAX_OPTION_QUOTE_AGE_SEC", str(max(MAX_OPTION_QUOTE_AGE_SEC, 60.0)))
)
OFFHOURS_MAX_LTP_AGE_SEC = float(
    os.getenv("OFFHOURS_MAX_LTP_AGE_SEC", str(max(MAX_LTP_AGE_SEC, 900.0)))
)
OFFHOURS_MAX_CANDLE_AGE_SEC = float(
    os.getenv("OFFHOURS_MAX_CANDLE_AGE_SEC", str(max(MAX_CANDLE_AGE_SEC, 1800.0)))
)
INDEX_BIDASK_MISSING_LOG_SEC = float(os.getenv("INDEX_BIDASK_MISSING_LOG_SEC", "60"))
INDEX_REST_QUOTE_REFRESH_SEC = float(os.getenv("INDEX_REST_QUOTE_REFRESH_SEC", "5"))
SYNTH_INDEX_SPREAD_PCT = float(os.getenv("SYNTH_INDEX_SPREAD_PCT", "0.00005"))
SYNTH_INDEX_SPREAD_ABS = float(os.getenv("SYNTH_INDEX_SPREAD_ABS", "0.5"))
INDEX_SYNTH_MIN_TICK = float(os.getenv("INDEX_SYNTH_MIN_TICK", "0.05"))
INDEX_SYNTH_SPREAD_BPS_LIVE = float(
    os.getenv("INDEX_SYNTH_SPREAD_BPS_LIVE", "5.0")
)
OFFHOURS_SYNTH_INDEX_SPREAD_BPS = float(
    os.getenv("OFFHOURS_SYNTH_INDEX_SPREAD_BPS", "20.0")
)
INDEX_REQUIRE_DEPTH_LIVE = os.getenv("INDEX_REQUIRE_DEPTH_LIVE", "false").lower() == "true"

# -------------------------------
# Synthetic option chain
# -------------------------------
ALLOW_SYNTHETIC_CHAIN = os.getenv("ALLOW_SYNTHETIC_CHAIN", "false").lower() == "true"
SYNTHETIC_CHAIN_MODE = os.getenv("SYNTHETIC_CHAIN_MODE", "analysis_only")

# -------------------------------
# Market / fallback indices
# -------------------------------
PREMARKET_INDICES_LTP = {
    "NIFTY": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "SENSEX": "BSE:SENSEX",
}

PREMARKET_INDICES_CLOSE = {
    "NIFTY": 16000,
    "BANKNIFTY": 37000,
    "SENSEX": 83000,
}
INDEX_LTP_SANITY_ENABLE = os.getenv("INDEX_LTP_SANITY_ENABLE", "true").lower() == "true"
INDEX_LTP_SANITY_MIN_RATIO = float(os.getenv("INDEX_LTP_SANITY_MIN_RATIO", "0.2"))
INDEX_LTP_SANITY_MIN_DEFAULT = float(os.getenv("INDEX_LTP_SANITY_MIN_DEFAULT", "1000"))
INDEX_LTP_SANITY_MIN_BY_SYMBOL = {
    "NIFTY": float(os.getenv("INDEX_LTP_SANITY_MIN_NIFTY", "5000")),
    "BANKNIFTY": float(os.getenv("INDEX_LTP_SANITY_MIN_BANKNIFTY", "10000")),
    "SENSEX": float(os.getenv("INDEX_LTP_SANITY_MIN_SENSEX", "30000")),
}
INDEX_TOKEN_BY_SYMBOL = {
    "NIFTY": int(os.getenv("INDEX_TOKEN_NIFTY", "256265")),
    "BANKNIFTY": int(os.getenv("INDEX_TOKEN_BANKNIFTY", "0")),
    "SENSEX": int(os.getenv("INDEX_TOKEN_SENSEX", "0")),
}

PRIMARY_INDEX = "NIFTY"
EXCHANGE = "NSE"
OPTION_INDEX = "NIFTY"
STRIKE_STEP = 50
STRIKE_STEP_BY_SYMBOL = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "SENSEX": 100,
}
EXPIRY_TYPE = "WEEKLY"
# Option contract expiry selection based on listed expiries from instruments dump.
# Supported: NEAREST, MONTHLY
OPTION_EXPIRY_SELECTION = os.getenv("OPTION_EXPIRY_SELECTION", "NEAREST").upper()
STRIKES_AROUND = 6
STRIKES_AROUND_BY_SYMBOL = {
    "NIFTY": 40,   # +/-2000 points (40 * 50)
    "SENSEX": 40,  # +/-2000 points (40 * 50)
    "BANKNIFTY": 40,  # +/-4000 points (40 * 100)
}
# Expiry weekdays by symbol (0=Mon ... 6=Sun)
EXPIRY_WEEKDAY_BY_SYMBOL = {
    "NIFTY": int(os.getenv("NIFTY_EXPIRY_WEEKDAY", "1")),         # Tue (NSE weekly)
    "BANKNIFTY": int(os.getenv("BANKNIFTY_EXPIRY_WEEKDAY", "1")), # Tue (NSE weekly)
    "SENSEX": int(os.getenv("SENSEX_EXPIRY_WEEKDAY", "3")),       # Thu (BSE weekly)
}

# -------------------------------
# Trade configuration
# -------------------------------
MIN_PREMIUM = 40          # Minimum option premium to consider
MAX_PREMIUM = 150         # Maximum option premium to consider
PREMIUM_BANDS = {
    "NIFTY": (5, 250),
    "BANKNIFTY": (40, 1500),
    "SENSEX": (10, 700),
}
OPTION_PREMIUM_SANITY_MIN = float(os.getenv("OPTION_PREMIUM_SANITY_MIN", "5"))
OPTION_PREMIUM_SANITY_MAX = float(os.getenv("OPTION_PREMIUM_SANITY_MAX", "1000"))
OPTION_PREMIUM_SANITY_MIN_BY_SYMBOL = {
    "NIFTY": float(os.getenv("OPTION_PREMIUM_SANITY_MIN_NIFTY", str(OPTION_PREMIUM_SANITY_MIN))),
    "BANKNIFTY": float(os.getenv("OPTION_PREMIUM_SANITY_MIN_BANKNIFTY", str(OPTION_PREMIUM_SANITY_MIN))),
    "SENSEX": float(os.getenv("OPTION_PREMIUM_SANITY_MIN_SENSEX", str(OPTION_PREMIUM_SANITY_MIN))),
}
OPTION_PREMIUM_SANITY_MAX_BY_SYMBOL = {
    "NIFTY": float(os.getenv("OPTION_PREMIUM_SANITY_MAX_NIFTY", str(OPTION_PREMIUM_SANITY_MAX))),
    "BANKNIFTY": float(os.getenv("OPTION_PREMIUM_SANITY_MAX_BANKNIFTY", str(OPTION_PREMIUM_SANITY_MAX))),
    "SENSEX": float(os.getenv("OPTION_PREMIUM_SANITY_MAX_SENSEX", str(OPTION_PREMIUM_SANITY_MAX))),
}
CONFIDENCE_THRESHOLD = 70 # Only suggest trades with confidence >= 70
MAX_STRIKES = 5           # Max strikes to suggest per scan
STRICT_STRATEGY_SCORE = 0.55
MIN_COOLDOWN_SEC = 300    # 5 minutes cooldown per symbol
STRATEGY_DISABLE_THRESHOLD = 0.45  # min win rate before disable
STRATEGY_MIN_TRADES = 30
STRATEGY_EPSILON = 0.1
STRATEGY_MIN_WEIGHT = 0.5
STRATEGY_MAX_WEIGHT = 1.5
STRATEGY_SHARPE_WINDOW = 30
ALLOC_TEMPERATURE = 1.0
BANDIT_MODE = "BAYES"  # BAYES, UCB, or EPS
BANDIT_WINDOW = 50
BANDIT_UTILITY_WEIGHT = 0.5
BANDIT_ALERT_THRESHOLD = 0.2
META_MODEL_ENABLED = os.getenv("META_MODEL_ENABLED", "true").lower() == "true"
META_MODEL_SHADOW_ONLY = os.getenv("META_MODEL_SHADOW_ONLY", "true").lower() == "true"
META_SHADOW_LOG_PATH = os.getenv("META_SHADOW_LOG_PATH", f"{LOGS_ROOT}/meta_shadow.jsonl")
META_EXECQ_MIN = float(os.getenv("META_EXECQ_MIN", "55"))
META_DECAY_PENALTY_THRESHOLD = float(os.getenv("META_DECAY_PENALTY_THRESHOLD", "0.6"))
META_DECAY_PENALTY_MULT = float(os.getenv("META_DECAY_PENALTY_MULT", "0.7"))
STRATEGY_WF_LOCK_ENABLE = os.getenv("STRATEGY_WF_LOCK_ENABLE", "true").lower() == "true"
STRATEGY_WF_LOCK_TTL = int(os.getenv("STRATEGY_WF_LOCK_TTL", "300"))
LIVE_WF_DRIFT_DISABLE = os.getenv("LIVE_WF_DRIFT_DISABLE", "true").lower() == "true"
REJECTED_STRIKE_WINDOW = int(os.getenv("REJECTED_STRIKE_WINDOW", "2000"))
REJECTED_STRIKE_WINDOW_BY_SYMBOL = {
    "NIFTY": int(os.getenv("REJECTED_STRIKE_WINDOW_NIFTY", "2000")),
    "BANKNIFTY": int(os.getenv("REJECTED_STRIKE_WINDOW_BANKNIFTY", "5000")),
    "SENSEX": int(os.getenv("REJECTED_STRIKE_WINDOW_SENSEX", "2000")),
}
WF_MIN_TRADES = int(os.getenv("WF_MIN_TRADES", "20"))
WF_MIN_PF = float(os.getenv("WF_MIN_PF", "1.2"))
WF_MIN_WIN_RATE = float(os.getenv("WF_MIN_WIN_RATE", "0.45"))
WF_MAX_DD = float(os.getenv("WF_MAX_DD", "-5000"))
MICRO_ROLLING_WINDOW = 20
MICRO_ALERT_THRESHOLD = 0.55
RL_SHARPE_ALERT = 0.0
RL_DD_ALERT = -5.0
EWMA_SPAN = 10
FILL_RATIO_ALERT = 0.8
DEPTH_SNAPSHOT_LIMIT = 10000
IMBALANCE_ALERT = 0.6
IMBALANCE_ALERT_ENABLE = False
TRAILING_STOP_ATR_MULT = 0.8
MAX_HOLD_MINUTES = 60
MIN_VOLUME_FILTER = 500
MAX_SPREAD_PCT = 0.03
MAX_SPREAD_PCT_QUICK = float(os.getenv("MAX_SPREAD_PCT_QUICK", "0.04"))
# Option filter profiles
PAPER_RELAXED_SPREAD_MULT = float(os.getenv("PAPER_RELAXED_SPREAD_MULT", "1.25"))
PAPER_RELAXED_MIN_VOLUME_MULT = float(os.getenv("PAPER_RELAXED_MIN_VOLUME_MULT", "0.60"))
PAPER_RELAXED_PREMIUM_RELAX_PCT = float(os.getenv("PAPER_RELAXED_PREMIUM_RELAX_PCT", "0.20"))
UI_REFRESH_SEC = float(os.getenv("UI_REFRESH_SEC", "2.0"))
UI_STATE_ENGINE_REFRESH_SEC = float(os.getenv("UI_STATE_ENGINE_REFRESH_SEC", "5.0"))
QUOTE_FALLBACK_SPREAD_PCT = float(os.getenv("QUOTE_FALLBACK_SPREAD_PCT", "0.002"))
NEWS_HALF_LIFE_HOURS = float(os.getenv("NEWS_HALF_LIFE_HOURS", "6.0"))
NEWS_SHOCK_EVENT_THRESHOLD = float(os.getenv("NEWS_SHOCK_EVENT_THRESHOLD", "0.4"))
NEWS_SHOCK_BLOCK_THRESHOLD = float(os.getenv("NEWS_SHOCK_BLOCK_THRESHOLD", "0.7"))
NEWS_SHOCK_BIAS_PENALTY = float(os.getenv("NEWS_SHOCK_BIAS_PENALTY", "15"))
NEWS_RSS_SOURCES = [s.strip() for s in os.getenv("NEWS_RSS_SOURCES", "").split(",") if s.strip()]
NEWS_SOURCE_WEIGHTS = json.loads(os.getenv("NEWS_SOURCE_WEIGHTS", "{}")) if os.getenv("NEWS_SOURCE_WEIGHTS") else {}
NEWS_API_PROVIDERS = json.loads(os.getenv("NEWS_API_PROVIDERS", "[]")) if os.getenv("NEWS_API_PROVIDERS") else []
NEWS_SHOCK_DECAY_MINUTES = float(os.getenv("NEWS_SHOCK_DECAY_MINUTES", "180"))
NEWS_SHOCK_TOPK = int(os.getenv("NEWS_SHOCK_TOPK", "5"))
NEWS_PRE_DECAY_MINUTES = float(os.getenv("NEWS_PRE_DECAY_MINUTES", "180"))
NEWS_POST_DECAY_MINUTES = float(os.getenv("NEWS_POST_DECAY_MINUTES", "120"))
NEWS_CLASSIFIER_PATH = os.getenv("NEWS_CLASSIFIER_PATH", "models/news_shock_model.pkl")
NEWS_VECTOR_PATH = os.getenv("NEWS_VECTOR_PATH", "models/news_vectorizer.pkl")

# -------------------------------
# Alpha Ensemble (multi-model fusion)
# -------------------------------
ALPHA_ENSEMBLE_ENABLE = os.getenv("ALPHA_ENSEMBLE_ENABLE", "true").lower() == "true"
ALPHA_METHOD = os.getenv("ALPHA_METHOD", "AUTO")  # AUTO | STACKING | BAYES
ALPHA_STACKING_MODEL_PATH = os.getenv("ALPHA_STACKING_MODEL_PATH", "models/alpha_stack.pkl")
ALPHA_BASE_WEIGHTS = {
    "xgb": float(os.getenv("ALPHA_W_XGB", "0.45")),
    "deep": float(os.getenv("ALPHA_W_DEEP", "0.35")),
    "micro": float(os.getenv("ALPHA_W_MICRO", "0.20")),
}
ALPHA_REGIME_WEIGHTS = {
    "TREND": {"xgb": 0.35, "deep": 0.5, "micro": 0.15},
    "RANGE": {"xgb": 0.45, "deep": 0.25, "micro": 0.30},
    "RANGE_VOLATILE": {"xgb": 0.40, "deep": 0.30, "micro": 0.30},
    "EVENT": {"xgb": 0.30, "deep": 0.30, "micro": 0.40},
    "PANIC": {"xgb": 0.25, "deep": 0.35, "micro": 0.40},
}
ALPHA_UNCERTAINTY_VETO = float(os.getenv("ALPHA_UNCERTAINTY_VETO", "0.78"))
ALPHA_UNCERTAINTY_DOWNSIZE = float(os.getenv("ALPHA_UNCERTAINTY_DOWNSIZE", "0.55"))
ALPHA_UNCERTAINTY_MIN_SIZE_MULT = float(os.getenv("ALPHA_UNCERTAINTY_MIN_SIZE_MULT", "0.5"))
ALPHA_UNCERT_W_DISAGREE = float(os.getenv("ALPHA_UNCERT_W_DISAGREE", "0.45"))
ALPHA_UNCERT_W_REGIME = float(os.getenv("ALPHA_UNCERT_W_REGIME", "0.25"))
ALPHA_UNCERT_W_SHOCK = float(os.getenv("ALPHA_UNCERT_W_SHOCK", "0.20"))
ALPHA_UNCERT_W_VOLSPILL = float(os.getenv("ALPHA_UNCERT_W_VOLSPILL", "0.10"))

# Model risk management
RETRAIN_MIN_TRADES = 50
RETRAIN_COOLDOWN_MIN = 180

# Multi-timeframe confirmation
HTF_BARS = 60
HTF_ALIGN_REQUIRED = True

# Email reports (optional)
EMAIL_REPORTS = os.getenv("EMAIL_REPORTS", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_TO = os.getenv("SMTP_TO", "")

# Lot sizes per instrument
LOT_SIZE = {
    "NIFTY": 50,
    "BANKNIFTY": 15,
    "SENSEX": 10
}

# -------------------------------
# Execution configuration
# -------------------------------
ORDER_TYPE = "LIMIT"  # LIMIT only
ORDER_RETRIES = 3
RETRY_SLEEP_SEC = 2
SLIPPAGE_BPS = 8      # 0.08% slippage estimate for limit buffer
EXEC_SLIPPAGE_BUDGET_ENABLE = os.getenv("EXEC_SLIPPAGE_BUDGET_ENABLE", "true").lower() == "true"
EXEC_SLIPPAGE_BUDGET_ENFORCE_LIVE_ONLY = os.getenv("EXEC_SLIPPAGE_BUDGET_ENFORCE_LIVE_ONLY", "true").lower() == "true"
EXEC_SLIPPAGE_BUDGET_BPS_BASE = float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_BASE", "18"))
EXEC_SLIPPAGE_BUDGET_BPS_VOL_Z_MULT = float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_VOL_Z_MULT", "1.5"))
EXEC_SLIPPAGE_BUDGET_BPS_FLOOR = float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_FLOOR", "4"))
EXEC_SLIPPAGE_BUDGET_BPS_CAP = float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_CAP", "80"))
EXEC_SLIPPAGE_BUDGET_BPS_BY_REGIME = {
    "DEFAULT": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_DEFAULT", "18")),
    "TREND": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_TREND", "20")),
    "RANGE": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_RANGE", "16")),
    "RANGE_VOLATILE": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_RANGE_VOLATILE", "14")),
    "EVENT": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_EVENT", "10")),
    "PANIC": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_PANIC", "8")),
    "NEUTRAL": float(os.getenv("EXEC_SLIPPAGE_BUDGET_BPS_NEUTRAL", "14")),
}
_EXEC_MODE_DEFAULT = str(os.getenv("EXECUTION_MODE", "SIM")).strip().upper()
TRADING_MODE = str(os.getenv("TRADING_MODE", _EXEC_MODE_DEFAULT)).strip().upper()
if TRADING_MODE not in {"LIVE", "PAPER", "SIM"}:
    TRADING_MODE = "SIM"
# Backward-compatible alias used by legacy call sites.
EXECUTION_MODE = TRADING_MODE
EXECUTION_MODE_PAPER = TRADING_MODE == "PAPER"
EXECUTION_MODE_LIVE = TRADING_MODE == "LIVE"
ALLOW_LIVE_PLACEMENT = False
PAPER_STRICT_MODE = os.getenv("PAPER_STRICT_MODE", "true").lower() == "true"
ORDER_SLICES = 3
SLICE_INTERVAL_SEC = 1
ORDER_SLICES_OPT = 3
ORDER_SLICES_FUT = 2
ORDER_SLICES_EQ = 1
IMPACT_ALPHA = 0.15
QUEUE_ALPHA = 0.25
QUEUE_POSITION_MODEL = True

# -------------------------------
# ML configuration
# -------------------------------
ML_MIN_PROBA = 0.45
ML_FULL_SIZE_PROBA = float(os.getenv("ML_FULL_SIZE_PROBA", "0.70"))
CONFIDENCE_MIN = float(os.getenv("CONFIDENCE_MIN", "0.55"))
CONFIDENCE_FULL = float(os.getenv("CONFIDENCE_FULL", "0.80"))
QUICK_TRADE_MODE = True
DEBUG_TRADE_REASONS = True
DEBUG_TRADE_MODE = os.getenv("DEBUG_TRADE_MODE", "false").lower() == "true"
DEBUG_TRADE_TOP_N = int(os.getenv("DEBUG_TRADE_TOP_N", "5"))
QUICK_MIN_PROBA = float(os.getenv("QUICK_MIN_PROBA", "0.35"))
QUICK_USE_SIGNAL_SCORE = os.getenv("QUICK_USE_SIGNAL_SCORE", "true").lower() == "true"
QUICK_NEUTRAL_FALLBACK_ENABLE = os.getenv("QUICK_NEUTRAL_FALLBACK_ENABLE", "true").lower() == "true"
QUICK_NEUTRAL_EDGE_MIN = float(os.getenv("QUICK_NEUTRAL_EDGE_MIN", "0.18"))
QUICK_NEUTRAL_VWAP_DEV_WEIGHT = float(os.getenv("QUICK_NEUTRAL_VWAP_DEV_WEIGHT", "35.0"))
QUICK_NEUTRAL_MOMENTUM_WEIGHT = float(os.getenv("QUICK_NEUTRAL_MOMENTUM_WEIGHT", "0.6"))
QUICK_NEUTRAL_VWAP_SLOPE_WEIGHT = float(os.getenv("QUICK_NEUTRAL_VWAP_SLOPE_WEIGHT", "120.0"))
QUICK_NEUTRAL_RSI_MOM_WEIGHT = float(os.getenv("QUICK_NEUTRAL_RSI_MOM_WEIGHT", "0.2"))
QUICK_NEUTRAL_SCORE_BASE = float(os.getenv("QUICK_NEUTRAL_SCORE_BASE", "0.53"))
QUICK_NEUTRAL_SCORE_EDGE_MULT = float(os.getenv("QUICK_NEUTRAL_SCORE_EDGE_MULT", "0.22"))
QUICK_NEUTRAL_SCORE_CAP = float(os.getenv("QUICK_NEUTRAL_SCORE_CAP", "0.68"))
# Planning-only signal controls (PAPER/SIM/OFFHOURS).
PLANNING_QUICK_FALLBACK_ENABLE = os.getenv("PLANNING_QUICK_FALLBACK_ENABLE", "true").lower() == "true"
PLANNING_SIGNAL_FALLBACK_ENABLE = os.getenv("PLANNING_SIGNAL_FALLBACK_ENABLE", "true").lower() == "true"
PLANNING_SIGNAL_VWAP_EDGE_MIN = float(os.getenv("PLANNING_SIGNAL_VWAP_EDGE_MIN", "0.0008"))
PLANNING_SIGNAL_MOMENTUM_EDGE_MIN = float(os.getenv("PLANNING_SIGNAL_MOMENTUM_EDGE_MIN", "0.12"))
PLANNING_SIGNAL_SCORE_BASE = float(os.getenv("PLANNING_SIGNAL_SCORE_BASE", "0.56"))
PLANNING_SIGNAL_SCORE_CAP = float(os.getenv("PLANNING_SIGNAL_SCORE_CAP", "0.66"))
PLANNING_SIGNAL_SCORE_MIN = float(os.getenv("PLANNING_SIGNAL_SCORE_MIN", "0.5"))
PLANNING_TRADE_SCORE_MIN = float(os.getenv("PLANNING_TRADE_SCORE_MIN", "58"))
PLANNING_NO_SIGNAL_FALLBACK_ENABLE = os.getenv("PLANNING_NO_SIGNAL_FALLBACK_ENABLE", "true").lower() == "true"
ALLOW_AUX_TRADES_LIVE = os.getenv("ALLOW_AUX_TRADES_LIVE", "false").lower() == "true"
ALLOW_BASELINE_SIGNAL = os.getenv("ALLOW_BASELINE_SIGNAL", "true").lower() == "true"
RELAX_BLOCK_REASON = os.getenv("RELAX_BLOCK_REASON", "")
MIN_RR = float(os.getenv("MIN_RR", "1.5"))
MIN_RR_QUICK = float(os.getenv("MIN_RR_QUICK", "1.2"))
OPT_STOP_ATR_MAIN = float(os.getenv("OPT_STOP_ATR_MAIN", "1.0"))
OPT_TARGET_ATR_MAIN = float(os.getenv("OPT_TARGET_ATR_MAIN", "1.8"))
OPT_STOP_ATR_QUICK = float(os.getenv("OPT_STOP_ATR_QUICK", "0.8"))
OPT_TARGET_ATR_QUICK = float(os.getenv("OPT_TARGET_ATR_QUICK", "1.5"))
TRADE_SCORE_MIN = float(os.getenv("TRADE_SCORE_MIN", "75"))
QUICK_TRADE_SCORE_MIN = float(os.getenv("QUICK_TRADE_SCORE_MIN", "60"))
TRADE_SCORE_MIN_BY_DAYTYPE = {
    "EXPIRY_DAY": float(os.getenv("TRADE_SCORE_MIN_EXPIRY", "60")),
    "EVENT_DAY": float(os.getenv("TRADE_SCORE_MIN_EVENT", "60")),
    "RANGE_DAY": float(os.getenv("TRADE_SCORE_MIN_RANGE", "65")),
    "RANGE_VOLATILE": float(os.getenv("TRADE_SCORE_MIN_RANGE_VOL", "65")),
    "TREND_DAY": float(os.getenv("TRADE_SCORE_MIN_TREND", "70")),
}
AUTO_TUNE_ENABLE = os.getenv("AUTO_TUNE_ENABLE", "true").lower() == "true"
AUTO_TUNE_WINDOW = int(os.getenv("AUTO_TUNE_WINDOW", "30"))
AUTO_TUNE_EVERY_SEC = int(os.getenv("AUTO_TUNE_EVERY_SEC", "600"))

# Harden live mode: no baseline/quick/relax
if str(EXECUTION_MODE).upper() == "LIVE":
    ALLOW_BASELINE_SIGNAL = False
    RELAX_BLOCK_REASON = ""
    QUICK_TRADE_MODE = False
    ALLOW_STALE_LTP = False
    ALLOW_CLOSE_FALLBACK = False
    RISK_PROFILE = "PILOT"
BLOCKED_TRACK_ENABLE = os.getenv("BLOCKED_TRACK_ENABLE", "true").lower() == "true"
BLOCKED_TRACK_SECONDS = int(os.getenv("BLOCKED_TRACK_SECONDS", "3600"))
BLOCKED_TRACK_POLL_SEC = int(os.getenv("BLOCKED_TRACK_POLL_SEC", "15"))
BLOCKED_TRAIN_MIN = int(os.getenv("BLOCKED_TRAIN_MIN", "20"))
BLOCKED_TRAIN_ENABLE = os.getenv("BLOCKED_TRAIN_ENABLE", "true").lower() == "true"
BLOCKED_TRAIN_WEIGHT = float(os.getenv("BLOCKED_TRAIN_WEIGHT", "0.5"))
BLOCKED_ML_MODEL_PATH = os.getenv("BLOCKED_ML_MODEL_PATH", "models/xgb_blocked_model.pkl")
BLOCKED_TRACK_PATH = os.getenv("BLOCKED_TRACK_PATH", f"{LOGS_ROOT}/blocked_tracking.jsonl")
BLOCKED_OUTCOMES_PATH = os.getenv("BLOCKED_OUTCOMES_PATH", f"{LOGS_ROOT}/blocked_outcomes.jsonl")
BLOCKED_OUTCOMES_PROCESSED_PATH = os.getenv(
    "BLOCKED_OUTCOMES_PROCESSED_PATH",
    f"{LOGS_ROOT}/blocked_outcomes_processed.json",
)
FEEDBACK_TRAIN_STATE_PATH = os.getenv("FEEDBACK_TRAIN_STATE_PATH", f"{LOGS_ROOT}/feedback_train_state.json")
BLOCKED_TRAIN_WINDOW = int(os.getenv("BLOCKED_TRAIN_WINDOW", "300"))
REJECT_OUTCOMES_LOG_PATH = os.getenv("REJECT_OUTCOMES_LOG_PATH", f"{LOGS_ROOT}/rejected_trade_outcomes.jsonl")
REJECT_OUTCOMES_SUMMARY_PATH = os.getenv(
    "REJECT_OUTCOMES_SUMMARY_PATH",
    f"{LOGS_ROOT}/rejected_trade_outcomes_summary.json",
)
REJECT_OUTCOME_CANDLE_SOURCE = os.getenv("REJECT_OUTCOME_CANDLE_SOURCE", "kite")
REJECT_OUTCOME_CANDLE_INTERVAL = os.getenv("REJECT_OUTCOME_CANDLE_INTERVAL", "minute")
REJECT_OUTCOME_ALLOW_MARKET_HOURS = os.getenv("REJECT_OUTCOME_ALLOW_MARKET_HOURS", "false").lower() == "true"
SHADOW_EVAL_HORIZONS_SEC = []
for _h in str(os.getenv("SHADOW_EVAL_HORIZONS_SEC", "300,900,1800")).split(","):
    _h = str(_h).strip()
    if not _h:
        continue
    try:
        _v = int(_h)
    except Exception:
        continue
    if _v > 0:
        SHADOW_EVAL_HORIZONS_SEC.append(_v)
if not SHADOW_EVAL_HORIZONS_SEC:
    SHADOW_EVAL_HORIZONS_SEC = [300, 900, 1800]
SHADOW_OUTCOMES_TABLE = os.getenv("SHADOW_OUTCOMES_TABLE", "shadow_outcomes")
PREMIUM_SOFT_VETO_CONF_MULT = float(os.getenv("PREMIUM_SOFT_VETO_CONF_MULT", "0.92"))
PREMIUM_SOFT_VETO_SIZE_MULT = float(os.getenv("PREMIUM_SOFT_VETO_SIZE_MULT", "0.90"))
PREMIUM_SOFT_VETO_CONF_FLOOR = float(os.getenv("PREMIUM_SOFT_VETO_CONF_FLOOR", "0.75"))
PREMIUM_SOFT_VETO_SIZE_FLOOR = float(os.getenv("PREMIUM_SOFT_VETO_SIZE_FLOOR", "0.70"))
PREMIUM_SOFT_VETO_PENALTY_SCALE = float(os.getenv("PREMIUM_SOFT_VETO_PENALTY_SCALE", "1.5"))
PREMIUM_BAND_PERCENTILE_LOW = float(os.getenv("PREMIUM_BAND_PERCENTILE_LOW", "0.10"))
PREMIUM_BAND_PERCENTILE_HIGH = float(os.getenv("PREMIUM_BAND_PERCENTILE_HIGH", "0.90"))
PREMIUM_BAND_ATM_MONEYNESS_MAX = float(os.getenv("PREMIUM_BAND_ATM_MONEYNESS_MAX", "0.03"))
PREMIUM_BAND_MIN_ROWS = int(os.getenv("PREMIUM_BAND_MIN_ROWS", "8"))
PREMIUM_BAND_MIN_VOLUME = int(os.getenv("PREMIUM_BAND_MIN_VOLUME", "1"))
REJECT_SHADOW_TIMEOUT_MIN = int(os.getenv("REJECT_SHADOW_TIMEOUT_MIN", "30"))
REJECT_SHADOW_BATCH_LIMIT = int(os.getenv("REJECT_SHADOW_BATCH_LIMIT", "5000"))
REJECT_SHADOW_CANDIDATE_BUCKET_SEC = int(os.getenv("REJECT_SHADOW_CANDIDATE_BUCKET_SEC", "30"))
REJECT_SHADOW_DEFAULT_RR = float(os.getenv("REJECT_SHADOW_DEFAULT_RR", "1.5"))
SUGGESTION_TRAIN_ENABLE = os.getenv("SUGGESTION_TRAIN_ENABLE", "true").lower() == "true"
SUGGESTION_TRAIN_MIN = int(os.getenv("SUGGESTION_TRAIN_MIN", "5"))
SUGGESTION_TRAIN_WEIGHT = float(os.getenv("SUGGESTION_TRAIN_WEIGHT", "0.35"))
LTP_MOM_ATR_MULT = 0.2
BASELINE_SIGNAL_SCORE = 0.62
LTP_CHANGE_WINDOW_SEC = 30
BASELINE_LTP_ATR_MULT = 0.01
BASELINE_LTP_ATR_MULT_WINDOW = 0.005

# Regime detection thresholds
EVENT_VOL_Z = 1.0
EVENT_ATR_PCT = 0.004
EVENT_IV_MEAN = 0.35
RANGE_VOL_Z = 0.6
RANGE_ATR_PCT = 0.003
RANGE_IV_MEAN = 0.3
TREND_ADX = 22
RANGE_ADX = 18
FORCE_REGIME = os.getenv("FORCE_REGIME", "")
# Deterministic rule-based regime classifier thresholds
REGIME_CLASSIFIER_ENABLE = os.getenv("REGIME_CLASSIFIER_ENABLE", "true").lower() == "true"
REGIME_RULE_TREND_VWAP_SLOPE_ABS_MIN = float(os.getenv("REGIME_RULE_TREND_VWAP_SLOPE_ABS_MIN", "0.0015"))
REGIME_RULE_TREND_ATR_PCT_MIN = float(os.getenv("REGIME_RULE_TREND_ATR_PCT_MIN", "0.0010"))
REGIME_RULE_EVENT_ATR_PCT_MIN = float(os.getenv("REGIME_RULE_EVENT_ATR_PCT_MIN", "0.0060"))
REGIME_RULE_EVENT_GAP_PCT_ABS_MIN = float(os.getenv("REGIME_RULE_EVENT_GAP_PCT_ABS_MIN", "0.0040"))
REGIME_RULE_RANGE_VWAP_SLOPE_ABS_MAX = float(os.getenv("REGIME_RULE_RANGE_VWAP_SLOPE_ABS_MAX", "0.0008"))
REGIME_RULE_RANGE_ATR_PCT_MAX = float(os.getenv("REGIME_RULE_RANGE_ATR_PCT_MAX", "0.0035"))
REGIME_RULE_RANGE_GAP_PCT_ABS_MAX = float(os.getenv("REGIME_RULE_RANGE_GAP_PCT_ABS_MAX", "0.0020"))
REGIME_UNSTABLE_CONSECUTIVE_BLOCK = max(1, int(os.getenv("REGIME_UNSTABLE_CONSECUTIVE_BLOCK", "1")))
PAPER_REGIME_UNSTABLE_CONSECUTIVE_BLOCK = max(
    1,
    int(os.getenv("PAPER_REGIME_UNSTABLE_CONSECUTIVE_BLOCK", "3")),
)
# Strategy routing by deterministic regime
REGIME_ROUTER_ENABLE = os.getenv("REGIME_ROUTER_ENABLE", "true").lower() == "true"
REGIME_TREND_STOP_MULT = float(os.getenv("REGIME_TREND_STOP_MULT", "1.2"))
REGIME_TREND_TARGET_MULT = float(os.getenv("REGIME_TREND_TARGET_MULT", "2.0"))
REGIME_RANGE_STOP_MULT = float(os.getenv("REGIME_RANGE_STOP_MULT", "0.8"))
REGIME_RANGE_TARGET_MULT = float(os.getenv("REGIME_RANGE_TARGET_MULT", "1.3"))
REGIME_EVENT_STOP_MULT = float(os.getenv("REGIME_EVENT_STOP_MULT", "1.1"))
REGIME_EVENT_TARGET_MULT = float(os.getenv("REGIME_EVENT_TARGET_MULT", "1.4"))
REGIME_EVENT_ROUTE_ALLOW = os.getenv("REGIME_EVENT_ROUTE_ALLOW", "true").lower() == "true"
# Controlled signal fallback (SIM/PAPER by default; LIVE disabled unless explicitly enabled)
TREND_VWAP_FALLBACK_ENABLE = os.getenv("TREND_VWAP_FALLBACK_ENABLE", "true").lower() == "true"
TREND_VWAP_FALLBACK_LIVE_ENABLE = os.getenv("TREND_VWAP_FALLBACK_LIVE_ENABLE", "false").lower() == "true"
TREND_VWAP_FALLBACK_SCORE = float(os.getenv("TREND_VWAP_FALLBACK_SCORE", "0.60"))
TREND_VWAP_FALLBACK_SLOPE_ABS_MIN = float(os.getenv("TREND_VWAP_FALLBACK_SLOPE_ABS_MIN", "0.0008"))

# Regime-based threshold multipliers
REGIME_SCORE_MULT = {
    "TREND": 0.9,
    "EVENT": 0.9,
    "RANGE": 1.05,
    "RANGE_VOLATILE": 1.05,
    "NEUTRAL": 1.0,
}
REGIME_PROBA_MULT = {
    "TREND": 0.9,
    "EVENT": 0.9,
    "RANGE": 1.05,
    "RANGE_VOLATILE": 1.05,
    "NEUTRAL": 1.0,
}

# Probabilistic regime gating
REGIME_MODEL_PATH = os.getenv("REGIME_MODEL_PATH", "models/regime_model.json")
REGIME_PROB_MIN = float(os.getenv("REGIME_PROB_MIN", "0.45"))
REGIME_PROB_TREND = float(os.getenv("REGIME_PROB_TREND", "0.45"))
REGIME_PROB_RANGE = float(os.getenv("REGIME_PROB_RANGE", "0.45"))
REGIME_PROB_EVENT = float(os.getenv("REGIME_PROB_EVENT", "0.40"))
REGIME_PROB_PANIC = float(os.getenv("REGIME_PROB_PANIC", "0.40"))
REGIME_ENTROPY_MAX = float(os.getenv("REGIME_ENTROPY_MAX", "1.3"))
REGIME_ENTROPY_UNSTABLE = float(os.getenv("REGIME_ENTROPY_UNSTABLE", "1.5"))
REGIME_TRANSITION_RATE_MAX = float(os.getenv("REGIME_TRANSITION_RATE_MAX", "6.0"))
# Confidence override for clearly stable regime distributions.
# Used to avoid false "unstable" when max-probability is effectively 1 and entropy is near 0.
REGIME_STABLE_PROB_OVERRIDE_MIN = float(os.getenv("REGIME_STABLE_PROB_OVERRIDE_MIN", "0.99"))
REGIME_STABLE_ENTROPY_OVERRIDE_MAX = float(os.getenv("REGIME_STABLE_ENTROPY_OVERRIDE_MAX", "0.01"))
PAPER_RELAX_GATES = os.getenv("PAPER_RELAX_GATES", "true").lower() == "true"
PAPER_REGIME_PROB_MIN = float(os.getenv("PAPER_REGIME_PROB_MIN", "0.30"))
PAPER_REGIME_ENTROPY_MAX = float(os.getenv("PAPER_REGIME_ENTROPY_MAX", "1.8"))
PAPER_NEUTRAL_FAMILY = os.getenv("PAPER_NEUTRAL_FAMILY", "DEFINED_RISK").upper()
# Paper/SIM-only soft unblock for non-contradictory regime instability.
PAPER_SOFT_UNBLOCK_ENABLE = os.getenv("PAPER_SOFT_UNBLOCK_ENABLE", "true").lower() == "true"
PAPER_SOFT_UNBLOCK_CONF_MIN = float(os.getenv("PAPER_SOFT_UNBLOCK_CONF_MIN", "0.80"))
PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS = [
    s.strip()
    for s in os.getenv("PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS", "entropy_too_high,prob_too_low").split(",")
    if s.strip()
]

# Research pipeline degradation thresholds
RESEARCH_DEGRADE_SHARPE_MIN = float(os.getenv("RESEARCH_DEGRADE_SHARPE_MIN", "0.2"))
RESEARCH_DEGRADE_EXPECTANCY_MIN = float(os.getenv("RESEARCH_DEGRADE_EXPECTANCY_MIN", "0.0"))
RESEARCH_DEGRADE_TAIL_CVAR_MAX = float(os.getenv("RESEARCH_DEGRADE_TAIL_CVAR_MAX", "-5.0"))

# Hard regime gate settings
EVENT_ALLOW_DEFINED_RISK = os.getenv("EVENT_ALLOW_DEFINED_RISK", "true").lower() == "true"

# Micro-pattern (5m impulse + 5m pullback) for RANGE regime
MICRO_5M_SEC = 300
MICRO_10M_SEC = 600
MICRO_5M_UP_PTS = 15
MICRO_5M_DOWN_PTS = -15
MICRO_10M_PULLBACK_PTS = 10
MICRO_PATTERN_SCORE = 0.66

# Option risk modeling (premium-based)
OPT_ATR_PCT = 0.2
OPT_SPREAD_ATR_MULT = 3.0

# Zero-to-hero (lotto ideas; paper-only)
STRATEGY_ZERO_TO_HERO = "ZERO_TO_HERO"
ZERO_TO_HERO_ENABLE = os.getenv("ZERO_TO_HERO_ENABLE", "true").lower() == "true"
ZERO_TO_HERO_ALLOWED_MODES = [
    s.strip().upper()
    for s in os.getenv("ZERO_TO_HERO_ALLOWED_MODES", "PAPER").split(",")
    if s.strip()
]
ZERO_TO_HERO_ALLOWED_REGIMES = [
    s.strip().upper()
    for s in os.getenv("ZERO_TO_HERO_ALLOWED_REGIMES", "TREND,EVENT").split(",")
    if s.strip()
]
ZERO_TO_HERO_MAX_DAILY = int(os.getenv("ZERO_TO_HERO_MAX_DAILY", "1"))
ZERO_TO_HERO_OTM_PCT_MIN = float(os.getenv("ZERO_TO_HERO_OTM_PCT_MIN", "0.01"))
ZERO_TO_HERO_OTM_PCT_MAX = float(os.getenv("ZERO_TO_HERO_OTM_PCT_MAX", "0.02"))
ZERO_TO_HERO_PREMIUM_PCT_LOW = float(os.getenv("ZERO_TO_HERO_PREMIUM_PCT_LOW", "0.02"))
ZERO_TO_HERO_PREMIUM_PCT_HIGH = float(os.getenv("ZERO_TO_HERO_PREMIUM_PCT_HIGH", "0.25"))
ZERO_TO_HERO_PREMIUM_MIN_ABS = float(os.getenv("ZERO_TO_HERO_PREMIUM_MIN_ABS", "5"))
ZERO_TO_HERO_PREMIUM_MAX_ABS = float(os.getenv("ZERO_TO_HERO_PREMIUM_MAX_ABS", "80"))
ZERO_TO_HERO_PREMIUM_MIN_ROWS = int(os.getenv("ZERO_TO_HERO_PREMIUM_MIN_ROWS", "8"))
ZERO_TO_HERO_SPREAD_PCT_MAX = float(os.getenv("ZERO_TO_HERO_SPREAD_PCT_MAX", "0.25"))
ZERO_TO_HERO_MOMENTUM_ATR_MULT = float(os.getenv("ZERO_TO_HERO_MOMENTUM_ATR_MULT", "0.12"))
ZERO_TO_HERO_CONF_BASE = float(os.getenv("ZERO_TO_HERO_CONF_BASE", "0.55"))
ZERO_TO_HERO_CONF_MOMENTUM_WEIGHT = float(os.getenv("ZERO_TO_HERO_CONF_MOMENTUM_WEIGHT", "0.3"))
ZERO_TO_HERO_CONF_CHEAPNESS_WEIGHT = float(os.getenv("ZERO_TO_HERO_CONF_CHEAPNESS_WEIGHT", "0.2"))
ZERO_TO_HERO_STOP_ATR = float(os.getenv("ZERO_TO_HERO_STOP_ATR", "0.8"))
ZERO_TO_HERO_TARGET_ATR = float(os.getenv("ZERO_TO_HERO_TARGET_ATR", "2.0"))

# Legacy zero-hero (kept for compatibility; no longer used by default)
ZERO_HERO_ENABLE = True
ZERO_HERO_MIN_PREMIUM = 5
ZERO_HERO_MAX_PREMIUM = 60
ZERO_HERO_MIN_PROBA = 0.55
ZERO_HERO_ATR_MULT = 0.08
ZERO_HERO_TARGET_ATR = 2.0
ZERO_HERO_STOP_ATR = 0.6
ZERO_HERO_EXPIRY_ENABLE = os.getenv("ZERO_HERO_EXPIRY_ENABLE", "true").lower() == "true"
ZERO_HERO_EXPIRY_MIN_PREMIUM = int(os.getenv("ZERO_HERO_EXPIRY_MIN_PREMIUM", "5"))
ZERO_HERO_EXPIRY_MAX_PREMIUM = int(os.getenv("ZERO_HERO_EXPIRY_MAX_PREMIUM", "60"))
ZERO_HERO_EXPIRY_MIN_DELTA = float(os.getenv("ZERO_HERO_EXPIRY_MIN_DELTA", "0.2"))
ZERO_HERO_EXPIRY_MAX_DELTA = float(os.getenv("ZERO_HERO_EXPIRY_MAX_DELTA", "0.5"))
ZERO_HERO_EXPIRY_TARGET_POINTS = {
    "NIFTY": int(os.getenv("ZERO_HERO_EXPIRY_TGT_NIFTY", "50")),
    "SENSEX": int(os.getenv("ZERO_HERO_EXPIRY_TGT_SENSEX", "50")),
    "BANKNIFTY": int(os.getenv("ZERO_HERO_EXPIRY_TGT_BANKNIFTY", "100")),
}
ZERO_HERO_EXPIRY_PREMIUM_MAX_BY_SYMBOL = {
    "NIFTY": int(os.getenv("ZERO_HERO_EXPIRY_MAX_PREMIUM_NIFTY", "60")),
    "SENSEX": int(os.getenv("ZERO_HERO_EXPIRY_MAX_PREMIUM_SENSEX", "70")),
    "BANKNIFTY": int(os.getenv("ZERO_HERO_EXPIRY_MAX_PREMIUM_BANKNIFTY", "80")),
}
ZERO_HERO_EXPIRY_MAX_TRADES_PER_SYMBOL = int(os.getenv("ZERO_HERO_EXPIRY_MAX_TRADES_PER_SYMBOL", "1"))
ZERO_HERO_EXPIRY_MAX_TRADES_NIFTY = int(os.getenv("ZERO_HERO_EXPIRY_MAX_TRADES_NIFTY", "1"))
ZERO_HERO_EXPIRY_MAX_TRADES_SENSEX = int(os.getenv("ZERO_HERO_EXPIRY_MAX_TRADES_SENSEX", "1"))
ZERO_HERO_EXPIRY_DISABLE_AFTER_WIN = os.getenv("ZERO_HERO_EXPIRY_DISABLE_AFTER_WIN", "false").lower() == "true"
ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK = int(os.getenv("ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK", "2"))
ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_NIFTY = int(os.getenv("ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_NIFTY", "2"))
ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_SENSEX = int(os.getenv("ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_SENSEX", "2"))
ZERO_HERO_EXPIRY_DISABLE_DRAWDOWN = float(os.getenv("ZERO_HERO_EXPIRY_DISABLE_DRAWDOWN", "-0.5"))
ZERO_HERO_EXPIRY_REENABLE_ON_TREND = os.getenv("ZERO_HERO_EXPIRY_REENABLE_ON_TREND", "true").lower() == "true"
ZERO_HERO_EXPIRY_DISABLE_COOLDOWN_MIN = int(os.getenv("ZERO_HERO_EXPIRY_DISABLE_COOLDOWN_MIN", "45"))
ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN = int(os.getenv("ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN", "90"))
ZERO_HERO_EXPIRY_MAX_TRADES = int(os.getenv("ZERO_HERO_EXPIRY_MAX_TRADES", "2"))
ZERO_HERO_IVCRUSH_MIN = float(os.getenv("ZERO_HERO_IVCRUSH_MIN", "0.20"))
ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS = float(os.getenv("ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", "6"))

# Scalp trades (range/low momentum)
SCALP_ENABLE = True
SCALP_MIN_PREMIUM = 100
SCALP_MAX_PREMIUM = 150
SCALP_MIN_PROBA = 0.5
SCALP_MAX_MOM_ATR = 0.15
SCALP_DIR_ATR = 0.05
SCALP_TARGET_ATR = 0.6
SCALP_STOP_ATR = 0.3
SCALP_MAX_HOLD_MINUTES = 3
ML_MODEL_PATH = "models/xgb_live_model.pkl"
ML_CHALLENGER_MODEL_PATH = os.getenv("ML_CHALLENGER_MODEL_PATH", "models/xgb_live_model_challenger.pkl")
ML_ONLINE_UPDATE_ASYNC = os.getenv("ML_ONLINE_UPDATE_ASYNC", "true").lower() == "true"
ML_ONLINE_UPDATE_MAX_BLOCK_SEC = float(os.getenv("ML_ONLINE_UPDATE_MAX_BLOCK_SEC", "0.2"))
ML_TRAIN_DATA_PATH = os.getenv("ML_TRAIN_DATA_PATH", f"{DATA_ROOT}/ml_features.csv")
ML_TRAIN_TARGET_COL = os.getenv("ML_TRAIN_TARGET_COL", "target")
ML_HOLDOUT_FRAC = float(os.getenv("ML_HOLDOUT_FRAC", "0.2"))
ML_SEGMENT_MIN_SAMPLES = int(os.getenv("ML_SEGMENT_MIN_SAMPLES", "200"))
ML_DRIFT_WINDOW = int(os.getenv("ML_DRIFT_WINDOW", "200"))
ML_PSI_THRESHOLD = float(os.getenv("ML_PSI_THRESHOLD", "0.2"))
ML_KS_THRESHOLD = float(os.getenv("ML_KS_THRESHOLD", "0.2"))
ML_RETRAIN_ROLLING_WINDOW = int(os.getenv("ML_RETRAIN_ROLLING_WINDOW", "20"))
ML_RETRAIN_MIN_WIN_RATE = float(os.getenv("ML_RETRAIN_MIN_WIN_RATE", "0.45"))
ML_RETRAIN_MAX_ROLLING_DRAWDOWN = float(os.getenv("ML_RETRAIN_MAX_ROLLING_DRAWDOWN", "-0.06"))
ML_RETRAIN_MIN_EXPECTANCY = float(os.getenv("ML_RETRAIN_MIN_EXPECTANCY", "0.0"))
ML_REGIME_SHIFT_PSI = float(os.getenv("ML_REGIME_SHIFT_PSI", "0.2"))
ML_CALIBRATION_DELTA = float(os.getenv("ML_CALIBRATION_DELTA", "0.05"))
ML_CALIBRATION_BINS = int(os.getenv("ML_CALIBRATION_BINS", "10"))
ML_SHARPE_DROP = float(os.getenv("ML_SHARPE_DROP", "0.3"))
ML_EXPECTANCY_WINDOW = int(os.getenv("ML_EXPECTANCY_WINDOW", "50"))
ML_EXPECTANCY_MIN_WINDOWS = int(os.getenv("ML_EXPECTANCY_MIN_WINDOWS", "3"))
ML_SHADOW_EVAL_DAYS = int(os.getenv("ML_SHADOW_EVAL_DAYS", "5"))
ML_TAIL_LOSS_Q = float(os.getenv("ML_TAIL_LOSS_Q", "0.05"))
ML_ROLLBACK_KEEP_N = int(os.getenv("ML_ROLLBACK_KEEP_N", "3"))
ML_CHALLENGER_MIN_DIFF = float(os.getenv("ML_CHALLENGER_MIN_DIFF", "0.01"))
ML_PROMOTE_PVALUE = float(os.getenv("ML_PROMOTE_PVALUE", "0.1"))
ML_PROMOTE_BOOTSTRAP = int(os.getenv("ML_PROMOTE_BOOTSTRAP", "500"))
ML_PROMOTION_MIN_RETURN_DELTA = float(os.getenv("ML_PROMOTION_MIN_RETURN_DELTA", "0.0"))
ML_PROMOTION_MAX_DRAWDOWN_WORSEN = float(os.getenv("ML_PROMOTION_MAX_DRAWDOWN_WORSEN", "0.0"))
ML_PROMOTION_REQUIRE_ABLATION_SAFETY = os.getenv("ML_PROMOTION_REQUIRE_ABLATION_SAFETY", "true").lower() == "true"
ML_ABLATION_CHEAT_RETURN_DELTA = float(os.getenv("ML_ABLATION_CHEAT_RETURN_DELTA", "0.05"))
ML_ABLATION_CHEAT_DRAWDOWN_IMPROVE = float(os.getenv("ML_ABLATION_CHEAT_DRAWDOWN_IMPROVE", "0.03"))
ABLATION_LATEST_PATH = os.getenv("ABLATION_LATEST_PATH", f"{REPORTS_ROOT}/ablation/ablation_latest.json")
ML_DRIFT_BASELINE_PATH = os.getenv("ML_DRIFT_BASELINE_PATH", f"{LOGS_ROOT}/drift_baseline.json")
ML_MODEL_DECISIONS_PATH = os.getenv("ML_MODEL_DECISIONS_PATH", f"{LOGS_ROOT}/model_decisions.jsonl")
ML_EXEC_QUALITY_MIN = float(os.getenv("ML_EXEC_QUALITY_MIN", "55"))
ML_GOV_ENABLE = os.getenv("ML_GOV_ENABLE", "true").lower() == "true"
ML_AB_ENABLE = os.getenv("ML_AB_ENABLE", "true").lower() == "true"
ML_AB_MIN_TRADES = int(os.getenv("ML_AB_MIN_TRADES", "50"))
ML_ROLLBACK_ENABLE = os.getenv("ML_ROLLBACK_ENABLE", "true").lower() == "true"
ML_ROLLBACK_PSI = float(os.getenv("ML_ROLLBACK_PSI", "0.4"))
ML_ROLLBACK_KS = float(os.getenv("ML_ROLLBACK_KS", "0.4"))
ML_ROLLBACK_SHARPE_DROP = float(os.getenv("ML_ROLLBACK_SHARPE_DROP", "0.6"))
PROMOTION_MIN_DAYS = int(os.getenv("PROMOTION_MIN_DAYS", "7"))
PROMOTION_MIN_ROWS = int(os.getenv("PROMOTION_MIN_ROWS", "100"))
PROMOTION_ECE_MAX_DELTA = float(os.getenv("PROMOTION_ECE_MAX_DELTA", "0.01"))
PROMOTION_TAIL_WORST_K = int(os.getenv("PROMOTION_TAIL_WORST_K", "20"))
PROMOTION_PSI_MAX = float(os.getenv("PROMOTION_PSI_MAX", "0.2"))
PROMOTION_KS_MAX = float(os.getenv("PROMOTION_KS_MAX", "0.2"))
PROMOTION_SEGMENT_MAX_BRIER_WORSEN = float(os.getenv("PROMOTION_SEGMENT_MAX_BRIER_WORSEN", "0.02"))
PROMOTION_EVENT_MAX_BRIER_WORSEN = float(os.getenv("PROMOTION_EVENT_MAX_BRIER_WORSEN", "0.01"))
TRUTH_DATASET_PATH = os.getenv("TRUTH_DATASET_PATH", f"{DATA_ROOT}/truth_dataset.parquet")
ACCEPTANCE_GATE_ENABLE = os.getenv("ACCEPTANCE_GATE_ENABLE", "true").lower() == "true"
ACCEPTANCE_GATE_LATEST_PATH = os.getenv("ACCEPTANCE_GATE_LATEST_PATH", f"{LOGS_ROOT}/acceptance_gate_latest.json")
ACCEPTANCE_WINDOW_DAYS = int(os.getenv("ACCEPTANCE_WINDOW_DAYS", "30"))
ACCEPTANCE_MIN_TRADES = int(os.getenv("ACCEPTANCE_MIN_TRADES", "20"))
ACCEPTANCE_MIN_OUTCOME_ROWS = int(
    os.getenv("ACCEPTANCE_MIN_OUTCOME_ROWS", "500")
)
ACCEPTANCE_MIN_WIN_RATE = float(os.getenv("ACCEPTANCE_MIN_WIN_RATE", "0.45"))
ACCEPTANCE_MIN_EXPECTANCY_R = float(os.getenv("ACCEPTANCE_MIN_EXPECTANCY_R", "0.0"))
ACCEPTANCE_MAX_DRAWDOWN_R = float(os.getenv("ACCEPTANCE_MAX_DRAWDOWN_R", "-3.0"))
ACCEPTANCE_MIN_SHARPE_LIKE = float(os.getenv("ACCEPTANCE_MIN_SHARPE_LIKE", "0.0"))
ACCEPTANCE_MIN_SHADOW_ROWS = int(os.getenv("ACCEPTANCE_MIN_SHADOW_ROWS", "1000"))
ACCEPTANCE_MIN_OUTCOME_LINK_RATE = float(os.getenv("ACCEPTANCE_MIN_OUTCOME_LINK_RATE", "0.95"))
ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE = int(
    os.getenv("ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE", "100")
)
ACCEPTANCE_MAX_SHADOW_BRIER_DELTA = float(os.getenv("ACCEPTANCE_MAX_SHADOW_BRIER_DELTA", "0.0"))
ACCEPTANCE_MAX_SHADOW_ECE_DELTA = float(os.getenv("ACCEPTANCE_MAX_SHADOW_ECE_DELTA", "0.02"))
OUTCOME_RECONCILE_ENABLE = os.getenv("OUTCOME_RECONCILE_ENABLE", "true").lower() == "true"
OUTCOME_TRUTH_STATUS_PATH = os.getenv("OUTCOME_TRUTH_STATUS_PATH", f"{LOGS_ROOT}/outcome_truth_status_latest.json")
HEALTHCHECK_ENFORCE_DATA_TRUTH_LIVE = os.getenv("HEALTHCHECK_ENFORCE_DATA_TRUTH_LIVE", "true").lower() == "true"
REGIME_TREND_VWAP_SLOPE = float(os.getenv("REGIME_TREND_VWAP_SLOPE", "0.002"))
REGIME_VOL_Z_RANGE_VOL = float(os.getenv("REGIME_VOL_Z_RANGE_VOL", "1.0"))
USE_DEEP_MODEL = os.getenv("USE_DEEP_MODEL", "false").lower() == "true"
DEEP_MODEL_PATH = "models/lstm_options_model.h5"
DEEP_SEQUENCE_LEN = 20
USE_MICRO_MODEL = os.getenv("USE_MICRO_MODEL", "false").lower() == "true"
MICRO_MODEL_PATH = "models/microstructure_model.h5"
MICRO_MODEL_TRAIN_BACKEND = os.getenv("MICRO_MODEL_TRAIN_BACKEND", "sklearn").strip().lower()
ML_MIN_TRAIN_TRADES = 200
ML_USE_ONLY_WITH_HISTORY = True

# Strategy decay meta-model
DECAY_WINDOW_TRADES = int(os.getenv("DECAY_WINDOW_TRADES", "50"))
DECAY_PROB_THRESHOLD = float(os.getenv("DECAY_PROB_THRESHOLD", "0.7"))
DECAY_DOWNSIZE_THRESHOLD = float(os.getenv("DECAY_DOWNSIZE_THRESHOLD", "0.5"))
DECAY_DOWNSIZE_MULT = float(os.getenv("DECAY_DOWNSIZE_MULT", "0.6"))
DECAY_SOFT_THRESHOLD = float(os.getenv("DECAY_SOFT_THRESHOLD", str(DECAY_DOWNSIZE_THRESHOLD)))
DECAY_HARD_THRESHOLD = float(os.getenv("DECAY_HARD_THRESHOLD", str(DECAY_PROB_THRESHOLD)))
DECAY_PERSIST_WINDOWS = int(os.getenv("DECAY_PERSIST_WINDOWS", "3"))
DECAY_MODEL_PATH = os.getenv("DECAY_MODEL_PATH", "models/decay_model.pkl")
DECAY_CALIBRATION_METHOD = os.getenv("DECAY_CALIBRATION_METHOD", "isotonic")
DECAY_WEIGHTS = {
    "exp": -0.6,
    "sharpe_decay": 0.8,
    "hit_drift": -0.5,
    "fill_decay": 0.6,
    "slippage_trend": 0.4,
    "regime_shift": 0.6,
    "psi": 0.7,
    "ks": 0.4,
    "importance_instability": 0.3,
}

# RL sizing agent
RL_ENABLED = os.getenv("RL_ENABLED", os.getenv("RL_SIZE_ENABLE", "true")).lower() == "true"
RL_ACTIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
RL_REWARD_MODE = os.getenv("RL_REWARD_MODE", "CRO_SAFE")
RL_SHADOW_ONLY = os.getenv("RL_SHADOW_ONLY", os.getenv("RL_SIZE_SHADOW_MODE", "true")).lower() == "true"
RL_MIN_DAYS_SHADOW = int(os.getenv("RL_MIN_DAYS_SHADOW", "7"))
RL_PROMOTION_RULES = os.getenv("RL_PROMOTION_RULES", "brier_improve_and_tail_ok")
RL_SIZE_ENABLE = RL_ENABLED
RL_SIZE_SHADOW_MODE = RL_SHADOW_ONLY
RL_SIZE_MODEL_PATH = os.getenv("RL_SIZE_MODEL_PATH", "models/rl_size_agent.json")
RL_SIZE_CHALLENGER_PATH = os.getenv("RL_SIZE_CHALLENGER_PATH", "models/rl_size_agent_challenger.json")
RL_SIZE_EVAL_PATH = os.getenv("RL_SIZE_EVAL_PATH", f"{LOGS_ROOT}/rl_size_eval.json")
RL_SIZE_PROMOTE_DIFF = float(os.getenv("RL_SIZE_PROMOTE_DIFF", "0.02"))

# Manual approval
MANUAL_APPROVAL = os.getenv("MANUAL_APPROVAL", "true").lower() == "true"
KILL_SWITCH = os.getenv("KILL_SWITCH", "false").lower() == "true"
HALT_SYMBOLS = [s.strip().upper() for s in os.getenv("HALT_SYMBOLS", "").split(",") if s.strip()]
HALT_STRATEGIES = [s.strip().upper() for s in os.getenv("HALT_STRATEGIES", "").split(",") if s.strip()]

# Experiment flags
EXPERIMENT_ID = os.getenv("EXPERIMENT_ID", "")

# Desk capital allocation
GLOBAL_CAPITAL = float(os.getenv("GLOBAL_CAPITAL", str(CAPITAL)))
DESK_MIN_TRADES = int(os.getenv("DESK_MIN_TRADES", "10"))
DESK_MIN_DAYS = int(os.getenv("DESK_MIN_DAYS", "5"))
DESK_MAX_CORR = float(os.getenv("DESK_MAX_CORR", "0.8"))
DESK_CORR_PENALTY = float(os.getenv("DESK_CORR_PENALTY", "0.3"))
DESK_MIN_CORR_DAYS = int(os.getenv("DESK_MIN_CORR_DAYS", "5"))
DESK_MAX_BUDGET_PCT = float(os.getenv("DESK_MAX_BUDGET_PCT", "0.6"))
DESK_MIN_BUDGET_PCT = float(os.getenv("DESK_MIN_BUDGET_PCT", "0.0"))
DESK_MAX_GROSS_PCT = float(os.getenv("DESK_MAX_GROSS_PCT", "0.6"))
DESK_MAX_SYMBOL_PCT = float(os.getenv("DESK_MAX_SYMBOL_PCT", "0.3"))

# Paper tournament
TOURNAMENT_MIN_TRADES = int(os.getenv("TOURNAMENT_MIN_TRADES", "20"))
TOURNAMENT_PROMOTE_SCORE = float(os.getenv("TOURNAMENT_PROMOTE_SCORE", "0.15"))
TOURNAMENT_QUARANTINE_DD = float(os.getenv("TOURNAMENT_QUARANTINE_DD", "-5.0"))
TOURNAMENT_MIN_WINRATE = float(os.getenv("TOURNAMENT_MIN_WINRATE", "0.4"))

# Storage
DESK_ID = os.getenv("DESK_ID", "DEFAULT")
DESK_DATA_DIR = os.getenv("DESK_DATA_DIR", str(canonical_desks_dir(DESK_ID)))
DESK_LOG_DIR = os.getenv("DESK_LOG_DIR", str(canonical_desk_logs_dir(DESK_ID)))
DB_PATH = os.getenv("DB_PATH", str(canonical_trade_db_path(DESK_ID)))
TRADE_DB_PATH = os.getenv("TRADE_DB_PATH", DB_PATH)
# Ensure canonical runtime tree exists before any SQLite open attempts.
canonical_ensure_dir(DESK_DATA_DIR)
canonical_ensure_dir(DESK_LOG_DIR)
canonical_ensure_dir(canonical_db_dir())
TRADE_DB_PATH = str(Path(TRADE_DB_PATH).expanduser())
canonical_ensure_dir(Path(TRADE_DB_PATH).parent)
DB_PATH = str(Path(DB_PATH).expanduser())
canonical_ensure_dir(Path(DB_PATH).parent)
DECISION_LOG_PATH = os.getenv("DECISION_LOG_PATH", f"{DESK_LOG_DIR}/decision_events.jsonl")
REJECT_REASONS_LOG_PATH = os.getenv("REJECT_REASONS_LOG_PATH", f"{DESK_LOG_DIR}/reject_reasons.jsonl")
DECISION_ERROR_LOG_PATH = os.getenv("DECISION_ERROR_LOG_PATH", f"{DESK_LOG_DIR}/decision_event_errors.jsonl")
DECISION_SQLITE_PATH = os.getenv("DECISION_SQLITE_PATH", f"{DESK_LOG_DIR}/decision_events.sqlite")
DECISION_TELEMETRY_ENABLE = os.getenv("DECISION_TELEMETRY_ENABLE", "true").lower() == "true"
REJECT_TELEMETRY_ENABLE = os.getenv("REJECT_TELEMETRY_ENABLE", "true").lower() == "true"
REJECT_TELEMETRY_MAX_IN_MEMORY = int(os.getenv("REJECT_TELEMETRY_MAX_IN_MEMORY", "500"))
REJECT_TELEMETRY_LOG_DIR = os.getenv(
    "REJECT_TELEMETRY_LOG_DIR",
    f"{DESK_LOG_DIR}/reject_telemetry",
)
DECISION_SCAN_SUMMARY_JSONL_PATH = os.getenv(
    "DECISION_SCAN_SUMMARY_JSONL_PATH",
    f"{DESK_LOG_DIR}/decision_scan_summary.jsonl",
)
DECISION_SCAN_SUMMARY_LATEST_PATH = os.getenv(
    "DECISION_SCAN_SUMMARY_LATEST_PATH",
    f"{DESK_LOG_DIR}/decision_scan_summary_latest.json",
)
DECISION_LOG_ENABLED = os.getenv("DECISION_LOG_ENABLED", "false").lower() == "true"
DECISION_DB_PATH = os.getenv("DECISION_DB_PATH", TRADE_DB_PATH)
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", f"{DESK_LOG_DIR}/audit_log.jsonl")
INCIDENTS_LOG_PATH = os.getenv("INCIDENTS_LOG_PATH", f"{DESK_LOG_DIR}/incidents.jsonl")
FEATURE_FLAGS_OVERRIDE_PATH = os.getenv("FEATURE_FLAGS_OVERRIDE_PATH", f"{DESK_LOG_DIR}/feature_flags_override.json")
FEATURE_FLAGS_SNAPSHOT_PATH = os.getenv("FEATURE_FLAGS_SNAPSHOT_PATH", f"{DESK_LOG_DIR}/feature_flags_snapshot.json")

# Readiness gate
READINESS_MIN_FREE_GB = float(os.getenv("READINESS_MIN_FREE_GB", "2.0"))
READINESS_REQUIRE_KITE_AUTH = os.getenv("READINESS_REQUIRE_KITE_AUTH", "true").lower() == "true"
READINESS_REQUIRE_FEED_HEALTH = os.getenv("READINESS_REQUIRE_FEED_HEALTH", "true").lower() == "true"
READINESS_REQUIRE_AUDIT_CHAIN = os.getenv("READINESS_REQUIRE_AUDIT_CHAIN", "true").lower() == "true"
READINESS_REQUIRE_RISK_HALT_CLEAR = os.getenv("READINESS_REQUIRE_RISK_HALT_CLEAR", "true").lower() == "true"
READINESS_REQUIRE_TRADE_SCHEMA = os.getenv("READINESS_REQUIRE_TRADE_SCHEMA", "true").lower() == "true"
READINESS_ENFORCE_ON_EXEC = os.getenv("READINESS_ENFORCE_ON_EXEC", "true").lower() == "true"
READINESS_ENFORCE_PAPER = os.getenv("READINESS_ENFORCE_PAPER", "false").lower() == "true"
# Backward-compatible alias
ENFORCE_READINESS_ON_EXECUTION = READINESS_ENFORCE_ON_EXEC

# Governance gate (single trade-emission choke point)
GOV_GATE_REQUIRE_AUTH = os.getenv("GOV_GATE_REQUIRE_AUTH", "true").lower() == "true"
GOV_GATE_ENFORCE_PAPER = os.getenv("GOV_GATE_ENFORCE_PAPER", "false").lower() == "true"
GOV_GATE_REQUIRE_ORB_RESOLVED = os.getenv("GOV_GATE_REQUIRE_ORB_RESOLVED", "false").lower() == "true"
GOV_GATE_REQUIRE_DAYTYPE_CONF = os.getenv("GOV_GATE_REQUIRE_DAYTYPE_CONF", "false").lower() == "true"
GOV_GATE_REQUIRE_REGIME_CONF = os.getenv("GOV_GATE_REQUIRE_REGIME_CONF", "false").lower() == "true"
GOV_GATE_MIN_DAY_CONFIDENCE = float(os.getenv("GOV_GATE_MIN_DAY_CONFIDENCE", "0.6"))
GOV_GATE_MIN_REGIME_CONFIDENCE = float(os.getenv("GOV_GATE_MIN_REGIME_CONFIDENCE", "0.45"))
GOV_AUTH_MAX_AGE_SEC = float(os.getenv("GOV_AUTH_MAX_AGE_SEC", "180"))

# Session startup safety
AUTO_CLEAR_RISK_HALT_ON_START = os.getenv("AUTO_CLEAR_RISK_HALT_ON_START", "true").lower() == "true"
AUTO_CLEAR_RISK_HALT_REQUIRE_MARKET_CLOSED = (
    os.getenv("AUTO_CLEAR_RISK_HALT_REQUIRE_MARKET_CLOSED", "true").lower() == "true"
)
AUTO_CLEAR_RISK_HALT_REQUIRE_NO_OPEN_POSITIONS = (
    os.getenv("AUTO_CLEAR_RISK_HALT_REQUIRE_NO_OPEN_POSITIONS", "true").lower() == "true"
)

# Pre-open auth warmup
AUTH_WARMUP_TRIGGER_RISK_HALT = os.getenv("AUTH_WARMUP_TRIGGER_RISK_HALT", "true").lower() == "true"
AUTH_WARMUP_LOG_PATH = os.getenv("AUTH_WARMUP_LOG_PATH", f"{LOGS_ROOT}/auth_warmup.json")
AUTH_HEALTH_TTL_SEC = float(os.getenv("AUTH_HEALTH_TTL_SEC", "60"))
KITE_AUTH_RETRY_ATTEMPTS = int(os.getenv("KITE_AUTH_RETRY_ATTEMPTS", "2"))
KITE_AUTH_RETRY_BACKOFF_SEC = float(os.getenv("KITE_AUTH_RETRY_BACKOFF_SEC", "0.8"))
AUTH_PROACTIVE_REFRESH_ENABLE = os.getenv("AUTH_PROACTIVE_REFRESH_ENABLE", "true").lower() == "true"
AUTH_PROACTIVE_REFRESH_MAX_STALE_SEC = float(
    os.getenv("AUTH_PROACTIVE_REFRESH_MAX_STALE_SEC", "150")
)
AUTH_PREOPEN_WARM_CHECK_ENABLE = os.getenv("AUTH_PREOPEN_WARM_CHECK_ENABLE", "true").lower() == "true"
AUTH_PREOPEN_FORCE_REFRESH = os.getenv("AUTH_PREOPEN_FORCE_REFRESH", "true").lower() == "true"
AUTH_PREOPEN_DEGRADE_TO_PLANNING = (
    os.getenv("AUTH_PREOPEN_DEGRADE_TO_PLANNING", "true").lower() == "true"
)
AUTH_PREOPEN_WARM_INTERVAL_SEC = float(os.getenv("AUTH_PREOPEN_WARM_INTERVAL_SEC", "45"))
AUTH_RUNTIME_GUARD_PATH = os.getenv("AUTH_RUNTIME_GUARD_PATH", f"{LOGS_ROOT}/auth_runtime_guard.json")

# Risk governance / scorecard
DAILY_LOSS_LIMIT = CAPITAL * MAX_DAILY_LOSS_PCT
PORTFOLIO_MAX_DRAWDOWN = MAX_DRAWDOWN_PCT
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", f"{LOGS_ROOT}/trade_log.jsonl")
EXECUTION_INTENTS_LOG_PATH = os.getenv(
    "EXECUTION_INTENTS_LOG_PATH",
    f"{LOGS_ROOT}/execution_intents.jsonl",
)
EXECUTION_INTENTS_LOG_WARN_ONCE = (
    os.getenv("EXECUTION_INTENTS_LOG_WARN_ONCE", "false").lower() == "true"
)
RISK_HALT_FILE = os.getenv("RISK_HALT_FILE", f"{LOGS_ROOT}/risk_halt.json")
LOG_LOCK_FILE = os.getenv("LOG_LOCK_FILE", f"{LOGS_ROOT}/trade_log.lock")
APPEND_ONLY_LOG = True

# Data QC / SLA thresholds
QC_MAX_NULL_RATE = 0.1
SLA_MAX_TICK_LAG_SEC = 120
SLA_MAX_DEPTH_LAG_SEC = 120
SLA_MIN_TICKS_PER_HOUR = 1000
SLA_MIN_DEPTH_PER_HOUR = 200
FEED_STALE_INCIDENT_COOLDOWN_SEC = int(os.getenv("FEED_STALE_INCIDENT_COOLDOWN_SEC", "300"))
FEED_FRESHNESS_TTL_SEC = float(os.getenv("FEED_FRESHNESS_TTL_SEC", "5"))
CHAIN_MAX_MISSING_IV_PCT = float(os.getenv("CHAIN_MAX_MISSING_IV_PCT", "0.2"))
CHAIN_MAX_MISSING_QUOTE_PCT = float(os.getenv("CHAIN_MAX_MISSING_QUOTE_PCT", "0.2"))

# Circuit breaker + run lock hardening
CB_ERROR_STORM_N = int(os.getenv("CB_ERROR_STORM_N", "5"))
CB_ERROR_STORM_MINS = float(os.getenv("CB_ERROR_STORM_MINS", "5"))
CB_HALT_MINS = float(os.getenv("CB_HALT_MINS", "15"))
CB_FEED_UNHEALTHY_SEC = float(os.getenv("CB_FEED_UNHEALTHY_SEC", "120"))
RUN_LOCK_NAME = os.getenv("RUN_LOCK_NAME", "live_monitoring.lock")
RUN_LOCK_MAX_AGE_SEC = float(os.getenv("RUN_LOCK_MAX_AGE_SEC", "3600"))

# Daily performance alerts
MIN_DAILY_PF = 1.1
MIN_DAILY_SHARPE = 0.2
PERF_ALERT_DAYS = 3

# Scorecard thresholds
SCORECARD_LIVE_DAYS = 180
SCORECARD_PAPER_DAYS = 30
SCORECARD_TICK_MIN = 50000
SCORECARD_DEPTH_MIN = 5000
TV_SHARED_SECRET = os.getenv("TV_SHARED_SECRET", "")

# Options filter thresholds
MIN_OI = 1000
MIN_IV = 0.10
MAX_IV = 0.60
DELTA_MIN = 0.25
DELTA_MAX = 0.70
MIN_OI_CHANGE = 100
MIN_OI_CHANGE_ATM = 200
MIN_OI_CHANGE_OTM = 300
ATM_MONEYNESS_THRESHOLD = 0.01
OI_DYNAMIC_IV_ALPHA = 2.0
OI_DYNAMIC_ATR_ALPHA = 1.0
IV_Z_MIN = -1.5
IV_Z_MAX = 1.5
IV_SKEW_MAX = 0.05
IV_SKEW_BULL_MAX = 0.02
IV_SKEW_BEAR_MIN = -0.02
IV_SKEW_CALL_MAX = 0.03
IV_SKEW_PUT_MIN = -0.03
IV_SURFACE_SLOPE_MAX = 0.25
IV_SKEW_CURVE_MAX = 1.2
IV_TERM_MIN = -0.05
IV_TERM_MAX = 0.05
ENABLE_TERM_STRUCTURE = True

# Volatility targeting
VOL_TARGET = 0.002
LOSS_STREAK_CAP = 3
LOSS_STREAK_RISK_MULT = 0.6
TERM_STRUCTURE_EXPIRY = os.getenv("TERM_STRUCTURE_EXPIRY", "WEEKLY")
DAYTYPE_LOG_EVERY_SEC = int(os.getenv("DAYTYPE_LOG_EVERY_SEC", "60"))

# Backtest realism
BACKTEST_ENTRY_WINDOW = int(os.getenv("BACKTEST_ENTRY_WINDOW", "3"))
BACKTEST_HORIZON = int(os.getenv("BACKTEST_HORIZON", "5"))
BACKTEST_SLIPPAGE_BPS = float(os.getenv("BACKTEST_SLIPPAGE_BPS", "5"))
BACKTEST_SPREAD_BPS = float(os.getenv("BACKTEST_SPREAD_BPS", "5"))
BACKTEST_FEE_PER_TRADE = float(os.getenv("BACKTEST_FEE_PER_TRADE", "0.0"))
BACKTEST_USE_SYNTH_CHAIN = os.getenv("BACKTEST_USE_SYNTH_CHAIN", "true").lower() == "true"

# -------------------------------
# Live monitoring interval (seconds)
# -------------------------------
SCAN_INTERVAL = 60  # check for trades every 60 seconds

# -------------------------------
# Kite / Data options
# -------------------------------
KITE_USE_API = os.getenv("KITE_USE_API", "true").lower() == "true"
REQUIRE_LIVE_QUOTES = os.getenv("REQUIRE_LIVE_QUOTES", "true").lower() == "true"
OFFHOURS_FORCE_ENABLE = os.getenv("OFFHOURS_FORCE_ENABLE", "false").lower() == "true"
OFFHOURS_FORCE_DISABLE = os.getenv("OFFHOURS_FORCE_DISABLE", "false").lower() == "true"
OFFHOURS_DEBUG_INDEX_BIDASK_MISSING = os.getenv("OFFHOURS_DEBUG_INDEX_BIDASK_MISSING", "false").lower() == "true"
INVALID_LTP_ACTION = os.getenv("INVALID_LTP_ACTION", "skip_symbol")
OUTCOME_PNL_EPSILON = float(os.getenv("OUTCOME_PNL_EPSILON", "0.000001"))

# Partial profit / trail-after-scaleout
PARTIAL_PROFIT_ENABLED = os.getenv("PARTIAL_PROFIT_ENABLED", "true").lower() == "true"
TP1_R_MULT = float(os.getenv("TP1_R_MULT", "0.7"))
TP1_FRACTION = float(os.getenv("TP1_FRACTION", "0.5"))
MOVE_SL_TO_BE = os.getenv("MOVE_SL_TO_BE", "true").lower() == "true"
TRAIL_AFTER_TP1 = os.getenv("TRAIL_AFTER_TP1", "true").lower() == "true"
TP2_R_MULT = float(os.getenv("TP2_R_MULT", "1.5"))
TRAIL_ENABLE = os.getenv("TRAIL_ENABLE", "false").lower() == "true"
TRAIL_ENABLE_PAPER = os.getenv("TRAIL_ENABLE_PAPER", "true").lower() == "true"
TRAIL_OFFSET_MIN = float(os.getenv("TRAIL_OFFSET_MIN", "5"))
TRAIL_OFFSET_RISK_MULT = float(os.getenv("TRAIL_OFFSET_RISK_MULT", "0.5"))
TRAIL_RULE_DEFAULT = os.getenv("TRAIL_RULE_DEFAULT", "MFE_MINUS_OFFSET")
TRAIL_START_DEFAULT = os.getenv("TRAIL_START_DEFAULT", "AFTER_1R")
REQUIRE_LIVE_OPTION_QUOTES = os.getenv("REQUIRE_LIVE_OPTION_QUOTES", "true").lower() == "true"
REQUIRE_DEPTH_QUOTES_FOR_TRADE = os.getenv("REQUIRE_DEPTH_QUOTES_FOR_TRADE", "true").lower() == "true"
REQUIRE_VOLUME_FOR_TRADE = os.getenv("REQUIRE_VOLUME_FOR_TRADE", "true").lower() == "true"
LIVE_QUOTE_ERROR_TTL_SEC = int(os.getenv("LIVE_QUOTE_ERROR_TTL_SEC", "300"))
ALLOW_STALE_LTP = os.getenv("ALLOW_STALE_LTP", "true").lower() == "true"
LTP_CACHE_TTL_SEC = int(os.getenv("LTP_CACHE_TTL_SEC", "300"))
FORCE_SYNTH_CHAIN_ON_FAIL = os.getenv("FORCE_SYNTH_CHAIN_ON_FAIL", "true").lower() == "true"
ALLOW_CLOSE_FALLBACK = os.getenv("ALLOW_CLOSE_FALLBACK", "true").lower() == "true"
QUEUE_ROW_MAX_AGE_MIN = int(os.getenv("QUEUE_ROW_MAX_AGE_MIN", "120"))
ENTRY_MISMATCH_PCT = float(os.getenv("ENTRY_MISMATCH_PCT", "0.25"))
INDICATOR_STALE_SEC = int(os.getenv("INDICATOR_STALE_SEC", "120"))
OHLC_BUFFER_MAX_BARS = int(os.getenv("OHLC_BUFFER_MAX_BARS", "500"))
OHLC_MIN_BARS = int(os.getenv("OHLC_MIN_BARS", "30"))
OHLC_WARM_SEED_WINDOWS_MIN = os.getenv("OHLC_WARM_SEED_WINDOWS_MIN", "120,240")
OHLC_WARM_SEED_INTERVAL = os.getenv("OHLC_WARM_SEED_INTERVAL", "minute")
STARTUP_WARMUP_ENABLE = os.getenv("STARTUP_WARMUP_ENABLE", "true").lower() == "true"
STARTUP_WARMUP_INTERVAL = os.getenv("STARTUP_WARMUP_INTERVAL", "5minute")
STARTUP_WARMUP_TARGET_BARS = int(os.getenv("STARTUP_WARMUP_TARGET_BARS", "200"))
STARTUP_WARMUP_FETCH_RETRIES = int(os.getenv("STARTUP_WARMUP_FETCH_RETRIES", "3"))
STARTUP_WARMUP_RETRY_BACKOFF_SEC = float(os.getenv("STARTUP_WARMUP_RETRY_BACKOFF_SEC", "0.4"))
STARTUP_WARMUP_MAX_BACKOFF_SEC = float(os.getenv("STARTUP_WARMUP_MAX_BACKOFF_SEC", "2.5"))
STARTUP_WARMUP_LOOKBACK_DAYS = int(os.getenv("STARTUP_WARMUP_LOOKBACK_DAYS", "7"))
STARTUP_WARMUP_LOOKBACK_MINUTES = int(
    os.getenv("STARTUP_WARMUP_LOOKBACK_MINUTES", str(max(STARTUP_WARMUP_LOOKBACK_DAYS, 1) * 24 * 60))
)
STARTUP_WARMUP_SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("STARTUP_WARMUP_SYMBOLS", "NIFTY,BANKNIFTY,SENSEX").split(",")
    if s.strip()
]
INDICATORS_NEVER_COMPUTED_AGE_SEC = float(os.getenv("INDICATORS_NEVER_COMPUTED_AGE_SEC", "1000000000"))
VWAP_WINDOW = int(os.getenv("VWAP_WINDOW", "20"))
VWAP_SLOPE_WINDOW = int(os.getenv("VWAP_SLOPE_WINDOW", "10"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
ADX_PERIOD = int(os.getenv("ADX_PERIOD", "14"))
VOL_WINDOW = int(os.getenv("VOL_WINDOW", "30"))
KITE_RATE_LIMIT_SLEEP = float(os.getenv("KITE_RATE_LIMIT_SLEEP", "0.35"))
KITE_TRADES_SYNC = os.getenv("KITE_TRADES_SYNC", "true").lower() == "true"
KITE_INSTRUMENTS_TTL = int(os.getenv("KITE_INSTRUMENTS_TTL", "3600"))
KITE_USE_DEPTH = os.getenv("KITE_USE_DEPTH", "true").lower() == "true"
KITE_STORE_TICKS = os.getenv("KITE_STORE_TICKS", "true").lower() == "true"
DEPTH_WS_LOCK_NAME = os.getenv("DEPTH_WS_LOCK_NAME", "depth_ws.lock")
DEPTH_WS_LOCK_MAX_AGE_SEC = float(os.getenv("DEPTH_WS_LOCK_MAX_AGE_SEC", "3600"))
DEPTH_WS_SINGLETON = os.getenv("DEPTH_WS_SINGLETON", "true").lower() == "true"
MAX_CLOCK_SKEW_SEC = float(os.getenv("MAX_CLOCK_SKEW_SEC", "5.0"))
FEED_RECONNECT_COOLDOWN_SEC = float(os.getenv("FEED_RECONNECT_COOLDOWN_SEC", "30"))
FEED_RESTART_STRIKES = int(os.getenv("FEED_RESTART_STRIKES", "3"))
FEED_FULL_RESTART_COOLDOWN_SEC = float(os.getenv("FEED_FULL_RESTART_COOLDOWN_SEC", "120"))
FEED_MAX_FULL_RESTARTS_PER_HOUR = int(os.getenv("FEED_MAX_FULL_RESTARTS_PER_HOUR", "6"))
FEED_RESTART_STORM_TRIP = int(os.getenv("FEED_RESTART_STORM_TRIP", "6"))
FEED_RESTART_STORM_WINDOW_SEC = float(os.getenv("FEED_RESTART_STORM_WINDOW_SEC", "3600"))
FEED_RESTART_STORM_MAX = int(os.getenv("FEED_RESTART_STORM_MAX", "6"))
FEED_RESTART_STORM_COOLDOWN_SEC = float(os.getenv("FEED_RESTART_STORM_COOLDOWN_SEC", "900"))
FEED_TRIP_ON_WS_403 = os.getenv("FEED_TRIP_ON_WS_403", "true").lower() == "true"
DEPTH_SUBSCRIPTION_STRIKES_AROUND = int(os.getenv("DEPTH_SUBSCRIPTION_STRIKES_AROUND", "6"))
DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL = {
    "NIFTY": int(os.getenv("DEPTH_SUBSCRIPTION_STRIKES_AROUND_NIFTY", "6")),
    "BANKNIFTY": int(os.getenv("DEPTH_SUBSCRIPTION_STRIKES_AROUND_BANKNIFTY", "6")),
    "SENSEX": int(os.getenv("DEPTH_SUBSCRIPTION_STRIKES_AROUND_SENSEX", "4")),
}
DEPTH_SUBSCRIPTION_MAX_TOKENS = int(os.getenv("DEPTH_SUBSCRIPTION_MAX_TOKENS", "150"))
DEPTH_SUBSCRIPTION_VALIDATE_TOKENS = os.getenv("DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", "true").lower() == "true"
DEPTH_REBALANCE_COOLDOWN_SEC = float(os.getenv("DEPTH_REBALANCE_COOLDOWN_SEC", "60"))
DEPTH_ATM_SHIFT_THRESHOLD_STEPS = int(os.getenv("DEPTH_ATM_SHIFT_THRESHOLD_STEPS", "1"))
FEED_WATCHDOG_POLL_SEC = float(os.getenv("FEED_WATCHDOG_POLL_SEC", "1.0"))
FEED_SILENT_INDEX_THRESHOLD_SEC = float(os.getenv("FEED_SILENT_INDEX_THRESHOLD_SEC", "1.5"))
FEED_SILENT_OPTION_THRESHOLD_SEC = float(os.getenv("FEED_SILENT_OPTION_THRESHOLD_SEC", "3.0"))
FEED_SILENT_CONFIRM_CYCLES = int(os.getenv("FEED_SILENT_CONFIRM_CYCLES", "2"))
FEED_SILENT_RECONNECT_BACKOFF_MIN_SEC = float(os.getenv("FEED_SILENT_RECONNECT_BACKOFF_MIN_SEC", "1.0"))
FEED_SILENT_RECONNECT_BACKOFF_MAX_SEC = float(os.getenv("FEED_SILENT_RECONNECT_BACKOFF_MAX_SEC", "10.0"))
SLA_MAX_LTP_AGE_SEC = float(os.getenv("SLA_MAX_LTP_AGE_SEC", "2.5"))
SLA_MAX_DEPTH_AGE_SEC = float(os.getenv("SLA_MAX_DEPTH_AGE_SEC", "6.0"))
OFFHOURS_SLA_MAX_LTP_AGE_SEC = float(
    os.getenv("OFFHOURS_SLA_MAX_LTP_AGE_SEC", str(max(SLA_MAX_LTP_AGE_SEC, 900.0)))
)
OFFHOURS_SLA_MAX_DEPTH_AGE_SEC = float(
    os.getenv("OFFHOURS_SLA_MAX_DEPTH_AGE_SEC", str(max(SLA_MAX_DEPTH_AGE_SEC, 900.0)))
)
SLO_GUARD_ENABLE = os.getenv("SLO_GUARD_ENABLE", "true").lower() == "true"
SLO_ENFORCE_LIVE_ONLY = os.getenv("SLO_ENFORCE_LIVE_ONLY", "true").lower() == "true"
SLO_AUTH_MAX_AGE_SEC = float(os.getenv("SLO_AUTH_MAX_AGE_SEC", str(GOV_AUTH_MAX_AGE_SEC)))
SLO_AUTH_MAX_LATENCY_SEC = float(os.getenv("SLO_AUTH_MAX_LATENCY_SEC", "2.0"))
SLO_FEED_MAX_LTP_AGE_SEC = float(os.getenv("SLO_FEED_MAX_LTP_AGE_SEC", str(SLA_MAX_LTP_AGE_SEC)))
SLO_FEED_MAX_DEPTH_AGE_SEC = float(os.getenv("SLO_FEED_MAX_DEPTH_AGE_SEC", str(SLA_MAX_DEPTH_AGE_SEC)))
SLO_FAILOVER_CONSECUTIVE_BREACHES = int(os.getenv("SLO_FAILOVER_CONSECUTIVE_BREACHES", "3"))
SLO_FAILOVER_ACTION = os.getenv("SLO_FAILOVER_ACTION", "RISK_HALT")
SLO_FAILOVER_COOLDOWN_SEC = float(os.getenv("SLO_FAILOVER_COOLDOWN_SEC", "300"))
SLO_FAILOVER_STATE_PATH = os.getenv("SLO_FAILOVER_STATE_PATH", f"{LOGS_ROOT}/slo_failover_state.json")
SLO_EVENT_LOG_PATH = os.getenv("SLO_EVENT_LOG_PATH", f"{LOGS_ROOT}/slo_events.jsonl")
SUGGESTION_RELIABILITY_CHECK_ENABLE = os.getenv("SUGGESTION_RELIABILITY_CHECK_ENABLE", "true").lower() == "true"
SUGGESTION_RELIABILITY_INTERVAL_SEC = float(os.getenv("SUGGESTION_RELIABILITY_INTERVAL_SEC", "900"))
SUGGESTION_RELIABILITY_WINDOW_SEC = float(os.getenv("SUGGESTION_RELIABILITY_WINDOW_SEC", "900"))
SUGGESTION_RELIABILITY_MIN_RATIO = float(os.getenv("SUGGESTION_RELIABILITY_MIN_RATIO", "0.15"))
SUGGESTION_RELIABILITY_MIN_ALLOWED = int(os.getenv("SUGGESTION_RELIABILITY_MIN_ALLOWED", "20"))
SUGGESTION_RELIABILITY_LOG_PATH = os.getenv(
    "SUGGESTION_RELIABILITY_LOG_PATH",
    f"{LOGS_ROOT}/suggestion_reliability.jsonl",
)
SUGGESTION_RELIABILITY_LATEST_PATH = os.getenv(
    "SUGGESTION_RELIABILITY_LATEST_PATH",
    f"{LOGS_ROOT}/suggestion_reliability_latest.json",
)
SUGGESTIONS_LOG_PATH = os.getenv("SUGGESTIONS_LOG_PATH", f"{LOGS_ROOT}/suggestions.jsonl")
SUGGESTION_EVAL_LOG_PATH = os.getenv("SUGGESTION_EVAL_LOG_PATH", f"{LOGS_ROOT}/suggestion_eval.jsonl")
REJECTED_CANDIDATES_LOG_PATH = os.getenv(
    "REJECTED_CANDIDATES_LOG_PATH",
    f"{LOGS_ROOT}/rejected_candidates.jsonl",
)
FEED_AUTO_REPAIR_ENABLE = os.getenv("FEED_AUTO_REPAIR_ENABLE", "true").lower() == "true"
FEED_AUTO_REPAIR_TRIGGER_STRIKES = max(1, int(os.getenv("FEED_AUTO_REPAIR_TRIGGER_STRIKES", "2")))
FEED_AUTO_REPAIR_COOLDOWN_SEC = float(os.getenv("FEED_AUTO_REPAIR_COOLDOWN_SEC", "60"))
FEED_AUTO_REPAIR_MAX_RETRIES = max(1, int(os.getenv("FEED_AUTO_REPAIR_MAX_RETRIES", "3")))
FEED_AUTO_REPAIR_AUTH_RECHECK_SEC = float(os.getenv("FEED_AUTO_REPAIR_AUTH_RECHECK_SEC", "90"))
LIVE_ENABLEMENT_STRICT = os.getenv("LIVE_ENABLEMENT_STRICT", "false").lower() == "true"
LIVE_ENABLEMENT_AUDIT_PATH = os.getenv("LIVE_ENABLEMENT_AUDIT_PATH", f"{LOGS_ROOT}/live_enablement_audit_latest.json")
LIVE_ENABLEMENT_REQUIRE_STATISTICAL_PASS = (
    os.getenv("LIVE_ENABLEMENT_REQUIRE_STATISTICAL_PASS", "true").lower() == "true"
)

# -------------------------------
# Cross-asset features
# -------------------------------
CROSS_ASSET_SYMBOLS = {
    "NIFTY_INDEX": os.getenv("CROSS_NIFTY_INDEX", "NSE:NIFTY 50"),
    "BANKNIFTY_INDEX": os.getenv("CROSS_BANKNIFTY_INDEX", "NSE:NIFTY BANK"),
    "SENSEX_INDEX": os.getenv("CROSS_SENSEX_INDEX", "BSE:SENSEX"),
    "USDINR_SPOT": os.getenv("CROSS_USDINR_SPOT", "CDS:USDINR"),
    "USDINR_FUT": os.getenv("CROSS_USDINR_FUT", "CDS:USDINR"),
    "CRUDEOIL": os.getenv("CROSS_CRUDEOIL", "MCX:CRUDEOIL"),
    "GIFT_NIFTY": os.getenv("CROSS_GIFT_NIFTY", ""),
    "INDIA_VIX": os.getenv("CROSS_INDIA_VIX", "NSE:INDIAVIX"),
    "BOND10Y": os.getenv("CROSS_BOND10Y", ""),
}
# +1 means risk-off when asset rises, -1 means risk-on
CROSS_ASSET_RISK_SIGN = {
    "NIFTY_INDEX": -1,
    "BANKNIFTY_INDEX": -1,
    "SENSEX_INDEX": -1,
    "USDINR_SPOT": 1,
    "USDINR_FUT": 1,
    "CRUDEOIL": 1,
    "GIFT_NIFTY": -1,
    "INDIA_VIX": 1,
    "BOND10Y": 1,
}
CROSS_ASSET_REFRESH_SEC = int(os.getenv("CROSS_ASSET_REFRESH_SEC", "30"))
CROSS_ASSET_MAXLEN = int(os.getenv("CROSS_ASSET_MAXLEN", "600"))
CROSS_ASSET_STALE_SEC = int(os.getenv("CROSS_ASSET_STALE_SEC", "120"))
CROSS_ASSET_OPTIONAL_SCORE_PENALTY = float(os.getenv("CROSS_ASSET_OPTIONAL_SCORE_PENALTY", "8"))
CROSS_ASSET_OPTIONAL_SIZE_MULT = float(os.getenv("CROSS_ASSET_OPTIONAL_SIZE_MULT", "0.85"))
REQUIRE_CROSS_ASSET = os.getenv("REQUIRE_CROSS_ASSET", "true").lower() == "true"
REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE = os.getenv("REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", "true").lower() == "true"

def _load_instrument_symbols():
    path = Path(DATA_ROOT) / "kite_instruments.csv"
    if not path.exists():
        return set()
    symbols = set()
    try:
        with path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                exch = (row.get("exchange") or "").strip()
                ts = (row.get("tradingsymbol") or "").strip()
                if exch and ts:
                    symbols.add(f"{exch}:{ts}")
    except Exception:
        return set()
    return symbols


_INSTRUMENT_SYMBOLS = _load_instrument_symbols()


_CROSS_INDEX_SYMBOLS = set(
    s
    for s in [
        CROSS_ASSET_SYMBOLS.get("NIFTY_INDEX"),
        CROSS_ASSET_SYMBOLS.get("BANKNIFTY_INDEX"),
        CROSS_ASSET_SYMBOLS.get("SENSEX_INDEX"),
    ]
    if s
)


def _is_supported_symbol(sym: str):
    if not _INSTRUMENT_SYMBOLS:
        return None
    return sym in _INSTRUMENT_SYMBOLS


_required_default = os.getenv("CROSS_REQUIRED_FEEDS", "NIFTY_INDEX")
_optional_default = os.getenv(
    "CROSS_OPTIONAL_FEEDS",
    "BANKNIFTY_INDEX,SENSEX_INDEX,CRUDEOIL,USDINR_SPOT,USDINR_FUT,INDIA_VIX,GIFT_NIFTY,BOND10Y",
)
_req_list = [s.strip() for s in _required_default.split(",") if s.strip()]
_opt_list = [s.strip() for s in _optional_default.split(",") if s.strip()]

CROSS_FEED_STATUS = {}

def _set_feed_status(feed_key: str, status: str, reason: str | None = None):
    CROSS_FEED_STATUS[feed_key] = {"status": status, "reason": reason}

def _classify_feed(feed_key: str, preferred: str):
    sym = CROSS_ASSET_SYMBOLS.get(feed_key)
    if not sym:
        _set_feed_status(feed_key, "disabled", "no_symbol")
        return
    # Explicitly downgrade unsupported or unreliable feeds to optional.
    if feed_key in {"GIFT_NIFTY", "BOND10Y", "INDIA_VIX"}:
        if preferred == "required":
            _set_feed_status(feed_key, "optional", "unsupported_default_optional")
        else:
            _set_feed_status(feed_key, "optional", "unsupported_default_optional")
        return
    supported = _is_supported_symbol(sym)
    if supported is True:
        _set_feed_status(feed_key, preferred, None)
        return
    if supported is False:
        if preferred == "required":
            _set_feed_status(feed_key, "optional", "unsupported_required_downgraded")
        else:
            _set_feed_status(feed_key, "disabled", "unsupported")
        return
    if preferred == "required":
        _set_feed_status(feed_key, "optional", "instrument_cache_missing_downgraded")
    else:
        _set_feed_status(feed_key, "optional", "instrument_cache_missing")

for _f in _req_list:
    _classify_feed(_f, "required")
for _f in _opt_list:
    if _f not in CROSS_FEED_STATUS:
        _classify_feed(_f, "optional")
for _f in CROSS_ASSET_SYMBOLS.keys():
    if _f not in CROSS_FEED_STATUS:
        _classify_feed(_f, "optional")

CROSS_REQUIRED_FEEDS = [k for k, v in CROSS_FEED_STATUS.items() if v.get("status") == "required"]
CROSS_OPTIONAL_FEEDS = [k for k, v in CROSS_FEED_STATUS.items() if v.get("status") == "optional"]
CROSS_DISABLED_FEEDS = {k: v.get("reason") for k, v in CROSS_FEED_STATUS.items() if v.get("status") == "disabled"}

# -------------------------------
# Synthetic stress generator
# -------------------------------
STRESS_TEST_ENABLE = os.getenv("STRESS_TEST_ENABLE", "false").lower() == "true"
STRESS_PATHS = int(os.getenv("STRESS_PATHS", "250"))
STRESS_STEPS = int(os.getenv("STRESS_STEPS", "240"))
STRESS_BLOCK_SIZE = int(os.getenv("STRESS_BLOCK_SIZE", "20"))
STRESS_MIN_VALID_ROWS = int(os.getenv("STRESS_MIN_VALID_ROWS", "1"))
STRESS_VOL_SCALE = float(os.getenv("STRESS_VOL_SCALE", "1.8"))
STRESS_JUMP_LAMBDA = float(os.getenv("STRESS_JUMP_LAMBDA", "0.03"))
STRESS_JUMP_SIGMA = float(os.getenv("STRESS_JUMP_SIGMA", "0.03"))
STRESS_GAP_PROB = float(os.getenv("STRESS_GAP_PROB", "0.02"))
STRESS_GAP_SIGMA = float(os.getenv("STRESS_GAP_SIGMA", "0.05"))
STRESS_SPREAD_WIDEN_PCT = float(os.getenv("STRESS_SPREAD_WIDEN_PCT", "0.5"))
STRESS_IV_SPIKE = float(os.getenv("STRESS_IV_SPIKE", "0.35"))
STRESS_OB_THIN_FACTOR = float(os.getenv("STRESS_OB_THIN_FACTOR", "0.6"))

# -------------------------------
# Execution simulation controls
# -------------------------------
EXEC_SIM_TIMEOUT_SEC = float(os.getenv("EXEC_SIM_TIMEOUT_SEC", "3.0"))
EXEC_SIM_POLL_SEC = float(os.getenv("EXEC_SIM_POLL_SEC", "0.25"))
MAX_QUOTE_AGE_SEC = float(os.getenv("MAX_QUOTE_AGE_SEC", "2.0"))
MAX_DEPTH_AGE_SEC = float(os.getenv("MAX_DEPTH_AGE_SEC", str(SLA_MAX_DEPTH_AGE_SEC)))
EXEC_MAX_CHASE_PCT = float(os.getenv("EXEC_MAX_CHASE_PCT", "0.002"))
EXEC_MAX_REPLACE = int(os.getenv("EXEC_MAX_REPLACE", "2"))
EXEC_REPRICE_PCT = float(os.getenv("EXEC_REPRICE_PCT", "0.002"))
EXEC_SPREAD_WIDEN_PCT = float(os.getenv("EXEC_SPREAD_WIDEN_PCT", "0.5"))
EXEC_MAX_SPREAD_PCT = float(os.getenv("EXEC_MAX_SPREAD_PCT", "0.015"))
# Fill realism layer for paper/sim executions.
_FILL_REALISM_DEFAULT = "true" if str(TRADING_MODE).upper() in {"PAPER", "SIM"} else "false"
FILL_REALISM_ENABLED = os.getenv("FILL_REALISM_ENABLED", _FILL_REALISM_DEFAULT).lower() == "true"
FILL_REALISM_SEED = int(os.getenv("FILL_REALISM_SEED", "20260227"))
MAX_SPREAD_PCT_FOR_MARKET = float(os.getenv("MAX_SPREAD_PCT_FOR_MARKET", str(EXEC_MAX_SPREAD_PCT)))
MAX_QUOTE_AGE_MS = int(os.getenv("MAX_QUOTE_AGE_MS", str(int(MAX_QUOTE_AGE_SEC * 1000.0))))
LATENCY_MS = int(os.getenv("LATENCY_MS", "120"))
ALLOW_PARTIAL_FILLS = os.getenv("ALLOW_PARTIAL_FILLS", "true").lower() == "true"
DEPTH_IMPACT_K = float(os.getenv("DEPTH_IMPACT_K", "0.10"))
VOL_IMPACT_K = float(os.getenv("VOL_IMPACT_K", "0.05"))
LIMIT_ORDER_REJECT_ON_SLIP = os.getenv("LIMIT_ORDER_REJECT_ON_SLIP", "true").lower() == "true"
FILL_REALISM_FILL_REMAINDER_AT_WORSE = (
    os.getenv("FILL_REALISM_FILL_REMAINDER_AT_WORSE", "false").lower() == "true"
)
FILL_REALISM_METRICS_MAX_POINTS = int(os.getenv("FILL_REALISM_METRICS_MAX_POINTS", "5000"))
_SPREAD_MULTIPLIER_RANGE_RAW = str(os.getenv("SPREAD_MULTIPLIER_RANGE", "0.25,1.0")).strip()
try:
    _spread_parts = [float(part.strip()) for part in _SPREAD_MULTIPLIER_RANGE_RAW.split(",") if part.strip()]
except Exception:
    _spread_parts = []
if len(_spread_parts) >= 2:
    SPREAD_MULTIPLIER_RANGE = (min(_spread_parts[0], _spread_parts[1]), max(_spread_parts[0], _spread_parts[1]))
elif len(_spread_parts) == 1:
    SPREAD_MULTIPLIER_RANGE = float(_spread_parts[0])
else:
    SPREAD_MULTIPLIER_RANGE = (0.25, 1.0)
# Cost sensitivity / edge-after-cost readiness gate.
COST_GATE_ENABLED = os.getenv("COST_GATE_ENABLED", "true").lower() == "true"
COST_GATE_WINDOW_TRADES = int(os.getenv("COST_GATE_WINDOW_TRADES", "50"))
MAX_REJECT_RATE = float(os.getenv("MAX_REJECT_RATE", "0.35"))
MAX_P95_SLIPPAGE_BPS = float(os.getenv("MAX_P95_SLIPPAGE_BPS", "15"))
MAX_P95_SPREAD_BPS = float(os.getenv("MAX_P95_SPREAD_BPS", "25"))
MIN_NET_EDGE_RATIO = float(os.getenv("MIN_NET_EDGE_RATIO", "0.60"))
MIN_NET_WINRATE = float(os.getenv("MIN_NET_WINRATE", "0.0"))
# Approximate fee knobs (basis points + optional fixed fee per order).
COST_BROKERAGE_BPS = float(os.getenv("COST_BROKERAGE_BPS", "2.0"))
COST_EXCHANGE_BPS = float(os.getenv("COST_EXCHANGE_BPS", "0.6"))
COST_TAXES_BPS = float(os.getenv("COST_TAXES_BPS", "0.4"))
COST_FIXED_FEE_PER_ORDER = float(os.getenv("COST_FIXED_FEE_PER_ORDER", "0.0"))
EXEC_FILL_PROB = float(os.getenv("EXEC_FILL_PROB", "0.85"))
EXEC_ALPHA_SPREAD_MULT = float(os.getenv("EXEC_ALPHA_SPREAD_MULT", "0.6"))
EXEC_ALPHA_VOL_Z_BPS = float(os.getenv("EXEC_ALPHA_VOL_Z_BPS", "3.0"))
EXEC_ALPHA_IMBALANCE_BPS = float(os.getenv("EXEC_ALPHA_IMBALANCE_BPS", "2.0"))
EXEC_ALPHA_MAX_BUFFER_PCT = float(os.getenv("EXEC_ALPHA_MAX_BUFFER_PCT", "0.01"))
EXEC_ALPHA_ATR_VOL_MULT = float(os.getenv("EXEC_ALPHA_ATR_VOL_MULT", "0.5"))
EXEC_ALPHA_QUEUE_BPS = float(os.getenv("EXEC_ALPHA_QUEUE_BPS", "4.0"))
EXEC_ALPHA_URGENCY_BPS = float(os.getenv("EXEC_ALPHA_URGENCY_BPS", "3.0"))
EXEC_ALPHA_TIME_DECAY_BPS = float(os.getenv("EXEC_ALPHA_TIME_DECAY_BPS", "5.0"))
EXEC_ALPHA_MIN_TICK = float(os.getenv("EXEC_ALPHA_MIN_TICK", "0.05"))
EXEC_ALPHA_QUEUE_LEVELS = int(os.getenv("EXEC_ALPHA_QUEUE_LEVELS", "3"))
EXEC_ADAPTIVE_RETRY_ENABLE = os.getenv("EXEC_ADAPTIVE_RETRY_ENABLE", "false").lower() == "true"
EXEC_ADAPTIVE_MAX_RETRIES = int(os.getenv("EXEC_ADAPTIVE_MAX_RETRIES", "5"))
EXEC_ADAPTIVE_STEP_PCT = float(os.getenv("EXEC_ADAPTIVE_STEP_PCT", "0.0005"))
EXEC_ADAPTIVE_MAX_SLIPPAGE_BPS = float(os.getenv("EXEC_ADAPTIVE_MAX_SLIPPAGE_BPS", "150.0"))
EXEC_ADAPTIVE_ABORT_ON_REGIME_CHANGE = (
    os.getenv("EXEC_ADAPTIVE_ABORT_ON_REGIME_CHANGE", "true").lower() == "true"
)
EXEC_ADAPTIVE_RETRY_LIMIT_REASON = os.getenv(
    "EXEC_ADAPTIVE_RETRY_LIMIT_REASON",
    "retry_limit_exceeded",
)
ORDER_STORE_STARTUP_LOAD_LIMIT = int(os.getenv("ORDER_STORE_STARTUP_LOAD_LIMIT", "2000"))
ORDER_RECONCILE_ON_STARTUP = os.getenv("ORDER_RECONCILE_ON_STARTUP", "true").lower() == "true"
ORDER_RECON_DAEMON_ENABLE = os.getenv("ORDER_RECON_DAEMON_ENABLE", "true").lower() == "true"
ORDER_RECON_INTERVAL_SEC = float(os.getenv("ORDER_RECON_INTERVAL_SEC", "5.0"))
RUNTIME_HEALTH_PATH = os.getenv("RUNTIME_HEALTH_PATH", f"{LOGS_ROOT}/runtime_health_latest.json")
SHADOW_EVAL_STATUS_PATH = os.getenv("SHADOW_EVAL_STATUS_PATH", f"{LOGS_ROOT}/shadow_eval_status_latest.json")
GATE_QUALITY_STATUS_PATH = os.getenv("GATE_QUALITY_STATUS_PATH", f"{LOGS_ROOT}/gate_quality_status_latest.json")
PRETRADE_RISK_ENABLE = os.getenv("PRETRADE_RISK_ENABLE", "true").lower() == "true"
PRETRADE_MARGIN_BUFFER_PCT = float(os.getenv("PRETRADE_MARGIN_BUFFER_PCT", "0.05"))
PRETRADE_MAX_EXPOSURE_PER_INSTRUMENT = float(
    os.getenv("PRETRADE_MAX_EXPOSURE_PER_INSTRUMENT", "1000000000")
)
PRETRADE_MAX_DAILY_LOSS = float(
    os.getenv("PRETRADE_MAX_DAILY_LOSS", str(DAILY_LOSS_LIMIT))
)
PRETRADE_MAX_TRADES_PER_MINUTE = int(os.getenv("PRETRADE_MAX_TRADES_PER_MINUTE", "20"))
PRETRADE_MAX_CORRELATED_EXPOSURE = float(
    os.getenv("PRETRADE_MAX_CORRELATED_EXPOSURE", "1000000000")
)
PRETRADE_DUPLICATE_WINDOW_SEC = float(os.getenv("PRETRADE_DUPLICATE_WINDOW_SEC", "300"))
PRETRADE_CORRELATION_THRESHOLD = float(os.getenv("PRETRADE_CORRELATION_THRESHOLD", "0.75"))
PRETRADE_REQUIRE_MARGIN_DATA = os.getenv("PRETRADE_REQUIRE_MARGIN_DATA", "false").lower() == "true"
PRETRADE_REQUIRE_DAILY_LOSS_DATA = (
    os.getenv("PRETRADE_REQUIRE_DAILY_LOSS_DATA", "false").lower() == "true"
)
EXEC_QUALITY_MIN = float(os.getenv("EXEC_QUALITY_MIN", "55"))
EXEC_QUALITY_BLOCK_BELOW = float(os.getenv("EXEC_QUALITY_BLOCK_BELOW", "35"))
EXEC_QUALITY_PENALTY = float(os.getenv("EXEC_QUALITY_PENALTY", "10"))
# Spread guard controls
SPREAD_GUARD_ENABLE = os.getenv("SPREAD_GUARD_ENABLE", "true").lower() == "true"
SPREAD_GUARD_BASE_SPREAD_PCT = float(
    os.getenv("SPREAD_GUARD_BASE_SPREAD_PCT", str(MAX_SPREAD_PCT))
)
SPREAD_GUARD_VOL_METHOD = os.getenv("SPREAD_GUARD_VOL_METHOD", "ATR").upper()
SPREAD_GUARD_VOL_PERIOD = int(os.getenv("SPREAD_GUARD_VOL_PERIOD", "20"))
SPREAD_GUARD_VOL_FACTOR = float(os.getenv("SPREAD_GUARD_VOL_FACTOR", "1.2"))
SPREAD_GUARD_STDDEV_TO_ATR_MULT = float(os.getenv("SPREAD_GUARD_STDDEV_TO_ATR_MULT", "1.0"))
SPREAD_GUARD_CRITICAL_VOL_PCT = float(os.getenv("SPREAD_GUARD_CRITICAL_VOL_PCT", "0.03"))
SPREAD_GUARD_DYNAMIC_MIN_PCT = float(os.getenv("SPREAD_GUARD_DYNAMIC_MIN_PCT", "0.001"))
SPREAD_GUARD_DYNAMIC_MAX_PCT = float(os.getenv("SPREAD_GUARD_DYNAMIC_MAX_PCT", "0.08"))
SPREAD_GUARD_ENABLE_OPENING_AUCTION = (
    os.getenv("SPREAD_GUARD_ENABLE_OPENING_AUCTION", "true").lower() == "true"
)
SPREAD_GUARD_OPENING_AUCTION_MIN = int(os.getenv("SPREAD_GUARD_OPENING_AUCTION_MIN", "5"))
SPREAD_GUARD_ENABLE_ILLIQUID_CHECK = (
    os.getenv("SPREAD_GUARD_ENABLE_ILLIQUID_CHECK", "true").lower() == "true"
)
SPREAD_GUARD_ILLIQUID_SPREAD_PCT = float(os.getenv("SPREAD_GUARD_ILLIQUID_SPREAD_PCT", "0.04"))
SPREAD_GUARD_MIN_VOLUME = float(os.getenv("SPREAD_GUARD_MIN_VOLUME", "1"))
SPREAD_GUARD_MIN_VOLUME_RATIO = float(os.getenv("SPREAD_GUARD_MIN_VOLUME_RATIO", "0.10"))
SPREAD_GUARD_CACHE_TTL_SEC = float(os.getenv("SPREAD_GUARD_CACHE_TTL_SEC", "15"))
# Execution performance controls
EXEC_PERF_WINDOW_TRADES = int(os.getenv("EXEC_PERF_WINDOW_TRADES", "100"))
EXEC_PERF_MIN_FILL_RATE_PCT = float(os.getenv("EXEC_PERF_MIN_FILL_RATE_PCT", "60"))
EXEC_PERF_MAX_REJECTION_RATE_PCT = float(os.getenv("EXEC_PERF_MAX_REJECTION_RATE_PCT", "10"))
EXEC_PERF_DISABLE_MINUTES = float(os.getenv("EXEC_PERF_DISABLE_MINUTES", "30"))
EXEC_PERF_LOG_PATH = os.getenv("EXEC_PERF_LOG_PATH", f"{LOGS_ROOT}/execution_performance.jsonl")

# -------------------------------
# Greeks / Pricing
# -------------------------------
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.06"))
# Day type thresholds
DAYTYPE_VWAP_DIST = float(os.getenv("DAYTYPE_VWAP_DIST", "0.002"))
DAYTYPE_LOCK_MIN = int(os.getenv("DAYTYPE_LOCK_MIN", "60"))
DAYTYPE_LOCK_ENABLE = os.getenv("DAYTYPE_LOCK_ENABLE", "true").lower() == "true"

# -------------------------------
# Tradingsymbol generation / replay fixture validation
# -------------------------------
OPTION_TS_WEEKLY_INCLUDE_DAY = os.getenv("OPTION_TS_WEEKLY_INCLUDE_DAY", "true").lower() == "true"
OPTION_TS_MONTHLY_INCLUDE_DAY = os.getenv("OPTION_TS_MONTHLY_INCLUDE_DAY", "false").lower() == "true"
OPTION_TS_MONTHLY_WEEKDAY = int(os.getenv("OPTION_TS_MONTHLY_WEEKDAY", "3"))  # 0=Mon ... 3=Thu
OPTION_TS_MONTHLY_WEEKDAY_BY_SYMBOL = {
    "NIFTY": int(os.getenv("OPTION_TS_MONTHLY_WEEKDAY_NIFTY", str(OPTION_TS_MONTHLY_WEEKDAY))),
    "BANKNIFTY": int(os.getenv("OPTION_TS_MONTHLY_WEEKDAY_BANKNIFTY", str(OPTION_TS_MONTHLY_WEEKDAY))),
    "SENSEX": int(os.getenv("OPTION_TS_MONTHLY_WEEKDAY_SENSEX", "1")),  # Tue by convention
}
REPLAY_FIXTURE_AUTO_SYMBOLS = os.getenv("REPLAY_FIXTURE_AUTO_SYMBOLS", "true").lower() == "true"
REPLAY_FIXTURE_LOG_PATH = os.getenv("REPLAY_FIXTURE_LOG_PATH", f"{LOGS_ROOT}/replay_fixture_symbols.jsonl")
DAYTYPE_CONF_SWITCH_MIN = float(os.getenv("DAYTYPE_CONF_SWITCH_MIN", "0.6"))
DAYTYPE_BUCKET_OPEN_END = int(os.getenv("DAYTYPE_BUCKET_OPEN_END", "11"))
DAYTYPE_BUCKET_MID_END = int(os.getenv("DAYTYPE_BUCKET_MID_END", "14"))
DAYTYPE_ALERT_COOLDOWN_SEC = int(os.getenv("DAYTYPE_ALERT_COOLDOWN_SEC", "600"))
DAYTYPE_RISK_MULT = {
    "TREND_DAY": 1.2,
    "RANGE_DAY": 0.9,
    "RANGE_VOLATILE": 0.85,
    "EVENT_DAY": 0.8,
    "PANIC_DAY": 0.7,
    "FAKE_BREAKOUT_DAY": 0.7,
    "TREND_RANGE_DAY": 1.0,
    "RANGE_TREND_DAY": 1.0,
    "EXPIRY_DAY": 0.6,
    "UNKNOWN": 0.9,
}
ORB_LOCK_MIN = int(os.getenv("ORB_LOCK_MIN", "15"))
ORB_BIAS_LOCK = os.getenv("ORB_BIAS_LOCK", "true").lower() == "true"
ORB_WINDOW_MIN = int(os.getenv("ORB_WINDOW_MIN", str(ORB_LOCK_MIN)))
ORB_CANDLE_MINUTES_LIVE = int(os.getenv("ORB_CANDLE_MINUTES_LIVE", "5"))
ORB_CANDLE_MINUTES_PAPER = int(os.getenv("ORB_CANDLE_MINUTES_PAPER", "0"))
ORB_CANDLE_MINUTES_SIM = int(os.getenv("ORB_CANDLE_MINUTES_SIM", "0"))
ORB_BREAK_BUFFER_PCT = float(os.getenv("ORB_BREAK_BUFFER_PCT", "0.0005"))
ORB_HARD_BLOCK_LIVE = os.getenv("ORB_HARD_BLOCK_LIVE", "false").lower() == "true"
ORB_HARD_CONFLICT_LIVE = os.getenv("ORB_HARD_CONFLICT_LIVE", "false").lower() == "true"
ORB_NEUTRAL_ALLOW = os.getenv("ORB_NEUTRAL_ALLOW", "true").lower() == "true"
PLANNING_ORB_NEUTRAL_ALLOW = os.getenv("PLANNING_ORB_NEUTRAL_ALLOW", "true").lower() == "true"
ORB_SOFT_VETO_CONF_MULT = float(os.getenv("ORB_SOFT_VETO_CONF_MULT", "0.95"))
ORB_SOFT_VETO_SIZE_MULT = float(os.getenv("ORB_SOFT_VETO_SIZE_MULT", "0.95"))
DAILY_PROFIT_LOCK = float(os.getenv("DAILY_PROFIT_LOCK", "0.012"))
DAILY_DRAWNDOWN_LOCK = float(os.getenv("DAILY_DRAWNDOWN_LOCK", "-0.01"))
BEST_TRADE_PER_DAY = os.getenv("BEST_TRADE_PER_DAY", "true").lower() == "true"
PRICE_CONFIRM_ENABLE = os.getenv("PRICE_CONFIRM_ENABLE", "true").lower() == "true"
PRICE_CONFIRM_PCT = float(os.getenv("PRICE_CONFIRM_PCT", "0.001"))
SYMBOL_DAILY_PROFIT_LOCK = float(os.getenv("SYMBOL_DAILY_PROFIT_LOCK", "0.006"))
BEST_TRADE_PER_REGIME = os.getenv("BEST_TRADE_PER_REGIME", "true").lower() == "true"
PRICE_CONFIRM_VWAP = os.getenv("PRICE_CONFIRM_VWAP", "true").lower() == "true"
SPREAD_SUGGESTIONS_ENABLE = os.getenv("SPREAD_SUGGESTIONS_ENABLE", "false").lower() == "true"
SPREAD_MAX_PER_SYMBOL = int(os.getenv("SPREAD_MAX_PER_SYMBOL", "2"))
IRON_CONDOR_WIDTH = int(os.getenv("IRON_CONDOR_WIDTH", "100"))
IRON_FLY_WIDTH = int(os.getenv("IRON_FLY_WIDTH", "100"))
SPREAD_MIN_CREDIT = float(os.getenv("SPREAD_MIN_CREDIT", "5"))
SPREAD_MIN_DEBIT = float(os.getenv("SPREAD_MIN_DEBIT", "5"))
SPREAD_MIN_IV = float(os.getenv("SPREAD_MIN_IV", "0.15"))
ENABLE_TARGET_POINTS_SUGGESTIONS = os.getenv("ENABLE_TARGET_POINTS_SUGGESTIONS", "true").lower() == "true"
TARGET_POINTS_MIN = float(os.getenv("TARGET_POINTS_MIN", "20.0"))

# Entry trigger logic (buy above / sell below)
ENTRY_TRIGGER_MODE = os.getenv("ENTRY_TRIGGER_MODE", "BREAKOUT").upper()
ENTRY_PREMIUM_BUFFER = float(os.getenv("ENTRY_PREMIUM_BUFFER", "2.0"))
ENTRY_PREMIUM_BUFFER_PCT = float(os.getenv("ENTRY_PREMIUM_BUFFER_PCT", "0.01"))
ENTRY_TRIGGER_MAIN_ONLY = os.getenv("ENTRY_TRIGGER_MAIN_ONLY", "false").lower() == "true"
DAILY_PROFIT_LOCK = float(os.getenv("DAILY_PROFIT_LOCK", "0.012"))
DAILY_DRAWNDOWN_LOCK = float(os.getenv("DAILY_DRAWNDOWN_LOCK", "-0.01"))
BEST_TRADE_PER_DAY = os.getenv("BEST_TRADE_PER_DAY", "true").lower() == "true"
PRICE_CONFIRM_ENABLE = os.getenv("PRICE_CONFIRM_ENABLE", "true").lower() == "true"
PRICE_CONFIRM_PCT = float(os.getenv("PRICE_CONFIRM_PCT", "0.001"))
DAYTYPE_LOCK_ENABLE = os.getenv("DAYTYPE_LOCK_ENABLE", "true").lower() == "true"

# -------------------------------
# Event/Snapshot storage subsystem
# -------------------------------
STORAGE_EVENTS_ENABLE = os.getenv("STORAGE_EVENTS_ENABLE", "true").lower() == "true"
STORAGE_BASE_DIR = os.getenv("STORAGE_BASE_DIR", "~/.trading_bot/data")
STORAGE_MIN_FREE_PCT = float(os.getenv("STORAGE_MIN_FREE_PCT", "10"))
STORAGE_CRITICAL_FREE_PCT = float(os.getenv("STORAGE_CRITICAL_FREE_PCT", "5"))
STORAGE_KEEP_SNAPSHOTS_DAYS = int(os.getenv("STORAGE_KEEP_SNAPSHOTS_DAYS", "7"))
STORAGE_KEEP_EVENTS_DAYS = int(os.getenv("STORAGE_KEEP_EVENTS_DAYS", "30"))
STORAGE_SNAPSHOT_N_BEFORE = int(os.getenv("STORAGE_SNAPSHOT_N_BEFORE", "2"))
STORAGE_SNAPSHOT_N_AFTER = int(os.getenv("STORAGE_SNAPSHOT_N_AFTER", "2"))
STORAGE_SNAPSHOT_INTERVAL_MS = int(os.getenv("STORAGE_SNAPSHOT_INTERVAL_MS", "500"))
STORAGE_SNAPSHOTS_FOR_CANDIDATE_CREATED = (
    os.getenv("STORAGE_SNAPSHOTS_FOR_CANDIDATE_CREATED", "false").lower() == "true"
)
STORAGE_FEATURES_SUMMARY_MAX_BYTES = int(os.getenv("STORAGE_FEATURES_SUMMARY_MAX_BYTES", "2048"))
STORAGE_FEATURES_SUMMARY_MAX_KEYS = int(os.getenv("STORAGE_FEATURES_SUMMARY_MAX_KEYS", "96"))
