from datetime import datetime, timedelta
from pathlib import Path

from core.news_calendar import NewsCalendar


def test_news_calendar_shock(tmp_path):
    now = datetime.now()
    ev = {
        "name": "RBI",
        "ts_ist": (now + timedelta(minutes=30)).isoformat(),
        "importance": 5,
        "category": "RBI",
    }
    path = tmp_path / "events.json"
    path.write_text("[" + __import__("json").dumps(ev) + "]")

    nc = NewsCalendar(calendar_path=path)
    shock = nc.get_shock()
    assert shock["shock_score"] > 0
    assert shock["event_name"] == "RBI"
