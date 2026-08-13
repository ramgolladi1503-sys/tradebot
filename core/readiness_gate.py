# Migration note:
# Readiness feed state now exposes OFFHOURS fields and SLA thresholds for market-closed mode.

from __future__ import annotations
from core.paths import data_root, logs_dir, runtime_dir

import json
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, Tuple, List, Any

from config import config as cfg
from core import risk_halt
from core.audit_log import verify_chain as verify_audit_chain
from core.auth_health import get_kite_auth_health, run_preopen_auth_warm_check
from core.feed_circuit_breaker import maybe_auto_clear as feed_breaker_maybe_auto_clear
from core.feed_debug import get_feed_debug
from core.market_context import derive_market_context
from core.freshness_policy import resolve_freshness_policy
from core.time_utils import compute_age_sec, is_market_open_ist, normalize_epoch_seconds, now_ist
from core.market_calendar import IN_HOLIDAYS
from core.trade_store import init_db
from core.readiness_state import ReadinessResult, ReadinessState
from core.gate_status_log import gate_status_path
from core.telemetry_streams import decisions_stream_path, iter_recent_events
from core.decision_telemetry_health import check_decision_telemetry
from core.feed.runtime_provenance import validate_feed_runtime_provenance

logger = logging.getLogger(__name__)

_LIFECYCLE_FEED_BLOCKER_CODES = {
    "NO_LIVE_OPTION_FEED",
    "STALE_OPTION_LTP",
    "PRICE_MISMATCH",
    "NO_TOKEN",
}


def _safe_mtime(path: Path) -> float | None:
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return None


def _read_json_dict(path: Path) -> Dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _feed_runtime_snapshot_paths() -> list[Path]:
    return [
        logs_dir() / "feed_runtime_latest.json",
        runtime_dir() / "feed_runtime_latest.json",
    ]


def _unwrap_feed_runtime_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    nested = payload.get("payload")
    if isinstance(nested, dict):
        return dict(nested)
    return dict(payload)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _load_fresh_feed_runtime_snapshot(now_epoch: float) -> Dict[str, Any]:
    max_age_sec = max(1.0, float(getattr(cfg, "READINESS_FEED_RUNTIME_MAX_AGE_SEC", 60.0) or 60.0))
    selected: Dict[str, Any] | None = None
    selected_ts_epoch = -1.0
    selected_mtime = -1.0
    selected_age_sec: float | None = None
    selected_path: Path | None = None

    for path in _feed_runtime_snapshot_paths():
        raw = _read_json_dict(path)
        mtime = _safe_mtime(path)
        if raw is None or mtime is None:
            continue
        payload = _unwrap_feed_runtime_payload(raw)
        ts_epoch = normalize_epoch_seconds(payload.get("ts_epoch"))
        age_by_ts = compute_age_sec(ts_epoch, now_epoch) if ts_epoch is not None else None
        age_by_mtime = compute_age_sec(mtime, now_epoch)
        # Clock-skew resilience: if payload ts is wildly old/new but file mtime is fresh,
        # fall back to mtime so we don't ignore an otherwise fresh snapshot.
        if age_by_ts is not None and age_by_mtime is not None and age_by_ts > max_age_sec and age_by_mtime <= max_age_sec:
            ts_epoch = None
            age_sec = age_by_mtime
        else:
            age_sec = age_by_ts if age_by_ts is not None else age_by_mtime
        if age_sec is None or age_sec > max_age_sec:
            continue
        ts_val = float(ts_epoch) if ts_epoch is not None else -1.0
        # Prefer the freshest declared ts_epoch; fall back to mtime when ts is missing.
        if (ts_val > selected_ts_epoch) or (ts_val <= 0.0 and selected_ts_epoch <= 0.0 and mtime > selected_mtime):
            selected = payload
            selected_ts_epoch = ts_val
            selected_mtime = mtime
            selected_age_sec = age_sec
            selected_path = path

    if selected is not None:
        current_generation = (get_feed_debug(now_epoch=now_epoch) or {}).get("recovery_generation_id")
        provenance = validate_feed_runtime_provenance(selected, current_generation=current_generation)
        if not provenance["valid"]:
            selected = dict(selected)
            selected["feed_ok"] = False
            selected["provenance_valid"] = False
            selected["provenance_reasons"] = list(provenance["reasons"])

    if not isinstance(selected, dict):
        return {}

    out = dict(selected)
    out["_source_path"] = str(selected_path) if selected_path is not None else None
    out["_source_mtime"] = float(selected_mtime) if selected_mtime >= 0.0 else None
    out["_source_age_sec"] = selected_age_sec
    return out


def _feed_runtime_block_reasons(snapshot: Dict[str, Any]) -> list[str]:
    if not isinstance(snapshot, dict):
        return []

    reasons: list[str] = []
    ws_connected = snapshot.get("ws_connected")
    if ws_connected is False:
        reasons.append("NO_LIVE_OPTION_FEED")

    runtime_state = str(snapshot.get("runtime_state") or "").strip().upper()
    if runtime_state in {"SUBSCRIBE_FAILED", "NO_RECONNECT", "DISCONNECTED", "FAILED", "ERROR"}:
        reasons.append("NO_LIVE_OPTION_FEED_SUBSCRIPTION" if runtime_state == "SUBSCRIBE_FAILED" else "NO_LIVE_OPTION_FEED")

    intended_tokens = _as_int(snapshot.get("intended_tokens_count"))
    subscribed_option_tokens = _as_int(snapshot.get("subscribed_option_tokens_count"))
    if intended_tokens > 0 and subscribed_option_tokens <= 0:
        reasons.append("NO_LIVE_OPTION_FEED_SUBSCRIPTION")

    block_reasons = snapshot.get("option_feed_block_reason_by_symbol")
    if isinstance(block_reasons, dict):
        for value in block_reasons.values():
            code = str(value or "").strip().upper()
            if not code or code in {"OK", "NONE"}:
                continue
            reasons.append(code)

    return list(dict.fromkeys(reasons))


def readiness_snapshot_is_stale(
    readiness_path: Path | None = None,
    *,
    feed_paths: list[Path] | None = None,
) -> bool:
    ready_path = readiness_path or (logs_dir() / "readiness_state.json")
    ready_mtime = _safe_mtime(ready_path) or 0.0
    compare_paths = list(feed_paths or _feed_runtime_snapshot_paths())
    latest_feed_mtime = max((_safe_mtime(path) or 0.0) for path in compare_paths)
    margin_sec = max(0.0, float(getattr(cfg, "READINESS_STATE_STALE_MARGIN_SEC", 1.0) or 1.0))
    return latest_feed_mtime > (ready_mtime + margin_sec)


def load_or_recompute_readiness_state(write_log: bool = True) -> Dict[str, object]:
    state_path = logs_dir() / "readiness_state.json"
    if readiness_snapshot_is_stale(state_path):
        return run_readiness_check(write_log=write_log)
    cached = _read_json_dict(state_path)
    if isinstance(cached, dict):
        return cached
    return run_readiness_check(write_log=write_log)


def _disk_free_gb(path: str = ".") -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def _check_kite_auth() -> Tuple[bool, str, str]:
    payload = get_kite_auth_health(force=False)
    ok = bool(payload.get("ok"))
    auth_state = str(payload.get("auth_state") or ("OK" if ok else "FAILED"))
    reason = str(payload.get("error") or payload.get("reason") or "unknown")
    return ok, reason, auth_state


def _check_trade_identity_schema() -> Tuple[bool, str]:
    try:
        init_db()
    except Exception as exc:
        return False, f"trade_schema_init_error:{exc}"
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", str(data_root() / "desks" / "DEFAULT" / "trades.db")))
    if not db_path.exists():
        return False, "trade_db_missing"
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cur.fetchone():
            con.close()
            return False, "trades_table_missing"
        cur.execute("PRAGMA table_info(trades)")
        cols = {row[1] for row in cur.fetchall()}
        con.close()
    except Exception as exc:
        return False, f"trade_schema_query_error:{exc}"
    required_cols = {
        "instrument_id",
        "underlying",
        "instrument_type",
        "expiry",
        "strike",
        "right",
        "qty_lots",
        "qty_units",
        "validity_sec",
        "timestamp_epoch",
    }
    missing = sorted(required_cols - cols)
    if missing:
        return False, f"trade_schema_missing:{','.join(missing)}"
    return True, "ok"


def check_trade_identity_schema() -> Tuple[bool, str]:
    """
    Public wrapper for schema audit callers.
    """
    return _check_trade_identity_schema()


def _load_recent_decision_rows(now_epoch: float) -> Dict[str, Dict[str, Any]]:
    desk = getattr(cfg, "DESK_ID", "DEFAULT")
    max_age = float(
        getattr(
            cfg,
            "READINESS_DECISION_MAX_AGE_SEC",
            getattr(cfg, "READINESS_DECISION_ENGINE_ACTIVE_SEC", 240.0),
        )
    )
    max_future_skew = float(getattr(cfg, "MAX_CLOCK_SKEW_SEC", 5.0))
    out: Dict[str, Dict[str, Any]] = {}
    decision_path = decisions_stream_path(desk_id=desk)
    if decision_path.exists():
        for payload in reversed(
            iter_recent_events(
                decision_path,
                now_epoch=now_epoch,
                max_age_sec=max_age,
                event_types={"decision_evaluated"},
                max_lines=5000,
            )
        ):
            symbol = str(payload.get("symbol") or "").upper()
            if not symbol or symbol in out:
                continue
            ts_epoch = normalize_epoch_seconds(payload.get("ts_epoch"))
            if ts_epoch is None:
                continue
            if ts_epoch > (now_epoch + max_future_skew):
                continue
            age_sec = compute_age_sec(ts_epoch, now_epoch)
            if age_sec is None or age_sec > max_age:
                continue
            payload["gate_allowed"] = bool(payload.get("allowed", payload.get("gate_allowed", False)))
            payload["decision_blockers"] = list(payload.get("blockers") or payload.get("decision_blockers") or [])
            out[symbol] = payload
        if out:
            logger.debug("decision rows loaded from decisions stream: %s", len(out))
            return out

    # Backward compatibility with legacy gate_status.jsonl payloads.
    path = gate_status_path(desk_id=desk)
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    for raw in reversed(lines[-500:]):
        row = raw.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
        except Exception:
            continue
        symbol = str(payload.get("symbol") or "").upper()
        if not symbol or symbol in out:
            continue
        ts_epoch = normalize_epoch_seconds(payload.get("ts_epoch"))
        if ts_epoch is None or ts_epoch > (now_epoch + max_future_skew):
            continue
        age_sec = compute_age_sec(ts_epoch, now_epoch)
        if age_sec is None or age_sec > max_age:
            continue
        has_decision_stage = str(payload.get("decision_stage") or "").strip() != ""
        has_decision_explain = payload.get("decision_explain") is not None
        has_decision_blockers = payload.get("decision_blockers") is not None
        is_gate_rejected_event = str(payload.get("event_type") or "").strip().lower() == "gate_rejected"
        if not (has_decision_stage or has_decision_explain or has_decision_blockers or is_gate_rejected_event):
            continue
        payload["gate_allowed"] = bool(payload.get("gate_allowed", False))
        out[symbol] = payload
    logger.debug("decision rows loaded: %s", len(out))
    return out


def _decision_gate_health(now_epoch: float, market_open: bool, execution_mode: str) -> Dict[str, Any]:
    rows = _load_recent_decision_rows(now_epoch)
    symbols = sorted(rows.keys())
    evaluations_last_window = len(rows)
    blocked_rows: List[Dict[str, Any]] = []
    allowed_rows: List[Dict[str, Any]] = []
    feed_stale_symbols: List[str] = []
    blockers_by_symbol: Dict[str, List[str]] = {}
    max_ltp_age = None
    max_depth_age = None
    latest_explain = None
    feed_stale_max_age_sec = max(
        1.0,
        float(
            getattr(
                cfg,
                "READINESS_DECISION_FEED_STALE_MAX_AGE_SEC",
                min(float(getattr(cfg, "READINESS_DECISION_MAX_AGE_SEC", 240.0) or 240.0), 45.0),
            )
            or 45.0
        ),
    )

    for sym, row in rows.items():
        row_blockers = [str(x) for x in (row.get("decision_blockers") or row.get("gate_reasons") or []) if str(x).strip()]
        blockers_by_symbol[sym] = row_blockers
        row_ts_epoch = normalize_epoch_seconds(row.get("ts_epoch"))
        row_age_sec = compute_age_sec(row_ts_epoch, now_epoch)
        if bool(row.get("gate_allowed")):
            allowed_rows.append(row)
        else:
            blocked_rows.append(row)
        fhs = row.get("feed_health_snapshot") or {}
        if isinstance(fhs, dict):
            try:
                ltp_age = float(fhs.get("ltp_age_sec")) if fhs.get("ltp_age_sec") is not None else None
            except Exception:
                ltp_age = None
            try:
                depth_age = float(fhs.get("depth_age_sec")) if fhs.get("depth_age_sec") is not None else None
            except Exception:
                depth_age = None
            if ltp_age is not None:
                max_ltp_age = ltp_age if max_ltp_age is None else max(max_ltp_age, ltp_age)
            if depth_age is not None:
                max_depth_age = depth_age if max_depth_age is None else max(max_depth_age, depth_age)
            is_fresh_row_for_feed = row_age_sec is not None and float(row_age_sec) <= float(feed_stale_max_age_sec)
            if market_open and (fhs.get("is_fresh") is False):
                if is_fresh_row_for_feed:
                    feed_stale_symbols.append(sym)
                    if bool(getattr(cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True)):
                        logger.warning(
                            "FEED_STALE_EVIDENCE symbol=%s source=readiness_decision_rows reason=feed_health_snapshot_not_fresh row_ts_epoch=%s row_age_sec=%s feed_is_fresh=%s ltp_age_sec=%s depth_age_sec=%s blockers=%s",
                            sym,
                            row_ts_epoch,
                            row_age_sec,
                            fhs.get("is_fresh"),
                            fhs.get("ltp_age_sec"),
                            fhs.get("depth_age_sec"),
                            row_blockers,
                        )
                elif bool(getattr(cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True)):
                    logger.info(
                        "FEED_STALE_EVIDENCE symbol=%s source=readiness_decision_rows reason=ignored_stale_decision_row row_ts_epoch=%s row_age_sec=%s max_feed_stale_age_sec=%s blockers=%s",
                        sym,
                        row_ts_epoch,
                        row_age_sec,
                        feed_stale_max_age_sec,
                        row_blockers,
                    )
        if market_open and any(str(reason).upper() == "FEED_STALE" for reason in row_blockers):
            if row_age_sec is not None and float(row_age_sec) <= float(feed_stale_max_age_sec):
                feed_stale_symbols.append(sym)
                if bool(getattr(cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True)):
                    logger.warning(
                        "FEED_STALE_EVIDENCE symbol=%s source=readiness_decision_rows reason=decision_blocker_feed_stale row_ts_epoch=%s row_age_sec=%s blockers=%s",
                        sym,
                        row_ts_epoch,
                        row_age_sec,
                        row_blockers,
                    )
            elif bool(getattr(cfg, "FEED_STALE_EVIDENCE_LOG_ENABLE", True)):
                logger.info(
                    "FEED_STALE_EVIDENCE symbol=%s source=readiness_decision_rows reason=ignored_stale_decision_row_blocker row_ts_epoch=%s row_age_sec=%s max_feed_stale_age_sec=%s blockers=%s",
                    sym,
                    row_ts_epoch,
                    row_age_sec,
                    feed_stale_max_age_sec,
                    row_blockers,
                )
        if latest_explain is None and row.get("decision_explain") is not None:
            latest_explain = row.get("decision_explain")

    blockers: List[str] = []
    reasons: List[str] = []
    decision_engine_active = evaluations_last_window > 0
    status = "ACTIVE" if decision_engine_active else "INSUFFICIENT_SAMPLE"
    status_reason = "OK" if decision_engine_active else "DECISION_ROWS_STALE_OR_MISSING"

    unique_feed_stale_symbols = sorted(set(feed_stale_symbols))
    if market_open and unique_feed_stale_symbols:
        for sym in unique_feed_stale_symbols:
            blockers.append(f"feed_health:feed_stale:{sym}")
        reasons.append("feed_stale:" + ",".join(unique_feed_stale_symbols))
    blockers = list(dict.fromkeys(blockers))

    execution_ready = len(allowed_rows) > 0
    decision_ok = (not market_open) or (not blockers)
    feed_ok = (not market_open) or (len(feed_stale_symbols) == 0)
    return {
        "ok": decision_ok,
        "feed_ok": feed_ok,
        "decision_engine_active": decision_engine_active,
        "execution_ready": execution_ready,
        "blockers": blockers,
        "reasons": reasons,
        "symbols": symbols,
        "allowed_symbols": sorted(str(row.get("symbol") or "").upper() for row in allowed_rows),
        "blocked_symbols": sorted(str(row.get("symbol") or "").upper() for row in blocked_rows),
        "blockers_by_symbol": blockers_by_symbol,
        "rows": rows,
        "evaluations_last_window": evaluations_last_window,
        "decisions_last_window": len(allowed_rows),
        "ltp_age_sec": max_ltp_age,
        "depth_age_sec": max_depth_age,
        "latest_explain": latest_explain,
        "status": status,
        "reason": status_reason,
    }


def run_readiness_check(write_log: bool = True) -> Dict[str, object]:
    """
    Backwards-compatible wrapper that now exposes state-machine keys.
    """
    res = run_readiness_state(write_log=write_log)
    payload = {
        "ts_epoch": res.checks.get("ts_epoch"),
        "ts_ist": res.checks.get("ts_ist"),
        "market_open": res.market_open,
        "holiday": res.holiday,
        "ready": res.can_trade,
        "reasons": res.blockers,
        "warnings": res.warnings,
        "checks": res.checks,
        "state": res.state.value,
        "can_trade": res.can_trade,
        "blockers": res.blockers,
    }
    return payload


def run_readiness_state(write_log: bool = True) -> ReadinessResult:
    now = now_ist()
    is_holiday = now.date() in IN_HOLIDAYS
    market_open = is_market_open_ist(now=now) and not is_holiday
    market_ctx = derive_market_context(
        {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
            "market_open": bool(market_open),
            "segment": getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO"),
        }
    )
    execution_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    offhours_mode = bool(market_ctx.mode == "OFFHOURS")
    require_live_quotes = bool(market_ctx.require_live_quotes)
    allow_stale_quotes = bool(market_ctx.allow_stale_quotes)
    freshness_policy = resolve_freshness_policy(
        mode=str(getattr(cfg, "EXECUTION_MODE", "SIM")),
        market_open=bool(market_open),
        allow_stale_quotes=bool(allow_stale_quotes),
        live_ltp_sec=float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
        live_depth_sec=float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0)),
        planning_ltp_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_LTP_AGE_SEC", 900.0)),
        planning_depth_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC", 900.0)),
        option_ok_live_sec=float(getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5)),
        option_ok_planning_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_LTP_AGE_SEC", 900.0)),
        expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
    )

    blockers = []
    warnings = []
    checks: Dict[str, object] = {}
    checks["ts_epoch"] = now.timestamp()
    checks["ts_ist"] = now.isoformat()
    checks["freshness_policy"] = {
        "profile": freshness_policy.name,
        "ltp_max_age_sec": float(freshness_policy.ltp_max_age_sec),
        "depth_max_age_sec": float(freshness_policy.depth_max_age_sec),
        "ltp_required": bool(freshness_policy.ltp_required),
        "depth_required": bool(freshness_policy.depth_required),
    }

    # Required config
    missing_cfg = []
    if not getattr(cfg, "DESK_ID", None):
        missing_cfg.append("missing_desk_id")
    if not getattr(cfg, "TRADE_DB_PATH", None):
        missing_cfg.append("missing_trade_db_path")
    if not getattr(cfg, "SYMBOLS", None):
        missing_cfg.append("missing_symbols")
    if missing_cfg:
        blockers.extend(missing_cfg)
    checks["config"] = {"ok": not missing_cfg, "missing": missing_cfg}

    # Risk halt
    halted = risk_halt.is_halted()
    if halted and getattr(cfg, "READINESS_REQUIRE_RISK_HALT_CLEAR", True):
        blockers.append("risk_halt_active")
    checks["risk_halt"] = {"ok": not halted, "halted": halted}

    # Audit chain
    audit_ok = True
    audit_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_AUDIT_CHAIN", True):
        audit_ok, audit_reason, _ = verify_audit_chain()
        if not audit_ok:
            blockers.append(f"audit_chain:{audit_reason}")
    checks["audit_chain"] = {"ok": audit_ok, "reason": audit_reason}

    # Kite auth
    kite_ok = True
    kite_reason = "ok"
    kite_state = "OK"
    auth_guard: Dict[str, Any] = {}
    if getattr(cfg, "READINESS_REQUIRE_KITE_AUTH", True):
        kite_ok, kite_reason, kite_state = _check_kite_auth()
        try:
            auth_guard = run_preopen_auth_warm_check(
                force=False,
                market_context={
                    "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                    "market_open": bool(market_open),
                },
            )
        except Exception:
            auth_guard = {}
        degrade_to_planning = bool(auth_guard.get("degrade_to_planning", False))
        if not kite_ok:
            if degrade_to_planning and bool(market_ctx.planning_only):
                warnings.append(f"auth_degraded_planning:{kite_reason}")
            else:
                blockers.append(kite_reason)
        elif kite_state == "UNKNOWN_NETWORK":
            warnings.append("kite_auth_unknown_network")
    checks["kite_auth"] = {
        "ok": kite_ok,
        "reason": kite_reason,
        "state": kite_state,
        "degraded_to_planning": bool(auth_guard.get("degrade_to_planning", False)),
    }
    checks["auth_guard"] = auth_guard

    # Trade schema readiness
    schema_ok = True
    schema_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_TRADE_SCHEMA", True):
        schema_ok, schema_reason = _check_trade_identity_schema()
        if not schema_ok:
            blockers.append(schema_reason)
    checks["trade_identity_schema"] = {"ok": schema_ok, "reason": schema_reason}

    # Decision DAG health (single source of truth for gating/readiness)
    decision_health = _decision_gate_health(
        now_epoch=float(checks["ts_epoch"]),
        market_open=market_open,
        execution_mode=execution_mode,
    )
    decision_stream_health = check_decision_telemetry(
        desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
        max_age_sec=float(
            getattr(
                cfg,
                "READINESS_DECISION_MAX_AGE_SEC",
                getattr(cfg, "READINESS_DECISION_ENGINE_ACTIVE_SEC", 240.0),
            )
        ),
    )
    # "Active" means we have recent decision telemetry (not just configured symbols).
    decision_engine_active = bool(decision_health.get("decision_engine_active", False))
    if not decision_engine_active:
        try:
            decision_engine_active = bool(
                int(decision_health.get("evaluations_last_window") or 0) > 0
                or int(decision_health.get("decisions_last_window") or 0) > 0
            )
        except Exception:
            decision_engine_active = False
    for reason in decision_health.get("blockers", []):
        blockers.append(reason)
    checks["decision_gate"] = {
        "ok": bool(decision_health.get("ok")),
        "decision_engine_active": decision_engine_active,
        "execution_ready": bool(decision_health.get("execution_ready", False)),
        "symbols": decision_health.get("symbols") or [],
        "allowed_symbols": decision_health.get("allowed_symbols") or [],
        "blocked_symbols": decision_health.get("blocked_symbols") or [],
        "blockers_by_symbol": decision_health.get("blockers_by_symbol") or {},
        "evaluations_last_window": int(decision_health.get("evaluations_last_window") or 0),
        "decisions_last_window": int(decision_health.get("decisions_last_window") or 0),
        "rows": decision_health.get("rows") or {},
        "latest_explain": decision_health.get("latest_explain"),
        "status": str(decision_health.get("status") or "UNKNOWN"),
        "reason": str(decision_health.get("reason") or ""),
        "stream_health": decision_stream_health,
    }
    feed_ok = bool(decision_health.get("feed_ok", True))
    feed_reasons = list(decision_health.get("reasons") or [])
    try:
        feed_debug = get_feed_debug(now_epoch=float(checks["ts_epoch"]))
    except Exception:
        feed_debug = {}
    active_blockers_by_symbol = {}
    if isinstance(feed_debug, dict):
        active_blockers_by_symbol = dict(feed_debug.get("option_active_blockers_by_symbol") or {})
    active_feed_blockers: list[str] = []
    for symbol in sorted(active_blockers_by_symbol.keys()):
        for code in list(active_blockers_by_symbol.get(symbol) or []):
            text = str(code or "").strip().upper()
            if not text or text not in _LIFECYCLE_FEED_BLOCKER_CODES:
                continue
            if text not in active_feed_blockers:
                active_feed_blockers.append(text)
    if market_open and active_feed_blockers and not decision_engine_active:
        feed_ok = False
        feed_reasons = list(dict.fromkeys(active_feed_blockers + feed_reasons))

    feed_runtime_snapshot = _load_fresh_feed_runtime_snapshot(now_epoch=float(checks["ts_epoch"]))
    feed_runtime_reasons = _feed_runtime_block_reasons(feed_runtime_snapshot)
    # Feed runtime snapshots are a secondary/bootstrapping signal. Once the decision
    # engine is active, the decision DAG is the source of truth for feed gating.
    if market_open and feed_runtime_reasons and (not decision_engine_active):
        feed_ok = False
        feed_reasons = list(dict.fromkeys(feed_runtime_reasons + feed_reasons))

    checks["feed_runtime_snapshot"] = {
        "present": bool(feed_runtime_snapshot),
        "path": feed_runtime_snapshot.get("_source_path") if isinstance(feed_runtime_snapshot, dict) else None,
        "mtime_epoch": feed_runtime_snapshot.get("_source_mtime") if isinstance(feed_runtime_snapshot, dict) else None,
        "age_sec": feed_runtime_snapshot.get("_source_age_sec") if isinstance(feed_runtime_snapshot, dict) else None,
        "runtime_state": (
            str(feed_runtime_snapshot.get("runtime_state") or "").strip().upper()
            if isinstance(feed_runtime_snapshot, dict)
            else None
        ),
        "ws_connected": (
            feed_runtime_snapshot.get("ws_connected") if isinstance(feed_runtime_snapshot, dict) else None
        ),
        "subscribed_option_tokens_count": (
            _as_int(feed_runtime_snapshot.get("subscribed_option_tokens_count"))
            if isinstance(feed_runtime_snapshot, dict)
            else 0
        ),
        "option_feed_block_reason_by_symbol": (
            dict(feed_runtime_snapshot.get("option_feed_block_reason_by_symbol") or {})
            if isinstance(feed_runtime_snapshot, dict)
            else {}
        ),
        "derived_reasons": feed_runtime_reasons,
    }
    if require_live_quotes and (not feed_ok):
        blockers.append(f"feed_health:{','.join(feed_reasons) or 'feed_stale'}")
    checks["feed_health"] = {
        "ok": bool(feed_ok or allow_stale_quotes),
        "reasons": feed_reasons,
        "active_blockers": active_feed_blockers,
        "active_blockers_by_symbol": active_blockers_by_symbol,
        "ltp_age_sec": decision_health.get("ltp_age_sec"),
        "depth_age_sec": decision_health.get("depth_age_sec"),
        "state": (
            "OFFHOURS"
            if offhours_mode
            else ("PLANNING" if allow_stale_quotes else ("OK" if feed_ok else "STALE"))
        ),
        "market_open": market_open,
        "offhours_mode": bool(offhours_mode),
        "allow_stale_quotes": bool(allow_stale_quotes),
        "require_live_quotes": bool(require_live_quotes),
        "ltp": {
            "age_sec": decision_health.get("ltp_age_sec"),
            "max_age_sec": float(
                getattr(
                    cfg,
                    "OFFHOURS_SLA_MAX_LTP_AGE_SEC" if offhours_mode else "SLA_MAX_LTP_AGE_SEC",
                    900.0 if offhours_mode else 2.5,
                )
            ),
        },
        "depth": {
            "age_sec": decision_health.get("depth_age_sec"),
            "max_age_sec": float(
                getattr(
                    cfg,
                    "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC" if offhours_mode else "SLA_MAX_DEPTH_AGE_SEC",
                    900.0 if offhours_mode else 6.0,
                )
            ),
        },
        "source": "decision_dag",
        "runtime_snapshot_path": checks["feed_runtime_snapshot"].get("path"),
        "runtime_snapshot_age_sec": checks["feed_runtime_snapshot"].get("age_sec"),
        "runtime_snapshot_state": checks["feed_runtime_snapshot"].get("runtime_state"),
        "runtime_snapshot_ws_connected": checks["feed_runtime_snapshot"].get("ws_connected"),
    }

    breaker_eval = feed_breaker_maybe_auto_clear(feed_debug if isinstance(feed_debug, dict) else {})
    breaker_tripped = bool((breaker_eval or {}).get("tripped", False))
    checks["feed_breaker"] = dict(breaker_eval or {"tripped": breaker_tripped})
    if breaker_tripped:
        blockers.append("feed_circuit_breaker_tripped")

    # Disk free
    min_gb = float(getattr(cfg, "READINESS_MIN_FREE_GB", 2.0))
    free_gb = _disk_free_gb(".")
    disk_ok = free_gb >= min_gb
    if not disk_ok:
        blockers.append("disk_low")
    checks["disk_free_gb"] = {"ok": disk_ok, "free_gb": round(free_gb, 2), "min_gb": min_gb}

    if not checks.get("ts_epoch"):
        state = ReadinessState.BOOTING
        can_trade = False
    elif blockers:
        print("WHY_BLOCKED:", blockers)
        state = ReadinessState.BLOCKED
        can_trade = False
    else:
        if not market_open:
            state = ReadinessState.MARKET_CLOSED if not warnings else ReadinessState.DEGRADED
            can_trade = False
        else:
            state = ReadinessState.READY if not warnings else ReadinessState.DEGRADED
            can_trade = state == ReadinessState.READY

    res = ReadinessResult(
        state=state,
        can_trade=can_trade,
        market_open=market_open,
        holiday=is_holiday,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
    )

    if write_log:
        payload = {
            "ts_epoch": checks["ts_epoch"],
            "ts_ist": checks["ts_ist"],
            **res.to_payload(),
        }
        try:
            out = logs_dir() / f"readiness_{now.date().isoformat()}.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps(payload, indent=2))
            _log_state_transition(payload)
        except Exception as exc:
            warnings.append("readiness_log_write_failed")
            checks["readiness_log_error"] = str(exc)
    return res


def _log_state_transition(payload: Dict[str, object]) -> None:
    try:
        state_path = logs_dir() / "readiness_state.json"
        log_path = logs_dir() / "readiness_state.jsonl"
        prev = {}
        if state_path.exists():
            try:
                prev = json.loads(state_path.read_text())
            except Exception:
                prev = {}
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        feed_runtime = checks.get("feed_runtime_snapshot") if isinstance(checks.get("feed_runtime_snapshot"), dict) else {}
        curr_core = {
            "state": payload.get("state"),
            "blockers": payload.get("blockers"),
            "warnings": payload.get("warnings"),
            "market_open": payload.get("market_open"),
        }
        curr = {
            **curr_core,
            "computed_at": payload.get("ts_epoch"),
            "computed_at_ist": payload.get("ts_ist"),
            "source_feed_mtime": feed_runtime.get("mtime_epoch"),
            "source_feed_runtime_state": feed_runtime.get("runtime_state"),
            "source_ws_connected": feed_runtime.get("ws_connected"),
            "source_feed_path": feed_runtime.get("path"),
            "source_feed_snapshot_age_sec": feed_runtime.get("age_sec"),
            "source_feed_block_reasons": list(feed_runtime.get("derived_reasons") or []),
        }
        state_path.write_text(json.dumps(curr, indent=2))

        prev_core = {
            "state": prev.get("state"),
            "blockers": prev.get("blockers"),
            "warnings": prev.get("warnings"),
            "market_open": prev.get("market_open"),
        }
        if prev_core != curr_core:
            with log_path.open("a") as f:
                f.write(json.dumps({
                    "ts_epoch": payload.get("ts_epoch"),
                    "ts_ist": payload.get("ts_ist"),
                    **curr_core,
                }) + "\n")
    except Exception:
        pass
