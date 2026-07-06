import re

with open("scripts/generate_opening_drive_trade_ledger.py", "r") as f:
    c = f.read()

new_log = """
                    if not is_within_window:
                        cand_base = {
                            "signal_time": ts_str, "symbol": symbol, "opening_drive_window_minutes": opening_drive_window_minutes,
                            "open_move_points": open_move_points, "vwap_distance": 0, "signal_close": row['close'],
                            "setup_type": "UNKNOWN", "reject_reason": "OUTSIDE_OPENING_DRIVE_WINDOW"
                        }
                        if elapsed_minutes < 120 and (int(elapsed_minutes) % 15 == 0):
                            f_cand.write(json.dumps(cand_base) + "\\n")
                        continue
                        
                    vwap_distance = abs(row['close'] - row['vwap'])
                    if abs(open_move_points) < min_open_move_points:
                        cand_base = {
                            "signal_time": ts_str, "symbol": symbol, "opening_drive_window_minutes": opening_drive_window_minutes,
                            "open_move_points": open_move_points, "vwap_distance": vwap_distance, "signal_close": row['close'],
                            "setup_type": "UNKNOWN", "reject_reason": "OPEN_MOVE_TOO_WEAK"
                        }
                        if int(elapsed_minutes) == 15:
                            f_cand.write(json.dumps(cand_base) + "\\n")
                        continue
"""

c = re.sub(r'                    if not is_within_window:.*?continue', new_log.strip(), c, flags=re.DOTALL)

with open("scripts/generate_opening_drive_trade_ledger.py", "w") as f:
    f.write(c)

