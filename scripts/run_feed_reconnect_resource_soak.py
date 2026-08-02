#!/usr/bin/env python3
"""Deterministic entrypoint for the feed reconnect resource-soak harness.

The implementation remains in ``run_feed_reconnect_resource_soak_impl``.  This
entrypoint keeps warm-up outside the measured recovery lifecycle: warm-up may
initialize stores, logging and one connected dummy websocket, but it must not
inject an unowned 1006 recovery immediately before cycle zero.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import run_feed_reconnect_resource_soak_impl as impl


def _normalized_counter(values) -> Counter:
    return Counter(impl._normalize_tokens(values))


class ResourceSoakRunner(impl.ResourceSoakRunner):
    """Resource-soak runner with a clean baseline and predicate diagnostics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_cycle_condition_snapshot: dict = {}

    def _do_warmup(self):
        process_start = impl._resource_snapshot()

        try:
            import core.feed.runtime_store as runtime_store

            with runtime_store._conn() as conn:
                conn.execute("SELECT 1").fetchall()
        except Exception:
            pass

        # Initialize the same logger/runtime/socket resources used by measured
        # cycles, but do not create an unmeasured recovery owner.  Recovery is
        # exercised only inside _run_reconnect_cycle(), where it is counted and
        # verified.
        try:
            impl.ws._log_ws(
                "SOAK_WARMUP_INITIALIZED",
                {"profile": self.profile, "token_count": len(self.tokens)},
            )
        except Exception:
            pass

        impl.ws._FEED_RECOVERY_COORDINATOR.reset()
        impl.ws._sync_ws1006_recovery_state_from_coordinator()
        setattr(impl.ws, "_STOP_REQUESTED", False)
        setattr(impl.ws, "_LAST_RUNTIME_ERROR", None)

        impl.ws.start_depth_ws(self.tokens, skip_lock=True, skip_guard=True)
        time.sleep(0.1)

        try:
            impl.ws.feed_restart_guard.reset(reason="soak_warmup_baseline")
        except Exception:
            pass

        post_warmup = impl._resource_snapshot()
        self.timeline.append({"stage": "process_start_baseline", "snapshot": process_start})
        self.timeline.append({"stage": "post_warmup_baseline", "snapshot": post_warmup})
        return post_warmup

    def _cycle_condition_snapshot(self, old_generation_id: int) -> dict:
        ticker = getattr(impl.ws, "_KITE_TICKER", None)
        recovery_state = getattr(impl.ws._FEED_RECOVERY_COORDINATOR, "state", None)
        current_generation_id = (
            getattr(ticker, "generation_id", id(ticker)) if ticker is not None else None
        )
        expected = _normalized_counter(getattr(impl.ws, "_LAST_TOKENS", []))
        actual = _normalized_counter(getattr(ticker, "tokens", [])) if ticker else Counter()
        snapshot = {
            "old_generation_id": old_generation_id,
            "current_generation_id": current_generation_id,
            "generation_advanced": bool(
                current_generation_id is not None and current_generation_id != old_generation_id
            ),
            "ticker_present": ticker is not None,
            "ticker_connected": bool(getattr(ticker, "connected", False)) if ticker else False,
            "terminal_failure": bool(getattr(recovery_state, "terminal_failure", False)),
            "process_restart_required": bool(
                getattr(recovery_state, "process_restart_required", False)
            ),
            "recovery_blocked": bool(getattr(recovery_state, "recovery_blocked", False)),
            "recovery_in_progress": bool(
                getattr(recovery_state, "recovery_in_progress", False)
            ),
            "module_recovery_in_progress": bool(
                getattr(impl.ws, "_RECOVERY_IN_PROGRESS", False)
            ),
            "depth_lock_acquired": bool(
                getattr(impl.ws, "_DEPTH_WS_LOCK_ACQUIRED", False)
            ),
            "expected_subscriptions": sorted(expected.elements()),
            "actual_subscriptions": sorted(actual.elements()),
            "subscriptions_match_exactly": expected == actual,
            "runtime_state": getattr(impl.ws, "_RUNTIME_STATE", None),
            "last_runtime_error": getattr(impl.ws, "_LAST_RUNTIME_ERROR", None),
        }
        self.last_cycle_condition_snapshot = snapshot
        return snapshot

    def _cycle_success_conditions_met(self, old_generation_id: int):
        snapshot = self._cycle_condition_snapshot(old_generation_id)
        ticker = getattr(impl.ws, "_KITE_TICKER", None)
        current_generation_id = snapshot["current_generation_id"]
        success = all(
            (
                snapshot["generation_advanced"],
                snapshot["ticker_connected"],
                not snapshot["terminal_failure"],
                not snapshot["process_restart_required"],
                not snapshot["recovery_blocked"],
                not snapshot["depth_lock_acquired"],
                snapshot["subscriptions_match_exactly"],
            )
        )
        return success, ticker, current_generation_id

    def run(self):
        result = super().run()
        result["last_cycle_condition_snapshot"] = dict(self.last_cycle_condition_snapshot)
        return result


determine_exit_code = impl.determine_exit_code
patch_kite = impl.patch_kite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        required=True,
        choices=[
            "control",
            "100_cycles",
            "1000_cycles",
            "reconnect",
            "reconnect_guarded",
            "reconnect_unbounded_resource_stress",
            "owner_failure",
            "negative_control",
            "negative_fd_leak",
            "sqlite_same_path_multi_descriptor_negative",
        ],
    )
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--required-token-count", type=int, default=150)
    parser.add_argument("--reconnect-failure-every", type=int, default=0)
    parser.add_argument("--sample-every", type=int, default=10)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    runner = ResourceSoakRunner(
        profile=args.profile,
        cycles=args.cycles,
        req_tokens=args.required_token_count,
        output_path=args.output_json,
        seed=args.seed,
        fail_every=args.reconnect_failure_every,
        sample_every=args.sample_every,
    )
    result = runner.run()

    with open(args.output_json, "w") as handle:
        json.dump(result, handle, indent=2)

    fd_leak = result["final"]["fd_count"] - result["post_warmup_baseline"]["fd_count"]
    thread_leak = (
        result["final"]["python_thread_count"]
        - result["post_warmup_baseline"]["python_thread_count"]
    )
    print(
        f"[{result['configuration']['profile']}] Cycles: {args.cycles}, "
        f"FD Leak vs Warmup: {fd_leak}, Thread Leak: {thread_leak}, "
        f"Verdict: {result['verdict']}"
    )
    sys.exit(determine_exit_code(result, args.profile))


if __name__ == "__main__":
    main()
