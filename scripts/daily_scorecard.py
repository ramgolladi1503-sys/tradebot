from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


from core.scorecard import append_scorecard_history, write_scorecard
from core.telegram_alerts import send_telegram_message

if __name__ == "__main__":
    sc = write_scorecard()
    hist = append_scorecard_history()
    # Build a compact summary
    total = len(sc)
    passed = sum(1 for x in sc if x.get("status") == "PASS")
    summary = f"Scorecard {passed}/{total} PASS"
    details = "\n".join([f"- {x['item']}: {x['status']}" for x in sc])
    send_telegram_message(summary + "\n" + details)
    print(summary)
