import argparse
import json
import shutil
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.decision_logger import verify_decision_chain
from core.audit_log import verify_chain as verify_audit_chain


def _copy_if_exists(src: Path, dst_dir: Path):
    if src.exists():
        shutil.copy2(src, dst_dir / src.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="logs/audit_bundle")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "ts_epoch": time.time(),
        "bundle_dir": str(out_dir),
        "files": [],
    }

    logs = Path(getattr(cfg, "DESK_LOG_DIR", "logs"))
    _copy_if_exists(Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl")), out_dir)
    _copy_if_exists(Path(getattr(cfg, "AUDIT_LOG_PATH", "logs/audit_log.jsonl")), out_dir)
    _copy_if_exists(logs / "model_registry.json", out_dir)
    for file in logs.glob("daily_audit_*.json"):
        _copy_if_exists(file, out_dir)
    for file in logs.glob("execution_report_*.json"):
        _copy_if_exists(file, out_dir)
    for file in logs.glob("decay_report_*.json"):
        _copy_if_exists(file, out_dir)
    for file in logs.glob("rl_shadow_report_*.json"):
        _copy_if_exists(file, out_dir)

    ok, status, count = verify_decision_chain()
    manifest["decision_chain_ok"] = ok
    manifest["decision_chain_status"] = status
    manifest["decision_chain_count"] = count
    audit_ok, audit_status, audit_count = verify_audit_chain()
    manifest["audit_chain_ok"] = audit_ok
    manifest["audit_chain_status"] = audit_status
    manifest["audit_chain_count"] = audit_count

    for file in out_dir.iterdir():
        if file.is_file():
            manifest["files"].append(file.name)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Audit bundle written: {out_dir}")
    print(f"Decision chain ok: {ok} ({status}), events: {count}")


if __name__ == "__main__":
    main()
