import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.desk_config import get_desk_config


def _contains(base: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


def main() -> int:
    desk = get_desk_config()
    errors = []
    print(f"desk_id={desk.desk_id}")
    print(f"data_dir={desk.data_dir}")
    print(f"log_dir={desk.log_dir}")
    print(f"trade_db_path={desk.trade_db_path}")
    print(f"decision_log_path={desk.decision_log_path}")
    print(f"audit_log_path={desk.audit_log_path}")
    print(f"incidents_log_path={desk.incidents_log_path}")

    if desk.desk_id != "DEFAULT":
        if desk.desk_id not in str(desk.trade_db_path):
            errors.append("trade_db_path_missing_desk_id")
        if desk.desk_id not in str(desk.decision_log_path):
            errors.append("decision_log_path_missing_desk_id")
        if desk.desk_id not in str(desk.audit_log_path):
            errors.append("audit_log_path_missing_desk_id")
        if desk.desk_id not in str(desk.incidents_log_path):
            errors.append("incidents_log_path_missing_desk_id")

    if not _contains(desk.log_dir, desk.decision_log_path):
        errors.append("decision_log_not_in_log_dir")
    if not _contains(desk.log_dir, desk.audit_log_path):
        errors.append("audit_log_not_in_log_dir")
    if not _contains(desk.log_dir, desk.incidents_log_path):
        errors.append("incidents_log_not_in_log_dir")

    if errors:
        print("FAIL:")
        for err in errors:
            print(f"- {err}")
        return 1
    print("PASS: desk paths look consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
