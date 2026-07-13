import pytest
import json
import math
from pathlib import Path
from core.tick_store import insert_tick
from core.vwap_accumulator import SessionVwapAccumulator, get_global_vwap_accumulator

def test_vwap_live_replay_parity():
    source = "data/ticks/20260702/index_ticks.jsonl"

    # 1. Collect all raw ticks for the traded token 11423234
    ticks = []
    with open(source, "r") as f:
        for line in f:
            if not line.strip():
                continue
            payload = json.loads(line)
            tick = payload.get("raw_tick") or {}
            if tick.get("instrument_token") == 11423234:
                ticks.append(payload)
                if len(ticks) >= 10:  # just test with 10 ticks for parity
                    break

    if not ticks:
        pytest.skip("No ticks for token 11423234 found")

    token = 11423234

    # 2. Simulate Live Mode
    # Reset global
    live_acc = get_global_vwap_accumulator(token)
    live_acc.reset_session()

    live_snapshots = []
    for payload in ticks:
        tick = payload.get("raw_tick") or {}
        # Parse timestamp
        # Replay payload has "local_ts" which is float
        ts_float = float(payload["local_ts"])
        ltp = tick.get("last_price")
        vol = tick.get("volume_traded")

        insert_tick(ts=ts_float, token=token, last_price=ltp, volume=vol)
        live_snapshots.append(live_acc.get_snapshot("LIVE_INCREMENTAL"))

    # 3. Simulate Replay Mode
    replay_acc = SessionVwapAccumulator()
    replay_snapshots = []
    for payload in ticks:
        tick = payload.get("raw_tick") or {}
        ts = payload.get("local_ts")
        ltp = tick.get("last_price")
        vol = tick.get("volume_traded")
        if ts is not None and ltp is not None and vol is not None:
            replay_acc.observe_tick(float(ts), float(ltp), float(vol))
        replay_snapshots.append(replay_acc.get_snapshot("REPLAY_RECONSTRUCTED"))

    # 4. Assert Parity
    for live, replay in zip(live_snapshots, replay_snapshots):
        if live["value"] is None:
            assert replay["value"] is None
        else:
            assert abs(live["value"] - replay["value"]) < 1e-6
        assert live["cumulative_volume"] == replay["cumulative_volume"]
        assert live["sample_count"] == replay["sample_count"]
        assert live["session_date"] == replay["session_date"]
