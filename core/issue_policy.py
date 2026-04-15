from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

try:
    from config import config as cfg
except Exception:
    cfg = None

logger = logging.getLogger(__name__)

ISSUE_CATEGORY_HARD = "hard_blocker"
ISSUE_CATEGORY_SOFT = "soft_penalty"
ISSUE_CATEGORY_WARNING = "warning"
ISSUE_CATEGORIES = {ISSUE_CATEGORY_HARD, ISSUE_CATEGORY_SOFT, ISSUE_CATEGORY_WARNING}


@dataclass(frozen=True)
class IssuePolicy:
    code: str
    default_category: str
    default_penalty: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class IssueClassification:
    code: str
    category: str
    penalty: float
    reason: str
    evidence: dict[str, Any]


ISSUE_POLICY_REGISTRY: dict[str, IssuePolicy] = {
    "NO_TOKEN": IssuePolicy("NO_TOKEN", ISSUE_CATEGORY_HARD, 0.0, "Selected option contract has no broker token."),
    "MISSING_CROSS_ASSET_FEATURE": IssuePolicy(
        "MISSING_CROSS_ASSET_FEATURE",
        ISSUE_CATEGORY_SOFT,
        0.05,
        "Cross-asset enrichment feature is missing for this advisory.",
    ),
    "DISPLAY_ENTRY_FALLBACK": IssuePolicy(
        "DISPLAY_ENTRY_FALLBACK",
        ISSUE_CATEGORY_WARNING,
        0.0,
        "Displayed entry is using an advisory fallback path.",
    ),
    "NO_LIVE_OPTION_FEED": IssuePolicy(
        "NO_LIVE_OPTION_FEED",
        ISSUE_CATEGORY_HARD,
        0.0,
        "No fresh live option feed is available for the selected contract.",
    ),
    "STALE_OPTION_LTP": IssuePolicy(
        "STALE_OPTION_LTP",
        ISSUE_CATEGORY_HARD,
        0.12,
        "Selected option quote is stale relative to the configured SLA.",
    ),
    "PRICE_MISMATCH": IssuePolicy(
        "PRICE_MISMATCH",
        ISSUE_CATEGORY_HARD,
        0.10,
        "Live option price deviates materially from the advisory reference price.",
    ),
    "MISSING_OPTION_TOKEN": IssuePolicy("MISSING_OPTION_TOKEN", ISSUE_CATEGORY_HARD, 0.0, "Selected option contract is unresolved."),
    "unresolved_contract": IssuePolicy("unresolved_contract", ISSUE_CATEGORY_HARD, 0.0, "Broker contract identity is incomplete."),
    "MISSING_ENTRY": IssuePolicy("MISSING_ENTRY", ISSUE_CATEGORY_HARD, 0.0, "Executable entry price is missing."),
    "HARD_SPREAD_TOO_WIDE": IssuePolicy("HARD_SPREAD_TOO_WIDE", ISSUE_CATEGORY_HARD, 0.0, "Quote spread is too wide for execution."),
    "NO_LIVE_OPTION_FEED_SUBSCRIPTION": IssuePolicy(
        "NO_LIVE_OPTION_FEED_SUBSCRIPTION",
        ISSUE_CATEGORY_HARD,
        0.0,
        "Option subscription is unavailable.",
    ),
    "missing_rr_context": IssuePolicy(
        "missing_rr_context",
        ISSUE_CATEGORY_SOFT,
        0.08,
        "Risk/reward context is incomplete; candidate should be penalized but not hard-blocked.",
    ),
    "rr_estimated_context": IssuePolicy(
        "rr_estimated_context",
        ISSUE_CATEGORY_SOFT,
        0.03,
        "Risk/reward context is estimated from fallback levels.",
    ),
    "missing_liquidity_context": IssuePolicy(
        "missing_liquidity_context",
        ISSUE_CATEGORY_SOFT,
        0.06,
        "Liquidity context is incomplete.",
    ),
    "missing_spread_context": IssuePolicy(
        "missing_spread_context",
        ISSUE_CATEGORY_SOFT,
        0.05,
        "Spread context is incomplete.",
    ),
    "missing_timing_context": IssuePolicy(
        "missing_timing_context",
        ISSUE_CATEGORY_SOFT,
        0.04,
        "Timing context is incomplete.",
    ),
    "type_mismatch": IssuePolicy(
        "type_mismatch",
        ISSUE_CATEGORY_SOFT,
        0.03,
        "Option contract type mismatch was softened for ranking.",
    ),
    "iv_bounds": IssuePolicy(
        "iv_bounds",
        ISSUE_CATEGORY_SOFT,
        0.04,
        "Option IV is outside preferred bounds.",
    ),
    "iv_skew_curvature": IssuePolicy(
        "iv_skew_curvature",
        ISSUE_CATEGORY_SOFT,
        0.04,
        "Option IV skew curvature is outside preferred bounds.",
    ),
    "signal_score_below_min": IssuePolicy(
        "signal_score_below_min",
        ISSUE_CATEGORY_SOFT,
        0.05,
        "Signal score is below strict minimum; keep as queue/advisory weakness.",
    ),
    "weak_signal": IssuePolicy(
        "weak_signal",
        ISSUE_CATEGORY_SOFT,
        0.05,
        "Signal quality is weak and should be penalized, not hard-blocked.",
    ),
    "no_signal": IssuePolicy(
        "no_signal",
        ISSUE_CATEGORY_SOFT,
        0.06,
        "No strong signal detected in this cycle; candidate remains low-confidence.",
    ),
    "missing_live_timing_context": IssuePolicy(
        "missing_live_timing_context",
        ISSUE_CATEGORY_WARNING,
        0.0,
        "Timing context is missing but market state allows degraded advisory evaluation.",
    ),
}


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(getattr(cfg, name, default))
    except Exception:
        return float(default)


def _ctx_bool(ctx: dict[str, Any], key: str, default: bool = False) -> bool:
    return bool(ctx.get(key, default))


def _ctx_text(ctx: dict[str, Any], key: str) -> str:
    return str(ctx.get(key) or "").strip().upper()


def _ctx_float(ctx: dict[str, Any], key: str) -> float | None:
    try:
        value = ctx.get(key)
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _ctx_has_executable_quote(ctx: dict[str, Any]) -> bool:
    explicit = ctx.get("has_executable_quote")
    if explicit is not None:
        return bool(explicit)
    bid = _ctx_float(ctx, "best_bid")
    ask = _ctx_float(ctx, "best_ask")
    return bool(bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid)


def _ctx_is_price_mismatch_severe(ctx: dict[str, Any]) -> bool:
    explicit = ctx.get("price_mismatch_severe")
    if explicit is not None:
        return bool(explicit)
    mismatch_abs = _ctx_float(ctx, "price_mismatch_abs")
    mismatch_pct = _ctx_float(ctx, "price_mismatch_pct")
    persistent = _ctx_bool(ctx, "price_mismatch_persistent")
    abs_tol = _ctx_float(ctx, "price_mismatch_abs_tol")
    pct_tol = _ctx_float(ctx, "price_mismatch_pct_tol")
    if persistent:
        return True
    abs_limit = float(abs_tol if abs_tol is not None and abs_tol > 0 else 5.0)
    pct_limit = float(pct_tol if pct_tol is not None and pct_tol > 0 else 0.03)
    abs_bad = mismatch_abs is not None and mismatch_abs > abs_limit
    pct_bad = mismatch_pct is not None and mismatch_pct > pct_limit
    return bool(abs_bad and pct_bad)


def _ctx_has_price_mismatch_detail(ctx: dict[str, Any]) -> bool:
    return any(
        ctx.get(key) not in (None, "", "None")
        for key in (
            "price_mismatch_severe",
            "price_mismatch_abs",
            "price_mismatch_pct",
            "price_mismatch_persistent",
            "price_mismatch_abs_tol",
            "price_mismatch_pct_tol",
        )
    )


def _base_issue_policy(issue_code: str) -> IssuePolicy:
    code = str(issue_code or "").strip()
    if not code:
        return IssuePolicy("", ISSUE_CATEGORY_WARNING, 0.0, "Unknown issue")
    if code in ISSUE_POLICY_REGISTRY:
        return ISSUE_POLICY_REGISTRY[code]
    lowered = code.lower()
    if lowered in ISSUE_POLICY_REGISTRY:
        return ISSUE_POLICY_REGISTRY[lowered]
    return IssuePolicy(code, ISSUE_CATEGORY_HARD, 0.0, "Unregistered issue")


def _log_classification(decision: IssueClassification, ctx: dict[str, Any]) -> None:
    try:
        logger.info(
            "ISSUE_CLASSIFIED %s",
            json.dumps(
                {
                    "code": decision.code,
                    "category": decision.category,
                    "penalty": decision.penalty,
                    "reason": decision.reason,
                    "mode": _ctx_text(ctx, "mode"),
                    "permission": _ctx_text(ctx, "permission"),
                    "entry_status": _ctx_text(ctx, "entry_status"),
                    "market_open": _ctx_bool(ctx, "market_open"),
                    "allow_stale_quotes": _ctx_bool(ctx, "allow_stale_quotes"),
                    "advisory_id": str(ctx.get("advisory_id") or ""),
                    "symbol": str(ctx.get("symbol") or ""),
                },
                sort_keys=True,
                default=str,
            ),
        )
    except Exception:
        return


def classify_issue(issue_code: str, ctx: dict[str, Any] | None = None) -> IssueClassification:
    policy = _base_issue_policy(issue_code)
    ctx = dict(ctx or {})
    code = policy.code
    mode = _ctx_text(ctx, "mode")
    permission = _ctx_text(ctx, "permission")
    market_open = _ctx_bool(ctx, "market_open")
    allow_stale_quotes = _ctx_bool(ctx, "allow_stale_quotes")
    subscription_failed = _ctx_bool(ctx, "subscription_failed")
    quote_source = str(ctx.get("quote_source") or "").strip().lower()
    quote_age_sec = _ctx_float(ctx, "quote_age_sec")
    has_executable_quote = _ctx_has_executable_quote(ctx)
    has_price_mismatch_detail = _ctx_has_price_mismatch_detail(ctx)
    price_mismatch_severe = _ctx_is_price_mismatch_severe(ctx)
    category = policy.default_category
    penalty = float(policy.default_penalty)
    reason = code

    relaxed_mode = mode in {"SIM", "PAPER", "OFFHOURS", "ADVISORY", "PLANNING"}
    executable_intent = permission in {"EXECUTE", "QUEUE_ONLY"}

    if code == "NO_LIVE_OPTION_FEED":
        if subscription_failed or permission == "BLOCK":
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "live_feed_required"
        elif not market_open:
            category = ISSUE_CATEGORY_WARNING
            penalty = 0.0
            reason = "market_closed"
        elif relaxed_mode or allow_stale_quotes:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_NO_LIVE_OPTION_FEED_SOFT_PENALTY", 0.08)
            reason = "relaxed_mode_feed_degraded"
        elif subscription_failed or executable_intent:
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "live_feed_required"
        else:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_NO_LIVE_OPTION_FEED_SOFT_PENALTY", 0.08)
            reason = "advisory_feed_degraded"
    elif code == "STALE_OPTION_LTP":
        if quote_source == "synthetic_offhours" or not market_open:
            category = ISSUE_CATEGORY_WARNING
            penalty = 0.0
            reason = "offhours_quote"
        elif has_executable_quote:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_STALE_OPTION_LTP_SOFT_PENALTY", 0.12)
            reason = "executable_quote_available"
        elif relaxed_mode or allow_stale_quotes:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_STALE_OPTION_LTP_SOFT_PENALTY", 0.12)
            reason = "relaxed_mode_quote_stale"
        elif executable_intent:
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "live_quote_stale"
        else:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_STALE_OPTION_LTP_SOFT_PENALTY", 0.12)
            reason = "advisory_quote_stale"
    elif code == "PRICE_MISMATCH":
        if quote_source == "synthetic_offhours" or not market_open:
            category = ISSUE_CATEGORY_WARNING
            penalty = 0.0
            reason = "offhours_price_check"
        elif has_price_mismatch_detail and not price_mismatch_severe:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_PRICE_MISMATCH_SOFT_PENALTY", 0.10)
            reason = "minor_or_transient_mismatch"
        elif relaxed_mode or allow_stale_quotes:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_PRICE_MISMATCH_SOFT_PENALTY", 0.10)
            reason = "relaxed_mode_price_mismatch"
        elif executable_intent and quote_age_sec is not None:
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "severe_or_persistent_mismatch"
        else:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_PRICE_MISMATCH_SOFT_PENALTY", 0.10)
            reason = "advisory_price_out_of_tolerance"
    elif code in {"NO_TOKEN", "MISSING_OPTION_TOKEN", "unresolved_contract", "MISSING_ENTRY"}:
        category = ISSUE_CATEGORY_HARD
        penalty = 0.0
        reason = "execution_identity_or_entry_missing"
    elif code == "type_mismatch":
        if bool(getattr(cfg, "OPTION_TYPE_MISMATCH_HARD_REJECT", False)):
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "type_mismatch_hard_reject_enabled"
        else:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_TYPE_MISMATCH_SOFT_PENALTY", policy.default_penalty)
            reason = "type_mismatch_softened"
    elif code == "iv_bounds":
        if bool(getattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", False)):
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "iv_bounds_hard_reject_enabled"
        else:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_IV_BOUNDS_SOFT_PENALTY", policy.default_penalty)
            reason = "iv_bounds_softened"
    elif code == "iv_skew_curvature":
        if bool(getattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", False)):
            category = ISSUE_CATEGORY_HARD
            penalty = 0.0
            reason = "iv_skew_curvature_hard_reject_enabled"
        else:
            category = ISSUE_CATEGORY_SOFT
            penalty = _cfg_float("ISSUE_POLICY_IV_SKEW_CURVATURE_SOFT_PENALTY", policy.default_penalty)
            reason = "iv_skew_curvature_softened"
    elif code == "signal_score_below_min":
        category = ISSUE_CATEGORY_SOFT
        penalty = _cfg_float("ISSUE_POLICY_SIGNAL_SCORE_BELOW_MIN_SOFT_PENALTY", policy.default_penalty)
        reason = "signal_score_softened"
    elif code in {"weak_signal", "no_signal"}:
        category = ISSUE_CATEGORY_SOFT
        penalty = _cfg_float("ISSUE_POLICY_WEAK_SIGNAL_SOFT_PENALTY", policy.default_penalty)
        reason = "weak_signal_softened"

    decision = IssueClassification(
        code=code,
        category=category,
        penalty=max(0.0, float(penalty)),
        reason=reason,
        evidence={
            "mode": mode,
            "permission": permission,
            "market_open": market_open,
            "allow_stale_quotes": allow_stale_quotes,
            "subscription_failed": subscription_failed,
            "quote_source": quote_source,
            "quote_age_sec": quote_age_sec,
        },
    )
    _log_classification(decision, ctx)
    return decision
