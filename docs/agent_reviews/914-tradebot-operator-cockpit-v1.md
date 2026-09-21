# TradeBot Operator Cockpit V1 with Isolated Upstox Option Chain

mode: SIM
candidate_id: 914-tradebot-operator-cockpit-v1
decision: integrate_operator_cockpit_v1_onto_main
reason: Rebase and cleanly integrate the high-density Operator Cockpit V1 and read-only Upstox option chain reader onto current main.
timestamp: 2026-09-21T22:33:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/914-tradebot-operator-cockpit-v1.md

## Agent Work Contract

PR #914 integration onto `main`. Adds `dashboard/operator_cockpit.py`, `dashboard/operator_truth.py`, `dashboard/upstox_option_chain_reader.py`, `core/upstox_ui_snapshot.py`, `scripts/upstox_option_chain_ui_sidecar.py`, `docs/ui/operator_cockpit_v1.md`, `tests/test_operator_cockpit_truth.py`, `tests/test_upstox_option_chain_reader.py`, and this review evidence file.

## Scope Guard

In scope:
- `core/upstox_ui_snapshot.py`
- `dashboard/operator_cockpit.py`
- `dashboard/operator_truth.py`
- `dashboard/upstox_option_chain_reader.py`
- `docs/ui/operator_cockpit_v1.md`
- `scripts/upstox_option_chain_ui_sidecar.py`
- `tests/test_operator_cockpit_truth.py`
- `tests/test_upstox_option_chain_reader.py`
- `docs/agent_reviews/914-tradebot-operator-cockpit-v1.md`

Out of scope:
- Live broker order routing, account trading execution, strategy threshold modifications, risk gate weakening, production kill switches, credential files, or live mode modifications.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- Replaces legacy console model with a high-density operator cockpit without altering any live runtime or trading pathways.
- Strict isolation: Operational Kite runtime and Upstox capture path remain completely decoupled. No synthetic price averaging, no cross-feed failover.
- Read-only guarantee: `broker_write_authority=false`, `order_authority=false`. The UI has zero mechanism to place, modify, or cancel orders.
- Secret safety: Streamlit never receives or displays broker tokens. The Upstox sidecar reads server-side environment variables and publishes local JSON snapshots atomically.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- Single-viewport Operator Cockpit with high-density market cards, Altair price curves with baseline preservation, market state regime levels, pipeline pulse, top opportunities, and candidate funnel.
- Fail-closed truth adapters: Missing, malformed, or stale data fails closed to `UNKNOWN` / `INACTIVE` / `STALE` instead of hiding failure states.
- Clean contract separation: Upstox option-chain drawer uses atomic snapshot reader decoupled from the Kite ticker.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- Rebased cleanly on top of `main` (commit `e16028e94`).
- All tests passing: 6/6 cockpit truth and Upstox reader tests, 32/32 existing Streamlit regression tests.
- Whole-tree compilation clean (`python -m py_compile`).

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Verification Evidence:
- `tests/test_operator_cockpit_truth.py`: PASS (3/3)
- `tests/test_upstox_option_chain_reader.py`: PASS (3/3)
- `tests/test_streamlit*.py`, `tests/test_edge53*.py`: PASS (32/32)
- Zero order authority. Zero broker writes. Read-only observation verified.
