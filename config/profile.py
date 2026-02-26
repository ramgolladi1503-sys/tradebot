"""Runtime trading profiles.

Migration note:
- Introduces an explicit profile layer so mode-specific policy is centralized.
- `TRADING_MODE` is now the primary selector (`LIVE|PAPER|SIM`), with
  backward-compatible fallback to `EXECUTION_MODE`.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from config import config as cfg


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def resolve_trading_mode(raw_mode: Any | None = None) -> str:
    """Single source of truth for runtime mode selection."""
    if raw_mode is not None:
        candidate = raw_mode
    else:
        env_mode = os.getenv("TRADING_MODE")
        if env_mode is not None and str(env_mode).strip():
            candidate = env_mode
        else:
            # Backward compatibility for existing callers/tests that patch EXECUTION_MODE.
            candidate = getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))
    mode = str(candidate or "SIM").strip().upper()
    if mode not in {"LIVE", "PAPER", "SIM"}:
        return "SIM"
    return mode


@dataclass(frozen=True)
class RuntimeProfile:
    mode: str
    suggestion_require_live_quotes: bool
    suggestion_require_depth: bool
    suggestion_require_volume: bool
    execution_require_live_quotes: bool
    execution_require_depth: bool
    execution_require_volume: bool
    allow_synthetic_chain_for_planning: bool
    allow_stale_quotes_for_planning: bool
    orb_candle_minutes: int
    orb_hard_block_live: bool
    orb_hard_conflict_live: bool
    best_trade_caps_enabled: bool
    price_confirm_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "suggestion_require_live_quotes": bool(self.suggestion_require_live_quotes),
            "suggestion_require_depth": bool(self.suggestion_require_depth),
            "suggestion_require_volume": bool(self.suggestion_require_volume),
            "execution_require_live_quotes": bool(self.execution_require_live_quotes),
            "execution_require_depth": bool(self.execution_require_depth),
            "execution_require_volume": bool(self.execution_require_volume),
            "allow_synthetic_chain_for_planning": bool(self.allow_synthetic_chain_for_planning),
            "allow_stale_quotes_for_planning": bool(self.allow_stale_quotes_for_planning),
            "orb_candle_minutes": int(self.orb_candle_minutes),
            "orb_hard_block_live": bool(self.orb_hard_block_live),
            "orb_hard_conflict_live": bool(self.orb_hard_conflict_live),
            "best_trade_caps_enabled": bool(self.best_trade_caps_enabled),
            "price_confirm_enabled": bool(self.price_confirm_enabled),
        }


def get_runtime_profile(*, mode: str | None = None) -> RuntimeProfile:
    resolved_mode = resolve_trading_mode(mode)

    if resolved_mode == "LIVE":
        return RuntimeProfile(
            mode="LIVE",
            # LIVE suggestion stage is moderately permissive; execution stage stays strict.
            suggestion_require_live_quotes=_env_bool("LIVE_SUGGEST_REQUIRE_LIVE_QUOTES", False),
            suggestion_require_depth=_env_bool("LIVE_SUGGEST_REQUIRE_DEPTH", False),
            suggestion_require_volume=_env_bool("LIVE_SUGGEST_REQUIRE_VOLUME", False),
            execution_require_live_quotes=_env_bool("LIVE_EXEC_REQUIRE_LIVE_QUOTES", True),
            execution_require_depth=_env_bool("LIVE_EXEC_REQUIRE_DEPTH", True),
            execution_require_volume=_env_bool("LIVE_EXEC_REQUIRE_VOLUME", True),
            allow_synthetic_chain_for_planning=_env_bool("LIVE_ALLOW_SYNTH_CHAIN_PLANNING", False),
            allow_stale_quotes_for_planning=_env_bool("LIVE_ALLOW_STALE_PLANNING", True),
            orb_candle_minutes=max(0, _env_int("ORB_CANDLE_MINUTES_LIVE", 5)),
            orb_hard_block_live=bool(getattr(cfg, "ORB_HARD_BLOCK_LIVE", False)),
            orb_hard_conflict_live=bool(getattr(cfg, "ORB_HARD_CONFLICT_LIVE", False)),
            best_trade_caps_enabled=_env_bool("LIVE_BEST_TRADE_CAPS_ENABLE", True),
            price_confirm_enabled=_env_bool("LIVE_PRICE_CONFIRM_ENABLE", True),
        )

    if resolved_mode == "PAPER":
        return RuntimeProfile(
            mode="PAPER",
            suggestion_require_live_quotes=_env_bool("PAPER_SUGGEST_REQUIRE_LIVE_QUOTES", False),
            suggestion_require_depth=_env_bool("PAPER_SUGGEST_REQUIRE_DEPTH", False),
            suggestion_require_volume=_env_bool("PAPER_SUGGEST_REQUIRE_VOLUME", False),
            execution_require_live_quotes=_env_bool("PAPER_EXEC_REQUIRE_LIVE_QUOTES", False),
            execution_require_depth=_env_bool("PAPER_EXEC_REQUIRE_DEPTH", False),
            execution_require_volume=_env_bool("PAPER_EXEC_REQUIRE_VOLUME", False),
            allow_synthetic_chain_for_planning=_env_bool("PAPER_ALLOW_SYNTH_CHAIN", True),
            allow_stale_quotes_for_planning=_env_bool("PAPER_ALLOW_STALE_QUOTES", True),
            orb_candle_minutes=max(0, _env_int("ORB_CANDLE_MINUTES_PAPER", 0)),
            orb_hard_block_live=False,
            orb_hard_conflict_live=False,
            best_trade_caps_enabled=_env_bool("PAPER_BEST_TRADE_CAPS_ENABLE", False),
            price_confirm_enabled=_env_bool("PAPER_PRICE_CONFIRM_ENABLE", False),
        )

    # SIM default profile.
    return RuntimeProfile(
        mode="SIM",
        suggestion_require_live_quotes=_env_bool("SIM_SUGGEST_REQUIRE_LIVE_QUOTES", False),
        suggestion_require_depth=_env_bool("SIM_SUGGEST_REQUIRE_DEPTH", False),
        suggestion_require_volume=_env_bool("SIM_SUGGEST_REQUIRE_VOLUME", False),
        execution_require_live_quotes=_env_bool("SIM_EXEC_REQUIRE_LIVE_QUOTES", False),
        execution_require_depth=_env_bool("SIM_EXEC_REQUIRE_DEPTH", False),
        execution_require_volume=_env_bool("SIM_EXEC_REQUIRE_VOLUME", False),
        allow_synthetic_chain_for_planning=_env_bool("SIM_ALLOW_SYNTH_CHAIN", True),
        allow_stale_quotes_for_planning=_env_bool("SIM_ALLOW_STALE_QUOTES", True),
        orb_candle_minutes=max(0, _env_int("ORB_CANDLE_MINUTES_SIM", 0)),
        orb_hard_block_live=False,
        orb_hard_conflict_live=False,
        best_trade_caps_enabled=_env_bool("SIM_BEST_TRADE_CAPS_ENABLE", False),
        price_confirm_enabled=_env_bool("SIM_PRICE_CONFIRM_ENABLE", False),
    )
