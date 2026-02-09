import argparse
import json
import hashlib
import zipfile
from pathlib import Path

from config import config as cfg


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_incident(incident_id: str):
    path = Path(getattr(cfg, "INCIDENTS_LOG_PATH", "logs/incidents.jsonl"))
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("incident_id") == incident_id:
            return row
    return None


def build_bundle(incident_id: str, out_dir: str = "logs/incident_bundles") -> Path:
    incident = _load_incident(incident_id)
    if not incident:
        raise SystemExit(f"incident_id not found: {incident_id}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bundle_path = out / f"incident_{incident_id}.zip"
    manifest = {
        "incident_id": incident_id,
        "files": [],
    }
    files = [
        Path(getattr(cfg, "INCIDENTS_LOG_PATH", "logs/incidents.jsonl")),
        Path(getattr(cfg, "AUDIT_LOG_PATH", "logs/audit_log.jsonl")),
        Path(getattr(cfg, "DESK_LOG_DIR", "logs")) / "sla_check.json",
        Path(getattr(cfg, "DESK_LOG_DIR", "logs")) / "config_snapshot.json",
        Path(cfg.TRADE_DB_PATH),
    ]
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("incident.json", json.dumps(incident, indent=2))
        for path in files:
            if not path.exists():
                continue
            data = path.read_bytes()
            sha = _sha256_bytes(data)
            manifest["files"].append({"path": str(path), "sha256": sha})
            zf.writestr(path.name, data)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return bundle_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--out-dir", default="logs/incident_bundles")
    args = parser.parse_args()
    path = build_bundle(args.incident_id, out_dir=args.out_dir)
    print(f"Bundle created: {path}")


if __name__ == "__main__":
    main()
