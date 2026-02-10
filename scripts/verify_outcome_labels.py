from pathlib import Path
import runpy
import sqlite3
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg


def main() -> int:
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", "data/desks/DEFAULT/trades.db"))
    if not db_path.exists():
        print("verify_outcome_labels: FAIL missing trades DB.")
        print("NEXT ACTION: run paper/live cycle to generate trades and outcomes.")
        return 2
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='outcomes'")
    if not cur.fetchone():
        con.close()
        print("verify_outcome_labels: FAIL missing outcomes table.")
        print("NEXT ACTION: run migration via trade_store.init_db().")
        return 2
    cur.execute("SELECT COUNT(1) FROM outcomes")
    total = int(cur.fetchone()[0] or 0)
    if total == 0:
        con.close()
        print("verify_outcome_labels: FAIL no outcomes rows.")
        print("NEXT ACTION: generate at least one closed trade outcome via paper run.")
        return 2
    eps = float(getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6))
    cur.execute(
        """
        SELECT trade_id, realized_pnl, outcome_label
        FROM outcomes
        WHERE realized_pnl > ? AND outcome_label != 'WIN'
        LIMIT 5
        """,
        (eps,),
    )
    wrong_win = cur.fetchall()
    cur.execute(
        """
        SELECT trade_id, realized_pnl, outcome_label
        FROM outcomes
        WHERE realized_pnl < ? AND outcome_label != 'LOSS'
        LIMIT 5
        """,
        (-eps,),
    )
    wrong_loss = cur.fetchall()
    con.close()
    if wrong_win or wrong_loss:
        print("verify_outcome_labels: FAIL inconsistent outcome labels.")
        for row in wrong_win:
            print("expected WIN:", row)
        for row in wrong_loss:
            print("expected LOSS:", row)
        return 1
    print(f"verify_outcome_labels: OK rows={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
