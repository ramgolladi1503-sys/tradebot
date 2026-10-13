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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import run_feed_reconnect_resource_soak_impl as impl


def _normalized_counter(values) -> Counter:
    return Counter(impl._normalize_tokens(values))


def _failure_diagnostic(
    runner: "ResourceSoakRunner",
    args: argparse.Namespace,
    *,
    result: dict | None = None,
    exc: BaseException | None = None,
) -> dict:
    result = result or {}
    final = result.get("final") or {}
    baseline = result.get("post_warmup_baseline") or {}
    resource_delta = {
        "fd_count": final.get("fd_count", 0) - baseline.get("fd_count", 0)
        if final and baseline
        else None,
        "python_thread_count": final.get("python_thread_count", 0)
        - baseline.get("python_thread_count", 0)
        if final and baseline
        else None,
    }
    return {
        "event": "SOAK_RUN_FAILURE",
        "profile": args.profile,
        "cycles": args.cycles,
        "exception_type": type(exc).__name__ if exc is not None else None,
        "exception": str(exc) if exc is not None else None,
        "verdict": result.get("verdict"),
        "failure_counters": result.get("failure_counters"),
        "reconnect_counters": result.get("reconnect_counters"),
        "first_mismatch": result.get("first_mismatch")
        or getattr(runner, "first_mismatch", None),
        "errors": result.get("errors")
        or list(getattr(runner, "errors", []))[-10:],
        "resource_delta": resource_delta,
        "last_cycle_condition_snapshot": dict(
            getattr(runner, "last_cycle_condition_snapshot", {})
        ),
        "timeline_tail": list(getattr(runner, "timeline", []))[-5:],
    }


def _emit_failure_diagnostic(
    runner: "ResourceSoakRunner",
    args: argparse.Namespace,
    *,
    result: dict | None = None,
    exc: BaseException | None = None,
) -> None:
    payload = _failure_diagnostic(runner, args, result=result, exc=exc)
    print(
        "SOAK_FAILURE_DIAGNOSTIC="
        + json.dumps(payload, sort_keys=True, default=str),
        file=sys.stderr,
        flush=True,
    )


class ResourceSoakRunner(impl.ResourceSoakRunner):
    """Resource-soak runner with a clean baseline and predicate diagnostics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requested_token_count = self.req_tokens
        self._original_symbols = list(getattr(impl.cfg, "SYMBOLS", []) or [])
        self._original_underlying_ltp = impl.ws._underlying_ltp
        self._synthetic_resolver_fixture_installed = False
        budget = int(impl.ws._GOVERNED_FEED_SUBSCRIPTION_BUDGET)
        if self.req_tokens > budget:
            self.tokens = self.tokens[:budget]
            self.req_tokens = len(self.tokens)
        self.last_cycle_condition_snapshot: dict = {}

    def _install_synthetic_resolver_fixture(self) -> None:
        """Give reconnect-time production resolution a matching offline master."""
        expiry = date(2026, 12, 31)
        index_token = 256265
        instruments = [
            {
                "instrument_token": index_token,
                "exchange": "NSE",
                "tradingsymbol": "NIFTY 50",
                "name": "NIFTY 50",
                "segment": "INDICES",
                "instrument_type": "INDEX",
            }
        ]
        for index, token in enumerate(self.tokens):
            instruments.append(
                {
                    "instrument_token": int(token),
                    "exchange": "NFO",
                    "tradingsymbol": f"NIFTY{expiry:%y%m%d}{23000 + index // 2 * 50}"
                    f"{'CE' if index % 2 == 0 else 'PE'}",
                    "name": "NIFTY",
                    "segment": "NFO-OPT",
                    "instrument_type": "CE" if index % 2 == 0 else "PE",
                    "expiry": expiry,
                    "strike": 23000 + index // 2 * 50,
                }
            )

        def instruments_for_exchange(exchange=None, force=False):
            _ = force
            if exchange is None:
                return list(instruments)
            exchange_key = str(exchange).upper()
            return [
                row for row in instruments
                if str(row.get("exchange") or "").upper() == exchange_key
            ]

        # The production resolver is intentionally exercised by reconnect and
        # watchdog rebuilds. Keep its instrument/spot inputs deterministic and
        # entirely local to this synthetic soak process.
        impl.cfg.SYMBOLS = ["NIFTY"]
        impl.ws.kite_client.instruments = instruments_for_exchange
        impl.ws.kite_client.next_available_expiry = lambda *args, **kwargs: expiry
        impl.ws._underlying_ltp = lambda *args, **kwargs: (25000.0, "synthetic_soak_fixture")
        self._synthetic_resolver_fixture_installed = True

    def _publish_validated_replay_candidate(self) -> None:
        """Give the synthetic soak socket a production-shaped replay contract."""
        tokens = list(self.tokens)
        option_contracts = {
            int(token): {
                "symbol": "NIFTY",
                "instrument_type": "CE" if index % 2 == 0 else "PE",
                "exchange": "NFO",
                "expiry": "2026-12-31",
                "strike": 25000 + (index // 2) * 50,
            }
            for index, token in enumerate(tokens)
        }
        desired_revision = impl.ws.record_desired_option_contracts(
            option_contracts,
            expected_tokens=tokens,
            source="feed_reconnect_resource_soak_fixture",
        )
        if desired_revision <= 0:
            raise RuntimeError("soak option identity fixture was not recorded")
        configured_budget = int(impl.ws._GOVERNED_FEED_SUBSCRIPTION_BUDGET)
        if len(tokens) > configured_budget:
            raise RuntimeError(
                "soak token count exceeds governed replay-candidate budget"
            )
        impl.ws.record_desired_subscription_candidate(
            tokens,
            option_tokens=tokens,
            configured_budget=configured_budget,
            source="feed_reconnect_resource_soak_fixture",
        )
        validated_tokens, reason = impl.ws._validated_desired_subscription_tokens()
        if validated_tokens != sorted(tokens):
            raise RuntimeError(
                f"soak replay candidate did not validate: {reason}"
            )

    def _do_warmup(self):
        self._install_synthetic_resolver_fixture()
        process_start = impl._resource_snapshot()

        try:
            import core.feed.runtime_store as runtime_store

            with runtime_store._conn() as conn:
                conn.execute("SELECT 1").fetchall()
        except Exception:
            pass

        # Initialize the same logger/runtime/socket resources used by measured
        # cycles, but do not create an unmeasured recovery owner. Recovery is
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

        self._publish_validated_replay_candidate()
        impl.ws.start_depth_ws(self.tokens, skip_lock=True, skip_guard=True)
        time.sleep(0.1)

        try:
            impl.ws.feed_restart_guard.reset(reason="soak_warmup_baseline")
        except Exception:
            pass

        post_warmup = impl._resource_snapshot()
        self.timeline.append(
            {"stage": "process_start_baseline", "snapshot": process_start}
        )
        self.timeline.append(
            {"stage": "post_warmup_baseline", "snapshot": post_warmup}
        )
        return post_warmup

    def _cleanup_runtime(self, reason: str) -> None:
        super()._cleanup_runtime(reason)
        if str(reason) == "shutdown" and self._synthetic_resolver_fixture_installed:
            impl.cfg.SYMBOLS = list(self._original_symbols)
            impl.ws._underlying_ltp = self._original_underlying_ltp
            self._synthetic_resolver_fixture_installed = False
        if str(reason) != "soak_finish":
            return

        # stop_depth_ws() persists its final lifecycle snapshot asynchronously.
        # Resource accounting must wait until that real persistence work has
        # completed; otherwise lsof can observe transient SQLite/WAL/SHM handles
        # and misclassify them as reconnect-correlated FD leaks.
        import core.feed.runtime_store as runtime_store

        persistence_state = runtime_store.shutdown_runtime_persistence(
            deadline_seconds=2.0
        )
        if not persistence_state.get("complete"):
            raise RuntimeError(
                "runtime persistence did not quiesce before resource measurement: "
                f"{persistence_state}"
            )

    def _cycle_condition_snapshot(self, old_generation_id: int) -> dict:
        ticker = getattr(impl.ws, "_KITE_TICKER", None)
        recovery_state = getattr(impl.ws._FEED_RECOVERY_COORDINATOR, "state", None)
        current_generation_id = (
            getattr(ticker, "generation_id", id(ticker)) if ticker is not None else None
        )
        expected = _normalized_counter(getattr(impl.ws, "_LAST_TOKENS", []))
        actual = _normalized_counter(getattr(ticker, "tokens", [])) if ticker else Counter()
        validated_candidate, candidate_reason = (
            impl.ws._validated_desired_subscription_tokens()
        )
        candidate_matches_expected = (
            candidate_reason == "validated_desired_plan"
            and validated_candidate == sorted(expected.elements())
        )
        snapshot = {
            "old_generation_id": old_generation_id,
            "current_generation_id": current_generation_id,
            "generation_advanced": bool(
                current_generation_id is not None
                and current_generation_id != old_generation_id
            ),
            "ticker_present": ticker is not None,
            "ticker_connected": bool(getattr(ticker, "connected", False))
            if ticker
            else False,
            "terminal_failure": bool(
                getattr(recovery_state, "terminal_failure", False)
            ),
            "process_restart_required": bool(
                getattr(recovery_state, "process_restart_required", False)
            ),
            "recovery_blocked": bool(
                getattr(recovery_state, "recovery_blocked", False)
            ),
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
            "replay_candidate_valid": candidate_reason == "validated_desired_plan",
            "replay_candidate_matches_expected": candidate_matches_expected,
            "replay_candidate_reason": candidate_reason,
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
                snapshot["replay_candidate_matches_expected"],
            )
        )
        return success, ticker, current_generation_id

    def run(self):
        result = super().run()
        result["configuration"]["requested_token_count"] = self.requested_token_count
        result["configuration"]["effective_token_count"] = self.req_tokens
        result["last_cycle_condition_snapshot"] = dict(
            self.last_cycle_condition_snapshot
        )
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
    try:
        result = runner.run()
    except BaseException as exc:
        _emit_failure_diagnostic(runner, args, exc=exc)
        raise

    with open(args.output_json, "w") as handle:
        json.dump(result, handle, indent=2)

    fd_leak = (
        result["final"]["fd_count"]
        - result["post_warmup_baseline"]["fd_count"]
    )
    thread_leak = (
        result["final"]["python_thread_count"]
        - result["post_warmup_baseline"]["python_thread_count"]
    )
    print(
        f"[{result['configuration']['profile']}] Cycles: {args.cycles}, "
        f"FD Leak vs Warmup: {fd_leak}, Thread Leak: {thread_leak}, "
        f"Verdict: {result['verdict']}"
    )
    exit_code = determine_exit_code(result, args.profile)
    if exit_code:
        _emit_failure_diagnostic(runner, args, result=result)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
