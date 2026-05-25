"""Read-only LIVE/PAPER feed policy separation.

This module chooses explicit feed-health thresholds by runtime mode and delegates
to canonical feed-health truth classification. It does not reconnect feeds,
resubscribe tokens, mutate runtime state, write files, call brokers, or create
order intent.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth

FEED_POLICY_SCHEMA_VERSION = 1
FEED_POLICY_CONFIG_SCHEMA_VERSION = 1
LIVE_FEED_POLICY = "LIVE_STRICT"
PAPER_FEED_POLICY = "PAPER_OBSERVATION"
SIM_FEED_POLICY = "SIM_OBSERVATION"
INVALID_FEED_POLICY = "INVALID_MODE_FAIL_CLOSED"
FEED_POLICY_BLOCKER = "feed_policy_invalid_mode"
FEED_POLICY_CONFIG_BLOCKER = "feed_policy_config_invalid"
_ORDER_ACTION_KEY = "is_" + "order_action"

_MODE_ALIASES: dict[str, str] = {
    "LIVE": "LIVE",
    "PROD": "LIVE",
    "PRODUCTION": "LIVE",
    "PAPER": "PAPER",
    "PAPER_TRADING": "PAPER",
    "SIM": "SIM",
    "SIMULATION": "SIM",
    "BACKTEST": "SIM",
}

_REQUIRED_POLICY_MODES: tuple[str, ...] = ("LIVE", "PAPER", "SIM")
_EXPECTED_POLICY_NAMES: dict[str, str] = {
    "LIVE": LIVE_FEED_POLICY,
    "PAPER": PAPER_FEED_POLICY,
    "SIM": SIM_FEED_POLICY,
}
_AGE_FIELDS: tuple[str, ...] = ("max_option_tick_age_sec", "max_ltp_age_sec", "max_depth_age_sec")


@dataclass(frozen=True)
class FeedPolicyThresholds:
    """Thresholds used to classify feed health for a runtime mode."""

    mode: str
    policy_name: str
    max_option_tick_age_sec: float
    max_ltp_age_sec: float
    max_depth_age_sec: float
    require_websocket: bool
    require_symbol_truth: bool

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedPolicyConfigIssue:
    """Static feed-policy config validation issue."""

    field: str
    reason: str
    value: str

    def to_payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class FeedPolicyConfigAudit:
    """Read-only audit for feed-policy threshold configuration."""

    schema_version: int
    read_only: bool
    append: bool
    config_ok: bool
    reason_code: str
    issues: tuple[FeedPolicyConfigIssue, ...]
    thresholds: tuple[FeedPolicyThresholds, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "config_ok": self.config_ok,
            "reason_code": self.reason_code,
            "issues": [issue.to_payload() for issue in self.issues],
            "thresholds": [threshold.to_payload() for threshold in self.thresholds],
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


@dataclass(frozen=True)
class FeedPolicyDecision:
    """Read-only feed policy decision with canonical feed truth evidence."""

    schema_version: int
    read_only: bool
    append: bool
    mode: str
    policy_name: str
    feed_ok: bool
    reason_code: str
    reasons: tuple[str, ...]
    thresholds: FeedPolicyThresholds
    feed_health_truth: dict[str, Any]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "mode": self.mode,
            "policy_name": self.policy_name,
            "feed_ok": self.feed_ok,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "thresholds": self.thresholds.to_payload(),
            "feed_health_truth": dict(self.feed_health_truth),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def classify_feed_with_policy(
    payload: Mapping[str, Any] | None,
    *,
    mode: str | None,
    symbols: tuple[str, ...] | list[str] = (),
    policy_config: Mapping[str, Any] | None = None,
) -> FeedPolicyDecision:
    """Classify feed truth using explicit LIVE/PAPER/SIM policy thresholds."""

    normalized_mode = _normalize_mode(mode)
    config_audit = validate_feed_policy_config(policy_config)
    thresholds = _thresholds_from_audit(normalized_mode, config_audit)
    if normalized_mode == "INVALID":
        truth = classify_feed_health_truth(None)
        return FeedPolicyDecision(
            schema_version=FEED_POLICY_SCHEMA_VERSION,
            read_only=True,
            append=False,
            mode="INVALID",
            policy_name=INVALID_FEED_POLICY,
            feed_ok=False,
            reason_code="invalid_feed_policy_mode",
            reasons=("invalid_mode",),
            thresholds=thresholds,
            feed_health_truth=truth.to_payload(),
            blockers=(FEED_POLICY_BLOCKER,),
            warnings=(),
            metadata={
                "policy": "feed_policy_v1",
                "scope": "read_only_mode_specific_feed_thresholds",
                "config_audit": config_audit.to_payload(),
            },
        )
    if not config_audit.config_ok:
        truth = classify_feed_health_truth(None)
        issue_reasons = tuple(issue.reason for issue in config_audit.issues)
        return FeedPolicyDecision(
            schema_version=FEED_POLICY_SCHEMA_VERSION,
            read_only=True,
            append=False,
            mode=normalized_mode,
            policy_name=INVALID_FEED_POLICY,
            feed_ok=False,
            reason_code=FEED_POLICY_CONFIG_BLOCKER,
            reasons=(FEED_POLICY_CONFIG_BLOCKER, *issue_reasons),
            thresholds=thresholds,
            feed_health_truth=truth.to_payload(),
            blockers=(FEED_POLICY_CONFIG_BLOCKER,),
            warnings=issue_reasons,
            metadata={
                "policy": "feed_policy_v1",
                "scope": "read_only_mode_specific_feed_thresholds",
                "config_audit": config_audit.to_payload(),
            },
        )

    payload_dict = dict(payload) if isinstance(payload, Mapping) else None
    truth = classify_feed_health_truth(
        payload_dict,
        symbols=symbols,
        max_option_tick_age_sec=thresholds.max_option_tick_age_sec,
        max_ltp_age_sec=thresholds.max_ltp_age_sec,
        max_depth_age_sec=thresholds.max_depth_age_sec,
    )
    reasons = list(truth.reasons)
    if thresholds.require_websocket and truth.websocket_ok is not True:
        _append_unique(reasons, "websocket_required_by_policy")
    if thresholds.require_symbol_truth and symbols and not truth.symbols:
        _append_unique(reasons, "symbol_truth_required_by_policy")

    feed_ok = bool(truth.feed_ok) and not reasons
    return FeedPolicyDecision(
        schema_version=FEED_POLICY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        mode=normalized_mode,
        policy_name=thresholds.policy_name,
        feed_ok=feed_ok,
        reason_code="ok" if feed_ok else "feed_policy_blocked",
        reasons=tuple(reasons),
        thresholds=thresholds,
        feed_health_truth=truth.to_payload(),
        blockers=tuple(reasons) if not feed_ok else (),
        warnings=(),
        metadata={
            "policy": "feed_policy_v1",
            "scope": "read_only_mode_specific_feed_thresholds",
            "input_mode": str(mode or ""),
            "symbols_requested": list(symbols or ()),
            "config_audit": config_audit.to_payload(),
        },
    )


def thresholds_for_mode(
    mode: str | None,
    *,
    policy_config: Mapping[str, Any] | None = None,
) -> FeedPolicyThresholds:
    normalized = _normalize_mode(mode)
    audit = validate_feed_policy_config(policy_config)
    return _thresholds_from_audit(normalized, audit)


def validate_feed_policy_config(policy_config: Mapping[str, Any] | None = None) -> FeedPolicyConfigAudit:
    """Validate feed policy thresholds before they are trusted by mode selection."""

    raw_config = _default_policy_config() if policy_config is None else policy_config
    issues: list[FeedPolicyConfigIssue] = []
    thresholds_by_mode: dict[str, FeedPolicyThresholds] = {}
    if not isinstance(raw_config, Mapping):
        issues.append(_issue("policy_config", "config_not_mapping", raw_config))
    else:
        for mode in _REQUIRED_POLICY_MODES:
            raw = _lookup_mode(raw_config, mode)
            if raw is None:
                issues.append(_issue(mode, "required_mode_missing", ""))
                continue
            threshold = _coerce_threshold(mode, raw, issues)
            if threshold is not None:
                thresholds_by_mode[mode] = threshold

    for mode, threshold in thresholds_by_mode.items():
        _validate_threshold(mode, threshold, issues)
    _validate_threshold_order(thresholds_by_mode, issues)

    thresholds = tuple(thresholds_by_mode[mode] for mode in _REQUIRED_POLICY_MODES if mode in thresholds_by_mode)
    return FeedPolicyConfigAudit(
        schema_version=FEED_POLICY_CONFIG_SCHEMA_VERSION,
        read_only=True,
        append=False,
        config_ok=not issues,
        reason_code="ok" if not issues else FEED_POLICY_CONFIG_BLOCKER,
        issues=tuple(issues),
        thresholds=thresholds,
        metadata={
            "policy_config": "feed_policy_config_v1",
            "scope": "read_only_static_feed_threshold_validation",
            "required_modes": list(_REQUIRED_POLICY_MODES),
        },
    )


def _default_policy_config() -> dict[str, FeedPolicyThresholds]:
    return {
        "LIVE": FeedPolicyThresholds(
            mode="LIVE",
            policy_name=LIVE_FEED_POLICY,
            max_option_tick_age_sec=2.0,
            max_ltp_age_sec=2.0,
            max_depth_age_sec=4.0,
            require_websocket=True,
            require_symbol_truth=True,
        ),
        "PAPER": FeedPolicyThresholds(
            mode="PAPER",
            policy_name=PAPER_FEED_POLICY,
            max_option_tick_age_sec=5.0,
            max_ltp_age_sec=5.0,
            max_depth_age_sec=10.0,
            require_websocket=True,
            require_symbol_truth=True,
        ),
        "SIM": FeedPolicyThresholds(
            mode="SIM",
            policy_name=SIM_FEED_POLICY,
            max_option_tick_age_sec=60.0,
            max_ltp_age_sec=60.0,
            max_depth_age_sec=120.0,
            require_websocket=False,
            require_symbol_truth=False,
        ),
    }


def _thresholds_from_audit(mode: str, audit: FeedPolicyConfigAudit) -> FeedPolicyThresholds:
    if mode == "INVALID" or not audit.config_ok:
        return _invalid_thresholds()
    for threshold in audit.thresholds:
        if threshold.mode == mode:
            return threshold
    return _invalid_thresholds()


def _invalid_thresholds() -> FeedPolicyThresholds:
    return FeedPolicyThresholds(
        mode="INVALID",
        policy_name=INVALID_FEED_POLICY,
        max_option_tick_age_sec=0.0,
        max_ltp_age_sec=0.0,
        max_depth_age_sec=0.0,
        require_websocket=True,
        require_symbol_truth=True,
    )


def _lookup_mode(config: Mapping[str, Any], mode: str) -> Any:
    for key, value in config.items():
        if _normalize_mode(str(key)) == mode:
            return value
    return None


def _coerce_threshold(
    mode: str,
    raw: Any,
    issues: list[FeedPolicyConfigIssue],
) -> FeedPolicyThresholds | None:
    if isinstance(raw, FeedPolicyThresholds):
        return raw
    if not isinstance(raw, Mapping):
        issues.append(_issue(mode, "mode_config_not_mapping", raw))
        return None

    policy_name = str(raw.get("policy_name") or _EXPECTED_POLICY_NAMES.get(mode, "")).strip()
    values: dict[str, float] = {}
    for field_name in _AGE_FIELDS:
        value = _finite_positive_float(raw.get(field_name))
        if value is None:
            issues.append(_issue(f"{mode}.{field_name}", "threshold_not_positive_finite", raw.get(field_name)))
            value = 0.0
        values[field_name] = value
    return FeedPolicyThresholds(
        mode=str(raw.get("mode") or mode).strip().upper(),
        policy_name=policy_name,
        max_option_tick_age_sec=values["max_option_tick_age_sec"],
        max_ltp_age_sec=values["max_ltp_age_sec"],
        max_depth_age_sec=values["max_depth_age_sec"],
        require_websocket=bool(raw.get("require_websocket")),
        require_symbol_truth=bool(raw.get("require_symbol_truth")),
    )


def _validate_threshold(mode: str, threshold: FeedPolicyThresholds, issues: list[FeedPolicyConfigIssue]) -> None:
    if threshold.mode != mode:
        issues.append(_issue(f"{mode}.mode", "mode_mismatch", threshold.mode))
    expected_policy_name = _EXPECTED_POLICY_NAMES.get(mode)
    if threshold.policy_name != expected_policy_name:
        issues.append(_issue(f"{mode}.policy_name", "policy_name_mismatch", threshold.policy_name))
    for field_name in _AGE_FIELDS:
        if _finite_positive_float(getattr(threshold, field_name)) is None:
            issues.append(_issue(f"{mode}.{field_name}", "threshold_not_positive_finite", getattr(threshold, field_name)))
    if mode in {"LIVE", "PAPER"}:
        if threshold.require_websocket is not True:
            issues.append(_issue(f"{mode}.require_websocket", "websocket_requirement_must_be_true", threshold.require_websocket))
        if threshold.require_symbol_truth is not True:
            issues.append(_issue(f"{mode}.require_symbol_truth", "symbol_truth_requirement_must_be_true", threshold.require_symbol_truth))


def _validate_threshold_order(
    thresholds_by_mode: Mapping[str, FeedPolicyThresholds],
    issues: list[FeedPolicyConfigIssue],
) -> None:
    live = thresholds_by_mode.get("LIVE")
    paper = thresholds_by_mode.get("PAPER")
    sim = thresholds_by_mode.get("SIM")
    if live and paper:
        _require_lte("LIVE", live, "PAPER", paper, issues)
    if paper and sim:
        _require_lte("PAPER", paper, "SIM", sim, issues)


def _require_lte(
    stricter_mode: str,
    stricter: FeedPolicyThresholds,
    looser_mode: str,
    looser: FeedPolicyThresholds,
    issues: list[FeedPolicyConfigIssue],
) -> None:
    for field_name in _AGE_FIELDS:
        if float(getattr(stricter, field_name)) > float(getattr(looser, field_name)):
            issues.append(
                _issue(
                    f"{stricter_mode}.{field_name}",
                    f"threshold_must_be_lte_{looser_mode.lower()}",
                    getattr(stricter, field_name),
                )
            )


def _finite_positive_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out) or out <= 0.0:
        return None
    return out


def _normalize_mode(mode: str | None) -> str:
    text = str(mode or "").strip().upper()
    return _MODE_ALIASES.get(text, "INVALID")


def _append_unique(reasons: list[str], reason: str) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _issue(field: str, reason: str, value: Any) -> FeedPolicyConfigIssue:
    return FeedPolicyConfigIssue(field=str(field), reason=str(reason), value=str(value))


__all__ = [
    "FEED_POLICY_BLOCKER",
    "FEED_POLICY_CONFIG_BLOCKER",
    "FEED_POLICY_CONFIG_SCHEMA_VERSION",
    "FEED_POLICY_SCHEMA_VERSION",
    "INVALID_FEED_POLICY",
    "LIVE_FEED_POLICY",
    "PAPER_FEED_POLICY",
    "SIM_FEED_POLICY",
    "FeedPolicyConfigAudit",
    "FeedPolicyConfigIssue",
    "FeedPolicyDecision",
    "FeedPolicyThresholds",
    "classify_feed_with_policy",
    "thresholds_for_mode",
    "validate_feed_policy_config",
]
