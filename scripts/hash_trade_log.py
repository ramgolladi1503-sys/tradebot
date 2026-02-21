# Migration note:
# Trade-log hashing now resolves through canonical trade-log path helper.

from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import hashlib
import json
from datetime import datetime

OUT = Path("logs/log_hashes.json")

from core.trade_log_paths import ensure_trade_log_exists

def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> dict | None:
    log_path = ensure_trade_log_exists()
    try:
        digest = _hash_file(log_path)
    except Exception as exc:
        print(f"[hash_trade_log][WARN] cannot hash trade log at {log_path}: {exc}")
        return None
    payload = {"timestamp": datetime.now().isoformat(), "path": str(log_path), "sha256": digest}
    history = []
    if OUT.exists():
        try:
            history = json.loads(OUT.read_text())
        except Exception:
            history = []
    history.append(payload)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(history[-2000:], indent=2))
    print(payload)
    return payload


if __name__ == "__main__":
    main()
