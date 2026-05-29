#!/usr/bin/env python
"""Pre-market LIVE readiness gate.

Read-only safety gate for validating LIVE startup prerequisites before the bot
enters the live market path. This script does not place orders and does not
change ranking or dashboard behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # Keep direct script execution and test imports both working.
    runpy.run_path(Path(__file__).with_name("bootstrap.py"))
except Exception:
    pass

PASS = "PASS"
FAIL = "FAIL"
MARKET_CLOSED_PENDING_TICK_PROOF = "MARKET_CLOSED_PENDING_TICK_PROOF"

EXIT_OK = 0
EXIT_FAIL = 2

SOURCE = "pre_live_readiness_gate_v1"
SCHEMA_VERSION = 1

FALLBACK_FLAG_NAMES = (
    "ALLOW_FALLBACK_EXECUTION",
    "ALLOW_RECOVERED_FALLBACK_EXECUTION",
    "ENABLE_FALLBACK_EXECUTION",
    "ENABLE_RECOVERED_FALLBACK_EXECUTION",
    "EXECUTION_ALLOW_FALLBACK",
    "FALLBACK_EXECUTION_ENABLED",
    "LIVE_ALLOW_FALLBACK_EXECUTION",
    "LIVE_EXECUTION_ALLOW_FALLBACK",
    "LIVE_FALLBACK_EXECUTION_ENABLED",
)

PENDING_WARMUP_BLOCKERS = {
    "INDICATOR_EMPTY_INPUT",
    "INDICATOR_BARS_BELOW_WARMUP",
    "indicator_empty_input",
    "indicator_bars_below_warmup",
}

Dependency = Callable[[], Any]
TokenResolver = Callable[[Sequence[str]], tuple[Sequence[int], Sequence[Mapping[str, Any]]]]


@dataclass(frozen=True)
class PreLiveReadinessDependencies:
    config: Any | None = None
    market_open: bool | None = None
    credential_checker: Dependency | None = None
    auth_health_loader: Dependency | None = None
    auth_latch_loader: Dependency | None = None
    token_resolver: TokenResolver | None = None
    feed_breaker_loader: Dependency | None = None
    lock_checker: Dependency | None = None
    indicator_loader: Dependency | None = None
    now_epoch: float | None = None


def evaluate_pre_live_readiness(
    *,
    mode: str = "LIVE",
    dependencies: PreLiveReadinessDependencies | None = None,
) -> dict[str, Any]:
    deps = dependencies or PreLiveReadinessDependencies()
    cfg = deps.config if deps.config is not None else _load_config()
    mode_u = _normalize_mode(mode, cfg)
    now_epoch = float(deps.now_epoch if deps.now_epoch is not None else time.time())
    market_open = bool(deps.market_open) if deps.market_open is not None else _is_market_open()

    blockers: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    def add_blocker(code: str) -> None:
        text = str(code or "").strip()
        if text and text not in blockers:
            blockers.append(text)

    def add_warning(code: str) -> None:
        text = str(code or "").strip()
        if text and text not in warnings:
            warnings.append(text)

    symbols = _configured_symbols(cfg)
    config_ok = bool(symbols)
    if not config_ok:
        add_blocker("config_symbols_missing")
    checks["config"] = {"ok": config_ok, "symbols": symbols}

    credentials = _run_loader(deps.credential_checker, _default_credentials_check)
    credentials_ok = bool(_mapping(credentials).get("ok", False))
    if mode_u == "LIVE" and not credentials_ok:
        add_blocker("credentials_missing")
    checks["credentials"] = _mapping(credentials) or {"ok": credentials_ok}

    auth_payload = _run_loader(deps.auth_health_loader, _default_auth_health)
    auth_check = _mapping(auth_payload)
    auth_ok = bool(auth_check.get("ok", False))
    auth_state = str(auth_check.get("auth_state") or auth_check.get("state") or "").strip().upper()
    if mode_u == "LIVE" and (not auth_ok or auth_state in {"AUTH_REQUIRED", "FAILED", "INVALID"}):
        add_blocker("auth_invalid")
    checks["auth_health"] = auth_check or {"ok": auth_ok, "auth_state": auth_state}

    latch_payload = _run_loader(deps.auth_latch_loader, _default_auth_latch)
    latch_check = _mapping(latch_payload)
    latch_active = _auth_latch_active(latch_check)
    if mode_u == "LIVE" and latch_active:
        add_blocker("auth_required_latch_active")
    checks["auth_latch"] = {**latch_check, "active": latch_active}

    fallback_enabled, fallback_flags = _fallback_execution_enabled(cfg)
    if mode_u == "LIVE" and fallback_enabled:
        add_blocker("fallback_execution_enabled_live")
    checks["fallback_execution"] = {"ok": not fallback_enabled, "enabled": fallback_enabled, "flags": fallback_flags}

    tokens, resolution = _resolve_tokens(deps.token_resolver, symbols)
    token_summary = _token_universe_summary(tokens, resolution)
    if mode_u == "LIVE" and int(token_summary["option_token_count"]) <= 0:
        add_blocker("token_universe_zero")
    if token_summary["degraded_but_subscribable"]:
        add_warning("token_universe_degraded_but_subscribable")
    checks["token_universe"] = token_summary

    breaker_payload = _run_loader(deps.feed_breaker_loader, _default_feed_breaker)
    breaker_check = _mapping(breaker_payload)
    breaker_tripped = bool(breaker_check.get("tripped", False))
    if breaker_tripped:
        add_blocker("feed_circuit_breaker_tripped")
    checks["feed_circuit_breaker"] = breaker_check or {"tripped": breaker_tripped}

    lock_payload = _run_loader(deps.lock_checker, _default_lock_check)
    lock_check = _mapping(lock_payload)
    lock_ok = bool(lock_check.get("ok", False))
    if not lock_ok:
        add_blocker("stale_lock_blocking_feed")
    checks["feed_lock"] = lock_check or {"ok": lock_ok}

    indicator_payload = _run_loader(deps.indicator_loader, _default_indicator_readiness)
    indicator_check = _classify_indicator_readiness(_mapping(indicator_payload))
    if indicator_check["pending_warmup"]:
        add_warning("indicator_readiness_pending_warmup")
    elif not indicator_check["ok"]:
        add_blocker("indicator_readiness_blocked")
    checks["indicator_readiness"] = indicator_check

    live_tick_proof_obtained = bool(market_open)
    if blockers:
        outcome = FAIL
        ready = False
        exit_code = EXIT_FAIL
    elif not live_tick_proof_obtained:
        outcome = MARKET_CLOSED_PENDING_TICK_PROOF
        ready = False
        exit_code = EXIT_OK
        add_warning("market_closed_pending_live_tick_proof")
    else:
        outcome = PASS
        ready = True
        exit_code = EXIT_OK

    return _payload(
        mode=mode_u,
        outcome=outcome,
        ready=ready,
        market_open=market_open,
        live_tick_proof_obtained=live_tick_proof_obtained,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
        now_epoch=now_epoch,
        exit_code=exit_code,
    )


def _payload(
    *,
    mode: str,
    outcome: str,
    ready: bool,
    market_open: bool,
    live_tick_proof_obtained: bool,
    blockers: Sequence[str],
    warnings: Sequence[str],
    checks: Mapping[str, Any],
    now_epoch: float,
    exit_code: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "ts_epoch": float(now_epoch),
        "mode": str(mode),
        "outcome": str(outcome),
        "ready": bool(ready),
        "hard_fail": bool(outcome == FAIL),
        "market_open": bool(market_open),
        "live_tick_proof_obtained": bool(live_tick_proof_obtained),
        "blockers": list(blockers),
        "warnings": list(warnings),
        "checks": dict(checks),
        "exit_code": int(exit_code),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def _normalize_mode(mode: str | None, cfg: Any) -> str:
    raw = str(mode or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper()
    return raw if raw in {"LIVE", "PAPER", "SIM", "DRY_RUN"} else "SIM"


def _configured_symbols(cfg: Any) -> list[str]:
    raw = getattr(cfg, "SYMBOLS", None)
    if raw is None:
        raw = os.getenv("SYMBOLS", "")
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        try:
            values = list(raw)
        except TypeError:
            values = []
    return [str(value).strip().upper() for value in values if str(value or "").strip()]


def _load_config() -> Any:
    from config import config as cfg

    return cfg


def _is_market_open() -> bool:
    try:
        from core.time_utils import is_market_open_ist

        return bool(is_market_open_ist())
    except Exception:
        return False


def _run_loader(loader: Dependency | None, fallback: Dependency) -> Any:
    try:
        fn = loader if loader is not None else fallback
        return fn()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def _default_credentials_check() -> dict[str, Any]:
    try:
        from core.auth import validate_kite_startup_credentials

        creds = validate_kite_startup_credentials(
            repo_root_path=Path(__file__).resolve().parents[1],
            require_access_token=True,
            caller_module=__name__,
        )
        return {
            "ok": bool(creds.get("api_key") and creds.get("access_token")),
            "api_key_present": bool(creds.get("api_key")),
            "access_token_present": bool(creds.get("access_token")),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "api_key_present": False, "access_token_present": False}


def _default_auth_health() -> dict[str, Any]:
    try:
        from core.auth_health import get_kite_auth_health

        return dict(get_kite_auth_health(force=True) or {})
    except Exception as exc:
        return {"ok": False, "auth_state": "FAILED", "error": str(exc)}


def _default_auth_latch() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from core.auth_manager import load_auth_state

        out["auth_state"] = dict(load_auth_state(repo_root_path=Path(__file__).resolve().parents[1]) or {})
    except Exception as exc:
        out["auth_state_error"] = str(exc)
    try:
        from core.auth_health import load_auth_runtime_guard

        out["auth_runtime_guard"] = dict(load_auth_runtime_guard() or {})
    except Exception as exc:
        out["auth_runtime_guard_error"] = str(exc)
    return out


def _auth_latch_active(payload: Mapping[str, Any]) -> bool:
    auth_state = _mapping(payload.get("auth_state"))
    runtime_guard = _mapping(payload.get("auth_runtime_guard"))
    status_values = {
        str(auth_state.get("status") or "").upper(),
        str(auth_state.get("auth_state") or "").upper(),
        str(runtime_guard.get("status") or "").upper(),
        str(runtime_guard.get("auth_state") or "").upper(),
    }
    if "AUTH_REQUIRED" in status_values:
        return True
    if bool(runtime_guard.get("degrade_to_planning")) and runtime_guard.get("auth_ok") is False:
        return True
    return False


def _fallback_execution_enabled(cfg: Any) -> tuple[bool, dict[str, bool]]:
    flags: dict[str, bool] = {}
    for name in FALLBACK_FLAG_NAMES:
        if os.getenv(name) is not None:
            flags[name] = _truthy(os.getenv(name))
        elif hasattr(cfg, name):
            flags[name] = _truthy(getattr(cfg, name))
    return any(flags.values()), flags


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _resolve_tokens(
    resolver: TokenResolver | None,
    symbols: Sequence[str],
) -> tuple[list[int], list[Mapping[str, Any]]]:
    try:
        if resolver is not None:
            raw_tokens, raw_resolution = resolver(list(symbols))
        else:
            raw_tokens, raw_resolution = _default_token_resolver(list(symbols))
    except Exception as exc:
        return [], [{"error": f"{type(exc).__name__}:{exc}", "option_coverage_status": "ZERO"}]
    return _positive_ints(raw_tokens), [dict(item) for item in list(raw_resolution or []) if isinstance(item, Mapping)]


def _default_token_resolver(symbols: Sequence[str]) -> tuple[Sequence[int], Sequence[Mapping[str, Any]]]:
    from config import config as cfg
    from core import kite_depth_ws as ws

    max_tokens = getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", None)
    return ws.build_depth_subscription_tokens(list(symbols), max_tokens=max_tokens)


def _positive_ints(values: Any) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for value in list(values or []):
        try:
            token = int(value)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _token_universe_summary(tokens: Sequence[int], resolution: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    option_count = 0
    resolved_option_count = 0
    coverage_statuses: list[str] = []
    coverage_reasons: list[str] = []
    rows: list[dict[str, Any]] = []
    for row_raw in resolution:
        row = dict(row_raw)
        final_count = _int(row.get("final_option_count"), _int(row.get("option_count"), 0))
        resolved_count = _int(row.get("resolved_option_count"), final_count)
        option_count += max(0, final_count)
        resolved_option_count += max(0, resolved_count)
        status = str(row.get("option_coverage_status") or "").strip().upper()
        reason = str(row.get("option_coverage_reason") or row.get("option_fail_reason") or "").strip()
        if status:
            coverage_statuses.append(status)
        if reason:
            coverage_reasons.append(reason)
        rows.append(row)
    if not resolution:
        coverage_statuses.append("ZERO")
    degraded = bool(option_count > 0 and any(status == "DEGRADED" for status in coverage_statuses))
    zero = bool(option_count <= 0)
    return {
        "ok": not zero,
        "token_count": len(list(tokens or [])),
        "option_token_count": int(option_count),
        "resolved_option_token_count": int(resolved_option_count),
        "coverage_statuses": _dedupe(coverage_statuses),
        "coverage_reasons": _dedupe(coverage_reasons),
        "degraded_but_subscribable": degraded,
        "rows": rows,
    }


def _default_feed_breaker() -> dict[str, Any]:
    try:
        from core.feed_circuit_breaker import maybe_auto_clear

        return dict(maybe_auto_clear({}) or {})
    except Exception as exc:
        return {"tripped": True, "error": str(exc)}


def _default_lock_check() -> dict[str, Any]:
    lock = None
    try:
        from core.instance_lock import InstanceLock

        lock = InstanceLock(repo_root_path=Path(__file__).resolve().parents[1])
        acquired, holder = lock.acquire()
        if not acquired:
            return {"ok": False, "holder": dict(holder or {})}
        return {"ok": True, "holder": dict(holder or {})}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            if lock is not None:
                lock.release()
        except Exception:
            pass


def _default_indicator_readiness() -> dict[str, Any]:
    try:
        from core.live_indicator_readiness import live_indicator_readiness_runtime_evidence_path

        path = live_indicator_readiness_runtime_evidence_path()
        if not path.exists():
            return {"ok": True, "pending_warmup": True, "reason": "indicator_readiness_evidence_missing"}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return dict(payload) if isinstance(payload, Mapping) else {"ok": False, "reason": "indicator_readiness_payload_invalid"}
    except Exception as exc:
        return {"ok": True, "pending_warmup": True, "reason": f"indicator_readiness_unavailable:{type(exc).__name__}:{exc}"}


def _classify_indicator_readiness(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(payload or {})
    if raw.get("pending_warmup") is True:
        return {**raw, "ok": True, "pending_warmup": True}
    if raw.get("indicators_ready") is True or raw.get("ready") is True:
        return {**raw, "ok": True, "pending_warmup": False}
    blockers = [str(value) for value in list(raw.get("blockers") or []) if str(value or "").strip()]
    decisions = [dict(item) for item in list(raw.get("decisions") or []) if isinstance(item, Mapping)]
    for decision in decisions:
        blockers.extend(str(value) for value in list(decision.get("blockers") or []) if str(value or "").strip())
    blockers = _dedupe(blockers)
    if not blockers:
        return {**raw, "ok": True, "pending_warmup": True, "blockers": blockers, "reason": raw.get("reason", "indicator_readiness_pending_warmup")}
    pending_only = all(str(code) in PENDING_WARMUP_BLOCKERS for code in blockers)
    return {**raw, "ok": bool(pending_only), "pending_warmup": bool(pending_only), "blockers": blockers}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _dedupe(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-market LIVE readiness gate.")
    parser.add_argument("--mode", default="LIVE", help="Execution mode override: LIVE|PAPER|SIM")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    args = parser.parse_args(argv)

    payload = evaluate_pre_live_readiness(mode=args.mode)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"{payload['outcome']} blockers={','.join(payload['blockers']) or '-'} warnings={','.join(payload['warnings']) or '-'}")
    return int(payload.get("exit_code", EXIT_FAIL))


if __name__ == "__main__":
    sys.exit(main())
