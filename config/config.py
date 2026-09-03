# config/config.py
# Migration note:
# Added market-context/depth-policy config keys for deterministic LIVE vs OFFHOURS behavior.

# -------------------------------
# Env loader (optional)
# -------------------------------
import os
import json
import csv
import logging
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


logger = logging.getLogger(__name__)


def _float_env(name: str, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default

DATA_ROOT = os.getenv("DATA_ROOT", str(_DATA_ROOT))
DESKS_ROOT = os.getenv("DESKS_ROOT", str(_DESKS_ROOT))
LOGS_ROOT = os.getenv("LOGS_ROOT", str(_LOGS_ROOT))
REPORTS_ROOT = os.getenv("REPORTS_ROOT", str(_REPORTS_ROOT))
LOCKS_ROOT = os.getenv("LOCKS_ROOT", str(_LOCKS_ROOT))
DB_ROOT = os.getenv("DB_ROOT", str(_DB_ROOT))
TB_LOG_ROTATE_MAX_MB = int(os.getenv("TB_LOG_ROTATE_MAX_MB", "20"))
TB_LOG_ROTATE_BACKUPS = int(os.getenv("TB_LOG_ROTATE_BACKUPS", "3"))
TB_LOG_RETENTION_DAYS = int(os.getenv("TB_LOG_RETENTION_DAYS", "7"))
TB_DB_RETENTION_DAYS = int(os.getenv("TB_DB_RETENTION_DAYS", "3"))
TB_COMPRESS_LOGS_AFTER_DAYS = int(os.getenv("TB_COMPRESS_LOGS_AFTER_DAYS", "1"))
TB_FORCE_COMPRESS_LARGE_LOG_MB = int(os.getenv("TB_FORCE_COMPRESS_LARGE_LOG_MB", "20"))

# -------------------------------
# Pipeline observability
# -------------------------------
PIPELINE_OBSERVABILITY_ENABLE = os.getenv("PIPELINE_OBSERVABILITY_ENABLE", "true").lower() == "true"
PIPELINE_OBSERVABILITY_SCHEMA_VERSION = int(os.getenv("PIPELINE_OBSERVABILITY_SCHEMA_VERSION", "1"))

# -------------------------------
# Dashboard runtime metrics
# -------------------------------
DASHBOARD_RUNTIME_METRICS_ENABLE = os.getenv("DASHBOARD_RUNTIME_METRICS_ENABLE", "true").lower() == "true"
DASHBOARD_RUNTIME_METRICS_MAX_ROWS = int(os.getenv("DASHBOARD_RUNTIME_METRICS_MAX_ROWS", "5000"))
DASHBOARD_RUNTIME_METRICS_CYCLE_LIMIT = int(os.getenv("DASHBOARD_RUNTIME_METRICS_CYCLE_LIMIT", "20"))

# -------------------------------
# Offline executable-shadow reporting
# -------------------------------
EXECUTABLE_SHADOW_PORTFOLIO_ENABLE = os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_ENABLE", "true").lower() == "true"
EXECUTABLE_SHADOW_PORTFOLIO_REPORT_DIR = os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_REPORT_DIR", "")
EXECUTABLE_SHADOW_PORTFOLIO_LOOKAHEAD_MINUTES = int(os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_LOOKAHEAD_MINUTES", "30"))
EXECUTABLE_SHADOW_PORTFOLIO_INTERVAL = os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_INTERVAL", "minute")
EXECUTABLE_SHADOW_PORTFOLIO_ENTRY_MODE = os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_ENTRY_MODE", "SIDE_QUOTE")
EXECUTABLE_SHADOW_PORTFOLIO_SLIPPAGE_MODEL = os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_SLIPPAGE_MODEL", "spread").lower()
EXECUTABLE_SHADOW_PORTFOLIO_SLIPPAGE_BPS = float(os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_SLIPPAGE_BPS", "0.0"))
EXECUTABLE_SHADOW_PORTFOLIO_SPREAD_SLIPPAGE_MULT = float(os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_SPREAD_SLIPPAGE_MULT", "0.5"))
EXECUTABLE_SHADOW_PORTFOLIO_STARTING_EQUITY = float(os.getenv("EXECUTABLE_SHADOW_PORTFOLIO_STARTING_EQUITY", "100000.0"))
DAILY_REPORT_INCLUDE_EXECUTABLE_SHADOW = os.getenv("DAILY_REPORT_INCLUDE_EXECUTABLE_SHADOW", "true").lower() == "true"

# -------------------------------
# Offline option-symbol backtest
# -------------------------------
OPTION_SYMBOL_BACKTEST_ENABLE = os.getenv("OPTION_SYMBOL_BACKTEST_ENABLE", "true").lower() == "true"
OPTION_SYMBOL_BACKTEST_TIMEZONE = os.getenv("OPTION_SYMBOL_BACKTEST_TIMEZONE", "Asia/Kolkata")
OPTION_SYMBOL_BACKTEST_REQUIRE_BID_ASK = os.getenv("OPTION_SYMBOL_BACKTEST_REQUIRE_BID_ASK", "true").lower() == "true"
OPTION_SYMBOL_BACKTEST_ALLOW_DERIVED_LEVELS = os.getenv("OPTION_SYMBOL_BACKTEST_ALLOW_DERIVED_LEVELS", "true").lower() == "true"
OPTION_SYMBOL_BACKTEST_DERIVED_STOP_PCT = float(os.getenv("OPTION_SYMBOL_BACKTEST_DERIVED_STOP_PCT", "0.12"))
OPTION_SYMBOL_BACKTEST_DERIVED_TARGET_RR = float(os.getenv("OPTION_SYMBOL_BACKTEST_DERIVED_TARGET_RR", "1.5"))
OPTION_SYMBOL_BACKTEST_MAX_HOLD_MINUTES = int(os.getenv("OPTION_SYMBOL_BACKTEST_MAX_HOLD_MINUTES", "30"))
OPTION_SYMBOL_BACKTEST_DEFAULT_QTY = int(os.getenv("OPTION_SYMBOL_BACKTEST_DEFAULT_QTY", "1"))
OPTION_SYMBOL_BACKTEST_OUTPUT_DIR = os.getenv("OPTION_SYMBOL_BACKTEST_OUTPUT_DIR", "")
OPTION_SYMBOL_BACKTEST_FILL_RUN_ID = os.getenv("OPTION_SYMBOL_BACKTEST_FILL_RUN_ID", "option_backtest")
OPTION_SYMBOL_BACKTEST_EXPORT_DB_PATH = os.getenv("OPTION_SYMBOL_BACKTEST_EXPORT_DB_PATH", str(Path(DB_ROOT) / "DEFAULT.sqlite"))
OPTION_SYMBOL_BACKTEST_EXPORT_OUTPUT_DIR = os.getenv("OPTION_SYMBOL_BACKTEST_EXPORT_OUTPUT_DIR", str(Path(DATA_ROOT) / "backtest"))
OPTION_SYMBOL_BACKTEST_EXPORT_CHAIN_PATH = os.getenv("OPTION_SYMBOL_BACKTEST_EXPORT_CHAIN_PATH", ".runtime/option_chain_latest.json")
OPTION_SYMBOL_BACKTEST_EXPORT_INSTRUMENTS_PATH = os.getenv("OPTION_SYMBOL_BACKTEST_EXPORT_INSTRUMENTS_PATH", str(Path(DATA_ROOT) / "kite_instruments.json"))

# -------------------------------
# Kite / broker API credentials
# -------------------------------
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")
KITE_ACCESS_TOKEN = ""

# -------------------------------
# Feed recovery stability
# -------------------------------
DEPTH_WS_RECOVERY_TIMEOUT_SEC = float(os.getenv("DEPTH_WS_RECOVERY_TIMEOUT_SEC", "90"))
DEPTH_WS_MAX_RECOVERIES_PER_WINDOW = int(os.getenv("DEPTH_WS_MAX_RECOVERIES_PER_WINDOW", "3"))
DEPTH_WS_RECOVERY_WINDOW_SEC = float(os.getenv("DEPTH_WS_RECOVERY_WINDOW_SEC", "3600.0"))
TOKEN_RECOVERY_MAX_ATTEMPTS = int(os.getenv("TOKEN_RECOVERY_MAX_ATTEMPTS", "3"))
TOKEN_RECOVERY_COOLDOWN_SEC = float(os.getenv("TOKEN_RECOVERY_COOLDOWN_SEC", "10.0"))
TOKEN_RECOVERY_VERIFY_TIMEOUT_SEC = float(os.getenv("TOKEN_RECOVERY_VERIFY_TIMEOUT_SEC", "15.0"))
RECOVERY_STABLE_CYCLES = int(os.getenv("RECOVERY_STABLE_CYCLES", "3"))
CORE_FEED_FRESH_QUORUM = float(os.getenv("CORE_FEED_FRESH_QUORUM", "0.95"))

# -------------------------------
# Telegram bot credentials
# -------------------------------
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "true").lower() == "true"

# ----------------------------------------------------
# V2 Opportunity Pipeline (Phase 1 only, legacy default)
# Only the candidate generator is active in Phase 1.
# Future phase flags will be added later and are
# intentionally omitted here to avoid false signals.
# ----------------------------------------------------
ENABLE_CANDIDATE_GENERATOR_V2 = os.getenv("ENABLE_CANDIDATE_GENERATOR_V2", "false").lower() == "true"
ENABLE_PRO_STRATEGY_LAYER = os.getenv("ENABLE_PRO_STRATEGY_LAYER", "false").lower() == "true"
ENABLE_PRO_STRATEGY_SHADOW = os.getenv("ENABLE_PRO_STRATEGY_SHADOW", "false").lower() == "true"
PRO_STRATEGY_LAYER_STRICT_MODE = os.getenv("PRO_STRATEGY_LAYER_STRICT_MODE", "true").lower() == "true"
PRO_STRATEGY_SHADOW_THREAD_TTL_SEC = _float_env("PRO_STRATEGY_SHADOW_THREAD_TTL_SEC", 30.0)
PRO_STRATEGY_SHADOW_WORKER_TTL_SEC = _float_env(
    "PRO_STRATEGY_SHADOW_WORKER_TTL_SEC",
    PRO_STRATEGY_SHADOW_THREAD_TTL_SEC,
)

# Candidate generator v2 defaults (shadow mode only).
V2_CANDIDATE_SYMBOLS = os.getenv("V2_CANDIDATE_SYMBOLS", "NIFTY,BANKNIFTY")
V2_CANDIDATE_STRIKE_WINDOW = int(os.getenv("V2_CANDIDATE_STRIKE_WINDOW", "2"))
V2_CANDIDATE_STRATEGY_FAMILIES = os.getenv(
    "V2_CANDIDATE_STRATEGY_FAMILIES",
    "breakout,mean_reversion,volatility_expansion,expiry_momentum",
)
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
    "CONSERVATIVE": {
        "MAX_DAILY_LOSS_PCT": float(os.getenv("CONSERVATIVE_MAX_DAILY_LOSS_PCT", "0.012")),
        "MAX_DRAWDOWN_PCT": float(os.getenv("CONSERVATIVE_MAX_DRAWDOWN_PCT", "-0.03")),
        "MAX_RISK_PER_TRADE_PCT": float(os.getenv("CONSERVATIVE_MAX_RISK_PER_TRADE_PCT", "0.0025")),
        "MAX_OPEN_RISK_PCT": float(os.getenv("CONSERVATIVE_MAX_OPEN_RISK_PCT", "0.01")),
        "MAX_TRADES_PER_DAY": int(os.getenv("CONSERVATIVE_MAX_TRADES_PER_DAY", "2")),
        "LOSS_STREAK_DOWNSIZE": int(os.getenv("CONSERVATIVE_LOSS_STREAK_DOWNSIZE", "2")),
        "EVENT_REGIME_RISK_MULT": float(os.getenv("CONSERVATIVE_EVENT_REGIME_RISK_MULT", "0.45")),
        "HIGH_ENTROPY_RISK_MULT": float(os.getenv("CONSERVATIVE_HIGH_ENTROPY_RISK_MULT", "0.5")),
        "RECOVERY_MODE_MULT": float(os.getenv("CONSERVATIVE_RECOVERY_MODE_MULT", "0.35")),
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
if RISK_PROFILE == "CONSERVATIVE":
    if _active_risk_limits["MAX_DAILY_LOSS_PCT"] > 0.012:
        _active_risk_limits["MAX_DAILY_LOSS_PCT"] = 0.012
    if abs(float(_active_risk_limits["MAX_DRAWDOWN_PCT"])) > 0.03:
        _active_risk_limits["MAX_DRAWDOWN_PCT"] = -0.03
    if _active_risk_limits["MAX_RISK_PER_TRADE_PCT"] > 0.0025:
        _active_risk_limits["MAX_RISK_PER_TRADE_PCT"] = 0.0025
    if _active_risk_limits["MAX_OPEN_RISK_PCT"] > 0.01:
        _active_risk_limits["MAX_OPEN_RISK_PCT"] = 0.01
    if _active_risk_limits["MAX_TRADES_PER_DAY"] > 2:
        _active_risk_limits["MAX_TRADES_PER_DAY"] = 2
MAX_DAILY_LOSS_PCT = float(_active_risk_limits["MAX_DAILY_LOSS_PCT"])
MAX_DRAWDOWN_PCT = float(_active_risk_limits["MAX_DRAWDOWN_PCT"])
MAX_RISK_PER_TRADE_PCT = float(_active_risk_limits["MAX_RISK_PER_TRADE_PCT"])
MAX_OPEN_RISK_PCT = float(_active_risk_limits["MAX_OPEN_RISK_PCT"])
MAX_TRADES_PER_DAY = int(_active_risk_limits["MAX_TRADES_PER_DAY"])
LOSS_STREAK_DOWNSIZE = int(_active_risk_limits["LOSS_STREAK_DOWNSIZE"])
EVENT_REGIME_RISK_MULT = float(_active_risk_limits["EVENT_REGIME_RISK_MULT"])
HIGH_ENTROPY_RISK_MULT = float(_active_risk_limits["HIGH_ENTROPY_RISK_MULT"])
RECOVERY_MODE_MULT = float(_active_risk_limits["RECOVERY_MODE_MULT"])
CONSERVATIVE_PROFIT_CAPTURE_ENABLE = os.getenv(
    "CONSERVATIVE_PROFIT_CAPTURE_ENABLE",
    "true" if RISK_PROFILE == "CONSERVATIVE" else "false",
).lower() == "true"
CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_TRIGGER_PCT = float(
    os.getenv("CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_TRIGGER_PCT", "0.006")
)
CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_DRAWDOWN_PCT = float(
    os.getenv("CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_DRAWDOWN_PCT", "-0.01")
)
CONSERVATIVE_PROFIT_CAPTURE_RISK_MULT = float(
    os.getenv("CONSERVATIVE_PROFIT_CAPTURE_RISK_MULT", "0.5")
)
CONSERVATIVE_PROFIT_CAPTURE_SOFT_HALT_FRACTION = float(
    os.getenv("CONSERVATIVE_PROFIT_CAPTURE_SOFT_HALT_FRACTION", "0.55")
)
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
LIVE_STRATEGY_PERF_SHADOW_FALLBACK_ENABLE = os.getenv(
    "LIVE_STRATEGY_PERF_SHADOW_FALLBACK_ENABLE",
    "true",
).lower() == "true"
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
ARMING_REQUIRE_HEALTH_PASS_RECENT = os.getenv("ARMING_REQUIRE_HEALTH_PASS_RECENT", "true").lower() == "true"
ARMING_HEALTH_PASS_MAX_AGE_SEC = float(os.getenv("ARMING_HEALTH_PASS_MAX_AGE_SEC", "1800"))
ARMING_P0_COOLDOWN_SEC = float(os.getenv("ARMING_P0_COOLDOWN_SEC", "1800"))
ARMING_CONFIRM_PHRASE = str(os.getenv("ARMING_CONFIRM_PHRASE", "YES I UNDERSTAND"))
ARMING_COOLDOWN_STATE_PATH = os.getenv("ARMING_COOLDOWN_STATE_PATH", f"{LOGS_ROOT}/arming_cooldown.json")
CONFIG_APPROVAL_ENFORCE_ON_ARM = os.getenv("CONFIG_APPROVAL_ENFORCE_ON_ARM", "true").lower() == "true"
CONFIG_APPROVAL_PATH = os.getenv("CONFIG_APPROVAL_PATH", f"{LOGS_ROOT}/approved_config.json")
CONFIG_APPROVAL_KEY_FILES = os.getenv(
    "CONFIG_APPROVAL_KEY_FILES",
    "config/config.py,config/profile.py,core/freshness_policy.py,core/readiness_gate.py,core/gating.py",
)
# Survival gates (execution guard fail-closed clamps).
SURVIVAL_GATES_ENABLED = os.getenv("SURVIVAL_GATES_ENABLED", "true").lower() == "true"
MAX_DAILY_DRAWDOWN = float(os.getenv("MAX_DAILY_DRAWDOWN", "-0.03"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
VOLATILITY_SIZING_MULTIPLIER = float(os.getenv("VOLATILITY_SIZING_MULTIPLIER", "0.50"))
SURVIVAL_VOLATILITY_TRIGGER_PCT = float(os.getenv("SURVIVAL_VOLATILITY_TRIGGER_PCT", "0.01"))
SURVIVAL_HALT_ENTRIES_ON_BREACH = os.getenv("SURVIVAL_HALT_ENTRIES_ON_BREACH", "true").lower() == "true"
AUTO_FLATTEN_ON_BREACH = os.getenv("AUTO_FLATTEN_ON_BREACH", "false").lower() == "true"
SURVIVAL_BREACH_COOLDOWN_SEC = float(os.getenv("SURVIVAL_BREACH_COOLDOWN_SEC", "60"))
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
OPTION_TICK_SOFT_STALE_SEC = float(os.getenv("OPTION_TICK_SOFT_STALE_SEC", "3.0"))
OPTION_TICK_HARD_STALE_SEC = float(os.getenv("OPTION_TICK_HARD_STALE_SEC", "6.0"))
OPTION_ENTRY_MISMATCH_PCT = float(os.getenv("OPTION_ENTRY_MISMATCH_PCT", "0.03"))
OPTION_ENTRY_REQUIRE_LIVE = os.getenv("OPTION_ENTRY_REQUIRE_LIVE", "true").lower() == "true"
EXECUTION_ENTRY_ALLOW_LAST_FALLBACK = os.getenv("EXECUTION_ENTRY_ALLOW_LAST_FALLBACK", "true").lower() == "true"
EXECUTION_ENTRY_RECOVERY_ENABLE = os.getenv("EXECUTION_ENTRY_RECOVERY_ENABLE", "true").lower() == "true"
EXECUTION_ENTRY_TRACE_ENABLE = os.getenv("EXECUTION_ENTRY_TRACE_ENABLE", "true").lower() == "true"
EXECUTION_ENTRY_TRACE_PATH = os.getenv("EXECUTION_ENTRY_TRACE_PATH", "")
PERMISSION_PROMOTION_ENABLE = os.getenv("PERMISSION_PROMOTION_ENABLE", "true").lower() == "true"
PERMISSION_PROMOTION_MIN_CONF = float(os.getenv("PERMISSION_PROMOTION_MIN_CONF", "0.72"))
PERMISSION_PROMOTION_STRONG_CONF = float(os.getenv("PERMISSION_PROMOTION_STRONG_CONF", "0.80"))
PERMISSION_PROMOTION_MIN_RAW_RANK = float(os.getenv("PERMISSION_PROMOTION_MIN_RAW_RANK", "0.35"))
PERMISSION_PROMOTION_TOP_RANK_MAX = int(os.getenv("PERMISSION_PROMOTION_TOP_RANK_MAX", "2"))
PERMISSION_PROMOTION_TRACE_PATH = os.getenv("PERMISSION_PROMOTION_TRACE_PATH", "")

# Decision engine scoring controls
DECISION_ENGINE_ENABLE = os.getenv("DECISION_ENGINE_ENABLE", "true").lower() == "true"
DECISION_ENGINE_EXECUTE_MIN_SCORE = float(
    os.getenv("DECISION_ENGINE_EXECUTE_MIN_SCORE", "0.70")
)
DECISION_ENGINE_QUEUE_MIN_SCORE = float(
    os.getenv("DECISION_ENGINE_QUEUE_MIN_SCORE", "0.55")
)
DECISION_ENGINE_WEAK_SIGNAL_EXECUTE_ENABLE = (
    os.getenv("DECISION_ENGINE_WEAK_SIGNAL_EXECUTE_ENABLE", "false").lower() == "true"
)
DECISION_ENGINE_SOFT_REJECT_EXECUTE_BLOCK_ENABLE = (
    os.getenv("DECISION_ENGINE_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", "false").lower()
    == "true"
)
DECISION_ENGINE_HARD_EXECUTION_QUALITY_REASONS = tuple(
    code.strip().lower()
    for code in os.getenv(
        "DECISION_ENGINE_HARD_EXECUTION_QUALITY_REASONS",
        "data_not_live,fallback_driven_data,missing_quote,spread_breached",
    ).split(",")
    if code.strip()
)
DECISION_ENGINE_SOFT_EXECUTION_QUALITY_REASONS = tuple(
    code.strip().lower()
    for code in os.getenv(
        "DECISION_ENGINE_SOFT_EXECUTION_QUALITY_REASONS",
        "stale_quote,inconsistent_quote,low_data_confidence,unverified_spread,missing_liquidity_validation",
    ).split(",")
    if code.strip()
)
DECISION_ENGINE_FEED_INVALID_MAX = float(
    os.getenv("DECISION_ENGINE_FEED_INVALID_MAX", "0.50")
)
DECISION_ENGINE_FEED_DEGRADED_MAX = float(
    os.getenv("DECISION_ENGINE_FEED_DEGRADED_MAX", "0.75")
)
# Safety default: decision paths must read ticks from SQLite, not process memory cache.
DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS = (
    os.getenv("DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", "true").lower() == "true"
)

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
PREMARKET_START_IST = os.getenv("PREMARKET_START_IST", "09:00")
MARKET_OPEN_IST = os.getenv("MARKET_OPEN_IST", "09:15")
MARKET_CLOSE_IST = os.getenv("MARKET_CLOSE_IST", "15:30")
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
QUOTE_SPLIT_BRAIN_LOG_RATE_LIMIT_SEC = float(os.getenv("QUOTE_SPLIT_BRAIN_LOG_RATE_LIMIT_SEC", "60"))
PHASE2_CAP_LIQUIDITY_WITH_QUOTE_CONSISTENCY = (
    os.getenv("PHASE2_CAP_LIQUIDITY_WITH_QUOTE_CONSISTENCY", "true").lower() == "true"
)
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
TRADE_BUILDER_ENFORCE_STRIKE_LADDER = os.getenv("TRADE_BUILDER_ENFORCE_STRIKE_LADDER", "false").lower() == "true"
TRADE_BUILDER_STRIKE_LADDER_WIDTH = int(os.getenv("TRADE_BUILDER_STRIKE_LADDER_WIDTH", "2"))
TRADE_BUILDER_EXPIRY_BUCKET_MODE = os.getenv("TRADE_BUILDER_EXPIRY_BUCKET_MODE", "ALL").strip().upper()
# Expiry weekdays by symbol (0=Mon ... 6=Sun)
EXPIRY_WEEKDAY_BY_SYMBOL = {
    "NIFTY": int(os.getenv("NIFTY_EXPIRY_WEEKDAY", "1")),         # Tue (NSE weekly)
    "BANKNIFTY": int(os.getenv("BANKNIFTY_EXPIRY_WEEKDAY", "1")), # Tue (NSE weekly)
    "SENSEX": int(os.getenv("SENSEX_EXPIRY_WEEKDAY", "3")),       # Thu (BSE weekly)
}

# -------------------------------
# Trade configuration
# -------------------------------
MIN_PREMIUM = 5           # Fallback minimum option premium when symbol-specific band is unavailable
MAX_PREMIUM = 700         # Fallback maximum option premium when symbol-specific band is unavailable
PREMIUM_BANDS = {
    "NIFTY": (5, 400),
    "BANKNIFTY": (20, 1800),
    "SENSEX": (10, 1200),
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
DEPTH_PERSIST_QUEUE_MAXSIZE = int(
    os.getenv("DEPTH_PERSIST_QUEUE_MAXSIZE", "16384")
)
DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC = float(
    os.getenv("DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", "1.0")
)
DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC = float(
    os.getenv("DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", "0.50")
)
DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC = float(
    os.getenv("DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC", "10.0")
)
DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS = int(
    os.getenv("DEPTH_SNAPSHOT_DB_WRITE_RETRY_ATTEMPTS", "5")
)
DEPTH_SNAPSHOT_DB_WRITE_RETRY_BACKOFF_SEC = float(
    os.getenv("DEPTH_SNAPSHOT_DB_WRITE_RETRY_BACKOFF_SEC", "0.1")
)
DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE = (
    os.getenv("DEPTH_SNAPSHOT_DB_LOCK_SKIP_ENABLE", "true").lower() == "true"
)
DEPTH_SNAPSHOT_DB_LOCK_MAX_WARN_EVERY_SEC = float(
    os.getenv("DEPTH_SNAPSHOT_DB_LOCK_MAX_WARN_EVERY_SEC", "30.0")
)
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
UI_LIVE_SNAPSHOT_MAX_AGE_SEC = float(os.getenv("UI_LIVE_SNAPSHOT_MAX_AGE_SEC", "120"))
UI_LIVE_ROW_REQUIRE_TODAY = os.getenv("UI_LIVE_ROW_REQUIRE_TODAY", "true").lower() == "true"
UI_STATE_ENGINE_REFRESH_SEC = float(os.getenv("UI_STATE_ENGINE_REFRESH_SEC", "5.0"))
UI_RUNTIME_HEALTH_MAX_AGE_SEC = float(os.getenv("UI_RUNTIME_HEALTH_MAX_AGE_SEC", "120"))
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
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "SENSEX": 20
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
TRADE_BUILDER_RAW_CONFIDENCE_MIN = float(
    os.getenv("TRADE_BUILDER_RAW_CONFIDENCE_MIN", str(ML_MIN_PROBA))
)
TRADE_BUILDER_RAW_CONFIDENCE_MIN_DEFAULT = float(ML_MIN_PROBA)
ML_FULL_SIZE_PROBA = float(os.getenv("ML_FULL_SIZE_PROBA", "0.70"))
CONFIDENCE_MIN = float(os.getenv("CONFIDENCE_MIN", "0.55"))
CONFIDENCE_FULL = float(os.getenv("CONFIDENCE_FULL", "0.80"))
CONFIDENCE_THRESHOLD_DISPLAY = float(os.getenv("CONFIDENCE_THRESHOLD_DISPLAY", "0.0"))
CONFIDENCE_THRESHOLD_ADVISORY = float(os.getenv("CONFIDENCE_THRESHOLD_ADVISORY", "0.15"))
CONFIDENCE_THRESHOLD_EXECUTION_LIVE = float(os.getenv("CONFIDENCE_THRESHOLD_EXECUTION_LIVE", "0.30"))
CONFIDENCE_THRESHOLD_EXECUTION_PAPER = float(os.getenv("CONFIDENCE_THRESHOLD_EXECUTION_PAPER", "0.27"))
CONFIDENCE_THRESHOLD_EXECUTION_SIM = float(
    os.getenv("CONFIDENCE_THRESHOLD_EXECUTION_SIM", str(CONFIDENCE_THRESHOLD_EXECUTION_PAPER))
)
GATING_HARD_MAX_TICK_AGE_SEC = float(os.getenv("GATING_HARD_MAX_TICK_AGE_SEC", str(OPTION_LTP_SLA_SEC)))
GATING_HARD_MAX_SPREAD_PCT = float(os.getenv("GATING_HARD_MAX_SPREAD_PCT", str(MAX_SPREAD_PCT)))
GATING_HARD_MIN_VOLUME = float(os.getenv("GATING_HARD_MIN_VOLUME", str(MIN_VOLUME_FILTER)))
GATING_SOFT_PENALTY_FEED_STATE = float(os.getenv("GATING_SOFT_PENALTY_FEED_STATE", "0.05"))
GATING_SOFT_PENALTY_MAX_AGE = float(os.getenv("GATING_SOFT_PENALTY_MAX_AGE", "0.12"))
GATING_SOFT_PENALTY_MAX_SPREAD = float(os.getenv("GATING_SOFT_PENALTY_MAX_SPREAD", "0.10"))
GATING_SOFT_PENALTY_LOW_VOLUME = float(os.getenv("GATING_SOFT_PENALTY_LOW_VOLUME", "0.06"))
GATING_RELAX_NON_LIVE_HARD_GATES = os.getenv("GATING_RELAX_NON_LIVE_HARD_GATES", "true").lower() == "true"
GATING_RELAX_NON_LIVE_SOFT_CODES = tuple(
    code.strip().upper()
    for code in os.getenv(
        "GATING_RELAX_NON_LIVE_SOFT_CODES",
        "HARD_STALE_LTP,HARD_MISSING_VOLUME",
    ).split(",")
    if code.strip()
)
GATING_RELAX_NON_LIVE_WARNING_CODES = tuple(
    code.strip().upper()
    for code in os.getenv(
        "GATING_RELAX_NON_LIVE_WARNING_CODES",
        "HARD_NO_LTP,HARD_MISSING_TICK_AGE",
    ).split(",")
    if code.strip()
)
GATING_RELAX_NON_LIVE_SOFT_PENALTY = float(os.getenv("GATING_RELAX_NON_LIVE_SOFT_PENALTY", "0.05"))
GATING_FINAL_CONFIDENCE_MIN = float(
    os.getenv("GATING_FINAL_CONFIDENCE_MIN", str(CONFIDENCE_THRESHOLD_EXECUTION_LIVE))
)
TRADE_BUILDER_FINAL_CONFIDENCE_MIN = float(
    os.getenv("TRADE_BUILDER_FINAL_CONFIDENCE_MIN", str(GATING_FINAL_CONFIDENCE_MIN))
)
TRADE_BUILDER_FINAL_CONFIDENCE_MIN_DEFAULT = float(GATING_FINAL_CONFIDENCE_MIN)
EXECUTION_GUARD_FINAL_CONFIDENCE_MIN = float(
    os.getenv("EXECUTION_GUARD_FINAL_CONFIDENCE_MIN", str(TRADE_BUILDER_FINAL_CONFIDENCE_MIN))
)
EXECUTION_GUARD_FINAL_CONFIDENCE_MIN_DEFAULT = float(TRADE_BUILDER_FINAL_CONFIDENCE_MIN)
GATING_DEFAULT_CONFIDENCE = float(os.getenv("GATING_DEFAULT_CONFIDENCE", "0.0"))
HIGH_EXECUTE_MIN_CONF = float(
    os.getenv("HIGH_EXECUTE_MIN_CONF", str(CONFIDENCE_THRESHOLD_EXECUTION_LIVE))
)
OPPORTUNITY_ENGINE_ENABLE = os.getenv("OPPORTUNITY_ENGINE_ENABLE", "true").lower() == "true"
PHASE2_ENGINE_ENABLE = os.getenv("PHASE2_ENGINE_ENABLE", "true").lower() == "true"
PHASE2_TOP_N = int(os.getenv("PHASE2_TOP_N", "5"))
PHASE2_MIN_ENTER_SCORE = float(os.getenv("PHASE2_MIN_ENTER_SCORE", "0.42"))
PHASE2_MIN_BORDERLINE_SCORE = float(os.getenv("PHASE2_MIN_BORDERLINE_SCORE", "0.32"))
PHASE2_REPLACE_MIN_ABS_DELTA = float(os.getenv("PHASE2_REPLACE_MIN_ABS_DELTA", "0.12"))
PHASE2_REPLACE_MIN_REL_DELTA = float(os.getenv("PHASE2_REPLACE_MIN_REL_DELTA", "0.20"))
PHASE2_MAX_SPREAD_PCT = float(os.getenv("PHASE2_MAX_SPREAD_PCT", str(MAX_SPREAD_PCT)))
PHASE2_MAX_SPREAD_PCT_HIGH_VOL = float(os.getenv("PHASE2_MAX_SPREAD_PCT_HIGH_VOL", "0.02"))
PHASE2_VOLATILITY_HIGH_CUTOFF = float(os.getenv("PHASE2_VOLATILITY_HIGH_CUTOFF", "0.7"))
PHASE2_MARKET_START_HOUR = int(os.getenv("PHASE2_MARKET_START_HOUR", "9"))
PHASE2_MARKET_END_HOUR = int(os.getenv("PHASE2_MARKET_END_HOUR", "15"))
PHASE2_SPREAD_OFFHOURS_MULT = float(os.getenv("PHASE2_SPREAD_OFFHOURS_MULT", "1.5"))
PHASE2_MIN_EXECUTION_SCORE = float(os.getenv("PHASE2_MIN_EXECUTION_SCORE", "0.50"))
PHASE2_MIN_EXECUTION_QUALITY_SCORE = float(
    os.getenv("PHASE2_MIN_EXECUTION_QUALITY_SCORE", "0.30")
)
PHASE2_MIN_LIQUIDITY_SCORE = float(os.getenv("PHASE2_MIN_LIQUIDITY_SCORE", "0.35"))
PHASE2_LIQUIDITY_SOFT_PENALTY = float(os.getenv("PHASE2_LIQUIDITY_SOFT_PENALTY", "0.08"))
PHASE2_SOFT_EXECUTION_DEGRADE_PENALTY = float(
    os.getenv("PHASE2_SOFT_EXECUTION_DEGRADE_PENALTY", "0.10")
)
PHASE2_SPREAD_FALLBACK_PCT = float(os.getenv("PHASE2_SPREAD_FALLBACK_PCT", "0.003"))
PHASE2_LIQUIDITY_FALLBACK_SCORE = float(
    os.getenv("PHASE2_LIQUIDITY_FALLBACK_SCORE", "0.50")
)
PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE = (
    os.getenv("PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", "true").lower() == "true"
)
PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE = (
    os.getenv("PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", "true").lower() == "true"
)
PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_FALLBACK_ENABLE = (
    os.getenv(
        "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_FALLBACK_ENABLE",
        "true",
    ).lower()
    == "true"
)
PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_MIN = float(
    os.getenv("PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_MIN", "0.50")
)
PHASE2_SOFT_EXECUTION_NOT_READY_REASON_CODES = os.getenv(
    "PHASE2_SOFT_EXECUTION_NOT_READY_REASON_CODES",
    "stale_quote,inconsistent_quote,low_data_confidence,unverified_spread,missing_liquidity_validation",
)
PHASE2_HARD_EXECUTION_NOT_READY_REASON_CODES = os.getenv(
    "PHASE2_HARD_EXECUTION_NOT_READY_REASON_CODES",
    "data_not_live,fallback_driven_data,missing_quote,spread_breached",
)
PHASE2_SOFT_REJECT_EXECUTE_BLOCK_ENABLE = (
    os.getenv("PHASE2_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", "false").lower() == "true"
)
PHASE2_WEAK_SIGNAL_QUEUE_CAP_ENABLE = (
    os.getenv("PHASE2_WEAK_SIGNAL_QUEUE_CAP_ENABLE", "false").lower() == "true"
)
PHASE2_WEAK_SIGNAL_SOFT_PENALTY = float(
    os.getenv("PHASE2_WEAK_SIGNAL_SOFT_PENALTY", "0.06")
)
PHASE2_SOFT_CONTEXT_REASON_CODES = os.getenv(
    "PHASE2_SOFT_CONTEXT_REASON_CODES",
    "missing_rr_context,rr_estimated_context,missing_liquidity_context,missing_spread_context,missing_timing_context,missing_live_timing_context,low_data_confidence,unknown_quote_source",
)
PHASE2_CRITICAL_EXECUTION_REASON_CODES = os.getenv(
    "PHASE2_CRITICAL_EXECUTION_REASON_CODES",
    "feed_stale,no_live_option_feed,unresolved_contract,missing_contract_fields,missing_option_token,no_token,missing_entry,invalid_level_geometry,hard_spread_too_wide,spread_breached,execution_quality_reject",
)
PHASE2_FILTER_DROP_DEBUG_LIMIT = int(os.getenv("PHASE2_FILTER_DROP_DEBUG_LIMIT", "25"))
PHASE2_FILTER_DROP_DEBUG_SAMPLE_LIMIT = int(os.getenv("PHASE2_FILTER_DROP_DEBUG_SAMPLE_LIMIT", "5"))
STATUS_VISIBLE_COUNTS_USE_REVIEW_QUEUE_SNAPSHOT = os.getenv(
    "STATUS_VISIBLE_COUNTS_USE_REVIEW_QUEUE_SNAPSHOT", "true"
).strip().lower() in {"1", "true", "yes", "on"}
STATUS_VISIBLE_SOURCE_MAX_AGE_SEC = float(os.getenv("STATUS_VISIBLE_SOURCE_MAX_AGE_SEC", "180"))
STATUS_ZERO_VISIBLE_COUNTS_WHEN_UNHEALTHY = os.getenv(
    "STATUS_ZERO_VISIBLE_COUNTS_WHEN_UNHEALTHY", "true"
).strip().lower() in {"1", "true", "yes", "on"}
PHASE2_INVALID_CANDIDATE_LOG_SAMPLE_LIMIT = int(os.getenv("PHASE2_INVALID_CANDIDATE_LOG_SAMPLE_LIMIT", "5"))
ORCHESTRATOR_INVALID_CYCLE_CANDIDATE_SAMPLE_LIMIT = int(
    os.getenv("ORCHESTRATOR_INVALID_CYCLE_CANDIDATE_SAMPLE_LIMIT", "5")
)
TRADE_BUILDER_INVALID_RANKED_CANDIDATE_SAMPLE_LIMIT = int(
    os.getenv("TRADE_BUILDER_INVALID_RANKED_CANDIDATE_SAMPLE_LIMIT", "5")
)
PHASE2_ACTIVE_TRADE_MAX_AGE_SEC = float(os.getenv("PHASE2_ACTIVE_TRADE_MAX_AGE_SEC", "30"))
PHASE2_RELAX_ALLOW_LIVE = os.getenv("PHASE2_RELAX_ALLOW_LIVE", "false").lower() == "true"
PHASE2_RELAX_NO_SIGNAL = os.getenv("PHASE2_RELAX_NO_SIGNAL", "true").lower() == "true"
PHASE2_DISABLE_LATENCY_BLOCK = os.getenv("PHASE2_DISABLE_LATENCY_BLOCK", "true").lower() == "true"
PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE = (
    os.getenv("PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", "false").lower() == "true"
)
PHASE2_FORCE_FALLBACK_MIN_SCORE = float(
    os.getenv("PHASE2_FORCE_FALLBACK_MIN_SCORE", "0.05")
)
PHASE2_FORCE_FALLBACK_ALLOW_LIVE = (
    os.getenv("PHASE2_FORCE_FALLBACK_ALLOW_LIVE", "false").lower() == "true"
)
PHASE2_STRICT_REAL_CANDIDATES_ONLY = (
    os.getenv("PHASE2_STRICT_REAL_CANDIDATES_ONLY", "false").lower() == "true"
)
PHASE2_STRICT_DROP_REASON_CODES = os.getenv(
    "PHASE2_STRICT_DROP_REASON_CODES",
    "weak_signal,no_signal,rr_estimated_context,missing_rr_context,missing_liquidity_context,missing_spread_context,missing_timing_context,missing_live_timing_context,unknown_quote_source,execution_context_degraded",
)
PHASE2_PLAYBOOK_SELECTION_ENABLE = (
    os.getenv("PHASE2_PLAYBOOK_SELECTION_ENABLE", "false").lower() == "true"
)
PHASE2_BREAKOUT_BUFFER_PCT = float(os.getenv("PHASE2_BREAKOUT_BUFFER_PCT", "0.001"))
PHASE2_BREAKOUT_MIN_BODY_PCT = float(os.getenv("PHASE2_BREAKOUT_MIN_BODY_PCT", "0.003"))
PHASE2_BREAKOUT_SETUP_SCORE_DEFAULT = float(
    os.getenv("PHASE2_BREAKOUT_SETUP_SCORE_DEFAULT", "0.70")
)
PHASE2_BREAKOUT_TRIGGER_SCORE_DEFAULT = float(
    os.getenv("PHASE2_BREAKOUT_TRIGGER_SCORE_DEFAULT", "0.68")
)
PHASE2_BREAKOUT_ENTRY_QUALITY_SCORE_DEFAULT = float(
    os.getenv("PHASE2_BREAKOUT_ENTRY_QUALITY_SCORE_DEFAULT", "0.66")
)
PHASE2_BREAKOUT_BUY_STOP_MULT = float(os.getenv("PHASE2_BREAKOUT_BUY_STOP_MULT", "0.88"))
PHASE2_BREAKOUT_BUY_TARGET_MULT = float(os.getenv("PHASE2_BREAKOUT_BUY_TARGET_MULT", "1.24"))
PHASE2_BREAKOUT_SELL_STOP_MULT = float(os.getenv("PHASE2_BREAKOUT_SELL_STOP_MULT", "1.12"))
PHASE2_BREAKOUT_SELL_TARGET_MULT = float(os.getenv("PHASE2_BREAKOUT_SELL_TARGET_MULT", "0.76"))
REVIEW_QUEUE_RUNTIME_RANKING_ENABLE = (
    os.getenv("REVIEW_QUEUE_RUNTIME_RANKING_ENABLE", "true").lower() == "true"
)
REVIEW_QUEUE_FINAL_ENTRY_LOCK_ENABLE = (
    os.getenv("REVIEW_QUEUE_FINAL_ENTRY_LOCK_ENABLE", "true").lower() == "true"
)
REVIEW_QUEUE_STRATEGY_FAMILY_FALLBACK = os.getenv(
    "REVIEW_QUEUE_STRATEGY_FAMILY_FALLBACK",
    "breakout",
).strip().lower() or "breakout"
CANDIDATE_ROW_KIND_CANONICAL_ONLY = (
    os.getenv("CANDIDATE_ROW_KIND_CANONICAL_ONLY", "true").lower() == "true"
)
CANDIDATE_ROW_CORRUPTION_LOG_ENABLE = (
    os.getenv("CANDIDATE_ROW_CORRUPTION_LOG_ENABLE", "true").lower() == "true"
)
CANDIDATE_SCORING_TRACE_ENABLE = (
    os.getenv("CANDIDATE_SCORING_TRACE_ENABLE", "false").lower() == "true"
)
CANDIDATE_SCORING_ASSERT_ENABLE = (
    os.getenv("CANDIDATE_SCORING_ASSERT_ENABLE", "false").lower() == "true"
)
CANDIDATE_FINALIZATION_ASSERT_ENABLE = (
    os.getenv("CANDIDATE_FINALIZATION_ASSERT_ENABLE", "true").lower() == "true"
)
CANDIDATE_SCORING_RR_FALLBACK_ENABLE_LIVE = (
    os.getenv("CANDIDATE_SCORING_RR_FALLBACK_ENABLE_LIVE", "false").lower() == "true"
)
CANDIDATE_SCORING_RR_FALLBACK_ENABLE_PAPER = (
    os.getenv("CANDIDATE_SCORING_RR_FALLBACK_ENABLE_PAPER", "true").lower() == "true"
)
# Keep legacy variable mapping to PAPER default if used directly
CANDIDATE_SCORING_RR_FALLBACK_ENABLE = CANDIDATE_SCORING_RR_FALLBACK_ENABLE_PAPER
CANDIDATE_SCORING_RR_FALLBACK_BUY_STOP_MULT = float(
    os.getenv("CANDIDATE_SCORING_RR_FALLBACK_BUY_STOP_MULT", "0.75")
)
CANDIDATE_SCORING_RR_FALLBACK_BUY_TARGET_MULT = float(
    os.getenv("CANDIDATE_SCORING_RR_FALLBACK_BUY_TARGET_MULT", "1.35")
)
CANDIDATE_SCORING_RR_FALLBACK_SELL_STOP_MULT = float(
    os.getenv("CANDIDATE_SCORING_RR_FALLBACK_SELL_STOP_MULT", "1.25")
)
CANDIDATE_SCORING_RR_FALLBACK_SELL_TARGET_MULT = float(
    os.getenv("CANDIDATE_SCORING_RR_FALLBACK_SELL_TARGET_MULT", "0.65")
)

# Timing SLAs
LIVE_OPTION_LTP_MAX_AGE_SEC = float(os.getenv("LIVE_OPTION_LTP_MAX_AGE_SEC", "2.0"))
LIVE_DEPTH_MAX_AGE_SEC = float(os.getenv("LIVE_DEPTH_MAX_AGE_SEC", "2.0"))
LIVE_SPOT_MAX_AGE_SEC = float(os.getenv("LIVE_SPOT_MAX_AGE_SEC", "2.0"))
PAPER_OPTION_LTP_MAX_AGE_SEC = float(os.getenv("PAPER_OPTION_LTP_MAX_AGE_SEC", "5.0"))
OFFHOURS_DIAGNOSTIC_MAX_AGE_SEC = float(os.getenv("OFFHOURS_DIAGNOSTIC_MAX_AGE_SEC", "300.0"))

CANDIDATE_SCORING_TIMING_MAX_AGE_SEC = float(os.getenv("CANDIDATE_SCORING_TIMING_MAX_AGE_SEC", "300.0"))

# Top Opportunities Requirements
TOP_OPPORTUNITIES_REQUIRE_FRESH_DATA = os.getenv("TOP_OPPORTUNITIES_REQUIRE_FRESH_DATA", "true").lower() == "true"
TOP_OPPORTUNITIES_ALLOW_FALLBACK = os.getenv("TOP_OPPORTUNITIES_ALLOW_FALLBACK", "false").lower() == "true"
TOP_OPPORTUNITIES_ALLOW_STALE = os.getenv("TOP_OPPORTUNITIES_ALLOW_STALE", "false").lower() == "true"
TOP_OPPORTUNITIES_ALLOW_SYNTHETIC = os.getenv("TOP_OPPORTUNITIES_ALLOW_SYNTHETIC", "false").lower() == "true"
CANDIDATE_SCORING_LIQUIDITY_VOLUME_CAP_MULT = float(
    os.getenv("CANDIDATE_SCORING_LIQUIDITY_VOLUME_CAP_MULT", "40")
)
CANDIDATE_SCORING_LIQUIDITY_OI_CAP_MULT = float(
    os.getenv("CANDIDATE_SCORING_LIQUIDITY_OI_CAP_MULT", "40")
)
CANDIDATE_SCORING_LIQUIDITY_FLOW_WEIGHT = float(
    os.getenv("CANDIDATE_SCORING_LIQUIDITY_FLOW_WEIGHT", "0.60")
)
CANDIDATE_SCORING_LIQUIDITY_BOOK_WEIGHT = float(
    os.getenv("CANDIDATE_SCORING_LIQUIDITY_BOOK_WEIGHT", "0.40")
)
TERMINAL_SCORING_MAX_ABS_DELTA = float(
    os.getenv("TERMINAL_SCORING_MAX_ABS_DELTA", "0.15")
)
TERMINAL_SCORING_MAX_MULT = float(
    os.getenv("TERMINAL_SCORING_MAX_MULT", "1.35")
)
OPPORTUNITY_TOP_N_EXECUTABLE = int(os.getenv("OPPORTUNITY_TOP_N_EXECUTABLE", "1"))
TOP_EXECUTABLE_OPPORTUNITIES_N = int(os.getenv("TOP_EXECUTABLE_OPPORTUNITIES_N", "5"))
TOP_ADVISORY_OPPORTUNITIES_N = int(os.getenv("TOP_ADVISORY_OPPORTUNITIES_N", "5"))
TOP_NEAR_EXECUTABLE_OPPORTUNITIES_N = int(
    os.getenv("TOP_NEAR_EXECUTABLE_OPPORTUNITIES_N", str(TOP_ADVISORY_OPPORTUNITIES_N))
)
CAPITAL_ALLOCATOR_ENABLE = os.getenv("CAPITAL_ALLOCATOR_ENABLE", "true").lower() == "true"
CAPITAL_ALLOCATOR_MAX_SLOTS = int(
    os.getenv("CAPITAL_ALLOCATOR_MAX_SLOTS", str(max(1, TOP_EXECUTABLE_OPPORTUNITIES_N)))
)
CAPITAL_ALLOCATOR_PER_SYMBOL_CAP = int(os.getenv("CAPITAL_ALLOCATOR_PER_SYMBOL_CAP", "1"))
CAPITAL_ALLOCATOR_PER_THEME_CAP = int(os.getenv("CAPITAL_ALLOCATOR_PER_THEME_CAP", "1"))
CAPITAL_ALLOCATOR_BUDGET_CAP = float(os.getenv("CAPITAL_ALLOCATOR_BUDGET_CAP", "0"))
CAPITAL_ALLOCATOR_MIN_QUALITY_THRESHOLD = float(os.getenv("CAPITAL_ALLOCATOR_MIN_QUALITY_THRESHOLD", "0.0"))
CAPITAL_ALLOCATOR_REPLACEMENT_ENABLE = os.getenv("CAPITAL_ALLOCATOR_REPLACEMENT_ENABLE", "true").lower() == "true"
CAPITAL_ALLOCATOR_REPLACEMENT_MIN_DELTA = float(os.getenv("CAPITAL_ALLOCATOR_REPLACEMENT_MIN_DELTA", "0.03"))
PORTFOLIO_OPTIMIZER_ENABLE = os.getenv("PORTFOLIO_OPTIMIZER_ENABLE", "false").lower() == "true"
PORTFOLIO_OPTIMIZER_MAX_GROUP_EXPOSURE = int(os.getenv("PORTFOLIO_OPTIMIZER_MAX_GROUP_EXPOSURE", "1"))
PORTFOLIO_OPTIMIZER_CORRELATION_PENALTY = float(os.getenv("PORTFOLIO_OPTIMIZER_CORRELATION_PENALTY", "0.08"))
PORTFOLIO_OPTIMIZER_EXISTING_EXPOSURE_PENALTY = float(
    os.getenv("PORTFOLIO_OPTIMIZER_EXISTING_EXPOSURE_PENALTY", "0.05")
)
PORTFOLIO_OPTIMIZER_DIVERSIFICATION_BONUS = float(
    os.getenv("PORTFOLIO_OPTIMIZER_DIVERSIFICATION_BONUS", "0.035")
)
PORTFOLIO_OPTIMIZER_CAPITAL_EFFICIENCY_WEIGHT = float(
    os.getenv("PORTFOLIO_OPTIMIZER_CAPITAL_EFFICIENCY_WEIGHT", "0.025")
)
OPPORTUNITY_SURVIVAL_SCORE_FLOOR = float(os.getenv("OPPORTUNITY_SURVIVAL_SCORE_FLOOR", "0.35"))
TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES = (
    os.getenv("TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES", "true").lower() == "true"
)
OPPORTUNITY_EXECUTION_SCORE_BASE = float(os.getenv("OPPORTUNITY_EXECUTION_SCORE_BASE", "0.52"))
OPPORTUNITY_EXECUTION_LIQUIDITY_BONUS = float(os.getenv("OPPORTUNITY_EXECUTION_LIQUIDITY_BONUS", "0.03"))
OPPORTUNITY_EXECUTION_HOSTILE_REGIME_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_HOSTILE_REGIME_PENALTY", "0.05")
)
OPPORTUNITY_EXECUTION_COUNTERTREND_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_COUNTERTREND_PENALTY", "0.04")
)
OPPORTUNITY_EXECUTION_SUPPORTIVE_REGIME_BONUS = float(
    os.getenv("OPPORTUNITY_EXECUTION_SUPPORTIVE_REGIME_BONUS", "0.02")
)
OPPORTUNITY_EXECUTION_WEAK_LIQUIDITY_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_WEAK_LIQUIDITY_PENALTY", "0.02")
)
OPPORTUNITY_EXECUTION_STRONG_FRESHNESS_BONUS = float(
    os.getenv("OPPORTUNITY_EXECUTION_STRONG_FRESHNESS_BONUS", "0.015")
)
OPPORTUNITY_EXECUTION_WEAK_FRESHNESS_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_WEAK_FRESHNESS_PENALTY", "0.025")
)
OPPORTUNITY_EXECUTION_STRONG_SPREAD_BONUS = float(
    os.getenv("OPPORTUNITY_EXECUTION_STRONG_SPREAD_BONUS", "0.01")
)
OPPORTUNITY_EXECUTION_WEAK_SPREAD_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_WEAK_SPREAD_PENALTY", "0.02")
)
OPPORTUNITY_STRONG_LIQUIDITY_THRESHOLD = float(
    os.getenv("OPPORTUNITY_STRONG_LIQUIDITY_THRESHOLD", "0.80")
)
OPPORTUNITY_WEAK_LIQUIDITY_THRESHOLD = float(
    os.getenv("OPPORTUNITY_WEAK_LIQUIDITY_THRESHOLD", "0.45")
)
OPPORTUNITY_STRONG_FRESHNESS_THRESHOLD = float(
    os.getenv("OPPORTUNITY_STRONG_FRESHNESS_THRESHOLD", "0.85")
)
OPPORTUNITY_WEAK_FRESHNESS_THRESHOLD = float(
    os.getenv("OPPORTUNITY_WEAK_FRESHNESS_THRESHOLD", "0.35")
)
OPPORTUNITY_STRONG_SPREAD_THRESHOLD = float(
    os.getenv("OPPORTUNITY_STRONG_SPREAD_THRESHOLD", "0.85")
)
OPPORTUNITY_WEAK_SPREAD_THRESHOLD = float(
    os.getenv("OPPORTUNITY_WEAK_SPREAD_THRESHOLD", "0.35")
)
OPPORTUNITY_EXECUTION_OPENING_WINDOW_MIN = int(
    os.getenv("OPPORTUNITY_EXECUTION_OPENING_WINDOW_MIN", "20")
)
OPPORTUNITY_EXECUTION_OPENING_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_OPENING_PENALTY", "0.02")
)
OPPORTUNITY_EXECUTION_CLOSING_WINDOW_MIN = int(
    os.getenv("OPPORTUNITY_EXECUTION_CLOSING_WINDOW_MIN", "30")
)
OPPORTUNITY_EXECUTION_CLOSING_PENALTY = float(
    os.getenv("OPPORTUNITY_EXECUTION_CLOSING_PENALTY", "0.03")
)
OPPORTUNITY_EXECUTION_THRESHOLD_MAX_ADJUSTMENT = float(
    os.getenv("OPPORTUNITY_EXECUTION_THRESHOLD_MAX_ADJUSTMENT", "0.08")
)
EXECUTION_QUALITY_ENABLE = os.getenv("EXECUTION_QUALITY_ENABLE", "true").lower() == "true"
EXECUTION_QUALITY_MARKET_MAX_SPREAD_PCT = float(
    os.getenv("EXECUTION_QUALITY_MARKET_MAX_SPREAD_PCT", "0.005")
)
EXECUTION_QUALITY_LIMIT_MAX_SPREAD_PCT = float(
    os.getenv("EXECUTION_QUALITY_LIMIT_MAX_SPREAD_PCT", str(MAX_SPREAD_PCT))
)
EXECUTION_QUALITY_MIN_LIQUIDITY_QUALITY = float(
    os.getenv("EXECUTION_QUALITY_MIN_LIQUIDITY_QUALITY", "0.35")
)
EXECUTION_QUALITY_MARKET_MIN_LIQUIDITY_QUALITY = float(
    os.getenv("EXECUTION_QUALITY_MARKET_MIN_LIQUIDITY_QUALITY", "0.75")
)
EXECUTION_QUALITY_MAX_SLIPPAGE_BPS = float(
    os.getenv("EXECUTION_QUALITY_MAX_SLIPPAGE_BPS", "75.0")
)
EXECUTION_QUALITY_MAX_DEPTH_RATIO = float(
    os.getenv("EXECUTION_QUALITY_MAX_DEPTH_RATIO", "1.25")
)
EXECUTION_QUALITY_MAX_SCORE_PENALTY = float(
    os.getenv("EXECUTION_QUALITY_MAX_SCORE_PENALTY", "0.22")
)
EXECUTION_QUALITY_LIMIT_SCORE_PENALTY = float(
    os.getenv("EXECUTION_QUALITY_LIMIT_SCORE_PENALTY", "0.015")
)
EXECUTION_QUALITY_DEPTH_IMPACT_MULT = float(
    os.getenv("EXECUTION_QUALITY_DEPTH_IMPACT_MULT", "0.35")
)
DATA_TRUTH_REQUIRE_BOOK_FOR_FRESH = os.getenv("DATA_TRUTH_REQUIRE_BOOK_FOR_FRESH", "true").lower() == "true"
DATA_TRUTH_MAX_CHAIN_SNAPSHOT_AGE_SEC = float(
    os.getenv(
        "DATA_TRUTH_MAX_CHAIN_SNAPSHOT_AGE_SEC",
        str(float(os.getenv("SLA_MAX_DEPTH_AGE_SEC", "6.0"))),
    )
)
DATA_TRUTH_LTP_BOOK_DRIFT_TOL_PCT = float(os.getenv("DATA_TRUTH_LTP_BOOK_DRIFT_TOL_PCT", "0.03"))
DATA_CONFIDENCE_SPREAD_CHANGE_FULL_SCALE = float(
    os.getenv("DATA_CONFIDENCE_SPREAD_CHANGE_FULL_SCALE", "1.0")
)
DATA_CONFIDENCE_MIN_SPREAD_STABILITY_OK = float(
    os.getenv("DATA_CONFIDENCE_MIN_SPREAD_STABILITY_OK", "0.35")
)
DATA_CONFIDENCE_MIN_EXECUTION = float(os.getenv("DATA_CONFIDENCE_MIN_EXECUTION", "0.20"))
DATA_CONFIDENCE_EXECUTION_SOFT_FLOOR = float(
    os.getenv("DATA_CONFIDENCE_EXECUTION_SOFT_FLOOR", "0.45")
)
OPPORTUNITY_WEIGHT_BUILDER_CONFIDENCE = float(os.getenv("OPPORTUNITY_WEIGHT_BUILDER_CONFIDENCE", "0.32"))
OPPORTUNITY_WEIGHT_PERMISSION_CONFIDENCE = float(os.getenv("OPPORTUNITY_WEIGHT_PERMISSION_CONFIDENCE", "0.12"))
OPPORTUNITY_WEIGHT_GATING_CONFIDENCE = float(os.getenv("OPPORTUNITY_WEIGHT_GATING_CONFIDENCE", "0.18"))
OPPORTUNITY_WEIGHT_CONFLUENCE = float(os.getenv("OPPORTUNITY_WEIGHT_CONFLUENCE", "0.16"))
OPPORTUNITY_WEIGHT_REGIME_ALIGNMENT = float(os.getenv("OPPORTUNITY_WEIGHT_REGIME_ALIGNMENT", "0.08"))
OPPORTUNITY_WEIGHT_LIQUIDITY = float(os.getenv("OPPORTUNITY_WEIGHT_LIQUIDITY", "0.07"))
OPPORTUNITY_WEIGHT_SPREAD = float(os.getenv("OPPORTUNITY_WEIGHT_SPREAD", "0.04"))
OPPORTUNITY_WEIGHT_FRESHNESS = float(os.getenv("OPPORTUNITY_WEIGHT_FRESHNESS", "0.03"))
FINAL_SCORE_WEIGHT_SETUP_QUALITY = float(os.getenv("FINAL_SCORE_WEIGHT_SETUP_QUALITY", "0.30"))
FINAL_SCORE_WEIGHT_CONFLUENCE = float(os.getenv("FINAL_SCORE_WEIGHT_CONFLUENCE", "0.16"))
FINAL_SCORE_WEIGHT_REGIME_FIT = float(os.getenv("FINAL_SCORE_WEIGHT_REGIME_FIT", "0.14"))
FINAL_SCORE_WEIGHT_LIQUIDITY = float(os.getenv("FINAL_SCORE_WEIGHT_LIQUIDITY", "0.14"))
FINAL_SCORE_WEIGHT_FRESHNESS = float(os.getenv("FINAL_SCORE_WEIGHT_FRESHNESS", "0.10"))
FINAL_SCORE_WEIGHT_EXECUTION_FEASIBILITY = float(
    os.getenv("FINAL_SCORE_WEIGHT_EXECUTION_FEASIBILITY", "0.16")
)
FINAL_SCORE_WEIGHT_DATA_CONFIDENCE = float(
    os.getenv("FINAL_SCORE_WEIGHT_DATA_CONFIDENCE", "0.12")
)
FINAL_SCORE_WEIGHT_TRIGGER_QUALITY = float(
    os.getenv("FINAL_SCORE_WEIGHT_TRIGGER_QUALITY", "0.12")
)
FINAL_SCORE_WEIGHT_ENTRY_QUALITY = float(
    os.getenv("FINAL_SCORE_WEIGHT_ENTRY_QUALITY", "0.14")
)
FINAL_SCORE_FAMILY_SURVIVAL_ADJUSTMENT_MAX = float(
    os.getenv("FINAL_SCORE_FAMILY_SURVIVAL_ADJUSTMENT_MAX", "0.05")
)
FINAL_SCORE_PENALTY_FALLBACK = float(os.getenv("FINAL_SCORE_PENALTY_FALLBACK", "0.20"))
FINAL_SCORE_PENALTY_STALE_QUOTE = float(os.getenv("FINAL_SCORE_PENALTY_STALE_QUOTE", "0.10"))
FINAL_SCORE_PENALTY_MISSING_LIQUIDITY = float(
    os.getenv("FINAL_SCORE_PENALTY_MISSING_LIQUIDITY", "0.08")
)
FINAL_SCORE_PENALTY_SPREAD_UNCERTAINTY = float(
    os.getenv("FINAL_SCORE_PENALTY_SPREAD_UNCERTAINTY", "0.07")
)
FINAL_SCORE_PENALTY_OFFHOURS = float(os.getenv("FINAL_SCORE_PENALTY_OFFHOURS", "0.18"))
FINAL_SCORE_CLASS_CAP_EXECUTABLE = float(os.getenv("FINAL_SCORE_CLASS_CAP_EXECUTABLE", "1.00"))
FINAL_SCORE_CLASS_CAP_NEAR_EXECUTABLE = float(
    os.getenv("FINAL_SCORE_CLASS_CAP_NEAR_EXECUTABLE", "0.79")
)
FINAL_SCORE_CLASS_CAP_ADVISORY_ONLY = float(
    os.getenv("FINAL_SCORE_CLASS_CAP_ADVISORY_ONLY", "0.49")
)
PRIORITY_SCORE_WEIGHT_SIGNAL = float(os.getenv("PRIORITY_SCORE_WEIGHT_SIGNAL", "0.62"))
PRIORITY_SCORE_WEIGHT_EXECUTION = float(os.getenv("PRIORITY_SCORE_WEIGHT_EXECUTION", "0.38"))
PRIORITY_SCORE_TREND_SIGNAL_BONUS = float(os.getenv("PRIORITY_SCORE_TREND_SIGNAL_BONUS", "0.08"))
PRIORITY_SCORE_SIDEWAYS_EXECUTION_BONUS = float(
    os.getenv("PRIORITY_SCORE_SIDEWAYS_EXECUTION_BONUS", "0.18")
)
PRIORITY_SCORE_UNSTABLE_EXECUTION_BONUS = float(
    os.getenv("PRIORITY_SCORE_UNSTABLE_EXECUTION_BONUS", "0.14")
)
PRIORITY_SCORE_LOW_DATA_CONFIDENCE_EXECUTION_BONUS = float(
    os.getenv("PRIORITY_SCORE_LOW_DATA_CONFIDENCE_EXECUTION_BONUS", "0.08")
)
MIN_PRIORITY_SCORE_FOR_EXECUTABLE = float(os.getenv("MIN_PRIORITY_SCORE_FOR_EXECUTABLE", "0.55"))
MIN_EXECUTION_SCORE_FOR_EXECUTABLE = float(os.getenv("MIN_EXECUTION_SCORE_FOR_EXECUTABLE", "0.45"))
MIN_EXECUTABLE_GAP_OVER_NEXT_NON_EXECUTABLE = float(
    os.getenv("MIN_EXECUTABLE_GAP_OVER_NEXT_NON_EXECUTABLE", "0.0")
)
SELECTION_SOFT_SCORE_BAND = float(os.getenv("SELECTION_SOFT_SCORE_BAND", "0.03"))
SELECTION_SOFT_EXECUTION_BAND = float(os.getenv("SELECTION_SOFT_EXECUTION_BAND", "0.08"))
SELECTION_SOFT_GAP_BAND = float(os.getenv("SELECTION_SOFT_GAP_BAND", "0.03"))
MIN_SELECTION_PROBABILITY = float(os.getenv("MIN_SELECTION_PROBABILITY", "0.45"))
OPPORTUNITY_SIZE_MIN_MULT = float(os.getenv("OPPORTUNITY_SIZE_MIN_MULT", "0.25"))
OPPORTUNITY_RANK_SIZE_DECAY = float(os.getenv("OPPORTUNITY_RANK_SIZE_DECAY", "0.20"))
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
# No-signal fallback (SIM/PAPER only).
NO_SIGNAL_FALLBACK_ENABLE = os.getenv("NO_SIGNAL_FALLBACK_ENABLE", "true").lower() == "true"
NO_SIGNAL_FALLBACK_SCORE = float(os.getenv("NO_SIGNAL_FALLBACK_SCORE", "0.45"))
LIVE_NO_SIGNAL_FALLBACK_ENABLE = os.getenv("LIVE_NO_SIGNAL_FALLBACK_ENABLE", "true").lower() == "true"
LIVE_NO_SIGNAL_FALLBACK_SCORE_MIN = float(os.getenv("LIVE_NO_SIGNAL_FALLBACK_SCORE_MIN", "0.58"))
LIVE_ALLOW_WEAK_SIGNAL_BORDERLINE_CANDIDATE = (
    os.getenv("LIVE_ALLOW_WEAK_SIGNAL_BORDERLINE_CANDIDATE", "false").lower() == "true"
)
LIVE_RELAX_IV_STRUCTURE_GATES_ENABLE = (
    os.getenv("LIVE_RELAX_IV_STRUCTURE_GATES_ENABLE", "true").lower() == "true"
)
LIVE_REQUIRE_OI_BUILD_ALIGNMENT = (
    os.getenv("LIVE_REQUIRE_OI_BUILD_ALIGNMENT", "false").lower() == "true"
)
LIVE_OPTION_TICK_SOFT_STALE_SEC = float(os.getenv("LIVE_OPTION_TICK_SOFT_STALE_SEC", "10.0"))
LIVE_OPTION_TICK_HARD_STALE_SEC = float(os.getenv("LIVE_OPTION_TICK_HARD_STALE_SEC", "24.0"))
TRADE_BUILDER_LIVE_STALE_SOFTEN_MIN_OI = float(
    os.getenv("TRADE_BUILDER_LIVE_STALE_SOFTEN_MIN_OI", "1000.0")
)
TRADE_BUILDER_LIVE_STALE_SOFTEN_REQUIRE_QUOTE_OK = (
    os.getenv("TRADE_BUILDER_LIVE_STALE_SOFTEN_REQUIRE_QUOTE_OK", "true").lower()
    == "true"
)
LIVE_DELTA_MIN = float(os.getenv("LIVE_DELTA_MIN", "0.15"))
LIVE_DELTA_MAX = float(os.getenv("LIVE_DELTA_MAX", "0.90"))
LIVE_TRADE_SCORE_MIN = float(os.getenv("LIVE_TRADE_SCORE_MIN", "68"))
LIVE_DELTA_HARD_REJECT_ENABLE = os.getenv("LIVE_DELTA_HARD_REJECT_ENABLE", "false").lower() == "true"
LIVE_TRADE_SCORE_HARD_REJECT_ENABLE = os.getenv("LIVE_TRADE_SCORE_HARD_REJECT_ENABLE", "false").lower() == "true"
# Allow softening option type mismatches in non-live runs.
ALLOW_OPTION_TYPE_MISMATCH_SOFTEN = os.getenv("ALLOW_OPTION_TYPE_MISMATCH_SOFTEN", "true").lower() == "true"
# Emergency rollback knob: when true, type mismatch is a hard reject instead of soft penalty.
OPTION_TYPE_MISMATCH_HARD_REJECT = os.getenv("OPTION_TYPE_MISMATCH_HARD_REJECT", "false").lower() == "true"
TRADE_BUILDER_SIGNAL_SCORE_BELOW_MIN_HARD_REJECT = (
    os.getenv("TRADE_BUILDER_SIGNAL_SCORE_BELOW_MIN_HARD_REJECT", "false").lower()
    == "true"
)
# Relax volume requirements in non-live runs.
RELAX_VOLUME_REQUIREMENTS_NONLIVE = os.getenv("RELAX_VOLUME_REQUIREMENTS_NONLIVE", "true").lower() == "true"
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
NONLIVE_FEATURE_FALLBACK_ENABLE = os.getenv("NONLIVE_FEATURE_FALLBACK_ENABLE", "true").lower() == "true"
NONLIVE_FEATURE_FALLBACK_ATR_PCT = float(os.getenv("NONLIVE_FEATURE_FALLBACK_ATR_PCT", "0.001"))
NONLIVE_FEATURE_FALLBACK_SIGNAL_HINT_MIN = float(os.getenv("NONLIVE_FEATURE_FALLBACK_SIGNAL_HINT_MIN", "0.15"))
NONLIVE_FALLBACK_SIGNAL_STRENGTH_MIN = float(os.getenv("NONLIVE_FALLBACK_SIGNAL_STRENGTH_MIN", "0.75"))
SIDEWAYS_DIRECTIONAL_EXCEPTIONAL_STRENGTH = float(
    os.getenv("SIDEWAYS_DIRECTIONAL_EXCEPTIONAL_STRENGTH", "1.75")
)
COUNTER_REGIME_DIRECTIONAL_EXCEPTIONAL_STRENGTH = float(
    os.getenv("COUNTER_REGIME_DIRECTIONAL_EXCEPTIONAL_STRENGTH", "1.50")
)
BEARISH_DIRECTIONAL_STRUCTURE_MIN = float(
    os.getenv("BEARISH_DIRECTIONAL_STRUCTURE_MIN", "0.95")
)
NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES = int(
    os.getenv("NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", "2")
)
NONLIVE_SIDEWAYS_DIRECTION_FAMILY_MAX_CANDIDATES = int(
    os.getenv("NONLIVE_SIDEWAYS_DIRECTION_FAMILY_MAX_CANDIDATES", "1")
)
RANGE_WATCHLIST_ENABLE = os.getenv("RANGE_WATCHLIST_ENABLE", "true").lower() == "true"
RANGE_WATCHLIST_MIN_STRENGTH = float(os.getenv("RANGE_WATCHLIST_MIN_STRENGTH", "0.90"))
RANGE_WATCHLIST_EDGE_MIN = float(os.getenv("RANGE_WATCHLIST_EDGE_MIN", "0.80"))
RANGE_WATCHLIST_EDGE_MAX = float(os.getenv("RANGE_WATCHLIST_EDGE_MAX", "2.80"))
RANGE_WATCHLIST_COMPRESSION_ATR_MAX = float(os.getenv("RANGE_WATCHLIST_COMPRESSION_ATR_MAX", "0.45"))
FAMILY_CONTEXT_GATE_OVERRIDE_ENABLE = os.getenv("FAMILY_CONTEXT_GATE_OVERRIDE_ENABLE", "true").lower() == "true"
FAMILY_CONTEXT_GATE_OVERRIDE_MIN_STRENGTH = float(
    os.getenv("FAMILY_CONTEXT_GATE_OVERRIDE_MIN_STRENGTH", "2.25")
)
FAMILY_CONTEXT_GATE_OVERRIDE_MIN_REGIME_CONFIDENCE = float(
    os.getenv("FAMILY_CONTEXT_GATE_OVERRIDE_MIN_REGIME_CONFIDENCE", "0.45")
)
FAMILY_CONTEXT_GATE_OVERRIDE_MIN_QUALITY = float(
    os.getenv("FAMILY_CONTEXT_GATE_OVERRIDE_MIN_QUALITY", "0.78")
)
STRATEGY_REGIME_CONFIDENCE_MIN = float(os.getenv("STRATEGY_REGIME_CONFIDENCE_MIN", "0.45"))
STRATEGY_REGIME_UNCERTAIN_CONFIDENCE_MAX = float(os.getenv("STRATEGY_REGIME_UNCERTAIN_CONFIDENCE_MAX", "0.30"))
STRATEGY_REGIME_TREND_ATR_MIN = float(os.getenv("STRATEGY_REGIME_TREND_ATR_MIN", "0.35"))
STRATEGY_REGIME_LOW_VOL_ATR_MAX = float(os.getenv("STRATEGY_REGIME_LOW_VOL_ATR_MAX", "0.18"))
STRATEGY_REGIME_COMPRESSION_VOL_Z_MAX = float(os.getenv("STRATEGY_REGIME_COMPRESSION_VOL_Z_MAX", "0.35"))
NONLIVE_LOW_VOL_EXCEPTIONAL_STRENGTH = float(os.getenv("NONLIVE_LOW_VOL_EXCEPTIONAL_STRENGTH", "1.95"))
NONLIVE_UNCERTAIN_FAMILY_MAX_CANDIDATES = int(os.getenv("NONLIVE_UNCERTAIN_FAMILY_MAX_CANDIDATES", "1"))
SESSION_OPENING_WINDOW_MIN = int(os.getenv("SESSION_OPENING_WINDOW_MIN", "20"))
SESSION_MIDDAY_START_MIN = int(os.getenv("SESSION_MIDDAY_START_MIN", "60"))
SESSION_CLOSING_WINDOW_MIN = int(os.getenv("SESSION_CLOSING_WINDOW_MIN", "35"))
SESSION_OPENING_ENTRY_PENALTY = float(os.getenv("SESSION_OPENING_ENTRY_PENALTY", "0.02"))
SESSION_MIDDAY_ENTRY_PENALTY = float(os.getenv("SESSION_MIDDAY_ENTRY_PENALTY", "0.12"))
SESSION_CLOSING_ENTRY_PENALTY = float(os.getenv("SESSION_CLOSING_ENTRY_PENALTY", "0.10"))
SESSION_OFFHOURS_ENTRY_PENALTY = float(os.getenv("SESSION_OFFHOURS_ENTRY_PENALTY", "0.20"))
SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN = float(os.getenv("SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN", "0.66"))
ENTRY_OVEREXTENSION_VWAP_ATR_SOFT = float(os.getenv("ENTRY_OVEREXTENSION_VWAP_ATR_SOFT", "1.00"))
ENTRY_OVEREXTENSION_VWAP_ATR_HARD = float(os.getenv("ENTRY_OVEREXTENSION_VWAP_ATR_HARD", "2.00"))
ENTRY_OVEREXTENSION_MOVE_ATR_SOFT = float(os.getenv("ENTRY_OVEREXTENSION_MOVE_ATR_SOFT", "1.20"))
ENTRY_OVEREXTENSION_MOVE_ATR_HARD = float(os.getenv("ENTRY_OVEREXTENSION_MOVE_ATR_HARD", "2.40"))
ENTRY_INVALIDATION_DISTANCE_MAX_PCT = float(os.getenv("ENTRY_INVALIDATION_DISTANCE_MAX_PCT", "0.35"))
ENTRY_INVALIDATION_DISTANCE_MAX_ATR = float(os.getenv("ENTRY_INVALIDATION_DISTANCE_MAX_ATR", "1.80"))
MEAN_REVERSION_MIN_STRETCH_ATR = float(os.getenv("MEAN_REVERSION_MIN_STRETCH_ATR", "0.45"))
FAMILY_SURVIVAL_COMPONENT_MIN = float(os.getenv("FAMILY_SURVIVAL_COMPONENT_MIN", "0.26"))
FAMILY_SURVIVAL_MIN_SCORE = float(os.getenv("FAMILY_SURVIVAL_MIN_SCORE", "0.42"))
NONLIVE_EXECUTABLE_MIN_FAMILY_SURVIVAL = float(os.getenv("NONLIVE_EXECUTABLE_MIN_FAMILY_SURVIVAL", "0.55"))
SETUP_SCORE_WEIGHT_REGIME = float(os.getenv("SETUP_SCORE_WEIGHT_REGIME", "0.40"))
SETUP_SCORE_WEIGHT_STRUCTURE = float(os.getenv("SETUP_SCORE_WEIGHT_STRUCTURE", "0.35"))
SETUP_SCORE_WEIGHT_THESIS = float(os.getenv("SETUP_SCORE_WEIGHT_THESIS", "0.25"))
ENTRY_QUALITY_WEIGHT_INVALIDATION = float(os.getenv("ENTRY_QUALITY_WEIGHT_INVALIDATION", "0.35"))
ENTRY_QUALITY_WEIGHT_OVEREXTENSION = float(os.getenv("ENTRY_QUALITY_WEIGHT_OVEREXTENSION", "0.35"))
ENTRY_QUALITY_WEIGHT_EXECUTION_FIT = float(os.getenv("ENTRY_QUALITY_WEIGHT_EXECUTION_FIT", "0.20"))
ENTRY_QUALITY_WEIGHT_SESSION = float(os.getenv("ENTRY_QUALITY_WEIGHT_SESSION", "0.10"))
FAMILY_SURVIVAL_WEIGHT_SETUP = float(os.getenv("FAMILY_SURVIVAL_WEIGHT_SETUP", "0.30"))
FAMILY_SURVIVAL_WEIGHT_TRIGGER = float(os.getenv("FAMILY_SURVIVAL_WEIGHT_TRIGGER", "0.25"))
FAMILY_SURVIVAL_WEIGHT_ENTRY_QUALITY = float(os.getenv("FAMILY_SURVIVAL_WEIGHT_ENTRY_QUALITY", "0.25"))
FAMILY_SURVIVAL_WEIGHT_EXECUTION = float(os.getenv("FAMILY_SURVIVAL_WEIGHT_EXECUTION", "0.10"))
FAMILY_SURVIVAL_WEIGHT_CONSENSUS = float(os.getenv("FAMILY_SURVIVAL_WEIGHT_CONSENSUS", "0.10"))
FAMILY_CONSENSUS_MIN_SCORE = float(os.getenv("FAMILY_CONSENSUS_MIN_SCORE", "0.28"))
FAMILY_CONSENSUS_LOW_VOL_MIN_SCORE = float(os.getenv("FAMILY_CONSENSUS_LOW_VOL_MIN_SCORE", "0.30"))
FAMILY_CONSENSUS_UNCERTAIN_MIN_SCORE = float(os.getenv("FAMILY_CONSENSUS_UNCERTAIN_MIN_SCORE", "0.26"))
FAMILY_CONSENSUS_WEIGHT_REGIME = float(os.getenv("FAMILY_CONSENSUS_WEIGHT_REGIME", "0.28"))
FAMILY_CONSENSUS_WEIGHT_STRUCTURE = float(os.getenv("FAMILY_CONSENSUS_WEIGHT_STRUCTURE", "0.24"))
FAMILY_CONSENSUS_WEIGHT_EXECUTION = float(os.getenv("FAMILY_CONSENSUS_WEIGHT_EXECUTION", "0.22"))
FAMILY_CONSENSUS_WEIGHT_QUALITY = float(os.getenv("FAMILY_CONSENSUS_WEIGHT_QUALITY", "0.18"))
FAMILY_CONSENSUS_WEIGHT_PRIOR = float(os.getenv("FAMILY_CONSENSUS_WEIGHT_PRIOR", "0.08"))
OFFLINE_THRESHOLD_AUDIT_ENABLE = os.getenv("OFFLINE_THRESHOLD_AUDIT_ENABLE", "true").lower() == "true"
OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR = float(
    os.getenv("OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR", "0.25")
)
OFFLINE_THRESHOLD_AUDIT_TOP_FAMILY_SHARE_WARN = float(
    os.getenv("OFFLINE_THRESHOLD_AUDIT_TOP_FAMILY_SHARE_WARN", "0.75")
)
OFFLINE_THRESHOLD_AUDIT_STAGE_CLUSTER_WARN = float(
    os.getenv("OFFLINE_THRESHOLD_AUDIT_STAGE_CLUSTER_WARN", "0.60")
)
OFFLINE_THRESHOLD_AUDIT_NO_EXECUTABLE_RATE_WARN = float(
    os.getenv("OFFLINE_THRESHOLD_AUDIT_NO_EXECUTABLE_RATE_WARN", "0.70")
)
OFFLINE_REJECTION_IMPACT_ENABLE = os.getenv("OFFLINE_REJECTION_IMPACT_ENABLE", "true").lower() == "true"
OFFLINE_REJECTION_IMPACT_TOP_N = int(os.getenv("OFFLINE_REJECTION_IMPACT_TOP_N", "3"))
OFFLINE_EDGE_IMPROVEMENT_MIN_R_DELTA = float(
    os.getenv("OFFLINE_EDGE_IMPROVEMENT_MIN_R_DELTA", "0.05")
)
OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR = float(
    os.getenv("OFFLINE_STARVATION_SURVIVAL_RATE_FLOOR", str(OFFLINE_THRESHOLD_AUDIT_SURVIVAL_RATE_FLOOR))
)
OFFLINE_FILTERING_WITHOUT_EDGE_WARN = os.getenv(
    "OFFLINE_FILTERING_WITHOUT_EDGE_WARN",
    "true",
).lower() == "true"
OFFLINE_THRESHOLD_TUNING_ENABLE = os.getenv("OFFLINE_THRESHOLD_TUNING_ENABLE", "false").lower() == "true"
OFFLINE_THRESHOLD_TUNING_MAX_DELTA = float(
    os.getenv("OFFLINE_THRESHOLD_TUNING_MAX_DELTA", "0.03")
)
OFFLINE_THRESHOLD_TUNING_MIN_IMPACT_SCORE = float(
    os.getenv("OFFLINE_THRESHOLD_TUNING_MIN_IMPACT_SCORE", "0.20")
)
OFFLINE_THRESHOLD_TUNING_PROTECT_SAVED_LOSS_RATE = float(
    os.getenv("OFFLINE_THRESHOLD_TUNING_PROTECT_SAVED_LOSS_RATE", "0.40")
)
OFFLINE_THRESHOLD_TUNING_STARVATION_RELIEF_ENABLE = os.getenv(
    "OFFLINE_THRESHOLD_TUNING_STARVATION_RELIEF_ENABLE",
    "true",
).lower() == "true"
OFFLINE_THRESHOLD_TRIAGE_ENABLE = os.getenv("OFFLINE_THRESHOLD_TRIAGE_ENABLE", "true").lower() == "true"
OFFLINE_THRESHOLD_TRIAGE_TOP_N = int(
    os.getenv("OFFLINE_THRESHOLD_TRIAGE_TOP_N", str(OFFLINE_REJECTION_IMPACT_TOP_N))
)
OFFLINE_THRESHOLD_TRIAGE_PROTECT_SAVED_LOSS_RATE = float(
    os.getenv("OFFLINE_THRESHOLD_TRIAGE_PROTECT_SAVED_LOSS_RATE", "0.40")
)
OFFLINE_THRESHOLD_TRIAGE_MIN_MISSED_WIN_RATE = float(
    os.getenv("OFFLINE_THRESHOLD_TRIAGE_MIN_MISSED_WIN_RATE", "0.30")
)
OFFLINE_THRESHOLD_TRIAGE_MIN_EDGE_R_DELTA = float(
    os.getenv("OFFLINE_THRESHOLD_TRIAGE_MIN_EDGE_R_DELTA", str(OFFLINE_EDGE_IMPROVEMENT_MIN_R_DELTA))
)
OFFLINE_THRESHOLD_LEARNING_ENABLE = os.getenv("OFFLINE_THRESHOLD_LEARNING_ENABLE", "false").lower() == "true"
OFFLINE_THRESHOLD_LEARNING_MIN_SAMPLES = int(
    os.getenv("OFFLINE_THRESHOLD_LEARNING_MIN_SAMPLES", "20")
)
OFFLINE_THRESHOLD_LEARNING_MAX_STEP_PCT = float(
    os.getenv("OFFLINE_THRESHOLD_LEARNING_MAX_STEP_PCT", "0.02")
)
OFFLINE_THRESHOLD_LEARNING_MAX_SCORE_ADJUSTMENT = float(
    os.getenv("OFFLINE_THRESHOLD_LEARNING_MAX_SCORE_ADJUSTMENT", "0.05")
)
OFFLINE_AGGRESSIVENESS_GUARD_ENABLE = os.getenv("OFFLINE_AGGRESSIVENESS_GUARD_ENABLE", "false").lower() == "true"
OFFLINE_AGGRESSIVENESS_MAX_THRESHOLD_SHIFT = float(
    os.getenv("OFFLINE_AGGRESSIVENESS_MAX_THRESHOLD_SHIFT", "0.01")
)
OFFLINE_AGGRESSIVENESS_TOO_TIMID_SURVIVAL_RATE = float(
    os.getenv("OFFLINE_AGGRESSIVENESS_TOO_TIMID_SURVIVAL_RATE", "0.10")
)
OFFLINE_AGGRESSIVENESS_STARVING_NO_TRADE_RATE = float(
    os.getenv("OFFLINE_AGGRESSIVENESS_STARVING_NO_TRADE_RATE", "0.70")
)
OFFLINE_AGGRESSIVENESS_OVERTRADING_SURVIVAL_RATE = float(
    os.getenv("OFFLINE_AGGRESSIVENESS_OVERTRADING_SURVIVAL_RATE", "0.50")
)
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
PREMIUM_SOFT_VETO_CONF_PENALTY_MIN = float(
    os.getenv("PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", str(max(0.0, 1.0 - PREMIUM_SOFT_VETO_CONF_MULT)))
)
PREMIUM_SOFT_VETO_CONF_PENALTY_MAX = float(
    os.getenv("PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", str(max(PREMIUM_SOFT_VETO_CONF_PENALTY_MIN, 0.12)))
)
SOFT_VETO_CONF_PENALTY_MAX_TOTAL = float(os.getenv("SOFT_VETO_CONF_PENALTY_MAX_TOTAL", "0.16"))
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
LIVE_REGIME_UNSTABLE_CONSECUTIVE_BLOCK = max(
    1,
    int(os.getenv("LIVE_REGIME_UNSTABLE_CONSECUTIVE_BLOCK", "2")),
)
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
ZERO_HERO_ALLOW_NON_EXPIRY_CONTEXT = os.getenv("ZERO_HERO_ALLOW_NON_EXPIRY_CONTEXT", "true").lower() == "true"
ZERO_HERO_NON_EXPIRY_PREMIUM_FLOOR = float(os.getenv("ZERO_HERO_NON_EXPIRY_PREMIUM_FLOOR", "15"))
ZERO_HERO_NON_EXPIRY_ENTRY_MULT = float(os.getenv("ZERO_HERO_NON_EXPIRY_ENTRY_MULT", "0.0035"))
ZERO_HERO_NON_EXPIRY_TARGET_MULT = float(os.getenv("ZERO_HERO_NON_EXPIRY_TARGET_MULT", "1.6"))
ZERO_HERO_NON_EXPIRY_STOP_MULT = float(os.getenv("ZERO_HERO_NON_EXPIRY_STOP_MULT", "0.85"))
ZERO_HERO_NON_EXPIRY_CONFIDENCE = int(os.getenv("ZERO_HERO_NON_EXPIRY_CONFIDENCE", "46"))
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
REGIME_ENTROPY_MODE = os.getenv("REGIME_ENTROPY_MODE", "normalized")
REGIME_ENTROPY_NORMALIZED_MAX_DEFAULT = float(os.getenv("REGIME_ENTROPY_NORMALIZED_MAX_DEFAULT", "0.80"))
REGIME_ENTROPY_NORMALIZED_MAX_OPEN_DISCOVERY = float(os.getenv("REGIME_ENTROPY_NORMALIZED_MAX_OPEN_DISCOVERY", "0.90"))
REGIME_ENTROPY_NORMALIZED_MAX_MID_SESSION = float(os.getenv("REGIME_ENTROPY_NORMALIZED_MAX_MID_SESSION", "0.78"))
REGIME_ENTROPY_NORMALIZED_MAX_EXPIRY_DAY = float(os.getenv("REGIME_ENTROPY_NORMALIZED_MAX_EXPIRY_DAY", "0.86"))
REGIME_ENTROPY_NORMALIZED_MAX_CLOSING_VOL = float(os.getenv("REGIME_ENTROPY_NORMALIZED_MAX_CLOSING_VOL", "0.88"))
REGIME_ENTROPY_NORMALIZED_MAX_EVENT_MODE = float(os.getenv("REGIME_ENTROPY_NORMALIZED_MAX_EVENT_MODE", "0.92"))

# Legacy values preserved for backward compat in external tests if needed
REGIME_TRANSITION_RATE_MAX = float(os.getenv("REGIME_TRANSITION_RATE_MAX", "6.0"))
# Confidence override for clearly stable regime distributions.
# Used to avoid false "unstable" when max-probability is effectively 1 and entropy is near 0.
REGIME_STABLE_PROB_OVERRIDE_MIN = float(os.getenv("REGIME_STABLE_PROB_OVERRIDE_MIN", "0.99"))
REGIME_STABLE_ENTROPY_OVERRIDE_MAX = float(os.getenv("REGIME_STABLE_ENTROPY_OVERRIDE_MAX", "0.01"))
PAPER_RELAX_GATES = os.getenv("PAPER_RELAX_GATES", "true").lower() == "true"
DECISION_DAG_ALLOW_NON_LIVE_MARKET_CLOSED = os.getenv(
    "DECISION_DAG_ALLOW_NON_LIVE_MARKET_CLOSED",
    "true",
).lower() == "true"
DECISION_DAG_ALLOW_NON_LIVE_OPTION_QUOTE_MISSING = os.getenv(
    "DECISION_DAG_ALLOW_NON_LIVE_OPTION_QUOTE_MISSING",
    "true",
).lower() == "true"
TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY = os.getenv(
    "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY",
    "true",
).lower() == "true"
TRADE_BUILDER_ALLOW_LIVE_STALE_OPTION_TICK_SOFTEN = os.getenv(
    "TRADE_BUILDER_ALLOW_LIVE_STALE_OPTION_TICK_SOFTEN",
    "true",
).lower() == "true"
TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ENABLE = os.getenv(
    "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ENABLE",
    "false",
).lower() == "true"
TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ALLOW_LIVE = os.getenv(
    "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ALLOW_LIVE",
    "false",
).lower() == "true"
TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_MAX_SEC = float(
    os.getenv("TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_MAX_SEC", "20.0")
)
TRADE_BUILDER_USE_SYMBOL_FEED_AGE_FALLBACK = os.getenv(
    "TRADE_BUILDER_USE_SYMBOL_FEED_AGE_FALLBACK",
    "true",
).lower() == "true"
TRADE_BUILDER_FEED_RUNTIME_CACHE_TTL_SEC = float(
    os.getenv("TRADE_BUILDER_FEED_RUNTIME_CACHE_TTL_SEC", "1.0")
)
TRADE_BUILDER_FEED_AGE_FALLBACK_MAX_SEC = float(
    os.getenv("TRADE_BUILDER_FEED_AGE_FALLBACK_MAX_SEC", "3.0")
)
ADVISORY_SCHEMA_STRICT_LEVEL_INVARIANTS = os.getenv(
    "ADVISORY_SCHEMA_STRICT_LEVEL_INVARIANTS",
    "true",
).lower() == "true"
ADVISORY_OPTION_STOP_TIGHTEN_ENABLE = os.getenv(
    "ADVISORY_OPTION_STOP_TIGHTEN_ENABLE",
    "true",
).lower() == "true"
ADVISORY_OPTION_STOP_MAX_PCT = _float_env("ADVISORY_OPTION_STOP_MAX_PCT", 0.35)
ADVISORY_OPTION_STOP_MIN_PCT = _float_env("ADVISORY_OPTION_STOP_MIN_PCT", 0.1)
ADVISORY_OPTION_STOP_SPREAD_MULT = _float_env("ADVISORY_OPTION_STOP_SPREAD_MULT", 2.0)
ADVISORY_OPTION_STOP_MAX_ABS = _float_env("ADVISORY_OPTION_STOP_MAX_ABS", None)
ADVISORY_OPTION_STOP_MIN_ABS = _float_env("ADVISORY_OPTION_STOP_MIN_ABS", None)
ADVISORY_INSTRUMENT_TYPE_ASSUME_OPT_CANDIDATE_TYPES = os.getenv(
    "ADVISORY_INSTRUMENT_TYPE_ASSUME_OPT_CANDIDATE_TYPES",
    "directional,breakout,momentum",
)
ADVISORY_INSTRUMENT_TYPE_FALLBACK = os.getenv("ADVISORY_INSTRUMENT_TYPE_FALLBACK", "UNKNOWN")
ADVISORY_OPTION_TYPE_FALLBACK = os.getenv("ADVISORY_OPTION_TYPE_FALLBACK", "CE")
ADVISORY_HIDE_UNKNOWN_INSTRUMENT = os.getenv("ADVISORY_HIDE_UNKNOWN_INSTRUMENT", "true").lower() == "true"
PREMIUM_BAND_DTE1_THRESHOLD = int(os.getenv("PREMIUM_BAND_DTE1_THRESHOLD", "1"))
PREMIUM_BAND_DTE1_MIN_MULT = _float_env("PREMIUM_BAND_DTE1_MIN_MULT", 0.6)
PREMIUM_BAND_DTE1_MAX_MULT = _float_env("PREMIUM_BAND_DTE1_MAX_MULT", 0.8)
PREMIUM_BAND_HIGH_VOL_MAX_MULT = _float_env("PREMIUM_BAND_HIGH_VOL_MAX_MULT", 1.35)
PREMIUM_BAND_TIGHT_SPREAD_PCT = _float_env("PREMIUM_BAND_TIGHT_SPREAD_PCT", 0.8)
PREMIUM_BAND_TIGHT_SPREAD_MAX_MULT = _float_env("PREMIUM_BAND_TIGHT_SPREAD_MAX_MULT", 1.15)
PREMIUM_BAND_HARD_REJECT_ENABLE = os.getenv("PREMIUM_BAND_HARD_REJECT_ENABLE", "false").lower() == "true"
ZERO_TO_HERO_PREMIUM_FALLBACK_LOW = _float_env("ZERO_TO_HERO_PREMIUM_FALLBACK_LOW", 10.0)
ZERO_TO_HERO_PREMIUM_FALLBACK_HIGH = _float_env("ZERO_TO_HERO_PREMIUM_FALLBACK_HIGH", 120.0)
LATENCY_GUARD_ALLOW_ADVISORY = os.getenv("LATENCY_GUARD_ALLOW_ADVISORY", "true").lower() == "true"
LATENCY_GUARD_LIVE_SKIP_TRADE_BUILDER = (
    os.getenv("LATENCY_GUARD_LIVE_SKIP_TRADE_BUILDER", "true").lower() == "true"
)
LATENCY_SOFT_PENALTY = _float_env("LATENCY_SOFT_PENALTY", 0.25)
LATENCY_SOFTEN_PRESERVE_STRATEGY_FAMILY = os.getenv(
    "LATENCY_SOFTEN_PRESERVE_STRATEGY_FAMILY",
    "true",
).lower() == "true"
LATENCY_SOFTEN_LOG_SAMPLE_LIMIT = int(os.getenv("LATENCY_SOFTEN_LOG_SAMPLE_LIMIT", "5"))
LATENCY_GUARD_ADVISORY_COOLDOWN_SEC = int(os.getenv("LATENCY_GUARD_ADVISORY_COOLDOWN_SEC", "60"))
STARTUP_STALE_LOCK_RECOVERY_ENABLE = os.getenv(
    "STARTUP_STALE_LOCK_RECOVERY_ENABLE", "true"
).strip().lower() in {"1", "true", "yes", "on"}

# Minimum candidate breadth (advisory backfill) before ranking.
CANDIDATE_BREADTH_MIN = int(os.getenv("CANDIDATE_BREADTH_MIN", "1"))
CANDIDATE_BREADTH_MIN_LIVE = int(os.getenv("CANDIDATE_BREADTH_MIN_LIVE", "0"))
MIN_CANDIDATES_PER_SYMBOL = int(os.getenv("MIN_CANDIDATES_PER_SYMBOL", str(CANDIDATE_BREADTH_MIN)))
MIN_CANDIDATES_PER_SYMBOL_LIVE = int(os.getenv("MIN_CANDIDATES_PER_SYMBOL_LIVE", str(CANDIDATE_BREADTH_MIN_LIVE)))
MIN_BREADTH_FALLBACK_ENABLE = os.getenv("MIN_BREADTH_FALLBACK_ENABLE", "true").lower() == "true"
MIN_BREADTH_FALLBACK_CONFIDENCE = _float_env("MIN_BREADTH_FALLBACK_CONFIDENCE", 0.12)
MIN_BREADTH_FALLBACK_MAX_PER_SYMBOL = int(os.getenv("MIN_BREADTH_FALLBACK_MAX_PER_SYMBOL", "4"))
MIN_BREADTH_USE_NEAREST_STRIKES = os.getenv("MIN_BREADTH_USE_NEAREST_STRIKES", "true").lower() == "true"
MIN_BREADTH_DIRECTION_INFERENCE_ENABLE = os.getenv(
    "MIN_BREADTH_DIRECTION_INFERENCE_ENABLE",
    "true",
).lower() == "true"
 
# -------------------------------
# Candidate soft-reject policy
# -------------------------------
CANDIDATE_SOFT_REJECT_ENABLE = os.getenv("CANDIDATE_SOFT_REJECT_ENABLE", "true").lower() == "true"
CANDIDATE_SOFT_REJECT_ALLOW_LIVE = os.getenv("CANDIDATE_SOFT_REJECT_ALLOW_LIVE", "false").lower() == "true"
CANDIDATE_SOFT_REJECT_MAX_PER_SYMBOL = int(os.getenv("CANDIDATE_SOFT_REJECT_MAX_PER_SYMBOL", "3"))
CANDIDATE_SOFT_REJECT_CONFIDENCE = _float_env("CANDIDATE_SOFT_REJECT_CONFIDENCE", 0.1)
CANDIDATE_SOFT_REJECT_UNKNOWN_CONFIDENCE = _float_env("CANDIDATE_SOFT_REJECT_UNKNOWN_CONFIDENCE", 0.08)
CANDIDATE_SOFT_REJECT_ALLOW_UNKNOWN_CRITICAL = os.getenv(
    "CANDIDATE_SOFT_REJECT_ALLOW_UNKNOWN_CRITICAL",
    "false",
).lower() == "true"
CANDIDATE_SOFT_REJECT_CONF_MIN = _float_env("CANDIDATE_SOFT_REJECT_CONF_MIN", 0.05)
CANDIDATE_SOFT_REJECT_PENALTY_PREMIUM = _float_env("CANDIDATE_SOFT_REJECT_PENALTY_PREMIUM", 0.05)
CANDIDATE_SOFT_REJECT_PENALTY_SPREAD = _float_env("CANDIDATE_SOFT_REJECT_PENALTY_SPREAD", 0.07)
CANDIDATE_SOFT_REJECT_PENALTY_LATENCY = _float_env("CANDIDATE_SOFT_REJECT_PENALTY_LATENCY", 0.1)
CANDIDATE_SOFT_REJECT_RECOVERABLE_REASONS = os.getenv(
    "CANDIDATE_SOFT_REJECT_RECOVERABLE_REASONS",
    "no_signal,weak_signal,no_candidates_survived,latency_guard_cooldown,regime_unstable",
)
CANDIDATE_SOFT_REJECT_CRITICAL_REASONS = os.getenv(
    "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS",
    "missing_symbol,missing_instrument_id,malformed_option_row,invalid_symbol,invalid_trade,unresolved_contract,auth_required",
)
SOFT_REJECT_STRATEGY_FAMILY_FALLBACK = os.getenv(
    "SOFT_REJECT_STRATEGY_FAMILY_FALLBACK",
    "breakout",
).strip().lower() or "breakout"
PAPER_REGIME_PROB_MIN = float(os.getenv("PAPER_REGIME_PROB_MIN", "0.30"))
PAPER_REGIME_ENTROPY_NORMALIZED_MAX = float(os.getenv("PAPER_REGIME_ENTROPY_NORMALIZED_MAX", "0.95"))
REGIME_CANDIDATE_ENTROPY_SOFT_PENALTY = float(
    os.getenv("REGIME_CANDIDATE_ENTROPY_SOFT_PENALTY", "0.08")
)
PAPER_NEUTRAL_FAMILY = os.getenv("PAPER_NEUTRAL_FAMILY", "DEFINED_RISK").upper()
# Paper/SIM-only soft unblock for non-contradictory regime instability.
PAPER_SOFT_UNBLOCK_ENABLE = os.getenv("PAPER_SOFT_UNBLOCK_ENABLE", "true").lower() == "true"
PAPER_SOFT_UNBLOCK_CONF_MIN = float(os.getenv("PAPER_SOFT_UNBLOCK_CONF_MIN", "0.80"))
PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS = [
    s.strip()
    for s in os.getenv("PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS", "entropy_too_high,prob_too_low").split(",")
    if s.strip()
]
# Regime monitor reliability guard.
REGIME_MONITOR_ENABLED = os.getenv("REGIME_MONITOR_ENABLED", "true").lower() == "true"
REGIME_MONITOR_WINDOW_SIZE = int(os.getenv("REGIME_MONITOR_WINDOW_SIZE", "120"))
REGIME_MONITOR_MIN_SAMPLES = int(os.getenv("REGIME_MONITOR_MIN_SAMPLES", "24"))
REGIME_MONITOR_COLLAPSE_ACCURACY_MIN = float(os.getenv("REGIME_MONITOR_COLLAPSE_ACCURACY_MIN", "0.45"))
REGIME_MONITOR_SEVERE_ACCURACY_MIN = float(os.getenv("REGIME_MONITOR_SEVERE_ACCURACY_MIN", "0.30"))
REGIME_MONITOR_COLLAPSE_CORR_MIN = float(os.getenv("REGIME_MONITOR_COLLAPSE_CORR_MIN", "-0.10"))
REGIME_MONITOR_SEVERE_WINDOWS = int(os.getenv("REGIME_MONITOR_SEVERE_WINDOWS", "3"))
REGIME_MONITOR_TREND_MOVE_MIN = float(os.getenv("REGIME_MONITOR_TREND_MOVE_MIN", "0.0007"))
REGIME_MONITOR_RANGE_MOVE_MAX = float(os.getenv("REGIME_MONITOR_RANGE_MOVE_MAX", "0.0008"))
REGIME_MONITOR_EVENT_MOVE_MIN = float(os.getenv("REGIME_MONITOR_EVENT_MOVE_MIN", "0.0015"))
REGIME_MONITOR_NEUTRAL_MOVE_MAX = float(os.getenv("REGIME_MONITOR_NEUTRAL_MOVE_MAX", "0.0010"))
REGIME_MONITOR_BLOCK_ON_COLLAPSE = os.getenv("REGIME_MONITOR_BLOCK_ON_COLLAPSE", "true").lower() == "true"
REGIME_MONITOR_SIZE_MULT_ON_COLLAPSE = float(os.getenv("REGIME_MONITOR_SIZE_MULT_ON_COLLAPSE", "0.50"))
REGIME_MONITOR_P0_ON_SEVERE = os.getenv("REGIME_MONITOR_P0_ON_SEVERE", "true").lower() == "true"
REGIME_DEPENDENT_STRATEGY_HINTS = [
    s.strip().upper()
    for s in os.getenv(
        "REGIME_DEPENDENT_STRATEGY_HINTS",
        "TREND,EVENT,RANGE,MEAN,ORB,VWAP,MICRO",
    ).split(",")
    if s.strip()
]
REGIME_MONITOR_STATUS_PATH = os.getenv("REGIME_MONITOR_STATUS_PATH", f"{LOGS_ROOT}/regime_monitor_status.json")
REGIME_MONITOR_LOG_PATH = os.getenv("REGIME_MONITOR_LOG_PATH", f"{LOGS_ROOT}/regime_monitor.jsonl")

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
EXPIRY_LOTTO_MODE = os.getenv("EXPIRY_LOTTO_MODE", "false").lower() == "true"
EXPIRY_LOTTO_TARGET_CANDIDATES = int(os.getenv("EXPIRY_LOTTO_TARGET_CANDIDATES", "4"))
EXPIRY_LOTTO_ATM_STRIKES = int(os.getenv("EXPIRY_LOTTO_ATM_STRIKES", "2"))
try:
    _expiry_lotto_steps_raw = os.getenv(
        "EXPIRY_LOTTO_ATM_STRIKES_BY_SYMBOL",
        '{"NIFTY": 6, "BANKNIFTY": 6, "SENSEX": 4}',
    )
    _expiry_lotto_steps = json.loads(_expiry_lotto_steps_raw)
except Exception:
    _expiry_lotto_steps = {"NIFTY": 6, "BANKNIFTY": 6, "SENSEX": 4}
EXPIRY_LOTTO_ATM_STRIKES_BY_SYMBOL = (
    _expiry_lotto_steps if isinstance(_expiry_lotto_steps, dict) else {"NIFTY": 6, "BANKNIFTY": 6, "SENSEX": 4}
)
EXPIRY_LOTTO_MAX_TRADES = int(os.getenv("EXPIRY_LOTTO_MAX_TRADES", "4"))
EXPIRY_LOTTO_MAX_LOSS_PER_TRADE = float(os.getenv("EXPIRY_LOTTO_MAX_LOSS_PER_TRADE", "1500"))
EXPIRY_LOTTO_MAX_SPREAD_PCT = float(os.getenv("EXPIRY_LOTTO_MAX_SPREAD_PCT", "0.35"))
EXPIRY_LOTTO_MIN_MOMENTUM_ATR = float(os.getenv("EXPIRY_LOTTO_MIN_MOMENTUM_ATR", "0.10"))
EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM = os.getenv("EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM", "true").lower() == "true"
EXPIRY_LOTTO_MIN_OPTION_TOKENS = int(os.getenv("EXPIRY_LOTTO_MIN_OPTION_TOKENS", "12"))
MIN_OPTION_TOKENS = int(os.getenv("MIN_OPTION_TOKENS", "12"))
MIN_OPTION_TOKEN_COUNT = int(os.getenv("MIN_OPTION_TOKEN_COUNT", "50"))
OPTION_TOKEN_INCIDENT_COOLDOWN_SEC = float(os.getenv("OPTION_TOKEN_INCIDENT_COOLDOWN_SEC", "300"))
OPTION_TOKEN_RESOLVER_CACHE_TTL_SEC = int(
    os.getenv("OPTION_TOKEN_RESOLVER_CACHE_TTL_SEC", str(os.getenv("KITE_INSTRUMENTS_TTL", "3600")))
)

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
ZERO_HERO_EXPIRY_TIME_HARD_CUTOFF_MIN = int(os.getenv("ZERO_HERO_EXPIRY_TIME_HARD_CUTOFF_MIN", "150"))
ZERO_HERO_EXPIRY_MAX_TRADES = int(os.getenv("ZERO_HERO_EXPIRY_MAX_TRADES", "2"))
ZERO_HERO_IVCRUSH_MIN = float(os.getenv("ZERO_HERO_IVCRUSH_MIN", "0.20"))
ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS = float(os.getenv("ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", "6"))
ZERO_HERO_EXPIRY_SOFT_MOMENTUM_RATIO = float(os.getenv("ZERO_HERO_EXPIRY_SOFT_MOMENTUM_RATIO", "0.65"))
ZERO_HERO_EXPIRY_SOFT_DELTA_MARGIN = float(os.getenv("ZERO_HERO_EXPIRY_SOFT_DELTA_MARGIN", "0.08"))
ZERO_HERO_EXPIRY_SOFT_IV_MARGIN = float(os.getenv("ZERO_HERO_EXPIRY_SOFT_IV_MARGIN", "0.03"))
ZERO_HERO_EXPIRY_SOFT_TTE_MARGIN_HRS = float(os.getenv("ZERO_HERO_EXPIRY_SOFT_TTE_MARGIN_HRS", "1.5"))
ZERO_HERO_EXPIRY_PREMIUM_SOFT_MARGIN_RATIO = float(
    os.getenv("ZERO_HERO_EXPIRY_PREMIUM_SOFT_MARGIN_RATIO", "0.20")
)
ZERO_HERO_EXPIRY_SPREAD_HARD_PCT = float(os.getenv("ZERO_HERO_EXPIRY_SPREAD_HARD_PCT", "0.45"))
ZERO_HERO_EXPIRY_WINDOW_DAYS = int(os.getenv("ZERO_HERO_EXPIRY_WINDOW_DAYS", "1"))

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
NONLIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD = (
    os.getenv("NONLIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", "true").lower() == "true"
)
LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD = (
    os.getenv("LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", "false").lower() == "true"
)
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
MICRO_CONF_OVERLAY_WEIGHT = float(os.getenv("MICRO_CONF_OVERLAY_WEIGHT", "0.25"))
MICRO_CONF_OVERLAY_MAX_DELTA = float(os.getenv("MICRO_CONF_OVERLAY_MAX_DELTA", "0.10"))
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
USE_DECISION_SNAPSHOT = os.getenv("USE_DECISION_SNAPSHOT", "false").lower() == "true"
DECISION_SNAPSHOT_INDEX_MAX_AGE_MS = float(os.getenv("DECISION_SNAPSHOT_INDEX_MAX_AGE_MS", "1500"))
DECISION_SNAPSHOT_OPTION_MAX_AGE_MS = float(os.getenv("DECISION_SNAPSHOT_OPTION_MAX_AGE_MS", "1500"))

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
TRADE_DB_TIMEOUT_SEC = float(os.getenv("TRADE_DB_TIMEOUT_SEC", "10.0"))
TRADE_DB_ENABLE_WAL = os.getenv("TRADE_DB_ENABLE_WAL", "true").lower() == "true"
TRADE_DB_BUSY_TIMEOUT_MS = int(os.getenv("TRADE_DB_BUSY_TIMEOUT_MS", "10000"))
TRADE_DB_SYNCHRONOUS = os.getenv("TRADE_DB_SYNCHRONOUS", "NORMAL").upper()
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
ORDER_INTENT_STORE_PATH = os.getenv("ORDER_INTENT_STORE_PATH", f"{DESK_LOG_DIR}/order_intents.sqlite")
DECISION_TELEMETRY_ENABLE = os.getenv("DECISION_TELEMETRY_ENABLE", "true").lower() == "true"
REJECT_TELEMETRY_ENABLE = os.getenv("REJECT_TELEMETRY_ENABLE", "true").lower() == "true"
REJECT_TELEMETRY_MAX_IN_MEMORY = int(os.getenv("REJECT_TELEMETRY_MAX_IN_MEMORY", "500"))
REJECT_TELEMETRY_LOG_DIR = os.getenv(
    "REJECT_TELEMETRY_LOG_DIR",
    f"{DESK_LOG_DIR}/reject_telemetry",
)
REJECT_SHADOW_ENABLE = os.getenv("REJECT_SHADOW_ENABLE", "true").lower() == "true"
REJECT_SHADOW_TABLE = os.getenv("REJECT_SHADOW_TABLE", "reject_shadow")
REJECT_SHADOW_HORIZON_MIN = int(os.getenv("REJECT_SHADOW_HORIZON_MIN", "30"))
REJECT_SHADOW_EVAL_INTERVAL_SEC = float(os.getenv("REJECT_SHADOW_EVAL_INTERVAL_SEC", "30"))
REJECT_SHADOW_EVAL_BATCH_SIZE = int(os.getenv("REJECT_SHADOW_EVAL_BATCH_SIZE", "200"))
REJECT_SHADOW_JSONL_PATH = os.getenv("REJECT_SHADOW_JSONL_PATH", f"{DESK_LOG_DIR}/reject_shadow.jsonl")
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
READINESS_DECISION_MAX_AGE_SEC = float(os.getenv("READINESS_DECISION_MAX_AGE_SEC", "240"))
# Guard against stale decision rows pinning feed_stale when feed runtime has recovered.
READINESS_DECISION_FEED_STALE_MAX_AGE_SEC = float(
    os.getenv("READINESS_DECISION_FEED_STALE_MAX_AGE_SEC", "45")
)
# Backward-compatible alias for older callers/tests.
READINESS_DECISION_ENGINE_ACTIVE_SEC = float(
    os.getenv("READINESS_DECISION_ENGINE_ACTIVE_SEC", str(READINESS_DECISION_MAX_AGE_SEC))
)
READINESS_REQUIRE_KITE_AUTH = os.getenv("READINESS_REQUIRE_KITE_AUTH", "true").lower() == "true"
READINESS_REQUIRE_FEED_HEALTH = os.getenv("READINESS_REQUIRE_FEED_HEALTH", "true").lower() == "true"
READINESS_REQUIRE_AUDIT_CHAIN = os.getenv("READINESS_REQUIRE_AUDIT_CHAIN", "true").lower() == "true"
READINESS_REQUIRE_RISK_HALT_CLEAR = os.getenv("READINESS_REQUIRE_RISK_HALT_CLEAR", "true").lower() == "true"
READINESS_ALLOW_RISK_HALT_MONITORING_STARTUP = (
    os.getenv("READINESS_ALLOW_RISK_HALT_MONITORING_STARTUP", "true").lower() == "true"
)
READINESS_REQUIRE_TRADE_SCHEMA = os.getenv("READINESS_REQUIRE_TRADE_SCHEMA", "true").lower() == "true"
READINESS_ENFORCE_ON_EXEC = os.getenv("READINESS_ENFORCE_ON_EXEC", "true").lower() == "true"
READINESS_ENFORCE_PAPER = os.getenv("READINESS_ENFORCE_PAPER", "false").lower() == "true"
READINESS_FEED_RUNTIME_MAX_AGE_SEC = float(os.getenv("READINESS_FEED_RUNTIME_MAX_AGE_SEC", "60"))
READINESS_STATE_STALE_MARGIN_SEC = float(os.getenv("READINESS_STATE_STALE_MARGIN_SEC", "1.0"))
ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK = (
    os.getenv("ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK", "true").lower() == "true"
)
STARTUP_READINESS_BREAKER_GRACE_ENABLE = (
    os.getenv("STARTUP_READINESS_BREAKER_GRACE_ENABLE", "true").lower() == "true"
)
STARTUP_READINESS_BREAKER_GRACE_SEC = float(os.getenv("STARTUP_READINESS_BREAKER_GRACE_SEC", "30"))
STARTUP_READINESS_BREAKER_POLL_SEC = float(os.getenv("STARTUP_READINESS_BREAKER_POLL_SEC", "1"))
READINESS_GLOBAL_ABORT_BLOCKERS = [
    s.strip().lower()
    for s in os.getenv(
        "READINESS_GLOBAL_ABORT_BLOCKERS",
        ",".join(
            [
                "risk_halt_active",
                "feed_circuit_breaker_tripped",
                "disk_low",
                "missing_desk_id",
                "missing_trade_db_path",
                "missing_symbols",
            ]
        ),
    ).split(",")
    if s.strip()
]
READINESS_GLOBAL_ABORT_PREFIXES = [
    s.strip().lower()
    for s in os.getenv(
        "READINESS_GLOBAL_ABORT_PREFIXES",
        ",".join(
            [
                "audit_chain:",
                "profile_error",
                "auth_",
                "kite_auth",
                "trade_identity_schema",
                "trade_schema",
            ]
        ),
    ).split(",")
    if s.strip()
]
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
AUTO_CLEAR_RISK_HALT_ALLOW_MARKET_OPEN_IF_FLAT = (
    os.getenv("AUTO_CLEAR_RISK_HALT_ALLOW_MARKET_OPEN_IF_FLAT", "true").lower() == "true"
)
AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE = (
    os.getenv("AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE", "true").lower() == "true"
)
AUTO_CLEAR_SLO_FAILOVER_RUNTIME_OK_STREAK = int(
    os.getenv("AUTO_CLEAR_SLO_FAILOVER_RUNTIME_OK_STREAK", "2")
)
AUTO_CLEAR_SLO_FAILOVER_RUNTIME_MAX_OPEN_POSITIONS = int(
    os.getenv("AUTO_CLEAR_SLO_FAILOVER_RUNTIME_MAX_OPEN_POSITIONS", "0")
)
AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ALLOWED_REASONS = [
    s.strip().upper()
    for s in os.getenv(
        "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ALLOWED_REASONS",
        "AUTH_LATENCY_BREACH",
    ).split(",")
    if s.strip()
]

# Pre-open auth warmup
AUTH_WARMUP_TRIGGER_RISK_HALT = os.getenv("AUTH_WARMUP_TRIGGER_RISK_HALT", "true").lower() == "true"
AUTH_WARMUP_LOG_PATH = os.getenv("AUTH_WARMUP_LOG_PATH", f"{LOGS_ROOT}/auth_warmup.json")
AUTH_HEALTH_TTL_SEC = float(os.getenv("AUTH_HEALTH_TTL_SEC", "60"))
KITE_AUTH_RETRY_ATTEMPTS = int(os.getenv("KITE_AUTH_RETRY_ATTEMPTS", "2"))
KITE_AUTH_RETRY_BACKOFF_SEC = float(os.getenv("KITE_AUTH_RETRY_BACKOFF_SEC", "0.8"))
KITE_HISTORICAL_AUTH_COOLDOWN_SEC = float(os.getenv("KITE_HISTORICAL_AUTH_COOLDOWN_SEC", "300"))
KITE_GENERATE_SESSION_RETRY_ATTEMPTS = int(
    os.getenv("KITE_GENERATE_SESSION_RETRY_ATTEMPTS", str(KITE_AUTH_RETRY_ATTEMPTS))
)
KITE_GENERATE_SESSION_RETRY_BACKOFF_SEC = float(
    os.getenv("KITE_GENERATE_SESSION_RETRY_BACKOFF_SEC", str(KITE_AUTH_RETRY_BACKOFF_SEC))
)
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
FEED_FRESHNESS_RUNTIME_SNAPSHOT_ENABLE = (
    os.getenv("FEED_FRESHNESS_RUNTIME_SNAPSHOT_ENABLE", "true").lower() == "true"
)
RUNTIME_SNAPSHOT_JSONL_TAIL_BYTES = int(os.getenv("RUNTIME_SNAPSHOT_JSONL_TAIL_BYTES", "65536"))
RUNTIME_SNAPSHOT_WRITE_DEDUP_ENABLE = (
    os.getenv("RUNTIME_SNAPSHOT_WRITE_DEDUP_ENABLE", "true").lower() == "true"
)
# Prefer in-memory tick evidence (WS tick store) for freshness SLA and decision gating.
# SQLite is used as a best-effort fallback only to avoid lock contention stalls in LIVE.
FEED_FRESHNESS_PREFER_TICKSTORE_MEMORY = (
    os.getenv("FEED_FRESHNESS_PREFER_TICKSTORE_MEMORY", "true").lower() == "true"
)
# Freshness SLA should not fail closed just because some subscribed option tokens are sparse.
# We treat the feed as unhealthy only when a large fraction of tracked tokens are stale.
FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO = float(os.getenv("FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO", "0.5"))
FEED_FRESHNESS_STALE_TOKEN_MIN_COUNT = int(os.getenv("FEED_FRESHNESS_STALE_TOKEN_MIN_COUNT", "5"))
# By default, the unscoped/global feed freshness check uses only index/underlying tokens.
# Option tokens are naturally sparse and should not drive a global fail-closed decision.
FEED_FRESHNESS_UNSCOPED_INDEX_ONLY = os.getenv("FEED_FRESHNESS_UNSCOPED_INDEX_ONLY", "true").lower() == "true"

# Index REST quote refresh (kite.quote) can stall and must never block the LIVE decision loop.
# When enabled, REST refresh is best-effort in a background thread; market data uses WS/synthetic quotes immediately.
INDEX_REST_QUOTE_REFRESH_ASYNC = os.getenv("INDEX_REST_QUOTE_REFRESH_ASYNC", "true").lower() == "true"
INDEX_REST_QUOTE_REFRESH_ASYNC_MAX_WORKERS = int(os.getenv("INDEX_REST_QUOTE_REFRESH_ASYNC_MAX_WORKERS", "1"))

# Option-chain should use WS ticks/depth instead of synchronous REST quote calls in LIVE.
OPTION_CHAIN_LIVE_USE_WS_QUOTES = os.getenv("OPTION_CHAIN_LIVE_USE_WS_QUOTES", "true").lower() == "true"
# Stale option subscription pruning must never starve the decision engine.
# When enabled, we keep at least the full resolved window size per symbol (ATM +/- strikes).
FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_USE_RESOLVED_COUNT = (
    os.getenv("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_USE_RESOLVED_COUNT", "true").lower() == "true"
)
FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR = int(
    os.getenv("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR", "14")
)
FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR_BY_SYMBOL = json.loads(
    os.getenv("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR_BY_SYMBOL", "{}")
    or "{}"
)
# Prune policy: avoid churn when ticks are merely sparse (3-6s is common intraday on some strikes).
# This impacts only the subscription universe; execution still requires fresh quotes via decision gates.
FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC = float(
    os.getenv("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", "12.0")
)
# Require a token to be stale for N consecutive prune evaluations before pruning it.
FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS = int(
    os.getenv("FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", "3")
)
# Stale-subscription refresh considers a symbol urgent when its max age exceeds this threshold.
FEED_STALE_OPTION_SUBSCRIPTION_URGENT_MAX_AGE_SEC = float(
    os.getenv("FEED_STALE_OPTION_SUBSCRIPTION_URGENT_MAX_AGE_SEC", "8.0")
)
FEED_BREAKER_MAX_BLOCK_TIME_SEC = float(os.getenv("FEED_BREAKER_MAX_BLOCK_TIME_SEC", "30"))
CHAIN_MAX_MISSING_IV_PCT = float(os.getenv("CHAIN_MAX_MISSING_IV_PCT", "0.2"))
CHAIN_MAX_MISSING_QUOTE_PCT = float(os.getenv("CHAIN_MAX_MISSING_QUOTE_PCT", "0.2"))

# Circuit breaker + run lock hardening
CB_ERROR_STORM_N = int(os.getenv("CB_ERROR_STORM_N", "5"))
CB_ERROR_STORM_MINS = float(os.getenv("CB_ERROR_STORM_MINS", "5"))
CB_HALT_MINS = float(os.getenv("CB_HALT_MINS", "15"))
CB_FEED_UNHEALTHY_SEC = float(os.getenv("CB_FEED_UNHEALTHY_SEC", "120"))
DECISION_BREAKERS_ENABLE = os.getenv("DECISION_BREAKERS_ENABLE", "true").lower() == "true"
BREAKER_STALE_FEED_WINDOW_SEC = float(os.getenv("BREAKER_STALE_FEED_WINDOW_SEC", "90"))
BREAKER_STALE_FEED_MIN_SAMPLES = int(os.getenv("BREAKER_STALE_FEED_MIN_SAMPLES", "3"))
BREAKER_STALE_FEED_TRIP_RATIO = float(os.getenv("BREAKER_STALE_FEED_TRIP_RATIO", "0.6"))
BREAKER_STALE_FEED_CLEAR_RATIO = float(os.getenv("BREAKER_STALE_FEED_CLEAR_RATIO", "0.2"))
BREAKER_STALE_FEED_COOLDOWN_SEC = float(os.getenv("BREAKER_STALE_FEED_COOLDOWN_SEC", "45"))
BREAKER_STALE_FEED_MAX_TICK_AGE_SEC = float(
    os.getenv("BREAKER_STALE_FEED_MAX_TICK_AGE_SEC", os.getenv("SLA_MAX_LTP_AGE_SEC", "2.5"))
)
BREAKER_STALE_FEED_MIN_FRESH_RATIO = float(os.getenv("BREAKER_STALE_FEED_MIN_FRESH_RATIO", "0.5"))
BREAKER_PRICE_MISMATCH_WINDOW_SEC = float(os.getenv("BREAKER_PRICE_MISMATCH_WINDOW_SEC", "120"))
BREAKER_PRICE_MISMATCH_MIN_SAMPLES = int(os.getenv("BREAKER_PRICE_MISMATCH_MIN_SAMPLES", "5"))
BREAKER_PRICE_MISMATCH_TRIP_RATIO = float(os.getenv("BREAKER_PRICE_MISMATCH_TRIP_RATIO", "0.7"))
BREAKER_PRICE_MISMATCH_CLEAR_RATIO = float(os.getenv("BREAKER_PRICE_MISMATCH_CLEAR_RATIO", "0.25"))
BREAKER_PRICE_MISMATCH_COOLDOWN_SEC = float(os.getenv("BREAKER_PRICE_MISMATCH_COOLDOWN_SEC", "60"))
ISSUE_POLICY_PRICE_MISMATCH_ABS_TOL = float(os.getenv("ISSUE_POLICY_PRICE_MISMATCH_ABS_TOL", "5.0"))
ISSUE_POLICY_PRICE_MISMATCH_PCT_TOL = float(os.getenv("ISSUE_POLICY_PRICE_MISMATCH_PCT_TOL", "0.03"))
BREAKER_BROKER_FAILURE_WINDOW_SEC = float(os.getenv("BREAKER_BROKER_FAILURE_WINDOW_SEC", "180"))
BREAKER_BROKER_FAILURE_MIN_SAMPLES = int(os.getenv("BREAKER_BROKER_FAILURE_MIN_SAMPLES", "3"))
BREAKER_BROKER_FAILURE_TRIP_RATIO = float(os.getenv("BREAKER_BROKER_FAILURE_TRIP_RATIO", "0.5"))
BREAKER_BROKER_FAILURE_CLEAR_RATIO = float(os.getenv("BREAKER_BROKER_FAILURE_CLEAR_RATIO", "0.1"))
BREAKER_BROKER_FAILURE_COOLDOWN_SEC = float(os.getenv("BREAKER_BROKER_FAILURE_COOLDOWN_SEC", "120"))
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
# Execution safety toggles for option-chain overfiltering.
OPTION_IV_BOUNDS_HARD_REJECT = os.getenv("OPTION_IV_BOUNDS_HARD_REJECT", "false").lower() == "true"
OPTION_IV_SKEW_CURVATURE_HARD_REJECT = os.getenv("OPTION_IV_SKEW_CURVATURE_HARD_REJECT", "false").lower() == "true"
OPTION_IV_SKEW_CURVE_HARD_REJECT = os.getenv("OPTION_IV_SKEW_CURVE_HARD_REJECT", "false").lower() == "true"

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
OUTCOME_LABEL_THESIS_INVALIDATED_SECONDS = float(os.getenv("OUTCOME_LABEL_THESIS_INVALIDATED_SECONDS", "900"))
OUTCOME_LABEL_POOR_FILL_QUALITY_RISK_FRACTION = float(
    os.getenv("OUTCOME_LABEL_POOR_FILL_QUALITY_RISK_FRACTION", "0.5")
)

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
# Exit intelligence (active-position management; entry logic unchanged)
EXIT_INTEL_ENABLED = os.getenv("EXIT_INTEL_ENABLED", "true").lower() == "true"
EXIT_INTEL_ACTION_COOLDOWN_SEC = float(os.getenv("EXIT_INTEL_ACTION_COOLDOWN_SEC", "15"))
EXIT_INTEL_MAX_QUOTE_AGE_SEC = float(os.getenv("EXIT_INTEL_MAX_QUOTE_AGE_SEC", "2.5"))
EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT = float(os.getenv("EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT", "0.01"))
EXIT_INTEL_BREAK_EVEN_BUFFER_PCT = float(os.getenv("EXIT_INTEL_BREAK_EVEN_BUFFER_PCT", "0.0005"))
EXIT_INTEL_TRAIL_USE_ATR = os.getenv("EXIT_INTEL_TRAIL_USE_ATR", "true").lower() == "true"
EXIT_INTEL_TRAIL_ATR_MULT = float(os.getenv("EXIT_INTEL_TRAIL_ATR_MULT", "0.8"))
EXIT_INTEL_TRAIL_OFFSET_PCT = float(os.getenv("EXIT_INTEL_TRAIL_OFFSET_PCT", "0.005"))
EXIT_INTEL_TRAIL_STEP_PCT = float(os.getenv("EXIT_INTEL_TRAIL_STEP_PCT", "0.002"))
EXIT_INTEL_STALL_TARGET_PCT = float(os.getenv("EXIT_INTEL_STALL_TARGET_PCT", "0.90"))
EXIT_INTEL_STALL_SECONDS = float(os.getenv("EXIT_INTEL_STALL_SECONDS", "45"))
EXIT_INTEL_STALL_MOMENTUM_BREAK = float(os.getenv("EXIT_INTEL_STALL_MOMENTUM_BREAK", "-0.001"))
EXIT_INTEL_STALL_ACTION = os.getenv("EXIT_INTEL_STALL_ACTION", "PARTIAL_EXIT").upper()
EXIT_INTEL_PARTIAL_EXIT_FRACTION = float(os.getenv("EXIT_INTEL_PARTIAL_EXIT_FRACTION", "0.5"))
EXECUTION_OPTIMIZER_ENABLE = os.getenv("EXECUTION_OPTIMIZER_ENABLE", "true").lower() == "true"
EXIT_INTEL_LOG_PATH = str(
    Path(os.getenv("EXIT_INTEL_LOG_PATH", str(Path(DESK_LOG_DIR) / "exit_intelligence_actions.jsonl")))
)
POSITION_STATE_ENGINE_ENABLE = os.getenv("POSITION_STATE_ENGINE_ENABLE", "true").lower() == "true"
POSITION_STATE_STORE_PATH = str(
    Path(os.getenv("POSITION_STATE_STORE_PATH", str(Path(DESK_LOG_DIR) / "position_state")))
)
POSITION_STATE_EXIT_MANAGER_ENABLE = (
    os.getenv("POSITION_STATE_EXIT_MANAGER_ENABLE", "true").lower() == "true"
)
POSITION_STATE_EXIT_MANAGER_AUTHORITATIVE = (
    os.getenv("POSITION_STATE_EXIT_MANAGER_AUTHORITATIVE", "false").lower() == "true"
)
POSITION_STATE_PERSIST_EVERY_CYCLE = (
    os.getenv("POSITION_STATE_PERSIST_EVERY_CYCLE", "true").lower() == "true"
)
POSITION_STATE_EXIT_SHADOW_COMPARE_ENABLE = (
    os.getenv("POSITION_STATE_EXIT_SHADOW_COMPARE_ENABLE", "true").lower() == "true"
)
REQUIRE_LIVE_OPTION_QUOTES = os.getenv("REQUIRE_LIVE_OPTION_QUOTES", "true").lower() == "true"
REQUIRE_DEPTH_QUOTES_FOR_TRADE = os.getenv("REQUIRE_DEPTH_QUOTES_FOR_TRADE", "true").lower() == "true"
REQUIRE_VOLUME_FOR_TRADE = os.getenv("REQUIRE_VOLUME_FOR_TRADE", "true").lower() == "true"
LIVE_QUOTE_ERROR_TTL_SEC = int(os.getenv("LIVE_QUOTE_ERROR_TTL_SEC", "300"))
ALLOW_STALE_LTP = os.getenv("ALLOW_STALE_LTP", "true").lower() == "true"
LTP_CACHE_TTL_SEC = int(os.getenv("LTP_CACHE_TTL_SEC", "300"))
_FORCE_SYNTH_CHAIN_ON_FAIL_RAW = os.getenv("FORCE_SYNTH_CHAIN_ON_FAIL")
FORCE_SYNTH_CHAIN_ON_FAIL = (
    (_FORCE_SYNTH_CHAIN_ON_FAIL_RAW if _FORCE_SYNTH_CHAIN_ON_FAIL_RAW is not None else "true").lower() == "true"
)
if _FORCE_SYNTH_CHAIN_ON_FAIL_RAW is not None:
    logger.warning(
        "CONFIG_DEPRECATED key=FORCE_SYNTH_CHAIN_ON_FAIL value=%s effective_runtime_control=ALLOW_SYNTHETIC_CHAIN allow_synthetic_chain=%s",
        _FORCE_SYNTH_CHAIN_ON_FAIL_RAW,
        ALLOW_SYNTHETIC_CHAIN,
    )
ALLOW_CLOSE_FALLBACK = os.getenv("ALLOW_CLOSE_FALLBACK", "true").lower() == "true"
QUEUE_ROW_MAX_AGE_MIN = int(os.getenv("QUEUE_ROW_MAX_AGE_MIN", "120"))
ENTRY_MISMATCH_PCT = float(os.getenv("ENTRY_MISMATCH_PCT", "0.25"))
INDICATOR_STALE_SEC = int(os.getenv("INDICATOR_STALE_SEC", "120"))
OHLC_BUFFER_MAX_BARS = int(os.getenv("OHLC_BUFFER_MAX_BARS", "500"))
OHLC_MIN_BARS = int(os.getenv("OHLC_MIN_BARS", "30"))
OHLC_WARM_SEED_WINDOWS_MIN = os.getenv("OHLC_WARM_SEED_WINDOWS_MIN", "120,240")
OHLC_WARM_SEED_INTERVAL = os.getenv("OHLC_WARM_SEED_INTERVAL", "minute")
STARTUP_WARMUP_ENABLE = os.getenv("STARTUP_WARMUP_ENABLE", "true").lower() == "true"
STARTUP_WARMUP_INTERVAL = os.getenv("STARTUP_WARMUP_INTERVAL", "minute")
STARTUP_WARMUP_TARGET_BARS = int(os.getenv("STARTUP_WARMUP_TARGET_BARS", "200"))
STARTUP_WARMUP_FETCH_RETRIES = int(os.getenv("STARTUP_WARMUP_FETCH_RETRIES", "3"))
STARTUP_WARMUP_RETRY_BACKOFF_SEC = float(os.getenv("STARTUP_WARMUP_RETRY_BACKOFF_SEC", "0.4"))
STARTUP_WARMUP_MAX_BACKOFF_SEC = float(os.getenv("STARTUP_WARMUP_MAX_BACKOFF_SEC", "2.5"))
NONLIVE_STARTUP_WARMUP_MAX_HIST_EMPTY_ATTEMPTS = int(
    os.getenv("NONLIVE_STARTUP_WARMUP_MAX_HIST_EMPTY_ATTEMPTS", "1")
)
NONLIVE_SKIP_HISTORY_SEED_AFTER_STARTUP_DEGRADE = (
    os.getenv("NONLIVE_SKIP_HISTORY_SEED_AFTER_STARTUP_DEGRADE", "true").lower() == "true"
)
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
DEPTH_WS_USE_SUBPROCESS = os.getenv("DEPTH_WS_USE_SUBPROCESS", "true").lower() == "true"
DEPTH_WS_ALLOW_SOFT_RECONNECTS = os.getenv("DEPTH_WS_ALLOW_SOFT_RECONNECTS", "false").lower() == "true"
DEPTH_WS_USE_INTERNAL_RECONNECT = os.getenv("DEPTH_WS_USE_INTERNAL_RECONNECT", "true").lower() == "true"
DEPTH_WS_STARTUP_FAIL_CLOSED = os.getenv("DEPTH_WS_STARTUP_FAIL_CLOSED", "true").lower() == "true"
DEPTH_WS_STARTUP_FAIL_OPEN_ON_RECOVERABLE_ERRORS = os.getenv(
    "DEPTH_WS_STARTUP_FAIL_OPEN_ON_RECOVERABLE_ERRORS",
    "true",
).lower() == "true"
DEPTH_WS_STARTUP_SNAPSHOT_MAX_AGE_SEC = float(
    os.getenv("DEPTH_WS_STARTUP_SNAPSHOT_MAX_AGE_SEC", "30.0")
)
MAX_CLOCK_SKEW_SEC = float(os.getenv("MAX_CLOCK_SKEW_SEC", "5.0"))
FEED_RECONNECT_COOLDOWN_SEC = float(os.getenv("FEED_RECONNECT_COOLDOWN_SEC", "30"))
FEED_RESTART_STRIKES = int(os.getenv("FEED_RESTART_STRIKES", "3"))
FEED_FULL_RESTART_COOLDOWN_SEC = float(os.getenv("FEED_FULL_RESTART_COOLDOWN_SEC", "30.0"))
FEED_MAX_FULL_RESTARTS_PER_HOUR = int(os.getenv("FEED_MAX_FULL_RESTARTS_PER_HOUR", "12"))
FEED_RESTART_STORM_TRIP = int(os.getenv("FEED_RESTART_STORM_TRIP", "4"))
FEED_RESTART_STORM_WINDOW_SEC = float(os.getenv("FEED_RESTART_STORM_WINDOW_SEC", "300.0"))
FEED_RESTART_STORM_MAX = int(os.getenv("FEED_RESTART_STORM_MAX", "6"))
FEED_RESTART_STORM_COOLDOWN_SEC = float(os.getenv("FEED_RESTART_STORM_COOLDOWN_SEC", "900"))
DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION = int(
    os.getenv("DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION", "10")
)
DEPTH_WS_WS1006_RECOVERABLE_RETRY_COOLDOWN_SEC = float(
    os.getenv("DEPTH_WS_WS1006_RECOVERABLE_RETRY_COOLDOWN_SEC", "5.0")
)
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
#
# Live option/index ticks can briefly pause without the websocket actually
# being broken. Keep silent-down detection conservative enough to avoid
# declaring the feed stale on short gaps, while still failing closed on true
# disconnects. The runtime gate should stay aligned with the live monitor.
#
FEED_HEALTH_INDEX_OK_AGE_SEC = float(os.getenv("FEED_HEALTH_INDEX_OK_AGE_SEC", "1.0"))
FEED_HEALTH_OPTION_OK_AGE_SEC = float(os.getenv("FEED_HEALTH_OPTION_OK_AGE_SEC", "2.5"))
FEED_HEALTH_INDEX_DOWN_NO_MSG_SEC = float(os.getenv("FEED_HEALTH_INDEX_DOWN_NO_MSG_SEC", "3.0"))
FEED_HEALTH_OPTION_DOWN_NO_MSG_SEC = float(os.getenv("FEED_HEALTH_OPTION_DOWN_NO_MSG_SEC", "5.0"))
FEED_SILENT_INDEX_THRESHOLD_SEC = float(os.getenv("FEED_SILENT_INDEX_THRESHOLD_SEC", "5.0"))
FEED_SILENT_OPTION_THRESHOLD_SEC = float(os.getenv("FEED_SILENT_OPTION_THRESHOLD_SEC", "8.0"))
FEED_SILENT_CONFIRM_CYCLES = int(os.getenv("FEED_SILENT_CONFIRM_CYCLES", "3"))
FEED_SILENT_RECONNECT_BACKOFF_MIN_SEC = float(os.getenv("FEED_SILENT_RECONNECT_BACKOFF_MIN_SEC", "1.0"))
FEED_SILENT_RECONNECT_BACKOFF_MAX_SEC = float(os.getenv("FEED_SILENT_RECONNECT_BACKOFF_MAX_SEC", "10.0"))
# Escalate a silent websocket to a full reconnect after this many seconds.
FEED_SILENT_FORCE_FULL_RESTART_SEC = float(os.getenv("FEED_SILENT_FORCE_FULL_RESTART_SEC", "20.0"))
FEED_SOFT_RESUBSCRIBE_MAX_TICK_AGE_SEC = float(
    os.getenv("FEED_SOFT_RESUBSCRIBE_MAX_TICK_AGE_SEC", "2.0")
)
FEED_SOFT_RESUBSCRIBE_HARD_BLOCK_MARKERS = os.getenv(
    "FEED_SOFT_RESUBSCRIBE_HARD_BLOCK_MARKERS",
    "no_ws_messages,watchdog_down,market_open_option_subscriptions_missing,ltp_stale,option_quote_missing,option_quote_not_live,no_live_option_feed",
)
# Keep generic feed-health reconnects from racing the dedicated silent-feed
# watchdog unless the operator explicitly opts in.
FEED_HEALTH_RECONNECT_ON_SILENT_DOWN = (
    os.getenv("FEED_HEALTH_RECONNECT_ON_SILENT_DOWN", "false").lower() == "true"
)
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
SLO_STARTUP_GRACE_ENABLE = os.getenv("SLO_STARTUP_GRACE_ENABLE", "true").lower() == "true"
SLO_STARTUP_GRACE_SEC = float(os.getenv("SLO_STARTUP_GRACE_SEC", "30"))
SLO_AUTH_MAX_AGE_SEC = float(os.getenv("SLO_AUTH_MAX_AGE_SEC", str(GOV_AUTH_MAX_AGE_SEC)))
SLO_AUTH_MAX_LATENCY_SEC = float(os.getenv("SLO_AUTH_MAX_LATENCY_SEC", "2.0"))
SLO_AUTH_LATENCY_HARD_BLOCK_ENABLE = (
    os.getenv("SLO_AUTH_LATENCY_HARD_BLOCK_ENABLE", "false").lower() == "true"
)
SLO_FEED_MAX_LTP_AGE_SEC = float(os.getenv("SLO_FEED_MAX_LTP_AGE_SEC", str(SLA_MAX_LTP_AGE_SEC)))
SLO_FEED_MAX_DEPTH_AGE_SEC = float(os.getenv("SLO_FEED_MAX_DEPTH_AGE_SEC", str(SLA_MAX_DEPTH_AGE_SEC)))
SLO_FAILOVER_CONSECUTIVE_BREACHES = int(os.getenv("SLO_FAILOVER_CONSECUTIVE_BREACHES", "3"))
# Failover on transient feed-stale is intentionally more conservative than other SLO breaches.
# This prevents brief websocket/reconnect gaps from triggering a sticky risk-halt while
# still blocking the live cycle on SLO breach.
SLO_FAILOVER_CONSECUTIVE_BREACHES_FEED_STALE = int(
    os.getenv("SLO_FAILOVER_CONSECUTIVE_BREACHES_FEED_STALE", "6")
)
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
SUGGESTION_EVAL_ENABLE = os.getenv("SUGGESTION_EVAL_ENABLE", "true").lower() == "true"
SUGGESTION_EVAL_INTERVAL_SEC = float(os.getenv("SUGGESTION_EVAL_INTERVAL_SEC", "0"))
SUGGESTION_EVAL_INCREMENTAL_READ_ENABLE = (
    os.getenv("SUGGESTION_EVAL_INCREMENTAL_READ_ENABLE", "true").lower() == "true"
)
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
MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE = os.getenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "false").lower() == "true"
MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH = os.getenv(
    "MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH",
    "runtime/market_event_graph_live_shadow/captured_metadata.jsonl",
)
MARKET_EVENT_GRAPH_LIVE_SOURCE_REJECTION_PATH = os.getenv(
    "MARKET_EVENT_GRAPH_LIVE_SOURCE_REJECTION_PATH",
    "runtime/market_event_graph_live_shadow/rejections.jsonl",
)
MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH = os.getenv("MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "")
MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL = os.getenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL", "NIFTY")
MARKET_EVENT_GRAPH_LIVE_SOURCE_SESSION_DATE = os.getenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_SESSION_DATE", "")
MARKET_EVENT_GRAPH_LIVE_SOURCE_DUMP_AUDIT_PATH = os.getenv(
    "MARKET_EVENT_GRAPH_LIVE_SOURCE_DUMP_AUDIT_PATH",
    "research/market_event_graph_live_shadow_v1/live_constituent_subscription_audit.md",
)
MARKET_EVENT_GRAPH_LIVE_SOURCE_FLUSH_ON_SHUTDOWN = os.getenv(
    "MARKET_EVENT_GRAPH_LIVE_SOURCE_FLUSH_ON_SHUTDOWN",
    "true",
).lower() == "true"

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

PAIRS_TRADING_UNIVERSE = {
    "BANKNIFTY_NIFTY": {
        "leg_a": "BANKNIFTY_INDEX",
        "leg_b": "NIFTY_INDEX",
        "hedge_ratio": 1.0,
    }
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

def _set_feed_status(feed_key: str, status: str, reason=None):
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
OFFLINE_EXECUTION_SIM_ENABLE = os.getenv("OFFLINE_EXECUTION_SIM_ENABLE", "true").lower() == "true"
OFFLINE_EXECUTION_SIM_DEFAULT_DELAY_SEC = float(os.getenv("OFFLINE_EXECUTION_SIM_DEFAULT_DELAY_SEC", "2.0"))
OFFLINE_EXECUTION_SIM_MAX_SPREAD_WIDEN_MULT = float(
    os.getenv("OFFLINE_EXECUTION_SIM_MAX_SPREAD_WIDEN_MULT", "1.75")
)
OFFLINE_EXECUTION_SIM_MAX_RR_COLLAPSE_PCT = float(
    os.getenv("OFFLINE_EXECUTION_SIM_MAX_RR_COLLAPSE_PCT", "0.30")
)
OFFLINE_EXECUTION_SIM_RANDOMNESS_ENABLE = (
    os.getenv("OFFLINE_EXECUTION_SIM_RANDOMNESS_ENABLE", "false").lower() == "true"
)
OFFLINE_EXECUTION_SIM_JITTER_MAX_SEC = float(
    os.getenv("OFFLINE_EXECUTION_SIM_JITTER_MAX_SEC", "0.75")
)
OFFLINE_EXECUTION_SIM_SLIPPAGE_NOISE_BPS = float(
    os.getenv("OFFLINE_EXECUTION_SIM_SLIPPAGE_NOISE_BPS", "4.0")
)
OFFLINE_EXECUTION_SIM_BOOK_DETERIORATION_PCT = float(
    os.getenv("OFFLINE_EXECUTION_SIM_BOOK_DETERIORATION_PCT", "0.20")
)
OFFLINE_EXECUTION_SIM_ALLOW_PARTIAL_FILL = (
    os.getenv("OFFLINE_EXECUTION_SIM_ALLOW_PARTIAL_FILL", "true").lower() == "true"
)
OFFLINE_EXECUTION_SIM_PARTIAL_FILL_MIN_RATIO = float(
    os.getenv("OFFLINE_EXECUTION_SIM_PARTIAL_FILL_MIN_RATIO", "0.25")
)
OFFLINE_FAMILY_LEARNING_ENABLE = (
    os.getenv("OFFLINE_FAMILY_LEARNING_ENABLE", "false").lower() == "true"
)
OFFLINE_FAMILY_LEARNING_MIN_SAMPLES = int(
    os.getenv("OFFLINE_FAMILY_LEARNING_MIN_SAMPLES", "25")
)
OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT", "0.06")
)
OFFLINE_FAMILY_LEARNING_EXPECTANCY_WEIGHT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_EXPECTANCY_WEIGHT", "0.36")
)
OFFLINE_FAMILY_LEARNING_WIN_RATE_WEIGHT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_WIN_RATE_WEIGHT", "0.24")
)
OFFLINE_FAMILY_LEARNING_MFE_WEIGHT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_MFE_WEIGHT", "0.12")
)
OFFLINE_FAMILY_LEARNING_MAE_WEIGHT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_MAE_WEIGHT", "0.12")
)
OFFLINE_FAMILY_LEARNING_REJECTION_SAVED_LOSS_WEIGHT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_REJECTION_SAVED_LOSS_WEIGHT", "0.10")
)
OFFLINE_FAMILY_LEARNING_REJECTION_MISSED_WIN_WEIGHT = float(
    os.getenv("OFFLINE_FAMILY_LEARNING_REJECTION_MISSED_WIN_WEIGHT", "0.06")
)
OFFLINE_FAMILY_LEARNING_MAX_SCARCITY_DELTA = int(
    os.getenv("OFFLINE_FAMILY_LEARNING_MAX_SCARCITY_DELTA", "1")
)
OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE = (
    os.getenv("OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE", "false").lower() == "true"
)
OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES = int(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MIN_SAMPLES", "40")
)
OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT", "0.04")
)
OFFLINE_STRATEGY_WEIGHT_MAX_SIGNAL_BIAS = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MAX_SIGNAL_BIAS", "0.015")
)
OFFLINE_STRATEGY_WEIGHT_MAX_EXECUTION_BIAS = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MAX_EXECUTION_BIAS", "0.015")
)
OFFLINE_STRATEGY_WEIGHT_MAX_SCARCITY_DELTA = int(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MAX_SCARCITY_DELTA", "1")
)
OFFLINE_STRATEGY_WEIGHT_EXPECTANCY_WEIGHT = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_EXPECTANCY_WEIGHT", "0.36")
)
OFFLINE_STRATEGY_WEIGHT_WIN_RATE_WEIGHT = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_WIN_RATE_WEIGHT", "0.22")
)
OFFLINE_STRATEGY_WEIGHT_PNL_WEIGHT = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_PNL_WEIGHT", "0.14")
)
OFFLINE_STRATEGY_WEIGHT_MFE_WEIGHT = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MFE_WEIGHT", "0.14")
)
OFFLINE_STRATEGY_WEIGHT_MAE_WEIGHT = float(
    os.getenv("OFFLINE_STRATEGY_WEIGHT_MAE_WEIGHT", "0.14")
)
OFFLINE_RISK_BUDGET_ENABLE = os.getenv("OFFLINE_RISK_BUDGET_ENABLE", "true").lower() == "true"
OFFLINE_RISK_ACCOUNT_CAPITAL = float(os.getenv("OFFLINE_RISK_ACCOUNT_CAPITAL", str(CAPITAL)))
OFFLINE_RISK_PER_TRADE_PCT = float(
    os.getenv("OFFLINE_RISK_PER_TRADE_PCT", str(MAX_RISK_PER_TRADE_PCT))
)
OFFLINE_RISK_MAX_STOP_DISTANCE_PCT = float(os.getenv("OFFLINE_RISK_MAX_STOP_DISTANCE_PCT", "0.35"))
OFFLINE_RISK_MAX_STOP_ATR_MULT = float(os.getenv("OFFLINE_RISK_MAX_STOP_ATR_MULT", "1.80"))
OFFLINE_RISK_MIN_RR = float(os.getenv("OFFLINE_RISK_MIN_RR", "1.20"))
OFFLINE_RISK_MAX_PORTFOLIO_HEAT = float(os.getenv("OFFLINE_RISK_MAX_PORTFOLIO_HEAT", "0.025"))
OFFLINE_RISK_MAX_DIRECTIONAL_HEAT = float(os.getenv("OFFLINE_RISK_MAX_DIRECTIONAL_HEAT", "0.015"))
OFFLINE_RISK_MAX_FAMILY_EXPOSURE = int(os.getenv("OFFLINE_RISK_MAX_FAMILY_EXPOSURE", "1"))
OFFLINE_RISK_CORRELATION_THRESHOLD = float(os.getenv("OFFLINE_RISK_CORRELATION_THRESHOLD", "0.75"))
OFFLINE_RISK_CORRELATION_PENALTY = float(os.getenv("OFFLINE_RISK_CORRELATION_PENALTY", "0.08"))
OFFLINE_RISK_DAILY_KILL_SWITCH_PCT = float(
    os.getenv("OFFLINE_RISK_DAILY_KILL_SWITCH_PCT", str(MAX_DAILY_LOSS_PCT))
)
OFFLINE_RISK_REGIME_FAILURE_LIMIT = int(os.getenv("OFFLINE_RISK_REGIME_FAILURE_LIMIT", "3"))
OFFLINE_RISK_FAMILY_FAILURE_LIMIT = int(os.getenv("OFFLINE_RISK_FAMILY_FAILURE_LIMIT", "3"))
OFFLINE_RISK_SESSION_FAILURE_LIMIT = int(os.getenv("OFFLINE_RISK_SESSION_FAILURE_LIMIT", "2"))
OFFLINE_RISK_FAILURE_THROTTLE_PENALTY = float(os.getenv("OFFLINE_RISK_FAILURE_THROTTLE_PENALTY", "0.12"))
OFFLINE_RISK_LEARNING_ENABLE = os.getenv("OFFLINE_RISK_LEARNING_ENABLE", "true").lower() == "true"
OFFLINE_RISK_LEARNING_MAX_ADJUSTMENT = float(os.getenv("OFFLINE_RISK_LEARNING_MAX_ADJUSTMENT", "0.03"))
OFFLINE_RISK_LEARNING_MAE_WEIGHT = float(os.getenv("OFFLINE_RISK_LEARNING_MAE_WEIGHT", "0.40"))
OFFLINE_RISK_LEARNING_R_MULTIPLE_WEIGHT = float(os.getenv("OFFLINE_RISK_LEARNING_R_MULTIPLE_WEIGHT", "0.35"))
OFFLINE_RISK_LEARNING_SAVED_LOSS_WEIGHT = float(os.getenv("OFFLINE_RISK_LEARNING_SAVED_LOSS_WEIGHT", "0.25"))
OFFLINE_RISK_PLAN_MAX_OVERSHOOT_R = float(os.getenv("OFFLINE_RISK_PLAN_MAX_OVERSHOOT_R", "0.20"))
FAMILY_RISK_BREAKOUT_MIN_RR = float(os.getenv("FAMILY_RISK_BREAKOUT_MIN_RR", "1.20"))
FAMILY_RISK_BREAKOUT_MAX_STOP_ATR_MULT = float(
    os.getenv("FAMILY_RISK_BREAKOUT_MAX_STOP_ATR_MULT", "3.00")
)
FAMILY_RISK_CONTINUATION_MIN_RR = float(os.getenv("FAMILY_RISK_CONTINUATION_MIN_RR", "1.00"))
FAMILY_RISK_CONTINUATION_MAX_STOP_ATR_MULT = float(
    os.getenv("FAMILY_RISK_CONTINUATION_MAX_STOP_ATR_MULT", "2.50")
)
FAMILY_RISK_MEAN_REVERSION_MIN_RR = float(os.getenv("FAMILY_RISK_MEAN_REVERSION_MIN_RR", "0.60"))
FAMILY_RISK_MEAN_REVERSION_MAX_STOP_ATR_MULT = float(
    os.getenv("FAMILY_RISK_MEAN_REVERSION_MAX_STOP_ATR_MULT", "1.50")
)
FAMILY_RISK_RANGE_WATCHLIST_MIN_RR = float(os.getenv("FAMILY_RISK_RANGE_WATCHLIST_MIN_RR", "0.50"))
FAMILY_RISK_RANGE_WATCHLIST_MAX_STOP_ATR_MULT = float(
    os.getenv("FAMILY_RISK_RANGE_WATCHLIST_MAX_STOP_ATR_MULT", "1.25")
)
OFFLINE_TRADE_DENSITY_ENABLE = os.getenv("OFFLINE_TRADE_DENSITY_ENABLE", "true").lower() == "true"
TRADE_DENSITY_OPENING_MAX_RANKED_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_OPENING_MAX_RANKED_CANDIDATES", "4")
)
TRADE_DENSITY_OPENING_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_OPENING_MAX_EXECUTABLE_CANDIDATES", "2")
)
TRADE_DENSITY_OPENING_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_OPENING_MAX_PER_FAMILY", "2")
)
TRADE_DENSITY_MIDDAY_MAX_RANKED_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_MIDDAY_MAX_RANKED_CANDIDATES", "2")
)
TRADE_DENSITY_MIDDAY_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_MIDDAY_MAX_EXECUTABLE_CANDIDATES", "1")
)
TRADE_DENSITY_MIDDAY_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_MIDDAY_MAX_PER_FAMILY", "1")
)
TRADE_DENSITY_CLOSING_MAX_RANKED_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_CLOSING_MAX_RANKED_CANDIDATES", "3")
)
TRADE_DENSITY_CLOSING_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_CLOSING_MAX_EXECUTABLE_CANDIDATES", "1")
)
TRADE_DENSITY_CLOSING_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_CLOSING_MAX_PER_FAMILY", "1")
)
TRADE_DENSITY_OFFHOURS_MAX_RANKED_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_OFFHOURS_MAX_RANKED_CANDIDATES", "2")
)
TRADE_DENSITY_OFFHOURS_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_OFFHOURS_MAX_EXECUTABLE_CANDIDATES", "0")
)
TRADE_DENSITY_OFFHOURS_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_OFFHOURS_MAX_PER_FAMILY", "1")
)
TRADE_DENSITY_TRENDING_RANKED_BONUS = int(
    os.getenv("TRADE_DENSITY_TRENDING_RANKED_BONUS", "1")
)
TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS = int(
    os.getenv("TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS", "1")
)
TRADE_DENSITY_TRENDING_PER_FAMILY_BONUS = int(
    os.getenv("TRADE_DENSITY_TRENDING_PER_FAMILY_BONUS", "1")
)
TRADE_DENSITY_SIDEWAYS_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_SIDEWAYS_MAX_EXECUTABLE_CANDIDATES", "1")
)
TRADE_DENSITY_SIDEWAYS_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_SIDEWAYS_MAX_PER_FAMILY", "1")
)
TRADE_DENSITY_LOW_VOL_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_LOW_VOL_MAX_EXECUTABLE_CANDIDATES", "1")
)
TRADE_DENSITY_LOW_VOL_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_LOW_VOL_MAX_PER_FAMILY", "1")
)
TRADE_DENSITY_UNCERTAIN_MAX_RANKED_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_UNCERTAIN_MAX_RANKED_CANDIDATES", "2")
)
TRADE_DENSITY_UNCERTAIN_MAX_EXECUTABLE_CANDIDATES = int(
    os.getenv("TRADE_DENSITY_UNCERTAIN_MAX_EXECUTABLE_CANDIDATES", "1")
)
TRADE_DENSITY_UNCERTAIN_MAX_PER_FAMILY = int(
    os.getenv("TRADE_DENSITY_UNCERTAIN_MAX_PER_FAMILY", "1")
)


def get_session_policy(session_mode: str | None = None) -> dict[str, float | int | str | None]:
    normalized = str(session_mode or "OFFHOURS").strip().upper() or "OFFHOURS"
    penalties = {
        "OPENING": float(SESSION_OPENING_ENTRY_PENALTY),
        "MIDDAY": float(SESSION_MIDDAY_ENTRY_PENALTY),
        "CLOSING": float(SESSION_CLOSING_ENTRY_PENALTY),
        "OFFHOURS": float(SESSION_OFFHOURS_ENTRY_PENALTY),
    }
    return {
        "session_mode": normalized,
        "opening_window_min": int(SESSION_OPENING_WINDOW_MIN),
        "midday_start_min": int(SESSION_MIDDAY_START_MIN),
        "closing_window_min": int(SESSION_CLOSING_WINDOW_MIN),
        "entry_penalty": float(penalties.get(normalized, SESSION_OFFHOURS_ENTRY_PENALTY)),
        "directional_trigger_min": (
            float(SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN) if normalized == "MIDDAY" else None
        ),
    }


def get_regime_policy(strategy_regime_mode: str | None = None) -> dict[str, float | int | str]:
    normalized = str(strategy_regime_mode or "UNCERTAIN").strip().upper() or "UNCERTAIN"
    family_consensus_min = float(FAMILY_CONSENSUS_MIN_SCORE)
    if normalized == "LOW_VOL":
        family_consensus_min = float(FAMILY_CONSENSUS_LOW_VOL_MIN_SCORE)
    elif normalized == "UNCERTAIN":
        family_consensus_min = float(FAMILY_CONSENSUS_UNCERTAIN_MIN_SCORE)
    return {
        "strategy_regime_mode": normalized,
        "strategy_regime_confidence_min": float(STRATEGY_REGIME_CONFIDENCE_MIN),
        "trend_atr_min": float(STRATEGY_REGIME_TREND_ATR_MIN),
        "low_vol_atr_max": float(STRATEGY_REGIME_LOW_VOL_ATR_MAX),
        "compression_vol_z_max": float(STRATEGY_REGIME_COMPRESSION_VOL_Z_MAX),
        "direction_family_max_candidates": int(NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES),
        "sideways_direction_family_max_candidates": int(NONLIVE_SIDEWAYS_DIRECTION_FAMILY_MAX_CANDIDATES),
        "uncertain_family_max_candidates": int(NONLIVE_UNCERTAIN_FAMILY_MAX_CANDIDATES),
        "sideways_directional_exceptional_strength": float(SIDEWAYS_DIRECTIONAL_EXCEPTIONAL_STRENGTH),
        "counter_regime_directional_exceptional_strength": float(COUNTER_REGIME_DIRECTIONAL_EXCEPTIONAL_STRENGTH),
        "low_vol_exceptional_strength": float(NONLIVE_LOW_VOL_EXCEPTIONAL_STRENGTH),
        "family_consensus_min_score": float(family_consensus_min),
    }


def get_risk_policy() -> dict[str, float | int | bool]:
    return {
        "offline_risk_budget_enable": bool(OFFLINE_RISK_BUDGET_ENABLE),
        "account_capital": float(OFFLINE_RISK_ACCOUNT_CAPITAL),
        "risk_per_trade_pct": float(OFFLINE_RISK_PER_TRADE_PCT),
        "max_stop_distance_pct": float(OFFLINE_RISK_MAX_STOP_DISTANCE_PCT),
        "max_stop_atr_mult": float(OFFLINE_RISK_MAX_STOP_ATR_MULT),
        "min_rr": float(OFFLINE_RISK_MIN_RR),
        "max_portfolio_heat": float(OFFLINE_RISK_MAX_PORTFOLIO_HEAT),
        "max_directional_heat": float(OFFLINE_RISK_MAX_DIRECTIONAL_HEAT),
        "max_family_exposure": int(OFFLINE_RISK_MAX_FAMILY_EXPOSURE),
        "correlation_penalty": float(OFFLINE_RISK_CORRELATION_PENALTY),
        "daily_kill_switch_pct": float(OFFLINE_RISK_DAILY_KILL_SWITCH_PCT),
        "regime_failure_limit": int(OFFLINE_RISK_REGIME_FAILURE_LIMIT),
        "family_failure_limit": int(OFFLINE_RISK_FAMILY_FAILURE_LIMIT),
        "session_failure_limit": int(OFFLINE_RISK_SESSION_FAILURE_LIMIT),
        "failure_throttle_penalty": float(OFFLINE_RISK_FAILURE_THROTTLE_PENALTY),
        "aggressiveness_too_timid_survival_rate": float(OFFLINE_AGGRESSIVENESS_TOO_TIMID_SURVIVAL_RATE),
        "aggressiveness_starving_no_trade_rate": float(OFFLINE_AGGRESSIVENESS_STARVING_NO_TRADE_RATE),
        "aggressiveness_overtrading_survival_rate": float(OFFLINE_AGGRESSIVENESS_OVERTRADING_SURVIVAL_RATE),
    }


def get_family_risk_profile(strategy_family: str | None = None) -> dict[str, float | str]:
    normalized = str(strategy_family or "").strip().lower().replace("_", "-")
    aliases = {
        "meanreversion": "mean-reversion",
        "rangewatchlist": "range-watchlist",
    }
    normalized = aliases.get(normalized, normalized)
    profiles = {
        "breakout": {
            "min_rr": float(FAMILY_RISK_BREAKOUT_MIN_RR),
            "max_stop_atr_mult": float(FAMILY_RISK_BREAKOUT_MAX_STOP_ATR_MULT),
        },
        "continuation": {
            "min_rr": float(FAMILY_RISK_CONTINUATION_MIN_RR),
            "max_stop_atr_mult": float(FAMILY_RISK_CONTINUATION_MAX_STOP_ATR_MULT),
        },
        "mean-reversion": {
            "min_rr": float(FAMILY_RISK_MEAN_REVERSION_MIN_RR),
            "max_stop_atr_mult": float(FAMILY_RISK_MEAN_REVERSION_MAX_STOP_ATR_MULT),
        },
        "range-watchlist": {
            "min_rr": float(FAMILY_RISK_RANGE_WATCHLIST_MIN_RR),
            "max_stop_atr_mult": float(FAMILY_RISK_RANGE_WATCHLIST_MAX_STOP_ATR_MULT),
        },
    }
    profile = dict(profiles.get(normalized) or {})
    if profile:
        profile["strategy_family"] = normalized
    return profile


def get_family_survival_policy(
    strategy_family: str | None = None,
    session_mode: str | None = None,
    regime_mode: str | None = None,
) -> dict[str, float | str | dict[str, float | int | str | None]]:
    effective_session_policy = get_session_policy(session_mode)
    effective_regime_policy = get_regime_policy(regime_mode)
    return {
        "strategy_family": str(strategy_family or "unknown").strip().lower() or "unknown",
        "session_mode": str(effective_session_policy.get("session_mode") or "OFFHOURS"),
        "strategy_regime_mode": str(effective_regime_policy.get("strategy_regime_mode") or "UNCERTAIN"),
        "weight_setup": float(FAMILY_SURVIVAL_WEIGHT_SETUP),
        "weight_trigger": float(FAMILY_SURVIVAL_WEIGHT_TRIGGER),
        "weight_entry_quality": float(FAMILY_SURVIVAL_WEIGHT_ENTRY_QUALITY),
        "weight_execution": float(FAMILY_SURVIVAL_WEIGHT_EXECUTION),
        "weight_consensus": float(FAMILY_SURVIVAL_WEIGHT_CONSENSUS),
        "component_min": float(FAMILY_SURVIVAL_COMPONENT_MIN),
        "min_score": float(FAMILY_SURVIVAL_MIN_SCORE),
        "executable_min_score": float(NONLIVE_EXECUTABLE_MIN_FAMILY_SURVIVAL),
        "effective_session_policy": dict(effective_session_policy),
        "effective_regime_policy": dict(effective_regime_policy),
    }


def get_trade_density_policy(
    session_mode: str | None = None,
    strategy_regime_mode: str | None = None,
) -> dict[str, int | str]:
    normalized_session = str(session_mode or "OFFHOURS").strip().upper() or "OFFHOURS"
    normalized_regime = str(strategy_regime_mode or "UNCERTAIN").strip().upper() or "UNCERTAIN"
    session_defaults = {
        "OPENING": {
            "max_ranked_candidates": int(TRADE_DENSITY_OPENING_MAX_RANKED_CANDIDATES),
            "max_executable_candidates": int(TRADE_DENSITY_OPENING_MAX_EXECUTABLE_CANDIDATES),
            "max_per_family": int(TRADE_DENSITY_OPENING_MAX_PER_FAMILY),
        },
        "MIDDAY": {
            "max_ranked_candidates": int(TRADE_DENSITY_MIDDAY_MAX_RANKED_CANDIDATES),
            "max_executable_candidates": int(TRADE_DENSITY_MIDDAY_MAX_EXECUTABLE_CANDIDATES),
            "max_per_family": int(TRADE_DENSITY_MIDDAY_MAX_PER_FAMILY),
        },
        "CLOSING": {
            "max_ranked_candidates": int(TRADE_DENSITY_CLOSING_MAX_RANKED_CANDIDATES),
            "max_executable_candidates": int(TRADE_DENSITY_CLOSING_MAX_EXECUTABLE_CANDIDATES),
            "max_per_family": int(TRADE_DENSITY_CLOSING_MAX_PER_FAMILY),
        },
        "OFFHOURS": {
            "max_ranked_candidates": int(TRADE_DENSITY_OFFHOURS_MAX_RANKED_CANDIDATES),
            "max_executable_candidates": int(TRADE_DENSITY_OFFHOURS_MAX_EXECUTABLE_CANDIDATES),
            "max_per_family": int(TRADE_DENSITY_OFFHOURS_MAX_PER_FAMILY),
        },
    }
    policy = dict(session_defaults.get(normalized_session) or session_defaults["OFFHOURS"])
    if normalized_regime == "TRENDING":
        policy["max_ranked_candidates"] += int(TRADE_DENSITY_TRENDING_RANKED_BONUS)
        policy["max_executable_candidates"] += int(TRADE_DENSITY_TRENDING_EXECUTABLE_BONUS)
        policy["max_per_family"] += int(TRADE_DENSITY_TRENDING_PER_FAMILY_BONUS)
    elif normalized_regime == "SIDEWAYS":
        policy["max_executable_candidates"] = min(
            int(policy["max_executable_candidates"]),
            int(TRADE_DENSITY_SIDEWAYS_MAX_EXECUTABLE_CANDIDATES),
        )
        policy["max_per_family"] = min(
            int(policy["max_per_family"]),
            int(TRADE_DENSITY_SIDEWAYS_MAX_PER_FAMILY),
        )
    elif normalized_regime == "LOW_VOL":
        policy["max_executable_candidates"] = min(
            int(policy["max_executable_candidates"]),
            int(TRADE_DENSITY_LOW_VOL_MAX_EXECUTABLE_CANDIDATES),
        )
        policy["max_per_family"] = min(
            int(policy["max_per_family"]),
            int(TRADE_DENSITY_LOW_VOL_MAX_PER_FAMILY),
        )
    elif normalized_regime == "UNCERTAIN":
        policy["max_ranked_candidates"] = min(
            int(policy["max_ranked_candidates"]),
            int(TRADE_DENSITY_UNCERTAIN_MAX_RANKED_CANDIDATES),
        )
        policy["max_executable_candidates"] = min(
            int(policy["max_executable_candidates"]),
            int(TRADE_DENSITY_UNCERTAIN_MAX_EXECUTABLE_CANDIDATES),
        )
        policy["max_per_family"] = min(
            int(policy["max_per_family"]),
            int(TRADE_DENSITY_UNCERTAIN_MAX_PER_FAMILY),
        )
    policy["max_ranked_candidates"] = max(1, int(policy["max_ranked_candidates"]))
    policy["max_executable_candidates"] = max(0, int(policy["max_executable_candidates"]))
    policy["max_per_family"] = max(1, int(policy["max_per_family"]))
    policy_name = f"{normalized_session}:{normalized_regime}"
    return {
        "policy_name": policy_name,
        "session_mode": normalized_session,
        "strategy_regime_mode": normalized_regime,
        "max_ranked_candidates": int(policy["max_ranked_candidates"]),
        "max_executable_candidates": int(policy["max_executable_candidates"]),
        "max_per_family": int(policy["max_per_family"]),
    }

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
RUNTIME_STATE_RESTORE_ON_STARTUP = os.getenv("RUNTIME_STATE_RESTORE_ON_STARTUP", "true").lower() == "true"
RUNTIME_RESTORE_POSITION_LIMIT = int(os.getenv("RUNTIME_RESTORE_POSITION_LIMIT", "2000"))
RUNTIME_RECONCILIATION_LOG_PATH = os.getenv(
    "RUNTIME_RECONCILIATION_LOG_PATH",
    f"{LOGS_ROOT}/runtime_reconciliation.jsonl",
)
BROKER_TRUTH_RECONCILE_ENABLED = os.getenv("BROKER_TRUTH_RECONCILE_ENABLED", "false").lower() == "true"
BROKER_TRUTH_INTERVAL_S = float(os.getenv("BROKER_TRUTH_INTERVAL_S", "60"))
DRIFT_MAX_QTY = float(os.getenv("DRIFT_MAX_QTY", "0"))
DRIFT_MAX_OPEN_ORDERS = int(os.getenv("DRIFT_MAX_OPEN_ORDERS", "0"))
DRIFT_MAX_PRICE_BPS = float(os.getenv("DRIFT_MAX_PRICE_BPS", "25"))
DRIFT_FILL_STALE_WINDOW_SEC = float(os.getenv("DRIFT_FILL_STALE_WINDOW_SEC", "30"))
AUTO_FLATTEN_ON_DRIFT = os.getenv("AUTO_FLATTEN_ON_DRIFT", "false").lower() == "true"
DRIFT_HALT_ENTRIES_ON_DETECT = os.getenv("DRIFT_HALT_ENTRIES_ON_DETECT", "true").lower() == "true"
# Latency budget guard.
LATENCY_MONITOR_WINDOW_SIZE = int(os.getenv("LATENCY_MONITOR_WINDOW_SIZE", "120"))
MAX_P95_TOTAL_MS = float(os.getenv("MAX_P95_TOTAL_MS", "600"))
MAX_P95_DECISION_MS = float(os.getenv("MAX_P95_DECISION_MS", "300"))
SUSTAINED_WINDOWS = int(os.getenv("SUSTAINED_WINDOWS", "3"))
LATENCY_GUARD_RECOVERY_WINDOWS = int(
    os.getenv("LATENCY_GUARD_RECOVERY_WINDOWS", str(SUSTAINED_WINDOWS))
)
EXIT_ONLY_COOLDOWN_S = float(os.getenv("EXIT_ONLY_COOLDOWN_S", "30"))
HALT_ON_BREACH = os.getenv("HALT_ON_BREACH", "true").lower() == "true"
LIVE_MAX_P95_TOTAL_MS = float(os.getenv("LIVE_MAX_P95_TOTAL_MS", "10000"))
LIVE_MAX_P95_DECISION_MS = float(os.getenv("LIVE_MAX_P95_DECISION_MS", "3000"))
LIVE_SUSTAINED_WINDOWS = int(os.getenv("LIVE_SUSTAINED_WINDOWS", str(SUSTAINED_WINDOWS)))
LIVE_EXIT_ONLY_COOLDOWN_S = float(os.getenv("LIVE_EXIT_ONLY_COOLDOWN_S", str(EXIT_ONLY_COOLDOWN_S)))
LIVE_HALT_ON_BREACH = os.getenv("LIVE_HALT_ON_BREACH", str(HALT_ON_BREACH).lower()).lower() == "true"
LATENCY_GUARD_USE_CRITICAL_PATH_ONLY = os.getenv("LATENCY_GUARD_USE_CRITICAL_PATH_ONLY", "true").lower() == "true"
LATENCY_GUARD_BACKGROUND_OVERHEAD_WARN_MS = float(
    os.getenv("LATENCY_GUARD_BACKGROUND_OVERHEAD_WARN_MS", "250")
)
FEED_RUNTIME_STATUS_OVERLAY_ENABLE = os.getenv("FEED_RUNTIME_STATUS_OVERLAY_ENABLE", "true").lower() == "true"
KITE_CLIENT_REUSE_SESSION = os.getenv("KITE_CLIENT_REUSE_SESSION", "true").lower() == "true"
KITE_NEXT_AVAILABLE_EXPIRY_CACHE_SEC = int(os.getenv("KITE_NEXT_AVAILABLE_EXPIRY_CACHE_SEC", "300"))
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
ORB_SOFT_VETO_CONF_PENALTY = float(
    os.getenv("ORB_SOFT_VETO_CONF_PENALTY", str(max(0.0, 1.0 - ORB_SOFT_VETO_CONF_MULT)))
)
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
QUEUE_REJECTED_CANDIDATES_ENABLE = os.getenv("QUEUE_REJECTED_CANDIDATES_ENABLE", "true").lower() == "true"
QUEUE_REJECTED_CANDIDATES_FORCE_ADVISORY = os.getenv("QUEUE_REJECTED_CANDIDATES_FORCE_ADVISORY", "true").lower() == "true"
QUEUE_PREBUILDER_GATE_CANDIDATES_ENABLE = os.getenv("QUEUE_PREBUILDER_GATE_CANDIDATES_ENABLE", "false").lower() == "true"
QUEUE_INVALID_SNAPSHOT_CANDIDATES_ENABLE = os.getenv("QUEUE_INVALID_SNAPSHOT_CANDIDATES_ENABLE", "false").lower() == "true"
QUEUE_SYNTHETIC_CANDIDATES_ENABLE = os.getenv("QUEUE_SYNTHETIC_CANDIDATES_ENABLE", "false").lower() == "true"
TRADE_BUILDER_RESULT_TRACE_ENABLE = os.getenv("TRADE_BUILDER_RESULT_TRACE_ENABLE", "true").lower() == "true"
GATE_REJECT_TRACE_ENABLE = os.getenv("GATE_REJECT_TRACE_ENABLE", "true").lower() == "true"
TARGET_POINTS_MIN = float(os.getenv("TARGET_POINTS_MIN", "20.0"))
TRADE_BUILDER_SOFT_REJECT_ENABLE = os.getenv("TRADE_BUILDER_SOFT_REJECT_ENABLE", "true").lower() == "true"
TRADE_BUILDER_SOFT_REJECT_ALLOW_LIVE = os.getenv("TRADE_BUILDER_SOFT_REJECT_ALLOW_LIVE", "false").lower() == "true"
TRADE_BUILDER_SOFT_REJECT_REASONS = os.getenv(
    "TRADE_BUILDER_SOFT_REJECT_REASONS",
    "premium_band_fail,no_viable_candidates,no_signal,weak_momentum,move_too_small,flat_vs_vwap,trend_regime_conflict,spread_pct,latency_guard_cooldown,regime_unstable",
)
TRADE_BUILDER_HARD_REJECT_REASONS = os.getenv(
    "TRADE_BUILDER_HARD_REJECT_REASONS",
    "feed_stale,quote_missing,unresolved_contract,invalid_risk_levels,missing_live_quote,no_live_option_feed",
)
OPTION_SCAN_SOFT_GATE_REASONS = os.getenv(
    "OPTION_SCAN_SOFT_GATE_REASONS",
    "type_mismatch,iv_skew_curvature,iv_skew_curve_call,iv_skew_curve_put,iv_bounds",
)
OPTION_SCAN_MIN_SURVIVORS_ENABLE = os.getenv(
    "OPTION_SCAN_MIN_SURVIVORS_ENABLE",
    "false",
).lower() == "true"
OPTION_SCAN_MIN_SURVIVORS_COUNT = int(
    os.getenv("OPTION_SCAN_MIN_SURVIVORS_COUNT", "0")
)
OPTION_SCAN_MIN_SURVIVORS_ALLOWED_MODES = os.getenv(
    "OPTION_SCAN_MIN_SURVIVORS_ALLOWED_MODES",
    "SIM,PAPER,OFFHOURS",
)
OPTION_SCAN_MIN_SURVIVOR_SCORE = float(
    os.getenv("OPTION_SCAN_MIN_SURVIVOR_SCORE", "0.32")
)
TRADE_BUILDER_BORDERLINE_CONF_MIN = float(os.getenv("TRADE_BUILDER_BORDERLINE_CONF_MIN", "0.18"))
TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS = int(
    os.getenv("TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS", "4")
)
TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_ABS = float(
    os.getenv("TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_ABS", "300")
)
TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_PCT = float(
    os.getenv("TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_PCT", "0.012")
)


def v2_flags_snapshot() -> dict:
    return {
        "ENABLE_CANDIDATE_GENERATOR_V2": ENABLE_CANDIDATE_GENERATOR_V2,
    }


def v2_flags_active() -> dict:
    flags = v2_flags_snapshot()
    return {name: value for name, value in flags.items() if value}


def pro_strategy_flags_snapshot() -> dict:
    return {
        "ENABLE_PRO_STRATEGY_LAYER": ENABLE_PRO_STRATEGY_LAYER,
        "ENABLE_PRO_STRATEGY_SHADOW": ENABLE_PRO_STRATEGY_SHADOW,
        "PRO_STRATEGY_LAYER_STRICT_MODE": PRO_STRATEGY_LAYER_STRICT_MODE,
        "PRO_STRATEGY_SHADOW_THREAD_TTL_SEC": PRO_STRATEGY_SHADOW_THREAD_TTL_SEC,
        "PRO_STRATEGY_SHADOW_WORKER_TTL_SEC": PRO_STRATEGY_SHADOW_WORKER_TTL_SEC,
    }


def pro_strategy_flags_active() -> dict:
    flags = pro_strategy_flags_snapshot()
    return {name: value for name, value in flags.items() if value}

# Entry trigger logic (buy above / sell below)
ENTRY_TRIGGER_MODE = os.getenv("ENTRY_TRIGGER_MODE", "ASK").upper()
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

# -------------------------------
# Feed verification and recovery
# -------------------------------
FEED_OPTION_VERIFY_TIMEOUT_SEC = float(os.getenv("FEED_OPTION_VERIFY_TIMEOUT_SEC", "45.0"))
FEED_RESTART_VERIFY_TIMEOUT_SEC = float(os.getenv("FEED_RESTART_VERIFY_TIMEOUT_SEC", "45.0"))
FEED_OPTION_VERIFY_TIMEOUT_MARKET_OPEN_SEC = float(os.getenv("FEED_OPTION_VERIFY_TIMEOUT_MARKET_OPEN_SEC", "90.0"))
