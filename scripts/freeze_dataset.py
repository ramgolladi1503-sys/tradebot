from pathlib import Path
import runpy
from core.paths import data_root

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

from config import config as cfg

SRC = {
    "trade_log": data_root() / "trade_log.json",
    "trades_db": Path(getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db"))),
}


def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_dir = data_root() / "snapshots" / ts
    snap_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"timestamp": ts, "files": []}
    for key, path in SRC.items():
        if not path.exists():
            continue
        dest = snap_dir / path.name
        shutil.copy2(path, dest)
        manifest["files"].append(
            {
                "key": key,
                "path": str(dest),
                "sha256": _hash_file(dest),
                "size": dest.stat().st_size,
            }
        )

    manifest_path = snap_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Snapshot saved to {snap_dir}")
