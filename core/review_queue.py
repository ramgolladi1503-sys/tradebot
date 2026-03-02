import json
import time
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from core.orders.order_intent import OrderIntent
from core.learning_paths import suggestion_log_paths
from core.paths import logs_dir, data_root
from core.upstox_resolver import resolve_upstox_key
from core.market_calendar import choose_nearest_available_expiry
from core.trade_schema import build_instrument_id
from core.trade_permission import build_permission_payload
from core.trade_identity import compute_trade_key, derive_strategy_id
from core.option_token_resolver import resolve_option_token
from core.option_entry import validate_live_entry
from core.tick_store import get_last_tick
from core.kite_depth_ws import ensure_subscribed_tokens

try:
    from config import config as cfg
except Exception:
    cfg = None

logger = logging.getLogger(__name__)


def _runtime_path(cfg_key: str, filename: str) -> Path:
    try:
        raw = str(getattr(cfg, cfg_key, "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw)
    return logs_dir() / filename


QUEUE_PATH = _runtime_path("REVIEW_QUEUE_PATH", "review_queue.json")
QUICK_QUEUE_PATH = _runtime_path("QUICK_REVIEW_QUEUE_PATH", "quick_review_queue.json")
ZERO_HERO_QUEUE_PATH = _runtime_path("ZERO_HERO_QUEUE_PATH", "zero_hero_queue.json")
SCALP_QUEUE_PATH = _runtime_path("SCALP_QUEUE_PATH", "scalp_queue.json")
TARGET_POINTS_QUEUE_PATH = _runtime_path("TARGET_POINTS_QUEUE_PATH", "target_points_queue.json")
APPROVED_PATH = _runtime_path("APPROVED_TRADES_PATH", "approved_trades.json")

_META_CACHE = {"ts": 0.0, "data": {}}
_CHAIN_CACHE = {"ts": 0.0, "data": {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}}}


def _coerce_expiry(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NONE", "NA", "N/A", "NAN"}:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def _coerce_option_type(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ("CE", "CALL"):
        return "CE"
    if text in ("PE", "PUT"):
        return "PE"
    return None


def _coerce_strike(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _option_chain_meta_map(ttl_sec: int = 300) -> dict:
    now = time.time()
    cache = _CHAIN_CACHE.get("data") or {}
    ts = float(_CHAIN_CACHE.get("ts") or 0.0)
    if cache and (now - ts) < ttl_sec:
        return cache
    path = data_root() / "option_chain_latest.json"
    if not path.exists():
        return cache if isinstance(cache, dict) else {}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return cache if isinstance(cache, dict) else {}
    by_token = {}
    by_contract = {}
    by_symbol_strike_type: dict[tuple, list] = {}
    if isinstance(raw, dict):
        for symbol, rows in raw.items():
            if not isinstance(rows, (list, tuple)):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                token = row.get("instrument_token")
                expiry = _coerce_expiry(row.get("expiry") or row.get("expiry_date"))
                strike = _coerce_strike(row.get("strike"))
                opt_type = _coerce_option_type(row.get("type") or row.get("option_type") or row.get("right"))
                tradingsymbol = row.get("tradingsymbol")
                meta = {
                    "symbol": symbol,
                    "expiry": expiry,
                    "strike": strike,
                    "type": opt_type,
                    "tradingsymbol": tradingsymbol,
                    "instrument_token": token,
                }
                if token:
                    by_token[token] = meta
                if symbol and expiry and strike is not None and opt_type:
                    by_contract[(symbol, expiry, float(strike), opt_type)] = meta
                if symbol and strike is not None and opt_type:
                    key = (symbol, float(strike), opt_type)
                    by_symbol_strike_type.setdefault(key, []).append(meta)
    _CHAIN_CACHE["ts"] = now
    _CHAIN_CACHE["data"] = {
        "by_token": by_token,
        "by_contract": by_contract,
        "by_symbol_strike_type": by_symbol_strike_type,
    }
    return _CHAIN_CACHE["data"]


def _instrument_meta_map(ttl_sec: int = 3600) -> dict:
    now = time.time()
    cache = _META_CACHE.get("data") or {}
    ts = float(_META_CACHE.get("ts") or 0.0)
    if cache and (now - ts) < ttl_sec:
        return cache
    try:
        from core.kite_client import kite_client
        meta = {}
        for exchange in ("NFO", "BFO"):
            for inst in kite_client.instruments_cached(exchange, ttl_sec=ttl_sec) or []:
                tok = inst.get("instrument_token")
                if not tok:
                    continue
                meta[tok] = {
                    "tradingsymbol": inst.get("tradingsymbol"),
                    "symbol": inst.get("name"),
                    "strike": inst.get("strike"),
                    "type": inst.get("instrument_type"),
                    "expiry": str(inst.get("expiry")) if inst.get("expiry") else None,
                    "segment": inst.get("segment"),
                }
        _META_CACHE["ts"] = now
        _META_CACHE["data"] = meta
        return meta
    except Exception:
        return cache if isinstance(cache, dict) else {}


def _parse_timestamp(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _dedupe_queue_entries(entries: list[dict], new_entry: dict, window_min: int) -> list[dict]:
    symbol = new_entry.get("symbol")
    strike = new_entry.get("strike")
    expiry = new_entry.get("expiry_date") or new_entry.get("expiry")
    if not symbol or strike in (None, ""):
        return entries + [new_entry]
    new_ts = _parse_timestamp(new_entry.get("timestamp")) or datetime.now()
    window_sec = max(int(window_min), 1) * 60

    def _key(entry):
        return (
            entry.get("symbol"),
            entry.get("expiry_date") or entry.get("expiry"),
            entry.get("strike"),
        )

    def _score(entry):
        score = entry.get("trade_score")
        conf = entry.get("confidence")
        try:
            score_val = float(score) if score is not None else None
        except Exception:
            score_val = None
        try:
            conf_val = float(conf) if conf is not None else None
        except Exception:
            conf_val = None
        ts_val = _parse_timestamp(entry.get("timestamp")) or datetime.min
        return (
            score_val if score_val is not None else -1e9,
            conf_val if conf_val is not None else -1e9,
            ts_val.timestamp(),
        )

    dupes = []
    survivors = []
    for entry in entries:
        if _key(entry) == (symbol, expiry, strike):
            ts = _parse_timestamp(entry.get("timestamp")) or new_ts
            if abs((new_ts - ts).total_seconds()) <= window_sec:
                dupes.append(entry)
                continue
        survivors.append(entry)
    if not dupes:
        return survivors + [new_entry]
    candidates = dupes + [new_entry]
    best = sorted(candidates, key=_score, reverse=True)[0]
    survivors.append(best)
    return survivors


def _append_jsonl(paths, payload):
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            continue


def _cfg_bool(name, default=False):
    try:
        from config import config as cfg
        return bool(getattr(cfg, name, default))
    except Exception:
        return bool(default)


def _cfg_int(name, default=0):
    try:
        from config import config as cfg
        return int(getattr(cfg, name, default))
    except Exception:
        return int(default)

def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _perm_rank(value: str | None) -> int:
    mapping = {
        "BLOCK": 0,
        "ADVISORY_ONLY": 1,
        "QUEUE_ONLY": 2,
        "EXECUTE": 3,
    }
    if value is None:
        return -1
    return mapping.get(str(value).strip().upper(), -1)


def _material_change(old_entry: dict, new_entry: dict, tol: float) -> bool:
    for key in ("entry", "target", "stop"):
        old_val = _safe_float(old_entry.get(key))
        new_val = _safe_float(new_entry.get(key))
        if old_val is None and new_val is None:
            continue
        if old_val is None or new_val is None:
            return True
        if abs(old_val - new_val) > float(tol):
            return True
    return False


def _find_existing_by_key(data: list[dict], trade_key: str) -> tuple[int | None, dict | None]:
    if not trade_key:
        return None, None
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            continue
        key = row.get("trade_key")
        if not key:
            key = compute_trade_key(
                row.get("symbol"),
                row.get("expiry_date") or row.get("expiry"),
                row.get("strike"),
                row.get("option_type") or row.get("type"),
                row.get("side"),
                row.get("strategy_id") or row.get("strategy") or row.get("generator"),
            )
            row["trade_key"] = key
        if key == trade_key:
            return idx, row
    return None, None


def _merge_trade_entry(data: list[dict], entry: dict) -> list[dict]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    trade_key = entry.get("trade_key")
    if not trade_key:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    idx, existing = _find_existing_by_key(data, trade_key)
    if existing is None:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    existing_status = str(existing.get("trade_status") or "").upper()
    if existing_status in {"INVALIDATED", "EXPIRED"}:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    tol = float(getattr(cfg, "TRADE_DEDUP_PRICE_TOL", 0.05)) if cfg else 0.05
    old_perm = existing.get("permission")
    new_perm = entry.get("permission")
    perm_escalated = _perm_rank(new_perm) > _perm_rank(old_perm)
    changed = _material_change(existing, entry, tol)
    if perm_escalated:
        trade_status = "UPDATED_PERMISSION"
    elif changed:
        trade_status = "UPDATED"
    else:
        trade_status = "REVALIDATED"

    existing_lifecycle = str(existing.get("status") or "").upper()
    incoming_lifecycle = str(entry.get("status") or "").upper()
    if existing_lifecycle in {"ACTIVE", "RESOLVED"} and incoming_lifecycle in {"PLANNING", "NEW", ""}:
        entry["status"] = existing_lifecycle

    update_count = int(existing.get("update_count") or 0) + 1
    first_seen = existing.get("first_seen") or entry.get("first_seen") or now_iso

    existing.update(entry)
    existing["first_seen"] = first_seen
    existing["last_seen"] = now_iso
    existing["update_count"] = update_count
    existing["trade_status"] = trade_status
    data[idx] = existing
    return data


def _derive_target(entry_val, stop_val, side, rr_default: float):
    try:
        entry_f = float(entry_val)
        stop_f = float(stop_val)
        rr_f = float(rr_default)
    except Exception:
        return None
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return None
    side_val = str(side or "").upper()
    if side_val == "SELL":
        target = entry_f - (risk * rr_f)
    else:
        target = entry_f + (risk * rr_f)
    if target <= 0:
        return None
    return round(float(target), 2)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)


def _looks_like_trade(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("symbol") or payload.get("trade_id"):
        return True
    if payload.get("strike") is not None:
        return True
    if payload.get("type") or payload.get("option_type"):
        return True
    return False


def _normalize_queue_row(row: dict) -> dict:
    out = dict(row or {})
    out.setdefault("symbol", out.get("underlying"))
    if out.get("expiry_date") in (None, "", "None"):
        out["expiry_date"] = _coerce_expiry(out.get("expiry")) or out.get("expiry")
    if out.get("expiry") in (None, "", "None"):
        out["expiry"] = out.get("expiry_date")
    opt_type = _coerce_option_type(out.get("option_type") or out.get("type") or out.get("right"))
    if opt_type:
        out["option_type"] = opt_type
        out["type"] = opt_type
    strike = out.get("strike")
    strike_val = _coerce_strike(strike)
    if strike_val is not None:
        out["strike"] = strike_val
    out.setdefault("status", "PLANNING")
    out.setdefault("entry", out.get("entry_price"))
    for key in ("symbol", "expiry_date", "strike", "type", "status"):
        out.setdefault(key, None)
    ts_ms = _coerce_timestamp_epoch_ms(out)
    out["timestamp_epoch_ms"] = int(ts_ms)
    out["timestamp_utc_iso"] = _epoch_ms_to_utc_iso(ts_ms)
    # Backward-compatible timestamp field
    if out.get("timestamp") in (None, "", "None"):
        out["timestamp"] = out["timestamp_utc_iso"]
    else:
        out["timestamp"] = str(out.get("timestamp"))
    return out


def _epoch_ms_to_utc_iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).isoformat()


def _coerce_epoch_ms(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        val = float(value)
        if val <= 0:
            return None
        # If already in ms, keep as-is; otherwise treat as seconds.
        if val >= 10_000_000_000:
            return int(val)
        return int(val * 1000.0)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000.0)


def _coerce_timestamp_epoch_ms(row: dict) -> int:
    for key in ("timestamp_epoch_ms", "timestamp_utc_iso", "timestamp"):
        ts_ms = _coerce_epoch_ms(row.get(key))
        if ts_ms is not None:
            return int(ts_ms)
    return int(time.time() * 1000.0)


def load_queue_rows(path: Path, rewrite_healed: bool = True) -> list[dict]:
    if not path.exists():
        return []
    raw = _read_json(path, [])
    if not isinstance(raw, list):
        logger.warning("queue_load_invalid_shape path=%s type=%s", path, type(raw).__name__)
        return []
    rows: list[dict] = []
    modified = False
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("queue_load_skip_non_dict path=%s item_type=%s", path, type(item).__name__)
            modified = True
            continue
        try:
            normalized = _normalize_queue_row(item)
        except Exception:
            logger.warning("queue_load_row_normalize_failed path=%s", path)
            modified = True
            continue
        if normalized != item:
            modified = True
        rows.append(normalized)
    if rewrite_healed and modified:
        try:
            write_queue_rows(path, rows)
        except Exception:
            logger.warning("queue_heal_write_failed path=%s", path)
    return rows


def write_queue_rows(path: Path, rows: list[dict]) -> None:
    safe_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        safe_rows.append(_normalize_queue_row(row))
    _write_json(path, safe_rows)


def _load_approvals():
    raw = _read_json(APPROVED_PATH, {"version": 2, "approvals": {}})
    if isinstance(raw, dict) and isinstance(raw.get("approvals"), dict):
        return raw
    # Backward-compat: old format was list[trade_id]. Keep detectable but fail-closed by default.
    if isinstance(raw, list):
        legacy = {}
        for trade_id in raw:
            legacy[str(trade_id)] = {"legacy": True, "status": "APPROVED"}
        return {"version": 2, "approvals": legacy}
    return {"version": 2, "approvals": {}}


def canonical_order_payload(trade):
    try:
        intent = OrderIntent.from_trade(trade, mode="PAPER")
        return intent.to_canonical_dict()
    except Exception:
        return {}


def order_payload_hash(trade):
    payload = canonical_order_payload(trade)
    if not payload:
        return ""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_status(trade_id, payload_hash=None, now_epoch=None):
    trade_id = str(trade_id or "")
    if not trade_id:
        return False, "approval_missing_trade_id"
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    strict = True
    if not _cfg_bool("APPROVAL_STRICT_PAYLOAD_HASH", True):
        return False, "approval_strict_mode_required"
    store = _load_approvals()
    record = (store.get("approvals") or {}).get(trade_id)
    if not record:
        return False, "approval_missing"
    if not isinstance(record, dict):
        return False, "approval_record_invalid"
    if record.get("status") and str(record.get("status")).upper() != "APPROVED":
        return False, "approval_not_approved"
    if record.get("legacy") is True and strict:
        return False, "approval_legacy_record"
    expires_epoch = record.get("expires_epoch")
    try:
        if expires_epoch is not None and now_epoch > float(expires_epoch):
            return False, "approval_expired"
    except Exception:
        return False, "approval_expiry_invalid"
    approved_hash = record.get("payload_hash")
    if strict and not approved_hash:
        return False, "approval_missing_payload_hash"
    if payload_hash and approved_hash and payload_hash != approved_hash:
        return False, "approval_payload_mismatch"
    if payload_hash and strict and not approved_hash:
        return False, "approval_missing_payload_hash"
    return True, "approved"

def add_to_queue(trade, queue_path=None, extra=None):
    try:
        from config import config as cfg
        instr = getattr(trade, "instrument", None)
        if instr is None and isinstance(trade, dict):
            instr = trade.get("instrument")
        if instr == "EQ" and not getattr(cfg, "ENABLE_EQUITIES", True):
            return
    except Exception:
        pass
    path = queue_path or QUEUE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_queue_rows(path)
    runtime_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()
    def get_attr(obj, name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
    strike_val = get_attr(trade, "strike")
    trade_id = get_attr(trade, "trade_id")
    if strike_val in (None, 0) and trade_id and "ATM" in str(trade_id):
        strike_val = "ATM"
    strategy_id = get_attr(trade, "strategy_id") or get_attr(trade, "strategy") or get_attr(trade, "generator")
    entry = {
        "trade_id": trade_id,
        "symbol": get_attr(trade, "symbol"),
        "underlying": get_attr(trade, "underlying") or get_attr(trade, "symbol"),
        "instrument_id": get_attr(trade, "instrument_id"),
        "tradingsymbol": get_attr(trade, "tradingsymbol"),
        "strike": strike_val,
        "instrument": get_attr(trade, "instrument"),
        "instrument_token": get_attr(trade, "instrument_token"),
        "expiry": get_attr(trade, "expiry"),
        "expiry_date": get_attr(trade, "expiry_date"),
        "type": get_attr(trade, "right") or get_attr(trade, "option_type"),
        "option_type": get_attr(trade, "option_type") or get_attr(trade, "right"),
        "side": get_attr(trade, "side"),
        "entry": get_attr(trade, "entry_price"),
        "entry_price": get_attr(trade, "entry_price"),
        "entry_condition": get_attr(trade, "entry_condition") or "BREAKOUT",
        "entry_ref_price": get_attr(trade, "entry_ref_price"),
        "signal_price": get_attr(trade, "entry_price"),
        "stop": get_attr(trade, "stop_loss"),
        "stop_price": get_attr(trade, "stop_price") or get_attr(trade, "stop_loss"),
        "target": get_attr(trade, "target"),
        "target_price": get_attr(trade, "target_price") or get_attr(trade, "target"),
        "original_stop": get_attr(trade, "original_stop") or get_attr(trade, "stop_loss"),
        "current_stop": get_attr(trade, "current_stop") or get_attr(trade, "stop_loss"),
        "trail_enabled": get_attr(trade, "trail_enabled"),
        "trail_rule": get_attr(trade, "trail_rule") or getattr(cfg, "TRAIL_RULE_DEFAULT", "MFE_MINUS_OFFSET"),
        "trail_offset": get_attr(trade, "trail_offset"),
        "trail_start": get_attr(trade, "trail_start") or getattr(cfg, "TRAIL_START_DEFAULT", "AFTER_1R"),
        "mfe_price": get_attr(trade, "mfe_price"),
        "trail_stop": get_attr(trade, "trail_stop"),
        "last_update_ts": get_attr(trade, "last_update_ts"),
        "exit_signal": get_attr(trade, "exit_signal"),
        "exit_reason": get_attr(trade, "exit_reason"),
        "status": get_attr(trade, "status") or "PLANNING",
        "activated_ts": get_attr(trade, "activated_ts"),
        "activation_price": get_attr(trade, "activation_price"),
        "fill_price": get_attr(trade, "fill_price"),
        "ltp_at_activation": get_attr(trade, "ltp_at_activation"),
        "qty": get_attr(trade, "qty"),
        "confidence": get_attr(trade, "confidence"),
        "strategy": get_attr(trade, "strategy"),
        "strategy_id": strategy_id,
        "regime": get_attr(trade, "regime"),
        "regime_confidence": get_attr(trade, "regime_confidence"),
        "day_confidence": get_attr(trade, "day_confidence"),
        "orb_bias": get_attr(trade, "orb_bias"),
        "tier": get_attr(trade, "tier", None),
        "legs": get_attr(trade, "legs", None),
        "max_profit": get_attr(trade, "max_profit", None),
        "max_loss": get_attr(trade, "max_loss", None),
        "max_profit_label": get_attr(trade, "max_profit_label", None),
        "max_loss_label": get_attr(trade, "max_loss_label", None),
        "breakeven_low": get_attr(trade, "breakeven_low", None),
        "breakeven_high": get_attr(trade, "breakeven_high", None),
        "est_pnl_at_ltp": get_attr(trade, "est_pnl_at_ltp", None),
        "opt_ltp": get_attr(trade, "opt_ltp", None),
        "opt_bid": get_attr(trade, "opt_bid", None),
        "opt_ask": get_attr(trade, "opt_ask", None),
        "quote_ok": get_attr(trade, "quote_ok", None),
        "underlying_spot": get_attr(trade, "underlying_spot", None),
        "spot_source": get_attr(trade, "spot_source", None),
        "option_ltp_source": get_attr(trade, "option_ltp_source", None),
        "option_ltp_timestamp": get_attr(trade, "option_ltp_timestamp", None),
        "current_ltp": get_attr(trade, "current_ltp", None),
        "suggested_entry": get_attr(trade, "suggested_entry", None),
        "price_age_sec": get_attr(trade, "price_age_sec", None),
        "quote_age_sec": get_attr(trade, "quote_age_sec", None),
        "entry_status": get_attr(trade, "entry_status", None),
        "price_source": get_attr(trade, "price_source", None),
        "mark_price": get_attr(trade, "mark_price", None),
        "mid_price": get_attr(trade, "mid_price", None),
        "best_bid": get_attr(trade, "best_bid", None),
        "best_ask": get_attr(trade, "best_ask", None),
        "entry_price_proxy": get_attr(trade, "entry_price_proxy", None),
        "entry_price_proxy_buy": get_attr(trade, "entry_price_proxy_buy", None),
        "entry_price_proxy_sell": get_attr(trade, "entry_price_proxy_sell", None),
        "chain_source": get_attr(trade, "chain_source", None),
        "trade_score": get_attr(trade, "trade_score", None),
        "trade_alignment": get_attr(trade, "trade_alignment", None),
        "trade_score_detail": get_attr(trade, "trade_score_detail", None),
        "direction": get_attr(trade, "direction", None),
        "global_confidence": get_attr(trade, "global_confidence", None),
        "permission": get_attr(trade, "permission", None),
        "permission_reason": get_attr(trade, "permission_reason", None),
        "countertrend": get_attr(trade, "countertrend", None),
        "raw_signal_confidence": get_attr(trade, "raw_signal_confidence", None),
        "timestamp": str(get_attr(trade, "timestamp")),
        "upstox_instrument_key": get_attr(trade, "upstox_instrument_key"),
    }
    if extra:
        entry.update(extra)
    if entry.get("instrument") == "OPT":
        if not entry.get("expiry_date") and entry.get("expiry"):
            entry["expiry_date"] = _coerce_expiry(entry.get("expiry")) or entry.get("expiry")
        if entry.get("expiry_date"):
            entry["expiry_date"] = _coerce_expiry(entry.get("expiry_date")) or entry.get("expiry_date")
        opt_type = _coerce_option_type(entry.get("option_type") or entry.get("type") or entry.get("right"))
        if opt_type:
            entry["option_type"] = opt_type
            entry["type"] = opt_type
        strike_val = _coerce_strike(entry.get("strike"))
        if strike_val is not None:
            entry["strike"] = strike_val
        chain_meta = _option_chain_meta_map()
        if entry.get("instrument_token") and (not entry.get("expiry_date") or not entry.get("tradingsymbol")):
            meta = _instrument_meta_map().get(entry.get("instrument_token"), {})
            if not meta and chain_meta:
                meta = (chain_meta.get("by_token") or {}).get(entry.get("instrument_token"), {})
            if meta:
                entry.setdefault("expiry_date", meta.get("expiry"))
                entry.setdefault("expiry", meta.get("expiry"))
                entry.setdefault("tradingsymbol", meta.get("tradingsymbol"))
                entry.setdefault("option_type", _coerce_option_type(meta.get("type")))
                entry.setdefault("type", _coerce_option_type(meta.get("type")))
                if meta.get("strike") is not None:
                    entry.setdefault("strike", meta.get("strike"))
        if (not entry.get("instrument_token")) and entry.get("symbol") and strike_val is not None and opt_type:
            meta = None
            expiry_date = entry.get("expiry_date")
            if expiry_date:
                meta = (chain_meta.get("by_contract") or {}).get((entry.get("symbol"), expiry_date, float(strike_val), opt_type))
            if meta is None:
                candidates = (chain_meta.get("by_symbol_strike_type") or {}).get(
                    (entry.get("symbol"), float(strike_val), opt_type),
                    [],
                )
                if candidates:
                    exp_dates = []
                    meta_by_exp = {}
                    for cand in candidates:
                        exp = _coerce_expiry(cand.get("expiry"))
                        if not exp:
                            continue
                        try:
                            exp_dt = datetime.fromisoformat(exp).date()
                        except Exception:
                            continue
                        exp_dates.append(exp_dt)
                        meta_by_exp[exp_dt.isoformat()] = cand
                    if exp_dates:
                        chosen = choose_nearest_available_expiry(exp_dates, today=datetime.now().date())
                        if chosen is not None:
                            meta = meta_by_exp.get(chosen.isoformat())
            if meta:
                entry.setdefault("expiry_date", meta.get("expiry"))
                entry.setdefault("expiry", meta.get("expiry"))
                entry.setdefault("tradingsymbol", meta.get("tradingsymbol"))
                entry.setdefault("instrument_token", meta.get("instrument_token"))
                entry.setdefault("option_type", _coerce_option_type(meta.get("type")))
                entry.setdefault("type", _coerce_option_type(meta.get("type")))
        if (not entry.get("instrument_token")) and entry.get("symbol") and entry.get("expiry_date") and strike_val is not None and opt_type:
            resolved = resolve_option_token(
                entry.get("symbol"),
                entry.get("expiry_date"),
                strike_val,
                opt_type,
            )
            if resolved:
                entry.setdefault("instrument_token", resolved.get("instrument_token"))
                entry.setdefault("tradingsymbol", resolved.get("tradingsymbol"))
        if not entry.get("instrument_id"):
            if entry.get("tradingsymbol"):
                entry["instrument_id"] = entry.get("tradingsymbol")
            elif entry.get("instrument_token"):
                entry["instrument_id"] = str(entry.get("instrument_token"))
            else:
                entry["instrument_id"] = build_instrument_id(
                    entry.get("underlying") or entry.get("symbol"),
                    "OPT",
                    entry.get("expiry_date"),
                    entry.get("strike"),
                    entry.get("option_type") or entry.get("type"),
                )
        if entry.get("target") in (None, "", "None"):
            rr_default = float(getattr(cfg, "TARGET_RR_DEFAULT", 1.5)) if cfg else 1.5
            derived_target = _derive_target(entry.get("entry"), entry.get("stop"), entry.get("side"), rr_default)
            if derived_target is not None:
                entry["target"] = derived_target
                entry["target_derived"] = True
                entry["target_rr"] = rr_default
        unresolved_contract = False
        if not entry.get("instrument_id"):
            unresolved_contract = True
        if not entry.get("expiry_date"):
            unresolved_contract = True
        if not entry.get("tradingsymbol"):
            unresolved_contract = True
        if unresolved_contract:
            entry["tradable"] = False
            entry["tradable_reasons_blocking"] = list(
                dict.fromkeys(list(entry.get("tradable_reasons_blocking") or []) + ["unresolved_contract"])
            )
            entry.setdefault("execution_allowed", False)
            entry.setdefault("hard_reason", "unresolved_contract")
            entry.setdefault("approval_blocked", True)
            if not entry.get("entry_status"):
                entry["entry_status"] = "NO_TOKEN"
            entry["entry"] = None
        else:
            token_val = entry.get("instrument_token")
            if token_val is not None:
                try:
                    ensure_subscribed_tokens([int(token_val)], reason="trade_created", symbol=entry.get("symbol"))
                except Exception:
                    pass
            tick = None
            try:
                tick = get_last_tick(entry.get("instrument_token"))
            except Exception:
                tick = None
            current_ltp = tick.get("ltp") if isinstance(tick, dict) else None
            ltp_ts_epoch = tick.get("ts_epoch") if isinstance(tick, dict) else None
            validation = validate_live_entry(
                signal_price=entry.get("signal_price"),
                current_ltp=current_ltp,
                ltp_ts_epoch=ltp_ts_epoch,
                mode=runtime_mode,
            )
            entry["current_ltp"] = validation.get("current_ltp")
            entry["option_ltp_timestamp"] = ltp_ts_epoch
            entry["price_age_sec"] = validation.get("price_age_sec")
            entry["entry_status"] = validation.get("entry_status")
            entry["suggested_entry"] = validation.get("suggested_entry")
            if validation.get("valid"):
                entry["entry"] = validation.get("suggested_entry")
                entry["option_ltp_source"] = tick.get("source") if isinstance(tick, dict) else entry.get("option_ltp_source")
            else:
                entry["entry"] = None
                entry.setdefault("execution_allowed", False)
                entry["permission"] = "ADVISORY_ONLY"
                entry["permission_reason"] = entry.get("permission_reason") or validation.get("entry_status")
            if not entry.get("upstox_instrument_key"):
                try:
                    entry["upstox_instrument_key"] = resolve_upstox_key(entry)
                except Exception:
                    entry["upstox_instrument_key"] = None
            try:
                entry_val = float(entry.get("entry") or 0.0)
                target_val = float(entry.get("target") or 0.0)
                stop_val = float(entry.get("stop") or 0.0)
                if entry_val > 0 and target_val > 0:
                    entry["target_premium"] = round(abs(target_val - entry_val), 2)
                if entry_val > 0 and stop_val > 0:
                    entry["stop_premium"] = round(abs(entry_val - stop_val), 2)
            except Exception:
                pass
    perm = {}
    try:
        raw_conf = entry.get("raw_signal_confidence")
        if raw_conf is None:
            raw_conf = entry.get("confidence")
        regime = entry.get("regime") or "UNKNOWN"
        regime_conf = entry.get("regime_confidence")
        if regime_conf is None:
            regime_conf = entry.get("day_confidence")
        orb_bias = entry.get("orb_bias")
        if not orb_bias and isinstance(entry.get("source_flags"), dict):
            orb_bias = entry.get("source_flags", {}).get("orb_bias")
        option_type = entry.get("option_type") or entry.get("type")
        side = entry.get("side")
        last_candle = entry.get("last_candle")
        atr_ratio = entry.get("atr_ratio") or entry.get("atr_pct")
        perm = build_permission_payload(
            signal_score=raw_conf,
            regime=regime,
            regime_conf=regime_conf,
            orb_bias=orb_bias,
            option_type=option_type,
            side=side,
            last_candle=last_candle if isinstance(last_candle, dict) else None,
            atr_ratio=atr_ratio,
        )
        entry["direction"] = perm.get("direction")
        entry["global_confidence"] = perm.get("global_confidence")
        entry["permission"] = perm.get("permission")
        entry["permission_reason"] = perm.get("permission_reason")
        entry["countertrend"] = perm.get("countertrend")
        entry["raw_signal_confidence"] = raw_conf
        if perm.get("global_confidence") is not None:
            entry["confidence"] = perm.get("global_confidence")
        if perm.get("regime_confidence") is not None:
            entry["regime_confidence"] = perm.get("regime_confidence")
        entry_status = str(entry.get("entry_status") or "")
        if entry_status and entry_status != "OK":
            entry["permission"] = "ADVISORY_ONLY"
            entry["permission_reason"] = entry.get("permission_reason") or entry_status
    except Exception as exc:
        logger.warning("permission_compute_failed: %s", exc)
        entry["permission_reason"] = f"permission_compute_failed:{type(exc).__name__}"
    entry_status = str(entry.get("entry_status") or "")
    entry_block_reason = entry_status if entry_status and entry_status != "OK" else None
    permission = str(entry.get("permission") or "ADVISORY_ONLY").upper()
    permission_reason = str(entry.get("permission_reason") or "")
    global_conf = _safe_float(entry.get("global_confidence"))
    high_execute_threshold = float(getattr(cfg, "HIGH_EXECUTE_MIN_CONF", 0.65))
    high_execute_eligible = bool(
        permission == "EXECUTE"
        and entry_block_reason is None
        and global_conf is not None
        and global_conf >= high_execute_threshold
    )
    final_action = "EXECUTE" if permission == "EXECUTE" and entry_block_reason is None else "ADVISORY_ONLY"
    high_execute_blockers: list[str] = []
    if global_conf is None or global_conf < high_execute_threshold:
        high_execute_blockers.append("global_conf_below_high_execute")
    if permission != "EXECUTE":
        high_execute_blockers.append(f"permission_{permission}")
    if entry_block_reason:
        high_execute_blockers.append(f"entry_{entry_block_reason}")
    decision_trace = {
        "signal_score": _safe_float(perm.get("signal_score") if isinstance(perm, dict) else entry.get("raw_signal_confidence")),
        "regime_conf": _safe_float(entry.get("regime_confidence")),
        "orb_bias": (perm.get("orb_bias") if isinstance(perm, dict) else None) or entry.get("orb_bias"),
        "orb_factor": _safe_float(perm.get("orb_factor") if isinstance(perm, dict) else None),
        "reg_penalty": _safe_float(perm.get("regime_penalty") if isinstance(perm, dict) else None),
        "global_conf": global_conf,
        "permission": permission,
        "permission_reason": permission_reason,
        "entry_status": entry_status or None,
        "entry_block_reason": entry_block_reason,
        "high_execute_threshold": high_execute_threshold,
        "high_execute_eligible": high_execute_eligible,
        "high_execute_blockers": high_execute_blockers,
        "final_action": final_action,
    }
    entry["decision_trace"] = decision_trace
    entry["final_action"] = final_action
    source_flags = entry.get("source_flags")
    if isinstance(source_flags, dict):
        merged_flags = dict(source_flags)
        merged_flags["decision_trace"] = decision_trace
        entry["source_flags"] = merged_flags
    entry["trade_key"] = compute_trade_key(
        entry.get("symbol"),
        entry.get("expiry_date") or entry.get("expiry"),
        entry.get("strike"),
        entry.get("option_type") or entry.get("type"),
        entry.get("side"),
        entry.get("strategy_id") or entry.get("strategy"),
    )
    data = _merge_trade_entry(data, entry)
    write_queue_rows(path, data)
    # Log suggestion for evaluation
    _append_jsonl(suggestion_log_paths(), entry)

def is_approved(trade_id, payload_hash=None):
    ok, _reason = approval_status(trade_id, payload_hash=payload_hash)
    return ok


def approve(trade_id, payload_hash=None, ttl_sec=None, approver=None):
    trade_id = str(trade_id)
    store = _load_approvals()
    approvals = store.setdefault("approvals", {})
    now_epoch = time.time()
    if ttl_sec is None:
        ttl_sec = _cfg_int("APPROVAL_TTL_SEC", 600)
    expires_epoch = now_epoch + max(int(ttl_sec), 0)
    approvals[trade_id] = {
        "status": "APPROVED",
        "payload_hash": payload_hash,
        "approved_epoch": now_epoch,
        "expires_epoch": expires_epoch,
        "approved_by": approver,
    }
    _write_json(APPROVED_PATH, store)


def get_queue_entry(trade_id, queue_paths=None):
    queue_paths = queue_paths or [QUEUE_PATH, QUICK_QUEUE_PATH, ZERO_HERO_QUEUE_PATH, SCALP_QUEUE_PATH, TARGET_POINTS_QUEUE_PATH]
    for path in queue_paths:
        rows = load_queue_rows(path)
        for row in rows:
            if isinstance(row, dict) and str(row.get("trade_id")) == str(trade_id):
                return row
    return None

def remove_from_queue(trade_id):
    if not QUEUE_PATH.exists():
        return
    data = load_queue_rows(QUEUE_PATH)
    data = [d for d in data if d.get("trade_id") != trade_id]
    write_queue_rows(QUEUE_PATH, data)
