import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audit_log import verify_chain
from core.incidents import trigger_audit_chain_fail


def main():
    ok, status, count = verify_chain()
    if ok:
        print(f"Audit chain OK. events={count}")
        raise SystemExit(0)
    print(f"Audit chain FAIL. status={status} events={count}")
    try:
        trigger_audit_chain_fail({"status": status, "events": count})
    except Exception as exc:
        print(f"[INCIDENT_ERROR] audit_chain_fail err={exc}")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
