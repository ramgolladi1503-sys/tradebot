"""Runtime boot safety guard.

This module performs deterministic startup validation before the bot enters a
runtime loop. It is intentionally read-only except for writing a small safety
report for audit/debugging.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.paths import logs_dir
from core.time_utils import utc_now

BOOT_SAFETY_SCHEMA_VERSION = 1
REPORT_FILENAME = "runtime_boot_safety_latest.json"
VALID_MODES: frozenset[str] = frozenset({"LIVE", "PAPER", "SIM"})

# Canonical unsafe startup switches. Some are explicit env flags, others are
# aliases for existing config names that create the same unsafe condition.
UNSAFE_FLAG_ALIASES: dict[str, tuple[str, ...]] = {
    "FORCE_FALLBACK_EXECUTION": ("FORCE_FALLBACK_EXECUTION",),
    "ALLOW_STALE_QUOTES": ("ALLOW_STALE_QUOTES",),
    "DISABLE_RISK_GATE": ("DISABLE_RISK_GATE",),
    "DISABLE_KILL_SWITCH": ("DISABLE_KILL_SWITCH",),
    "ALLOW_SYNTHETIC_OPTION_QUOTES": (
        "ALLOW_SYNTHETIC_OPTION_QUOTES",
        "ALLOW_SYNTHETIC_CHAIN",
    ),
    "ALLOW_MARKET_CLOSED_EXECUTION": (
        "ALLOW_MARKET_CLOSED_EXECUTION",
        "OFFHOURS_FORCE_ENABLE",
    ),
    "PHASE2_FORCE_FALLBACK_EXECUTION": (
        "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE",
        "PHASE2_FORCE_FALLBACK_ALLOW_LIVE",
    ),
}


def _norm_mode(value: Any) -> str:
    mode = str(value or "SIM").strip().upper()
    return mode if mode in VALID_MODES else "INVALID"


def _flag_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _config_value(config: Any, name: str) -> Any:
    if config is None:
        return None
    if isinstance(config, Mapping):
        return config.get(name)
    return getattr(config, name, None)


def _env_value(env: Mapping[str, Any] | None, name: str) -> Any:
    if env is None:
        return None
    return env.get(name)


def _enabled_aliases(*, config: Any, env: Mapping[str, Any] | None, aliases: tuple[str, ...]) -> tuple[str, ...]:
    enabled: list[str] = []
    for alias in aliases:
        env_value = _env_value(env, alias)
        cfg_value = _config_value(config, alias)
        if env_value is not None:
            if _flag_enabled(env_value):
                enabled.append(alias)
            continue
        if _flag_enabled(cfg_value):
            enabled.append(alias)
    return tuple(enabled)


def _record_boot_safety_event(event: str, decision: "BootSafetyDecision", *, error: str | None = None) -> None:
    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        record_runtime_startup_event(
            event,
            source="core.runtime_safety_boot_guard.enforce_runtime_boot_safety",
            details={
                "mode": decision.mode,
                "allowed": bool(decision.allowed),
                "fatal_reasons": list(decision.fatal_reasons),
                "warnings": list(decision.warnings),
                "unsafe_flags_count": len(decision.unsafe_flags),
                "is_order_action": False,
            },
            error=error,
        )
    except Exception:
        pass


@dataclass(frozen=True)
class BootSafetyDecision:
    schema_version: int
    allowed: bool
    mode: str
    unsafe_flags: tuple[str, ...]
    unsafe_sources: dict[str, list[str]]
    fatal_reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def append(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["unsafe_flags"] = list(self.unsafe_flags)
        payload["fatal_reasons"] = list(self.fatal_reasons)
        payload["warnings"] = list(self.warnings)
        payload["unsafe_sources"] = {key: list(value) for key, value in self.unsafe_sources.items()}
        payload.update({"is_order_action": False, "append": False})
        return payload


def assess_runtime_boot_safety(
    *,
    mode: str | None = None,
    config: Any = None,
    env: Mapping[str, Any] | None = None,
) -> BootSafetyDecision:
    """Return the startup safety decision for the requested runtime mode."""

    env = env if env is not None else os.environ
    resolved_mode = _norm_mode(mode or _env_value(env, "EXECUTION_MODE") or _config_value(config, "EXECUTION_MODE"))
    unsafe_sources: dict[str, list[str]] = {}
    fatal_reasons: list[str] = []
    warnings: list[str] = []

    if resolved_mode == "INVALID":
        fatal_reasons.append("INVALID_EXECUTION_MODE")

    for canonical, aliases in UNSAFE_FLAG_ALIASES.items():
        enabled = _enabled_aliases(config=config, env=env, aliases=aliases)
        if not enabled:
            continue
        unsafe_sources[canonical] = list(enabled)

    unsafe_flags = tuple(sorted(unsafe_sources.keys()))

    if resolved_mode == "LIVE" and unsafe_flags:
        for flag in unsafe_flags:
            fatal_reasons.append(f"LIVE_UNSAFE_FLAG:{flag}")
    elif resolved_mode in {"PAPER", "SIM"} and unsafe_flags:
        for flag in unsafe_flags:
            warnings.append(f"NON_LIVE_UNSAFE_FLAG:{flag}")

    allowed = not fatal_reasons
    return BootSafetyDecision(
        schema_version=BOOT_SAFETY_SCHEMA_VERSION,
        allowed=allowed,
        mode=resolved_mode,
        unsafe_flags=unsafe_flags,
        unsafe_sources=unsafe_sources,
        fatal_reasons=tuple(sorted(set(fatal_reasons))),
        warnings=tuple(sorted(set(warnings))),
    )


def write_boot_safety_report(
    decision: BootSafetyDecision,
    *,
    path: Path | None = None,
) -> Path:
    """Write the latest boot-safety report and return its path."""

    target = path or (logs_dir() / REPORT_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = decision.to_dict()
    payload["ts"] = utc_now().isoformat()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def enforce_runtime_boot_safety(
    *,
    mode: str | None = None,
    config: Any = None,
    env: Mapping[str, Any] | None = None,
    report_path: Path | None = None,
) -> BootSafetyDecision:
    """Assess, write evidence, and raise RuntimeError when boot is unsafe."""

    decision = assess_runtime_boot_safety(mode=mode, config=config, env=env)
    write_boot_safety_report(decision, path=report_path)
    if not decision.allowed:
        _record_boot_safety_event(
            "MAIN_SAFETY_VALIDATION_FAILED",
            decision,
            error="runtime_boot_safety_failed:" + ",".join(decision.fatal_reasons),
        )
        raise RuntimeError("runtime_boot_safety_failed:" + ",".join(decision.fatal_reasons))
    _record_boot_safety_event("MAIN_SAFETY_VALIDATED", decision)
    return decision


__all__ = [
    "BootSafetyDecision",
    "assess_runtime_boot_safety",
    "enforce_runtime_boot_safety",
    "write_boot_safety_report",
]
