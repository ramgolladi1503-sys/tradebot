# config/config.py

# -------------------------------
# Env loader (optional)
# -------------------------------
import os
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

# -------------------------------
# Capital & Risk Configuration
# -------------------------------
CAPITAL = 100000
MAX_RISK_PER_TRADE = 0.03   # 3% default (adjust 2-5% as desired)
MAX_DAILY_LOSS = 0.15       # 15% daily loss cap
MAX_TRADES_PER_DAY = 5
MAX_RISK_PER_TRADE_EQ = 0.02
MAX_RISK_PER_TRADE_FUT = 0.03
MAX_RISK_PER_TRADE_OPT = 0.03

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
MIN_RR = float(os.getenv("MIN_RR", "1.5"))
MIN_RR_QUICK = float(os.getenv("MIN_RR_QUICK", "1.2"))
OPT_STOP_ATR_MAIN = float(os.getenv("OPT_STOP_ATR_MAIN", "1.0"))
OPT_TARGET_ATR_MAIN = float(os.getenv("OPT_TARGET_ATR_MAIN", "1.8"))
OPT_STOP_ATR_QUICK = float(os.getenv("OPT_STOP_ATR_QUICK", "0.8"))
OPT_TARGET_ATR_QUICK = float(os.getenv("OPT_TARGET_ATR_QUICK", "1.5"))
REQUIRE_LIVE_OPTION_QUOTES = os.getenv("REQUIRE_LIVE_OPTION_QUOTES", "false").lower() == "true"
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
RELAX_BLOCK_REASON = os.getenv("RELAX_BLOCK_REASON", "")
BLOCKED_TRACK_ENABLE = os.getenv("BLOCKED_TRACK_ENABLE", "true").lower() == "true"
BLOCKED_TRACK_SECONDS = int(os.getenv("BLOCKED_TRACK_SECONDS", "3600"))
BLOCKED_TRACK_POLL_SEC = int(os.getenv("BLOCKED_TRACK_POLL_SEC", "15"))
BLOCKED_TRAIN_MIN = int(os.getenv("BLOCKED_TRAIN_MIN", "20"))
BLOCKED_TRAIN_ENABLE = os.getenv("BLOCKED_TRAIN_ENABLE", "true").lower() == "true"
BLOCKED_TRAIN_WEIGHT = float(os.getenv("BLOCKED_TRAIN_WEIGHT", "0.5"))
BLOCKED_ML_MODEL_PATH = os.getenv("BLOCKED_ML_MODEL_PATH", "models/xgb_blocked_model.pkl")
LTP_MOM_ATR_MULT = 0.2
ALLOW_BASELINE_SIGNAL = True
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
USE_DEEP_MODEL = os.getenv("USE_DEEP_MODEL", "false").lower() == "true"
DEEP_MODEL_PATH = "models/lstm_options_model.h5"
DEEP_SEQUENCE_LEN = 20
USE_MICRO_MODEL = os.getenv("USE_MICRO_MODEL", "false").lower() == "true"
MICRO_MODEL_PATH = "models/microstructure_model.h5"
ML_MIN_TRAIN_TRADES = 200
ML_USE_ONLY_WITH_HISTORY = True

# Manual approval
MANUAL_APPROVAL = os.getenv("MANUAL_APPROVAL", "true").lower() == "true"

# Storage
TRADE_DB_PATH = "data/trades.db"

# Risk governance / scorecard
DAILY_LOSS_LIMIT = CAPITAL * MAX_DAILY_LOSS
PORTFOLIO_MAX_DRAWDOWN = -0.2
RISK_HALT_FILE = "logs/risk_halt.json"
LOG_LOCK_FILE = "logs/trade_log.lock"
APPEND_ONLY_LOG = True

# Data QC / SLA thresholds
QC_MAX_NULL_RATE = 0.1
SLA_MAX_TICK_LAG_SEC = 120
SLA_MAX_DEPTH_LAG_SEC = 120
SLA_MIN_TICKS_PER_HOUR = 1000
SLA_MIN_DEPTH_PER_HOUR = 200
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
LIVE_QUOTE_ERROR_TTL_SEC = int(os.getenv("LIVE_QUOTE_ERROR_TTL_SEC", "300"))
ALLOW_STALE_LTP = os.getenv("ALLOW_STALE_LTP", "true").lower() == "true"
LTP_CACHE_TTL_SEC = int(os.getenv("LTP_CACHE_TTL_SEC", "300"))
FORCE_SYNTH_CHAIN_ON_FAIL = os.getenv("FORCE_SYNTH_CHAIN_ON_FAIL", "true").lower() == "true"
ALLOW_CLOSE_FALLBACK = os.getenv("ALLOW_CLOSE_FALLBACK", "true").lower() == "true"
QUEUE_ROW_MAX_AGE_MIN = int(os.getenv("QUEUE_ROW_MAX_AGE_MIN", "120"))
ENTRY_MISMATCH_PCT = float(os.getenv("ENTRY_MISMATCH_PCT", "0.25"))
KITE_RATE_LIMIT_SLEEP = float(os.getenv("KITE_RATE_LIMIT_SLEEP", "0.35"))
KITE_TRADES_SYNC = os.getenv("KITE_TRADES_SYNC", "true").lower() == "true"
KITE_INSTRUMENTS_TTL = int(os.getenv("KITE_INSTRUMENTS_TTL", "3600"))
KITE_USE_DEPTH = os.getenv("KITE_USE_DEPTH", "true").lower() == "true"
KITE_STORE_TICKS = os.getenv("KITE_STORE_TICKS", "true").lower() == "true"

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
