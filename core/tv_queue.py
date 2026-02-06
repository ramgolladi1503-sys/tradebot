import json
from pathlib import Path
from core.review_queue import add_to_queue

TV_QUEUE = Path("logs/tv_queue.json")

def enqueue_alert(payload):
    TV_QUEUE.parent.mkdir(exist_ok=True)
    data = []
    if TV_QUEUE.exists():
        try:
            data = json.loads(TV_QUEUE.read_text())
        except Exception:
            data = []
    data.append(payload)
    TV_QUEUE.write_text(json.dumps(data, indent=2))
    # Also add to review queue if payload has trade fields
    try:
        if "trade_id" in payload:
            add_to_queue(type("Obj", (), payload))
    except Exception:
        pass
