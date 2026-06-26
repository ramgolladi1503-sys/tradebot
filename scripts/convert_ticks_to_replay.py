#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from datetime import datetime


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_ticks_to_replay.py <input_jsonl>")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    if not input_file.exists():
        print(f"Error: {input_file} does not exist.")
        sys.exit(1)

    out_file = (
        Path(__file__).resolve().parents[1] / "data" / "active_options_replay.json"
    )

    snapshots = []
    current_state = {}
    last_second = None

    print(f"Processing {input_file}...")
    with open(input_file, "r") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except:
                continue

            ts_epoch = record.get("ts")
            if not ts_epoch:
                continue

            current_sec = int(ts_epoch)

            # If we rolled over to a new second, save the snapshot
            if last_second is not None and current_sec > last_second:
                snapshot = dict(current_state)
                # Form ISO datetime using UTC or IST? run_live_replay expects string timestamp
                # Let's assume standard local timezone formatting
                dt_str = datetime.fromtimestamp(last_second).isoformat()
                snapshot["timestamp"] = dt_str
                snapshots.append(snapshot)

            last_second = current_sec

            sym = record.get("symbol")
            if sym == "NIFTY 50":
                sym = "NIFTY_INDEX"
            elif sym == "NIFTY BANK":
                sym = "BANKNIFTY_INDEX"

            ltp = record.get("ltp")
            if ltp is not None:
                current_state[sym] = ltp

    # final snapshot
    if last_second is not None:
        snapshot = dict(current_state)
        dt_str = datetime.fromtimestamp(last_second).isoformat()
        snapshot["timestamp"] = dt_str
        snapshots.append(snapshot)

    print(f"Generated {len(snapshots)} snapshots.")

    # Save the array
    print(f"Saving to {out_file}...")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(snapshots, f, indent=2)
    print("Done!")


if __name__ == "__main__":
    main()
