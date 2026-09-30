# Broker Write Guard Module Identity — Hermes Stage 1

**Date:** 2026-09-30
**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`
**Status:** Scoped offline repair contract; no broker or order authority.

## Source-agent task contract

```text
source_agent: hermes
action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
title: Bind broker write guards to the module object callers actually import
scope: Prevent stale parent-package attributes from causing guard installation on a different ExecutionEngine class than the one in sys.modules.
requested_paths: core/trade_truth/prospective_capture_engine.py; tests/test_trade_truth_prospective_repair.py
allowed_paths: core/trade_truth/prospective_capture_engine.py; tests/test_trade_truth_prospective_repair.py; this design/verification evidence
forbidden_paths: core/execution_engine.py; core/broker/**; core/order/**; credentials; environment files; live runtime; broker APIs; order actions; strategy thresholds
expected_tests: Reproduce stale core.execution_engine package attribute; verify the active sys.modules class receives the security spy; verify one observed blocked call and restoration; run the full offline suite.
acceptance_proof: The current imported class raises SECURITY BREACH before original place_order execution; CALL_COUNTS increments once; stale class remains untouched; no broker or order call occurs; focused and full suites pass.
```

## Forensic basis

The completed whole-repository run had one aggregate-only failure in `test_broker_write_guards_active`: the test received a `TypeError` from the original keyword-only `ExecutionEngine.place_order`, indicating that the guard spy had been attached to a different class object. A controlled offline reproduction created two module objects for `core.execution_engine`, left the parent package attribute pointing to the stale object, and restored the active module object in `sys.modules`. The old installer patched the stale class while callers resolved the active class.

## Contract and design

- Resolve `core.execution_engine`, `core.broker.mock_broker`, and `core.kite_client` through `importlib.import_module` and install guards on the class object returned by that import.
- Preserve existing guard functions, counters, exception text, reset semantics, and candidate/read-only behavior.
- The spy must raise before the original write method is entered. This is test instrumentation; it does not authorize, simulate, or call a broker.
- A stale parent-package attribute must not receive the guard or determine which class is protected.
- Preserve the current exception handling around unavailable optional boundary imports; this repair does not claim to solve absent-boundary policy.

## Acceptance gates

1. Test with `core.execution_engine` package attribute deliberately bound to a different stale class while `sys.modules` contains the active module.
2. Assert a call through the active class reaches the guard and raises `RuntimeError("SECURITY BREACH: ...")` before the original keyword-only method.
3. Assert exactly one execution-engine boundary count and no change to the stale class.
4. Reset guards in `finally`; verify no spy leaks beyond the test.
5. Run focused guard/observer/torture/data tests, then the full offline repository suite.
6. Preserve `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, and `append=false`.

## Risks and limits

This fix addresses module-object identity only. Existing broad exception handling for unavailable boundary imports remains and must not be reported as a general fail-closed import guarantee. The full suite and synthetic tests provide offline code evidence, not production behavior or live readiness.
