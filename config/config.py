# config/config.py

# -------------------------------
# Env loader (optional)
# -------------------------------
import os
import json
import csv
from pathlib import Path
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

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
AUDIT_REQUIRED_TO_TRADE = os.getenv("AUDIT_REQUIRED_TO_TRADE", "true").lower() == "true"
EXEC_DEGRADATION_MAX_MISSED_FILL_RATE = float(os.getenv("EXEC_DEGRADATION_MAX_MISSED_FILL_RATE", "0.5"))
EXEC_DEGRADATION_MAX_SLIPPAGE_MULT = float(os.getenv("EXEC_DEGRADATION_MAX_SLIPPAGE_MULT", "2.0"))
# Baseline slippage (price units) for degradation checks. If zero/unknown, pilot mode halts.
EXEC_BASELINE_SLIPPAGE = float(os.getenv("EXEC_BASELINE_SLIPPAGE", "0.0"))

# -------------------------------
# Strategy lifecycle governance
# -------------------------------
STRATEGY_LIFECYCLE_PATH = os.getenv("STRATEGY_LIFECYCLE_PATH", "logs/strategy_lifecycle.json")
STRATEGY_LIFECYCLE_DEFAULT_STATE = os.getenv("STRATEGY_LIFECYCLE_DEFAULT_STATE", "PAPER")
ALLOW_RESEARCH_STRATEGIES = os.getenv("ALLOW_RESEARCH_STRATEGIES", "false").lower() == "true"
PROMOTION_PILOT_DAYS_REQUIRED = int(os.getenv("PROMOTION_PILOT_DAYS_REQUIRED", "3"))
PROMOTION_REQUIRE_STRESS = os.getenv("PROMOTION_REQUIRE_STRESS", "true").lower() == "true"
PROMOTION_REQUIRE_BACKTEST = os.getenv("PROMOTION_REQUIRE_BACKTEST", "true").lower() == "true"

# -------------------------------
# Symbols to monitor
# -------------------------------
SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
ENABLE_FUTURES = True
ENABLE_EQUITIES = False
FUTURES_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
EQUITY_SYMBOLS = ["NIFTY 50", "BANKNIFTY", "SENSEX"]

# -------------------------------
# Expiry configuration
# -------------------------------
# 0 = Monday, 1 = Tuesday, ..., 4 = Friday
EXPIRY_DAY = 1  # always take next Tuesday expiry

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
STRIKES_AROUND = 6
STRIKES_AROUND_BY_SYMBOL = {
    "NIFTY": 40,   # +/-2000 points (40 * 50)
    "SENSEX": 40,  # +/-2000 points (40 * 50)
    "BANKNIFTY": 40,  # +/-4000 points (40 * 100)
}
# Expiry weekdays by symbol (0=Mon ... 6=Sun)
EXPIRY_WEEKDAY_BY_SYMBOL = {
    "NIFTY": int(os.getenv("NIFTY_EXPIRY_WEEKDAY", "3")),        # Thu
    "BANKNIFTY": int(os.getenv("BANKNIFTY_EXPIRY_WEEKDAY", "2")), # Wed
    "SENSEX": int(os.getenv("SENSEX_EXPIRY_WEEKDAY", "3")),       # Thu (per user preference)
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
META_SHADOW_LOG_PATH = os.getenv("META_SHADOW_LOG_PATH", "logs/meta_shadow.jsonl")
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
EXECUTION_MODE = "SIM"  # SIM only for now
EXECUTION_MODE_PAPER = True
EXECUTION_MODE_LIVE = False
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
QUICK_TRADE_MODE = True
DEBUG_TRADE_REASONS = True
DEBUG_TRADE_MODE = os.getenv("DEBUG_TRADE_MODE", "false").lower() == "true"
DEBUG_TRADE_TOP_N = int(os.getenv("DEBUG_TRADE_TOP_N", "5"))
QUICK_MIN_PROBA = float(os.getenv("QUICK_MIN_PROBA", "0.35"))
QUICK_USE_SIGNAL_SCORE = os.getenv("QUICK_USE_SIGNAL_SCORE", "true").lower() == "true"
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

# Zero-hero (cheap option momentum)
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
ML_TRAIN_DATA_PATH = os.getenv("ML_TRAIN_DATA_PATH", "data/ml_features.csv")
ML_TRAIN_TARGET_COL = os.getenv("ML_TRAIN_TARGET_COL", "target")
ML_HOLDOUT_FRAC = float(os.getenv("ML_HOLDOUT_FRAC", "0.2"))
ML_SEGMENT_MIN_SAMPLES = int(os.getenv("ML_SEGMENT_MIN_SAMPLES", "200"))
ML_DRIFT_WINDOW = int(os.getenv("ML_DRIFT_WINDOW", "200"))
ML_PSI_THRESHOLD = float(os.getenv("ML_PSI_THRESHOLD", "0.2"))
ML_KS_THRESHOLD = float(os.getenv("ML_KS_THRESHOLD", "0.2"))
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
ML_DRIFT_BASELINE_PATH = os.getenv("ML_DRIFT_BASELINE_PATH", "logs/drift_baseline.json")
ML_MODEL_DECISIONS_PATH = os.getenv("ML_MODEL_DECISIONS_PATH", "logs/model_decisions.jsonl")
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
REGIME_TREND_VWAP_SLOPE = float(os.getenv("REGIME_TREND_VWAP_SLOPE", "0.002"))
REGIME_VOL_Z_RANGE_VOL = float(os.getenv("REGIME_VOL_Z_RANGE_VOL", "1.0"))
USE_DEEP_MODEL = os.getenv("USE_DEEP_MODEL", "false").lower() == "true"
DEEP_MODEL_PATH = "models/lstm_options_model.h5"
DEEP_SEQUENCE_LEN = 20
USE_MICRO_MODEL = os.getenv("USE_MICRO_MODEL", "false").lower() == "true"
MICRO_MODEL_PATH = "models/microstructure_model.h5"
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
RL_SIZE_EVAL_PATH = os.getenv("RL_SIZE_EVAL_PATH", "logs/rl_size_eval.json")
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
DESK_DATA_DIR = os.getenv("DESK_DATA_DIR", f"data/desks/{DESK_ID}")
DESK_LOG_DIR = os.getenv("DESK_LOG_DIR", f"logs/desks/{DESK_ID}")
TRADE_DB_PATH = os.getenv("TRADE_DB_PATH", f"{DESK_DATA_DIR}/trades.db")
DECISION_LOG_PATH = os.getenv("DECISION_LOG_PATH", f"{DESK_LOG_DIR}/decision_events.jsonl")
DECISION_ERROR_LOG_PATH = os.getenv("DECISION_ERROR_LOG_PATH", f"{DESK_LOG_DIR}/decision_event_errors.jsonl")
DECISION_SQLITE_PATH = os.getenv("DECISION_SQLITE_PATH", f"{DESK_LOG_DIR}/decision_events.sqlite")
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

# Risk governance / scorecard
DAILY_LOSS_LIMIT = CAPITAL * MAX_DAILY_LOSS_PCT
PORTFOLIO_MAX_DRAWDOWN = MAX_DRAWDOWN_PCT
RISK_HALT_FILE = "logs/risk_halt.json"
LOG_LOCK_FILE = "logs/trade_log.lock"
APPEND_ONLY_LOG = True

# Data QC / SLA thresholds
QC_MAX_NULL_RATE = 0.1
SLA_MAX_TICK_LAG_SEC = 120
SLA_MAX_DEPTH_LAG_SEC = 120
SLA_MIN_TICKS_PER_HOUR = 1000
SLA_MIN_DEPTH_PER_HOUR = 200
FEED_STALE_INCIDENT_COOLDOWN_SEC = int(os.getenv("FEED_STALE_INCIDENT_COOLDOWN_SEC", "300"))
CHAIN_MAX_MISSING_IV_PCT = float(os.getenv("CHAIN_MAX_MISSING_IV_PCT", "0.2"))
CHAIN_MAX_MISSING_QUOTE_PCT = float(os.getenv("CHAIN_MAX_MISSING_QUOTE_PCT", "0.2"))

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
MAX_CLOCK_SKEW_SEC = float(os.getenv("MAX_CLOCK_SKEW_SEC", "5.0"))
FEED_RECONNECT_COOLDOWN_SEC = float(os.getenv("FEED_RECONNECT_COOLDOWN_SEC", "30"))

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
    path = Path("data/kite_instruments.csv")
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
MAX_DEPTH_AGE_SEC = float(os.getenv("MAX_DEPTH_AGE_SEC", str(MAX_QUOTE_AGE_SEC)))
EXEC_MAX_CHASE_PCT = float(os.getenv("EXEC_MAX_CHASE_PCT", "0.002"))
EXEC_MAX_REPLACE = int(os.getenv("EXEC_MAX_REPLACE", "2"))
EXEC_REPRICE_PCT = float(os.getenv("EXEC_REPRICE_PCT", "0.002"))
EXEC_SPREAD_WIDEN_PCT = float(os.getenv("EXEC_SPREAD_WIDEN_PCT", "0.5"))
EXEC_MAX_SPREAD_PCT = float(os.getenv("EXEC_MAX_SPREAD_PCT", "0.015"))
EXEC_FILL_PROB = float(os.getenv("EXEC_FILL_PROB", "0.85"))
EXEC_ALPHA_SPREAD_MULT = float(os.getenv("EXEC_ALPHA_SPREAD_MULT", "0.6"))
EXEC_ALPHA_VOL_Z_BPS = float(os.getenv("EXEC_ALPHA_VOL_Z_BPS", "3.0"))
EXEC_ALPHA_IMBALANCE_BPS = float(os.getenv("EXEC_ALPHA_IMBALANCE_BPS", "2.0"))
EXEC_ALPHA_MAX_BUFFER_PCT = float(os.getenv("EXEC_ALPHA_MAX_BUFFER_PCT", "0.01"))
EXEC_QUALITY_MIN = float(os.getenv("EXEC_QUALITY_MIN", "55"))
EXEC_QUALITY_BLOCK_BELOW = float(os.getenv("EXEC_QUALITY_BLOCK_BELOW", "35"))
EXEC_QUALITY_PENALTY = float(os.getenv("EXEC_QUALITY_PENALTY", "10"))

# -------------------------------
# Greeks / Pricing
# -------------------------------
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.06"))
# Day type thresholds
DAYTYPE_VWAP_DIST = float(os.getenv("DAYTYPE_VWAP_DIST", "0.002"))
DAYTYPE_LOCK_MIN = int(os.getenv("DAYTYPE_LOCK_MIN", "60"))
DAYTYPE_LOCK_ENABLE = os.getenv("DAYTYPE_LOCK_ENABLE", "true").lower() == "true"
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
ORB_NEUTRAL_ALLOW = os.getenv("ORB_NEUTRAL_ALLOW", "false").lower() == "true"
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
