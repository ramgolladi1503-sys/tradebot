import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.incidents import (
    trigger_audit_chain_fail,
    trigger_db_write_fail,
    trigger_feed_stale,
    trigger_hard_halt,
)
from incident_bundle import build_bundle


def main():
    ids = []
    ids.append(trigger_audit_chain_fail({"detail": "test"}))
    ids.append(trigger_db_write_fail({"detail": "test"}))
    ids.append(trigger_feed_stale({"detail": "test"}))
    ids.append(trigger_hard_halt({"detail": "test"}))
    print("Created incidents:")
    for i in ids:
        print(i)
    if ids:
        path = build_bundle(ids[-1])
        print(f"Incident bundle: {path}")


if __name__ == "__main__":
    main()
