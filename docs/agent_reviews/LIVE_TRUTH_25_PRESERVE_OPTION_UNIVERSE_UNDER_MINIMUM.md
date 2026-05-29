# LIVE-TRUTH-25 — Preserve Option Universe Under Minimum (Agent Review Evidence)

mode: DEV
candidate_id: N/A
decision: preserve_option_universe_under_minimum
reason: keep_under_min_option_universe_and_fail_closed_until_fresh_option_ticks
timestamp: 2026-05-29T15:00:00+0530
is_order_action: false
broker_api_called: false
source: agent_review

## Agent Work Contract

- source_agent: Codex (GPT-5.2)
- action: Implement scoped feed-safety + deterministic tests
- title: LIVE-TRUTH-25 — Preserve Option Universe Under Minimum
- scope: Preserve nonzero under-min option universes, mark degraded coverage, and keep execution blocked until fresh option ticks clear blockers
- requested_paths:
  - core/kite_depth_ws.py
  - core/depth_subscription_engine.py
  - tests/test_depth_subscription_tokens.py
- allowed_paths:
  - core/kite_depth_ws.py
  - core/depth_subscription_engine.py
  - tests/test_depth_subscription_tokens.py
  - docs/agent_reviews/LIVE_TRUTH_25_PRESERVE_OPTION_UNIVERSE_UNDER_MINIMUM.md
- forbidden_paths:
  - core/order*
  - core/broker*
  - core/execution*
  - core/risk*
  - strategies/
  - config/
- expected_tests:
  - tests/test_depth_subscription_tokens.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
- acceptance_proof:
  - Under-min nonzero option tokens are preserved and subscribed
  - Zero-token state is hard blocked and non-tradable
  - Degraded coverage remains blocked until fresh option tick proof clears `NO_LIVE_OPTION_FEED`

## Scope Guard

- Verdict: PASS
- Candidate ranking/scoring: Not touched
- Broker calls: Not added
- Live orders: Not added
- Execution behavior: Not changed (only feed subscription/token metadata + existing blockers)
- UI/Dashboard: Not touched

## Grill Me Review

- Verdict: PASS
- Primary risk: accidentally allowing LIVE execution with partial/zero option feed
- Mitigation: preserve nonzero tokens but keep runtime blocked by existing `NO_LIVE_OPTION_FEED` until fresh option ticks arrive; zero-token state remains blocked
- Non-goals enforced: no broker/order wiring, no ranking changes, no strategy threshold changes

## Hermes Review

- Verdict: PASS
- Design: represent option universe coverage explicitly (`FULL` / `DEGRADED` / `ZERO`) and never discard a nonzero under-min universe
- Observability: write coverage status + reason into per-symbol subscription resolution rows (via existing resolution log contracts)
- Fail-closed: execution stays blocked until tick proof clears feed blockers

## GSD Review

- Verdict: PASS
- Implementation:
  - Stop discarding option tokens for `option_tokens_under_min` when the set is nonzero
  - Add explicit `option_tokens_zero` reason for true zero-token resolution
  - Attach `option_coverage_status` + `option_coverage_reason` to resolution metadata
  - Keep behavior consistent for both the legacy module implementation and the installed depth-subscription engine implementation

## QA / Safety Review

- Verdict: PASS
- Determinism: tests use explicit token sets and explicit tick timestamps; no network/broker calls
- Safety gates: relies on existing blocker lifecycle (`NO_LIVE_OPTION_FEED`) to block execution until a fresh option tick clears the blocker
- Regression surface: limited to option subscription token selection metadata and under-min handling

## High-Risk Path Review

- Changed high-risk file: core/kite_depth_ws.py (feed/WebSocket)
- Review focus:
  - Under-min nonzero option universe is preserved (no silent deletion)
  - Zero-token universe remains non-tradable (blocked)
  - Existing blocker semantics remain authoritative for LIVE readiness

## Acceptance Proof

- Under-min nonzero: `option_coverage_status=DEGRADED`, `final_option_count` equals the resolved subset (no forced drop-to-zero)
- Zero coverage: `option_coverage_status=ZERO`, `final_option_count=0`, subscription contains only underlyings
- Tick-proof gate: without option ticks the symbol remains blocked (`NO_LIVE_OPTION_FEED`); with a fresh tick the blocker clears

## Runtime Proof Required After Merge

- During a live-session dry observation (no orders), confirm `logs/token_resolution.json` includes:
  - `option_coverage_status`, `option_coverage_reason`, `resolved_option_count`, `final_option_count`, `option_min_required`, `option_fail_reason`
- Confirm runtime snapshot continues to show `NO_LIVE_OPTION_FEED` until fresh option ticks arrive for target symbols.

## What This PR Does Not Prove

- It does not prove market profitability, strategy quality, or ranking quality.
- It does not prove broker connectivity, order routing, fills, or execution correctness.
- It does not prove that an under-min universe is sufficient for every strategy; it only prevents self-starvation and preserves fail-closed execution gating.

## Human Approval

- Required: YES (mission-critical feed behavior change)
- Reviewer checklist:
  - Confirm degraded coverage is visible in `token_resolution.json`
  - Confirm no order/broker code paths changed
  - Confirm `NO_LIVE_OPTION_FEED` blocks execution until fresh tick proof
