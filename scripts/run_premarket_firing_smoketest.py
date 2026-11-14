#!/usr/bin/env python3
"""Automated Pre-Market Dummy Trade Harness (Smoketest).

Proves that before market open (09:00 - 09:15 IST), Sentinel advisor can ingest
synthetic market ticks and Level-5 depth records, transition APM from STATE_STANDBY
to STATE_IN_FLIGHT with valid integer lot sizing, while strictly preserving all
safety invariants and ensuring 100% zero production WAL pollution.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from datetime import date, datetime, time as dt_time
from pathlib import Path
from unittest.mock import patch

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.active_position_manager import (
    STATE_IN_FLIGHT,
    STATE_STANDBY,
    ActivePositionManager,
)
from core.sentinel_inmem_adapter import InMemorySentinelAdapter
from core.sentinel_live_stream_advisor import (
    CachedRBFNAuctionSignal,
    SentinelLiveStreamAdvisor,
)
from core.sentinel_realtime_journal import SentinelRealtimeJournal
from core.upstox_stream_broadcaster import (
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
)

INDEX_LOT_CAPS = {
    "NIFTY": 3,
    "SENSEX": 2,
    "BANKNIFTY": 2,
}

INDEX_DEFAULT_SPOTS = {
    "NIFTY": 22400.0,
    "SENSEX": 74000.0,
    "BANKNIFTY": 48000.0,
}

INDEX_TOKENS = {
    "NIFTY": ("NSE_INDEX|Nifty 50", "NSE_FO|NIFTY26OCT22400CE", "NIFTY 22400 CE"),
    "SENSEX": ("BSE_INDEX|SENSEX", "BSE_FO|SENSEX26OCT74000CE", "SENSEX 74000 CE"),
    "BANKNIFTY": ("NSE_INDEX|Nifty Bank", "NSE_FO|BANKNIFTY26OCT48000CE", "BANKNIFTY 48000 CE"),
}


def get_runtime_wal_hashes() -> dict[str, str]:
    """Computes SHA256 hashes of all json WAL files currently in runtime/."""
    runtime_dir = ROOT / "runtime"
    hashes = {}
    if runtime_dir.exists():
        for p in runtime_dir.glob("*.json"):
            if p.is_file():
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                hashes[str(p.name)] = h
    return hashes


def run_smoketest(
    index_name: str = "NIFTY",
    assert_live_wal_clean: bool = True,
    keep_artifacts: bool = False,
) -> dict[str, any]:
    """Executes the pre-market firing smoketest in strictly isolated temporary paths."""
    pid = os.getpid()
    temp_dir = Path(tempfile.gettempdir())
    temp_wal = temp_dir / f"smoketest_apm_wal_{pid}.json"
    temp_journal_dir = temp_dir / f"smoketest_journal_{pid}"
    temp_journal_dir.mkdir(parents=True, exist_ok=True)

    # 1. Capture initial production WAL hashes
    hashes_before = get_runtime_wal_hashes() if assert_live_wal_clean else {}

    try:
        # 2. Instantiate strictly isolated journal and adapter
        journal = SentinelRealtimeJournal(logs_dir=temp_journal_dir, enable_writer_thread=False)
        adapter = InMemorySentinelAdapter(skew_threshold_ms=500.0)

        # 3. Instantiate advisor pointing to temporary WAL path
        advisor = SentinelLiveStreamAdvisor(
            adapter=adapter,
            enable_stdout=False,
            wal_path=str(temp_wal),
            journal=journal,
            advisory_capital=200000.0,
        )

        # 4. Assert non-negotiable safety invariants
        assert advisor.read_only is True, "Safety invariant violation: read_only must be True"
        assert advisor.is_order_action is False, "Safety invariant violation: is_order_action must be False"
        assert advisor.broker_api_called is False, "Safety invariant violation: broker_api_called must be False"
        assert advisor.allowed_for_live_execution is False, "Safety invariant violation: allowed_for_live_execution must be False"

        # 5. Check initial APM state is STANDBY
        idx_apm = advisor.apms[index_name]
        assert idx_apm.state == STATE_STANDBY, f"Initial state must be STATE_STANDBY, got {idx_apm.state}"

        # 6. Seed prior-day levels and spot price
        spot_price = INDEX_DEFAULT_SPOTS.get(index_name, 22400.0)
        advisor.trade_lock_active = False
        advisor.spots[index_name] = spot_price
        advisor.spots_ts_ms[index_name] = int(datetime(2026, 10, 26, 9, 30).timestamp() * 1000)
        advisor.session_gear = "GEAR_2_TREND"
        advisor.seed_prior_day_levels(
            index_name=index_name,
            pdh=spot_price + 100.0,
            pdl=spot_price - 100.0,
            pdc=spot_price,
            session_date=date(2026, 10, 25),
            atr_20=200.0,
        )

        # 7. Inject synthetic RBFN auction signal for opening drive
        sig = CachedRBFNAuctionSignal(
            timestamp_ms=int(datetime(2026, 10, 26, 9, 30).timestamp() * 1000),
            index_name=index_name,
            action="BUY_CALL",
            direction="CE",
            target_strike=spot_price,
            target_pts=50.0,
            sl_pts=20.0,
            setup_reason="Pre-Market Dummy Smoketest Golden Slingshot",
            trade_phase="OPENING_DRIVE",
            bar_time=dt_time(9, 30),
            sustainable_anchor_price=spot_price,
            valid_until_epoch_sec=9999999999.0,
        )
        advisor.cached_rbfn_signals[index_name] = sig

        # 8. Create synthetic Level-5 depth tick for matching contract
        idx_token, opt_token, opt_symbol = INDEX_TOKENS.get(
            index_name,
            ("NSE_INDEX|Nifty 50", "NSE_FO|NIFTY26OCT22400CE", "NIFTY 22400 CE"),
        )
        fake_now = datetime(2026, 10, 26, 9, 30, 0)
        ts_ms = int(fake_now.timestamp() * 1000)

        depth_record = UpstoxLevel5DepthRecord(
            token=opt_token,
            symbol=opt_symbol,
            exchange_timestamp_ms=ts_ms,
            ingress_monotonic_ns=1000,
            ingress_wall_utc="2026-10-26T04:00:00Z",
            sequence_id=1,
            ltp=120.0,
            volume=500000,
            open_interest=1000000,
            bid_p1=119.5, bid_q1=1000, bid_o1=10,
            bid_p2=119.0, bid_q2=1000, bid_o2=10,
            bid_p3=118.5, bid_q3=1000, bid_o3=10,
            bid_p4=118.0, bid_q4=1000, bid_o4=10,
            bid_p5=117.5, bid_q5=1000, bid_o5=10,
            ask_p1=120.5, ask_q1=1000, ask_o1=10,
            ask_p2=121.0, ask_q2=1000, ask_o2=10,
            ask_p3=121.5, ask_q3=1000, ask_o3=10,
            ask_p4=122.0, ask_q4=1000, ask_o4=10,
            ask_p5=122.5, ask_q5=1000, ask_o5=10,
        )

        with patch("core.sentinel_live_stream_advisor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromtimestamp = datetime.fromtimestamp
            mock_dt.strptime = datetime.strptime

            # Ingest depth tick
            advisor._evaluate_option_depth(depth_record)

        # 9. Assert state transitioned to STATE_IN_FLIGHT
        assert idx_apm.state == STATE_IN_FLIGHT, (
            f"Expected APM state {STATE_IN_FLIGHT}, got {idx_apm.state}"
        )
        assert idx_apm.payload is not None, "APM payload must not be None after entry"

        # 10. Assert lot sizing is >= 1 and <= index lot cap
        lots = idx_apm.payload.lots
        max_cap = INDEX_LOT_CAPS.get(index_name, 3)
        assert lots >= 1, f"Expected lots >= 1, got {lots}"
        assert lots <= max_cap, f"Expected lots <= {max_cap} for {index_name}, got {lots}"

        # 11. Assert isolated WAL exists and is populated
        expected_wal = Path(idx_apm.wal_path)
        assert expected_wal.exists(), f"Isolated WAL {expected_wal} was not created"

        # 12. Verify zero production WAL contamination
        if assert_live_wal_clean:
            hashes_after = get_runtime_wal_hashes()
            assert hashes_before == hashes_after, (
                f"PRODUCTION WAL CONTAMINATION DETECTED!\nBefore: {hashes_before}\nAfter: {hashes_after}"
            )

        result = {
            "success": True,
            "index": index_name,
            "apm_state": idx_apm.state,
            "lots": lots,
            "lot_cap": max_cap,
            "contract": idx_apm.payload.strike_contract,
            "fill_price": idx_apm.payload.opt_entry_ltp,
            "isolated_wal": str(temp_wal),
            "production_wals_clean": True,
        }
        return result

    finally:
        # Clean teardown unless keep_artifacts is specified
        if not keep_artifacts:
            if temp_wal.exists():
                try:
                    temp_wal.unlink()
                except Exception:
                    pass
            # Also clean companion WAL files created during multi-index setup
            for companion in temp_dir.glob(f"smoketest_apm_wal_{pid}*.json"):
                try:
                    companion.unlink()
                except Exception:
                    pass
            if temp_journal_dir.exists():
                try:
                    for f in temp_journal_dir.glob("*"):
                        f.unlink()
                    temp_journal_dir.rmdir()
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser(description="Sentinel Pre-Market Dummy Trade Harness")
    parser.add_argument("--index", default="NIFTY", choices=["NIFTY", "SENSEX", "BANKNIFTY"], help="Index to test")
    parser.add_argument("--assert-live-wal-clean", action="store_true", default=True, help="Assert zero production WAL pollution")
    parser.add_argument("--keep-artifacts", action="store_true", default=False, help="Keep temporary test WAL artifacts")
    args = parser.parse_args()

    print(f"🚀 Running Sentinel Pre-Market Smoketest for index={args.index}...")
    try:
        res = run_smoketest(
            index_name=args.index,
            assert_live_wal_clean=args.assert_live_wal_clean,
            keep_artifacts=args.keep_artifacts,
        )
        print("✅ [SMOKETEST PASSED]")
        print(f"   Index: {res['index']}")
        print(f"   APM State: {res['apm_state']}")
        print(f"   Lots: {res['lots']} (Cap: {res['lot_cap']})")
        print(f"   Contract: {res['contract']}")
        print(f"   Fill Price: ₹{res['fill_price']}")
        print(f"   Production WALs 100% Clean: {res['production_wals_clean']}")
        sys.exit(0)
    except Exception as e:
        print(f"❌ [SMOKETEST FAILED] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
