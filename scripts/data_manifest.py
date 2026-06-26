from pathlib import Path
from core.paths import data_root, logs_dir

from config import config as cfg
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import hashlib
import json
from pathlib import Path
from datetime import datetime

FILES = [
    str(data_root() / "trade_log.json"),
    cfg.TRADE_DB_PATH,
    str(data_root() / "ml_features.csv"),
    str(data_root() / "tick_features.csv"),
]

OUT = logs_dir() / "data_manifest.json"


def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    items = []
    for p in FILES:
        path = Path(p)
        if not path.exists():
            continue
        items.append(
            {
                "path": p,
                "sha256": _hash_file(path),
                "size": path.stat().st_size,
            }
        )
    payload = {
        "timestamp": datetime.now().isoformat(),
        "items": items,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(payload)
