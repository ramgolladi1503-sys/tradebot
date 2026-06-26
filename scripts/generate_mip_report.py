import os
import sqlite3
import datetime
from core.intelligence.config import config


def generate_report():
    print("Generating MIP Advisory Dashboard Report...")
    print("=========================================")
    print("DISCLAIMER: NOT A TRADE SIGNAL.")
    print("DISCLAIMER: NO EXECUTION INFLUENCE.")
    print("DISCLAIMER: NO RANKING INFLUENCE.")
    print("=========================================\n")

    if not os.path.exists(config.SQLITE_DB_PATH):
        print("Database not found. Pipeline has not run yet.")
        return

    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. Source Health & Freshness
    print("## Source Health & Freshness")
    sources = conn.execute("""
        SELECT s.source_id, s.url, MAX(r.fetch_timestamp) as last_fetch, r.status
        FROM intelligence_sources s
        LEFT JOIN intelligence_fetch_runs r ON s.source_id = r.source_id
        GROUP BY s.source_id
    """).fetchall()

    for s in sources:
        ts = (
            datetime.datetime.fromtimestamp(s["last_fetch"]).isoformat()
            if s["last_fetch"]
            else "NEVER"
        )
        print(f"[{s['source_id']}] Health: {s['status']} | Last Fetch: {ts}")

    print("\n## Latest Advisory Events")

    events = conn.execute("""
        SELECT e.event_id, d.title, d.published_timestamp, e.calibration_status, e.evidence_pointer, d.content_hash
        FROM intelligence_events e
        JOIN intelligence_documents d ON e.doc_id = d.doc_id
        ORDER BY d.published_timestamp DESC LIMIT 10
    """).fetchall()

    if not events:
        print("No extracted events found.")

    for e in events:
        pts = (
            datetime.datetime.fromtimestamp(e["published_timestamp"]).isoformat()
            if e["published_timestamp"]
            else "UNKNOWN"
        )
        print(f"\n--- Event ID: {e['event_id']} ---")
        print(f"Title: {e['title']}")
        print(f"Date: {pts}")
        print(f"Calibration Status: {e['calibration_status']}")
        print(f"Evidence: {e['evidence_pointer']}")
        print(f"Document Hash: {e['content_hash']}")

        # Factor Breakdown
        print("Factor Breakdown:")
        factors = conn.execute(
            "SELECT name, value, unit FROM intelligence_factors WHERE event_id = ?",
            (e["event_id"],),
        ).fetchall()
        for f in factors:
            print(f"  - {f['name']}: {f['value']} {f['unit']}")

    conn.close()


if __name__ == "__main__":
    generate_report()
