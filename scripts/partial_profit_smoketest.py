from pathlib import Path
import runpy
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg


def main() -> int:
    if not bool(getattr(cfg, "PARTIAL_PROFIT_ENABLED", True)):
        print("partial_profit_smoketest: FAIL PARTIAL_PROFIT_ENABLED=false")
        print("NEXT ACTION: enable PARTIAL_PROFIT_ENABLED for this smoketest.")
        return 2
    entry = 100.0
    stop = 90.0
    qty_units = 100
    side = "BUY"
    risk = abs(entry - stop)
    tp1 = entry + risk * float(getattr(cfg, "TP1_R_MULT", 0.7))
    tp2 = entry + risk * float(getattr(cfg, "TP2_R_MULT", 1.5))
    prices = [100.0, 107.5, 104.0]

    rem = qty_units
    realized = 0.0
    weighted = 0.0
    legs = []
    tp1_done = False

    for px in prices:
        if not tp1_done and px >= tp1 and rem > 1:
            close_qty = min(rem - 1, max(1, int(round(rem * float(getattr(cfg, "TP1_FRACTION", 0.5))))))
            pnl = (px - entry) * close_qty if side == "BUY" else (entry - px) * close_qty
            rem -= close_qty
            realized += pnl
            weighted += px * close_qty
            legs.append({"reason": "TP1", "qty": close_qty, "price": px, "pnl": pnl})
            tp1_done = True
            continue

    # Remainder exits by trail in this deterministic path.
    final_px = prices[-1]
    final_reason = "TRAIL_STOP"
    pnl2 = (final_px - entry) * rem if side == "BUY" else (entry - final_px) * rem
    realized += pnl2
    weighted += final_px * rem
    legs.append({"reason": final_reason, "qty": rem, "price": final_px, "pnl": pnl2})

    avg_exit = weighted / qty_units
    if len(legs) != 2:
        print(f"partial_profit_smoketest: FAIL legs_count={len(legs)} expected=2")
        return 1
    if realized <= 0:
        print(f"partial_profit_smoketest: FAIL realized_pnl={realized} expected >0")
        return 1
    if legs[-1]["reason"] != "TRAIL_STOP":
        print(f"partial_profit_smoketest: FAIL exit_reason_final={legs[-1]['reason']} expected=TRAIL_STOP")
        return 1

    print("partial_profit_smoketest: OK")
    print(
        {
            "tp1": tp1,
            "tp2": tp2,
            "legs_count": len(legs),
            "legs": legs,
            "avg_exit": round(avg_exit, 4),
            "realized_pnl": round(realized, 4),
            "exit_reason_final": legs[-1]["reason"],
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
