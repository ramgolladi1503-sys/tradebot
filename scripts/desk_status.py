import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.desk_config import get_desk_config


def main():
    desk = get_desk_config()
    print(f"Desk: {desk.desk_id}")
    print(f"Data dir: {desk.data_dir}")
    print(f"Log dir: {desk.log_dir}")
    print(f"Trade DB: {desk.trade_db_path}")
    print(f"Decision log: {desk.decision_log_path}")
    print(f"Audit log: {desk.audit_log_path}")
    print(f"Incidents log: {desk.incidents_log_path}")


if __name__ == "__main__":
    main()
