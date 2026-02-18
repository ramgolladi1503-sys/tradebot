import json
import time
import hashlib
from pathlib import Path

from core.orders.order_intent import OrderIntent

QUEUE_PATH = Path("logs/review_queue.json")
QUICK_QUEUE_PATH = Path("logs/quick_review_queue.json")
ZERO_HERO_QUEUE_PATH = Path("logs/zero_hero_queue.json")
SCALP_QUEUE_PATH = Path("logs/scalp_queue.json")
TARGET_POINTS_QUEUE_PATH = Path("logs/target_points_queue.json")
APPROVED_PATH = Path("logs/approved_trades.json")


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


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


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
    path.parent.mkdir(exist_ok=True)
    data = []
    if path.exists():
        data = json.loads(path.read_text())
    def get_attr(obj, name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)
    strike_val = get_attr(trade, "strike")
    trade_id = get_attr(trade, "trade_id")
    if strike_val in (None, 0) and trade_id and "ATM" in str(trade_id):
        strike_val = "ATM"
    entry = {
        "trade_id": trade_id,
        "symbol": get_attr(trade, "symbol"),
        "strike": strike_val,
        "instrument": get_attr(trade, "instrument"),
        "instrument_token": get_attr(trade, "instrument_token"),
        "side": get_attr(trade, "side"),
        "entry": get_attr(trade, "entry_price"),
        "entry_condition": get_attr(trade, "entry_condition"),
        "entry_ref_price": get_attr(trade, "entry_ref_price"),
        "stop": get_attr(trade, "stop_loss"),
        "target": get_attr(trade, "target"),
        "qty": get_attr(trade, "qty"),
        "confidence": get_attr(trade, "confidence"),
        "strategy": get_attr(trade, "strategy"),
        "regime": get_attr(trade, "regime"),
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
        "trade_score": get_attr(trade, "trade_score", None),
        "trade_alignment": get_attr(trade, "trade_alignment", None),
        "trade_score_detail": get_attr(trade, "trade_score_detail", None),
        "timestamp": str(get_attr(trade, "timestamp"))
    }
    if extra:
        entry.update(extra)
    data.append(entry)
    path.write_text(json.dumps(data, indent=2))
    # Log suggestion for evaluation
    try:
        sug_path = Path("logs/suggestions.jsonl")
        sug_path.parent.mkdir(exist_ok=True)
        with open(sug_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

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
        rows = _read_json(path, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and str(row.get("trade_id")) == str(trade_id):
                return row
    return None

def remove_from_queue(trade_id):
    if not QUEUE_PATH.exists():
        return
    data = json.loads(QUEUE_PATH.read_text())
    data = [d for d in data if d.get("trade_id") != trade_id]
    QUEUE_PATH.write_text(json.dumps(data, indent=2))
