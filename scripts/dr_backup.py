import argparse
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_files() -> list[Path]:
    files: list[Path] = []
    db_path = Path(cfg.TRADE_DB_PATH)
    if db_path.exists():
        files.append(db_path)
    for p in Path("data").glob("*.db"):
        if p not in files and p.exists():
            files.append(p)
    cfg_path = Path("config") / "config.py"
    if cfg_path.exists():
        files.append(cfg_path)
    log_dir = Path(getattr(cfg, "DESK_LOG_DIR", "logs"))
    if log_dir.exists():
        for p in log_dir.glob("model_registry.json"):
            files.append(p)
        decision_log = Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl"))
        if decision_log.exists():
            files.append(decision_log)
        audit_log = Path(getattr(cfg, "AUDIT_LOG_PATH", "logs/audit_log.jsonl"))
        if audit_log.exists():
            files.append(audit_log)
        for pat in ["daily_audit_*.json", "execution_report_*.json", "decay_report_*.json", "rl_shadow_report_*.json"]:
            for p in log_dir.glob(pat):
                files.append(p)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="Output zip path (default logs/dr_backup_<ts>.zip)")
    args = parser.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else Path("logs") / f"dr_backup_{ts}.zip"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = _collect_files()
    if not files:
        print("ERROR:DR_NO_FILES no files to backup", file=sys.stderr)
        raise SystemExit(2)

    manifest = {
        "ts_epoch": time.time(),
        "files": [],
        "checksums": {},
    }

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            rel = path.as_posix()
            zf.write(path, arcname=rel)
            manifest["files"].append(rel)
            manifest["checksums"][rel] = _sha256(path)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    print(f"DR backup created: {out_path}")
    print(f"Files: {len(manifest['files'])}")


if __name__ == "__main__":
    main()
