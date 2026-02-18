from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import config as cfg
from core import risk_halt
from core.feed_circuit_breaker import is_tripped as feed_breaker_tripped
from core.freshness_sla import get_freshness_status
from core.paths import logs_dir
from core.time_utils import now_utc_epoch


@dataclass(frozen=True)
class TradingAllowedSnapshot:
    allowed: bool
    reasons: List[str]
    ts_epoch: float
    market_open: bool
    auth_ok: bool
    auth_age_sec: Optional[float]
    freshness_state: str
    ltp_age_sec: Optional[float]
    depth_age_sec: Optional[float]
    risk_halted: bool
    feed_breaker_tripped: bool
    regime_confidence: Optional[float] = None
    day_confidence: Optional[float] = None
    orb_bias: Optional[str] = None
    quote_health: str = "UNKNOWN"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _unique_reasons(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _read_last_jsonl(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        lines = path.read_text().splitlines()
    except Exception:
        return {}
    for line in reversed(lines):
        row = line.strip()
        if not row:
            continue
        try:
            parsed = json.loads(row)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return {}


def _load_recent_auth_health(now_epoch: float) -> Dict[str, Any]:
    payload = _read_last_jsonl(logs_dir() / "auth_health.jsonl")
    if not payload:
        return {
            "ok": False,
            "age_sec": None,
            "reason": "auth_health_missing",
            "auth_state": "MISSING",
        }
    ts_epoch = payload.get("ts_epoch")
    try:
        ts_epoch_f = float(ts_epoch)
    except Exception:
        ts_epoch_f = None
    age_sec = None if ts_epoch_f is None else max(0.0, now_epoch - ts_epoch_f)
    max_age = float(
        getattr(
            cfg,
            "GOV_AUTH_MAX_AGE_SEC",
            max(float(getattr(cfg, "AUTH_HEALTH_TTL_SEC", 60.0)) * 2.0, 180.0),
        )
    )
    auth_state = str(payload.get("auth_state") or "FAILED").upper()
    ok = bool(payload.get("ok")) and auth_state == "OK" and age_sec is not None and age_sec <= max_age
    reason = ""
    if not ok:
        if age_sec is None:
            reason = "auth_health_missing_ts"
        elif age_sec > max_age:
            reason = f"auth_health_stale:{age_sec:.1f}s>{max_age:.1f}s"
        else:
            reason = str(payload.get("error") or payload.get("reason") or f"auth_state:{auth_state}")
    return {
        "ok": ok,
        "age_sec": age_sec,
        "reason": reason,
        "auth_state": auth_state,
    }


def _regime_confidence(market_data: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(market_data, dict):
        return None
    direct = market_data.get("regime_confidence")
    if direct is not None:
        try:
            return float(direct)
        except Exception:
            return None
    probs = market_data.get("regime_probs") or {}
    if not isinstance(probs, dict) or not probs:
        return None
    try:
        return max(float(v) for v in probs.values())
    except Exception:
        return None


def _quote_health(market_data: Optional[Dict[str, Any]]) -> str:
    if not isinstance(market_data, dict):
        return "UNKNOWN"
    quote_ok = bool(market_data.get("quote_ok"))
    chain_source = str(market_data.get("chain_source") or "").lower()
    health = market_data.get("option_chain_health") or {}
    missing_quote_pct = health.get("missing_quote_pct") if isinstance(health, dict) else None
    max_missing_quote_pct = float(getattr(cfg, "CHAIN_MAX_MISSING_QUOTE_PCT", 0.2))
    missing_ok = True if missing_quote_pct is None else float(missing_quote_pct) <= max_missing_quote_pct
    if quote_ok and chain_source == "live" and missing_ok:
        return "OK"
    if quote_ok or chain_source in {"live", "synthetic"}:
        return "DEGRADED"
    return "ERROR"


def trading_allowed_snapshot(market_data: Optional[Dict[str, Any]] = None) -> TradingAllowedSnapshot:
    """
    Single fail-closed permission gate used before trade emission.
    Deterministic by design: no direct network calls.
    """
    now_epoch = now_utc_epoch()
    reasons: List[str] = []
    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()

    freshness = get_freshness_status(force=False)
    market_open = bool(freshness.get("market_open"))
    freshness_state = str(freshness.get("state") or "UNKNOWN")
    ltp_age_sec = (freshness.get("ltp") or {}).get("age_sec")
    depth_age_sec = (freshness.get("depth") or {}).get("age_sec")

    risk_halted = bool(risk_halt.is_halted())
    if risk_halted:
        reasons.append("RISK_HALT_ACTIVE")

    feed_breaker = bool(feed_breaker_tripped())
    if feed_breaker:
        reasons.append("FEED_BREAKER_TRIPPED")

    if not market_open:
        reasons.append("MARKET_CLOSED")

    if market_open and not bool(freshness.get("ok")):
        reasons.append("FEED_STALE")

    auth_check = _load_recent_auth_health(now_epoch)
    auth_required = bool(getattr(cfg, "GOV_GATE_REQUIRE_AUTH", True))
    auth_enforced = auth_required and (mode == "LIVE" or bool(getattr(cfg, "GOV_GATE_ENFORCE_PAPER", False)))
    if market_open and auth_enforced and not auth_check.get("ok"):
        reasons.append("AUTH_NOT_VERIFIED_RECENTLY")

    regime_conf = _regime_confidence(market_data)
    day_conf = None
    orb_bias = None
    if isinstance(market_data, dict):
        day_raw = market_data.get("day_confidence")
        try:
            day_conf = float(day_raw) if day_raw is not None else None
        except Exception:
            day_conf = None
        orb_bias = str(market_data.get("orb_bias") or "").upper() or None

    if market_open and bool(getattr(cfg, "GOV_GATE_REQUIRE_ORB_RESOLVED", False)):
        if orb_bias in {None, "", "PENDING"}:
            reasons.append("ORB_PENDING")

    if market_open and bool(getattr(cfg, "GOV_GATE_REQUIRE_DAYTYPE_CONF", False)):
        min_day_conf = float(getattr(cfg, "GOV_GATE_MIN_DAY_CONFIDENCE", getattr(cfg, "DAYTYPE_CONF_SWITCH_MIN", 0.6)))
        if day_conf is None or day_conf < min_day_conf:
            reasons.append("DAYTYPE_CONFIDENCE_LOW")

    if market_open and bool(getattr(cfg, "GOV_GATE_REQUIRE_REGIME_CONF", False)):
        min_regime_conf = float(getattr(cfg, "GOV_GATE_MIN_REGIME_CONFIDENCE", getattr(cfg, "REGIME_PROB_MIN", 0.45)))
        if regime_conf is None or regime_conf < min_regime_conf:
            reasons.append("REGIME_CONFIDENCE_LOW")

    quote_health = _quote_health(market_data)
    require_live_quotes = bool(getattr(cfg, "REQUIRE_LIVE_QUOTES", True))
    quote_enforced = require_live_quotes and (mode == "LIVE" or bool(getattr(cfg, "GOV_GATE_ENFORCE_PAPER", False)))
    if market_open and quote_enforced and quote_health == "ERROR":
        reasons.append("LIVE_QUOTES_UNHEALTHY")

    reasons = _unique_reasons(reasons)
    allowed = len(reasons) == 0
    details = {
        "mode": mode,
        "auth_state": auth_check.get("auth_state"),
        "auth_reason": auth_check.get("reason"),
        "freshness_reasons": list(freshness.get("reasons") or []),
        "symbol": (market_data or {}).get("symbol") if isinstance(market_data, dict) else None,
        "chain_source": (market_data or {}).get("chain_source") if isinstance(market_data, dict) else None,
    }

    return TradingAllowedSnapshot(
        allowed=allowed,
        reasons=reasons,
        ts_epoch=now_epoch,
        market_open=market_open,
        auth_ok=bool(auth_check.get("ok")),
        auth_age_sec=auth_check.get("age_sec"),
        freshness_state=freshness_state,
        ltp_age_sec=ltp_age_sec,
        depth_age_sec=depth_age_sec,
        risk_halted=risk_halted,
        feed_breaker_tripped=feed_breaker,
        regime_confidence=regime_conf,
        day_confidence=day_conf,
        orb_bias=orb_bias,
        quote_health=quote_health,
        details=details,
    )


def write_trading_allowed_snapshot(snapshot: TradingAllowedSnapshot) -> None:
    payload = snapshot.to_dict()
    base = logs_dir()
    base.mkdir(parents=True, exist_ok=True)
    latest_path = base / "trading_allowed_snapshot.json"
    history_path = base / "trading_allowed_snapshot.jsonl"
    latest_path.write_text(json.dumps(payload, indent=2))
    with history_path.open("a") as f:
        f.write(json.dumps(payload) + "\n")
