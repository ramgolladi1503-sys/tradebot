from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import hmac
import hashlib
from flask import Flask, request, jsonify
from config import config as cfg
from core.tv_queue import enqueue_alert

REQUIRED_FIELDS = {"trade_id", "symbol", "instrument", "entry", "stop", "target", "strategy"}

app = Flask(__name__)

@app.post("/webhook")
def webhook():
    # Signature verification
    signature = request.headers.get("X-Signature", "")
    raw = request.get_data() or b""
    if cfg.TV_SHARED_SECRET:
        digest = hmac.new(cfg.TV_SHARED_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, digest):
            return jsonify({"status": "rejected", "error": "invalid signature"}), 401

    payload = request.get_json(force=True, silent=True) or {}
    missing = REQUIRED_FIELDS - set(payload.keys())
    if missing:
        return jsonify({"status": "rejected", "missing": list(missing)}), 400
    enqueue_alert(payload)
    return jsonify({"status": "queued"})

@app.get("/signature_example")
def signature_example():
    import json as _json
    sample = {
        "trade_id": "TV-001",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "entry": 100,
        "stop": 90,
        "target": 120,
        "strategy": "TV_SIGNAL"
    }
    raw = _json.dumps(sample).encode()
    if cfg.TV_SHARED_SECRET:
        digest = hmac.new(cfg.TV_SHARED_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    else:
        digest = "set TV_SHARED_SECRET to generate"
    return jsonify({"payload": sample, "signature": digest})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
