import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.decision_logger import verify_decision_chain


def main():
    ok, status, count = verify_decision_chain()
    if ok:
        print(f"Decision chain OK. events={count}")
        raise SystemExit(0)
    print(f"Decision chain FAIL. status={status} events={count}")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
