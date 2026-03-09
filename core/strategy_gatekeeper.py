import logging
from dataclasses import dataclass
from config import config as cfg
from core.market_context import derive_market_context

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    allowed: bool
    family: str | None
    reasons: list


class StrategyGatekeeper:
    """
    Hard regime gating:
      TREND -> only trend strategies
      RANGE -> only mean reversion
      EVENT -> defined-risk only or NO TRADE
      NEUTRAL -> NO TRADE
    """
    def __init__(self) -> None:
        self._unstable_streak_by_symbol: dict[str, int] = {}

    def evaluate(self, market_data, mode="MAIN") -> GateResult:
        reasons = []
        symbol = str(market_data.get("symbol") or "UNKNOWN").upper()
        regime_probs = market_data.get("regime_probs") or {}
        if "unstable_reasons" in market_data:
            unstable_reasons = [str(x) for x in (market_data.get("unstable_reasons") or []) if str(x)]
        else:
            unstable_reasons = ["legacy_unstable_flag"] if bool(market_data.get("unstable_regime_flag", False)) else []
        regime = (market_data.get("primary_regime") or market_data.get("regime") or "NEUTRAL").upper()
        ctx_payload = {}
        if isinstance(market_data.get("market_context"), dict):
            ctx_payload.update(dict(market_data.get("market_context") or {}))
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = market_data.get("execution_mode")
        if "market_open" not in ctx_payload:
            ctx_payload["market_open"] = market_data.get("market_open")
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = market_data.get("segment")
        mode_hint = str(
            ctx_payload.get("execution_mode") or getattr(cfg, "EXECUTION_MODE", "SIM")
        ).upper()
        if ("market_open" not in ctx_payload) or (ctx_payload.get("market_open") is None):
            # Backward compatibility: historical callsites expected LIVE mode to
            # run strict gates even without explicit market_open context.
            if mode_hint == "LIVE":
                ctx_payload["market_open"] = True
        market_ctx = derive_market_context(ctx_payload)
        live_mode = str(market_ctx.mode).upper() == "LIVE"
        paper_relax = bool(market_ctx.allow_stale_quotes) and bool(
            getattr(cfg, "PAPER_RELAX_GATES", True)
        )
        unstable_block_after_default = int(getattr(cfg, "REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 1))
        unstable_block_after = unstable_block_after_default
        if paper_relax:
            unstable_block_after = int(
                getattr(
                    cfg,
                    "PAPER_REGIME_UNSTABLE_CONSECUTIVE_BLOCK",
                    unstable_block_after_default,
                )
            )
        unstable_block_after = max(1, int(unstable_block_after))
        explicit_streak = None
        try:
            explicit_streak = int(market_data.get("regime_unstable_streak"))
        except Exception:
            explicit_streak = None
        if unstable_reasons:
            if explicit_streak is not None and explicit_streak > 0:
                unstable_streak = explicit_streak
            else:
                unstable_streak = int(self._unstable_streak_by_symbol.get(symbol, 0)) + 1
            self._unstable_streak_by_symbol[symbol] = unstable_streak
        else:
            self._unstable_streak_by_symbol[symbol] = 0
            unstable_streak = 0
        regime_prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
        if paper_relax:
            regime_prob_min = float(getattr(cfg, "PAPER_REGIME_PROB_MIN", regime_prob_min))
        indicators_ok = market_data.get("indicators_ok", True)
        indicators_age = market_data.get("indicators_age_sec")
        if indicators_age is None:
            indicators_age = 0
        stale = indicators_age > getattr(cfg, "INDICATOR_STALE_SEC", 120)
        if not indicators_ok or stale:
            reasons.append("indicators_missing_or_stale")
            return GateResult(False, None, reasons)
        # cross-asset data quality gating
        required = set(getattr(cfg, "CROSS_REQUIRED_FEEDS", []) or [])
        optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
        require_x = bool(getattr(cfg, "REQUIRE_CROSS_ASSET", True))
        if getattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True):
            require_x = require_x and live_mode
        try:
            cross_q = market_data.get("cross_asset_quality")
            if not cross_q:
                if require_x and required:
                    reasons.append("cross_asset_required_missing")
                    return GateResult(False, None, reasons)
                cross_q = {}
            feed_status = cross_q.get("feed_status") or {}
            disabled_required = {
                k for k, v in feed_status.items()
                if (v or {}).get("status") == "disabled" and k in required
            }
            if disabled_required and require_x:
                reasons.append("cross_asset_required_missing")
                return GateResult(False, None, reasons)
            if cross_q.get("disabled"):
                stale_required = set(cross_q.get("required_stale", []) or []) & required
                if not stale_required:
                    stale = set(cross_q.get("stale_feeds", []) or [])
                    missing = set((cross_q.get("missing") or {}).keys())
                    stale_required = (stale | missing) & required
                if stale_required and require_x:
                    reasons.append("cross_asset_required_stale")
                    return GateResult(False, None, reasons)
                reasons.append(f"cross_asset_disabled:{cross_q.get('disabled_reason')}")
            stale_required = set(cross_q.get("required_stale", []) or []) & required
            stale_optional = set(cross_q.get("optional_stale", []) or []) & optional
            if not stale_required and not stale_optional:
                # fallback if older payload
                stale = set(cross_q.get("stale_feeds", []) or [])
                missing = set((cross_q.get("missing") or {}).keys())
                stale_required = (stale | missing) & required
                stale_optional = (stale | missing) & optional
            if stale_required and require_x:
                reasons.append("cross_asset_required_stale")
                return GateResult(False, None, reasons)
            if stale_optional:
                if require_x:
                    reasons.append("cross_asset_optional_stale")
                else:
                    reasons.append("cross_asset_optional_warn")
        except Exception as exc:
            logger.warning("gatekeeper_cross_asset_check_failed err=%s", exc)
            reasons.append("cross_asset_check_error")
            if require_x and required:
                return GateResult(False, None, reasons)

        shock_score = float(market_data.get("shock_score") or 0.0)
        uncertainty = float(market_data.get("uncertainty_index") or 0.0)
        if shock_score >= getattr(cfg, "NEWS_SHOCK_BLOCK_THRESHOLD", 0.7):
            reasons.append("news_shock_block")
            return GateResult(False, None, reasons)
        if shock_score >= getattr(cfg, "NEWS_SHOCK_EVENT_THRESHOLD", 0.4) or uncertainty >= 0.8:
            if getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True):
                return GateResult(True, "DEFINED_RISK", reasons + ["news_shock_defined_risk_only"])
            reasons.append("news_shock_no_trade")
            return GateResult(False, None, reasons)

        if regime_probs:
            max_prob = max(regime_probs.values()) if regime_probs else 0.0
            paper_soft_unblock_enabled = bool(getattr(cfg, "PAPER_SOFT_UNBLOCK_ENABLE", True))
            paper_soft_unblock_conf_min = float(getattr(cfg, "PAPER_SOFT_UNBLOCK_CONF_MIN", 0.80))
            contradictory_reasons = set(
                str(x).strip()
                for x in (getattr(cfg, "PAPER_SOFT_UNBLOCK_CONTRADICTORY_REASONS", ["entropy_too_high", "prob_too_low"]) or [])
                if str(x).strip()
            )
            soft_unblock_ok = bool(
                unstable_reasons
                and paper_relax
                and paper_soft_unblock_enabled
                and bool(indicators_ok)
                and max_prob >= paper_soft_unblock_conf_min
                and not (set(unstable_reasons) & contradictory_reasons)
            )
            if unstable_reasons:
                if soft_unblock_ok:
                    return GateResult(True, "DEFINED_RISK", reasons + ["paper_soft_unblock"])
                if unstable_block_after > 1 and unstable_streak < unstable_block_after:
                    reasons.append(
                        f"regime_unstable_debounced:{int(unstable_streak)}/{int(unstable_block_after)}"
                    )
                    unstable_reasons = []
                else:
                    reasons.append("regime_unstable")
                    if unstable_reasons:
                        reasons.extend(f"unstable:{r}" for r in unstable_reasons)
                    return GateResult(False, None, reasons)
            if unstable_reasons:
                if soft_unblock_ok:
                    return GateResult(True, "DEFINED_RISK", reasons + ["paper_soft_unblock"])
                reasons.append("regime_unstable")
                reasons.extend(f"unstable:{r}" for r in unstable_reasons)
                return GateResult(False, None, reasons)
            if max_prob < regime_prob_min:
                reasons.append("regime_low_confidence")
                return GateResult(False, None, reasons)

        if regime == "TREND":
            return GateResult(True, "TREND", reasons)
        if regime in ("RANGE", "RANGE_VOLATILE"):
            return GateResult(True, "MEAN_REVERT", reasons)
        if regime == "EVENT":
            if getattr(cfg, "EVENT_ALLOW_DEFINED_RISK", True):
                return GateResult(True, "DEFINED_RISK", reasons + ["event_defined_risk_only"])
            reasons.append("event_no_trade")
            return GateResult(False, None, reasons)
        if regime == "NEUTRAL":
            if paper_relax:
                family = str(getattr(cfg, "PAPER_NEUTRAL_FAMILY", "DEFINED_RISK")).upper()
                if family in {"DEFINED_RISK", "SCALP_ONLY"}:
                    return GateResult(True, family, reasons + ["paper_neutral_routed"])
            reasons.append("neutral_no_trade")
            return GateResult(False, None, reasons)

        # default: block unknown regimes
        reasons.append(f"unsupported_regime:{regime}")
        return GateResult(False, None, reasons)
