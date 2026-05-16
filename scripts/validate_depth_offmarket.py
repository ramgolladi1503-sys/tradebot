#!/usr/bin/env python3
"""Off-market depth subscription sanity checks.

This script is intentionally read-only. It does not start websocket feeds, place
orders, mutate broker state, or relax execution gates.

It verifies that the depth subscription rewrite is the final owner of the public
functions that matter after sitecustomize and compatibility hooks load.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from typing import Callable

EXPECTED_MODULE = "core.depth_subscription_engine"
TARGETS = (
    "build_subscription_tokens",
    "build_depth_subscription_tokens",
    "_prune_stale_option_subscription_tokens",
    "_maybe_refresh_stale_option_subscription_universe",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _result(name: str, ok: bool, detail: str) -> CheckResult:
    return CheckResult(name=name, ok=ok, detail=detail)


def check_import() -> list[CheckResult]:
    try:
        importlib.import_module("core.kite_depth_ws")
        importlib.import_module("core.depth_subscription_engine")
        return [_result("imports", True, "core.kite_depth_ws and core.depth_subscription_engine imported")]
    except Exception as exc:  # pragma: no cover - diagnostic path
        return [_result("imports", False, f"import failed: {type(exc).__name__}: {exc}")]


def check_function_ownership() -> list[CheckResult]:
    import core.kite_depth_ws as ws

    results: list[CheckResult] = []
    for name in TARGETS:
        fn = getattr(ws, name, None)
        module = getattr(fn, "__module__", None)
        ok = callable(fn) and module == EXPECTED_MODULE
        results.append(
            _result(
                f"owner:{name}",
                ok,
                f"module={module!r}; expected={EXPECTED_MODULE!r}",
            )
        )
    return results


def check_no_ci_depth_owner() -> list[CheckResult]:
    import core.kite_depth_ws as ws

    results: list[CheckResult] = []
    for name in TARGETS:
        fn = getattr(ws, name, None)
        module = str(getattr(fn, "__module__", "") or "")
        ok = not module.startswith("core.ci_")
        results.append(_result(f"not_ci_owner:{name}", ok, f"module={module!r}"))
    return results


def run_checks() -> list[CheckResult]:
    checks: tuple[Callable[[], list[CheckResult]], ...] = (
        check_import,
        check_function_ownership,
        check_no_ci_depth_owner,
    )
    results: list[CheckResult] = []
    for check in checks:
        results.extend(check())
    return results


def main() -> int:
    results = run_checks()
    failed = [item for item in results if not item.ok]

    print("Depth off-market validation")
    print("=" * 32)
    for item in results:
        status = "PASS" if item.ok else "FAIL"
        print(f"[{status}] {item.name}: {item.detail}")

    print("=" * 32)
    if failed:
        print(f"FAILED: {len(failed)} check(s) failed")
        return 1
    print("PASSED: depth ownership checks are clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
