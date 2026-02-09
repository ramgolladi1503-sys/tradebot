import sys
from pathlib import Path
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.time_utils import is_today_local, age_minutes_local, now_local


def main():
    now = now_local()
    ts_today = now.isoformat()
    ts_yesterday = (now - timedelta(days=1, hours=1)).isoformat()
    ts_time_only = now.strftime("%H:%M:%S")

    assert is_today_local(ts_today, now=now) is True, "today ts should be today"
    assert is_today_local(ts_yesterday, now=now) is False, "yesterday ts should not be today"
    assert is_today_local(ts_time_only, now=now) is False, "time-only ts should be rejected"

    age = age_minutes_local(ts_yesterday, now=now)
    assert age is not None and age > 60, "yesterday age should be > 60 min"
    print("verify_queue_filter: OK")


if __name__ == "__main__":
    main()
