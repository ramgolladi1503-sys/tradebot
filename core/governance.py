import json
import hashlib
from datetime import datetime
from pathlib import Path
from config import config as cfg


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _safe_cfg_snapshot() -> dict:
    snap = {}
    for k, v in cfg.__dict__.items():
        if k.startswith("_"):
            continue
        key_upper = k.upper()
        if any(x in key_upper for x in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            continue
        if callable(v):
            continue
        try:
            json.dumps(v, default=str)
            snap[k] = v
        except Exception:
            snap[k] = str(v)
    return snap


def _file_hash(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return _sha256_bytes(p.read_bytes())


def model_hashes() -> dict:
    paths = {
        "ml_model": getattr(cfg, "ML_MODEL_PATH", ""),
        "ml_challenger": getattr(cfg, "ML_CHALLENGER_MODEL_PATH", ""),
        "deep_model": getattr(cfg, "DEEP_MODEL_PATH", ""),
        "micro_model": getattr(cfg, "MICRO_MODEL_PATH", ""),
        "regime_model": getattr(cfg, "REGIME_MODEL_PATH", ""),
    }
    out = {}
    for k, p in paths.items():
        if p:
            out[k] = _file_hash(p)
    return out


def append_immutable_ledger(entry: dict, ledger_path: str = "logs/trade_ledger.jsonl") -> str:
    path = Path(ledger_path)
    path.parent.mkdir(exist_ok=True)
    prev_hash = None
    if path.exists():
        try:
            with path.open("rb") as f:
                last = f.readlines()[-1]
                prev = json.loads(last.decode("utf-8"))
                prev_hash = prev.get("hash")
        except Exception:
            prev_hash = None
    entry["prev_hash"] = prev_hash
    payload = json.dumps(entry, sort_keys=True, default=str).encode("utf-8")
    entry["hash"] = _sha256_bytes(payload)
    with path.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry["hash"]


def record_governance(trade, market_data, risk_state, exec_report, extra=None) -> str:
    entry = {
        "timestamp": str(datetime.now()),
        "trade_id": getattr(trade, "trade_id", None),
        "symbol": getattr(trade, "symbol", None),
        "instrument": getattr(trade, "instrument", None),
        "strike": getattr(trade, "strike", None),
        "type": getattr(trade, "type", None),
        "side": getattr(trade, "side", None),
        "entry": getattr(trade, "entry_price", None),
        "stop": getattr(trade, "stop_loss", None),
        "target": getattr(trade, "target", None),
        "qty": getattr(trade, "qty", None),
        "strategy": getattr(trade, "strategy", None),
        "regime": getattr(trade, "regime", None),
        "day_type": getattr(trade, "day_type", None),
        "regime_probs": market_data.get("regime_probs") if market_data else None,
        "risk_state": risk_state.to_dict() if risk_state else None,
        "execution_metrics": exec_report,
        "config_snapshot": _safe_cfg_snapshot(),
        "model_hashes": model_hashes(),
        "extra": extra or {},
    }
    return append_immutable_ledger(entry)
