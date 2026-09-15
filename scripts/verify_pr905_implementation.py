#!/usr/bin/env python3
"""Compatibility entrypoint for the independent primitive PR #905 verifier.

The verifier's own deterministic replay is guarded by the same read-only
broker boundary used by prospective proof generation. A verifier must never
create execution authority merely by replaying TradeBuilder.
"""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.execution_router import ExecutionRouter  # noqa: E402
from core.trade_truth.prospective_capture_engine import (  # noqa: E402
    CALL_COUNTS,
    arm_broker_write_guards,
    reset_broker_write_guards,
)
from pr905_verifier_v2 import main, verify_pr905_codebase, verify_pr905_evidence  # noqa: E402,F401


def guarded_main() -> int:
    reset_broker_write_guards()
    arm_broker_write_guards()
    original_execute = ExecutionRouter.execute
    router_calls = [0]

    def _guard_execution_router(self, *args, **kwargs):
        router_calls[0] += 1
        raise RuntimeError("EXECUTION_ROUTER_CALLED_DURING_PR905_VERIFIER_REPLAY")

    ExecutionRouter.execute = _guard_execution_router
    try:
        try:
            rc = int(main())
        except Exception as exc:
            print(f"PR905_VERIFIER_RUNTIME_ERROR:{type(exc).__name__}:{exc}", file=sys.stderr)
            return 1
        if router_calls[0] != 0:
            print(f"PR905_VERIFIER_EXECUTION_ROUTER_CALLS={router_calls[0]}", file=sys.stderr)
            return 1
        observed_writes = sum(int(v) for v in CALL_COUNTS.values())
        if observed_writes != 0:
            print(f"PR905_VERIFIER_BROKER_WRITE_CALLS={observed_writes}", file=sys.stderr)
            return 1
        return rc
    finally:
        ExecutionRouter.execute = original_execute


if __name__ == "__main__":
    raise SystemExit(guarded_main())
