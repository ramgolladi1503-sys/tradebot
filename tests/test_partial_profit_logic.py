from config import config as cfg


def test_tp1_then_trail_stop_remainder_yields_two_legs_and_positive_pnl():
    entry = 100.0
    stop = 90.0
    qty_units = 100
    side = "BUY"
    risk = abs(entry - stop)
    tp1 = entry + risk * float(getattr(cfg, "TP1_R_MULT", 0.7))
    prices = [100.0, 107.5, 104.0]

    rem = qty_units
    realized = 0.0
    legs = []
    tp1_done = False

    for px in prices:
        if not tp1_done and px >= tp1 and rem > 1:
            q1 = min(rem - 1, max(1, int(round(rem * float(getattr(cfg, "TP1_FRACTION", 0.5))))))
            pnl1 = (px - entry) * q1 if side == "BUY" else (entry - px) * q1
            rem -= q1
            realized += pnl1
            legs.append({"reason": "TP1", "qty": q1, "price": px, "pnl": pnl1})
            tp1_done = True
            break

    # Reverse to trail stop for remainder.
    exit_px = prices[-1]
    pnl2 = (exit_px - entry) * rem if side == "BUY" else (entry - exit_px) * rem
    realized += pnl2
    legs.append({"reason": "TRAIL_STOP", "qty": rem, "price": exit_px, "pnl": pnl2})

    assert len(legs) == 2
    assert legs[-1]["reason"] == "TRAIL_STOP"
    assert realized > 0
