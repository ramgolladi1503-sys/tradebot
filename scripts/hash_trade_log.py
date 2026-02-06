from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import hashlib
import json
from pathlib import Path
from datetime import datetime

LOG = Path("data/trade_log.json")
OUT = Path("logs/log_hashes.json")

def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

if __name__ == "__main__":
    if not LOG.exists():
        raise SystemExit("trade_log.json not found")
    digest = _hash_file(LOG)
    payload = {"timestamp": datetime.now().isoformat(), "path": str(LOG), "sha256": digest}
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
