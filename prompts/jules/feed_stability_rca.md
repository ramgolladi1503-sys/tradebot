You are working on my Tradebot repository.

Goal:
Perform an evidence-backed RCA explaining why the live feed module is not stable enough.

Target SLO:
Feed must remain HEALTHY or RECOVERABLE for at least 5 cumulative hours inside a 6-hour Indian market window, without lying about websocket health, tick freshness, depth freshness, option tick validity, feed recovery state, or candidate readiness.

This is an RCA-only task. Do not edit files.

Hard safety rules:
- Do not enable live orders.
- Do not enable auto-trading.
- Do not bypass manual approval.
- Do not weaken stale feed guards.
- Do not weaken risk gates.
- Do not fake healthy feed state by increasing thresholds without evidence.
- Do not touch credentials, broker auth, .env files, Kite tokens, or session files.
- Do not create fake candidates by bypassing feed validation.

Audit requirement:
Inspect feed-related code line by line and produce a coverage table.

Minimum files/modules to inspect:
- core/feed_runtime.py
- core/feed_recovery_runtime.py
- core/feed_recovery_coordinator.py
- core/feed_health_truth.py
- core/kite_depth_ws.py
- core/engine_phase2_adapter.py
- core/orchestrator.py
- core/runtime_health.py
- core/feed_debug.py
- core/feed_execution_truth.py
- strategies/trade_builder.py
- tests related to feed runtime, websocket, stale state, quote truth, option tick verification, feed recovery, candidate rejection, and no-trade evidence.

Run these first:
git status -sb
git branch --show-current
git diff --stat
git diff --check
find core strategies tests scripts -type f | sort
grep -R "feed\|depth\|websocket\|ws\|stale\|fresh\|tick\|quote\|option_tick\|ltp\|recovery\|fatal\|healthy\|degraded" -n core strategies tests scripts || true

RCA questions:
1. What exactly makes feed unstable?
2. Is the instability caused by real websocket failure, stale classification, bad state propagation, bad recovery logic, lock handling, market-session logic, or candidate pipeline misreading feed state?
3. What is the dominant root cause?
4. What are secondary contributors?
5. Where does feed health become inconsistent with actual tick/depth truth?
6. Where can the system falsely claim healthy?
7. Where can the system falsely claim fatal/stale while recovery is still possible?
8. What exact code changes would improve stability without weakening safety?
9. What tests must be added?
10. How should we measure the 5-hour / 6-hour feed SLO?

For every finding include:
- file path
- function/class name
- current behavior
- failure mode
- runtime symptom
- evidence
- proposed modification
- safety impact
- test required
- expected improvement

Final output format:
1. Branch/base inspected
2. Files inspected
3. Feed lifecycle map
4. File coverage table
5. RCA findings table
6. Dominant root cause
7. Secondary contributors
8. Proposed patch plan split into small commits
9. Tests to add
10. Live-soak validation plan
11. Acceptance criteria for 5 healthy hours in a 6-hour window
12. Risks if the fix is wrong

Do not write code in this session.
