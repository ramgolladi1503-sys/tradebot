# EDGE-81 — NoTrade Evidence in Review Queue/UI

## Purpose

EDGE-81 surfaces EDGE-80 NoTradeOracle evidence as read-only review queue/UI rows.

The goal is to make no-trade decisions explainable in the operator surface without creating a new execution path.

## What changed

Added `dashboard/ui/no_trade_evidence.py` with:

- `build_no_trade_review_rows(...)`
- `build_no_trade_review_table_payload(...)`
- `NO_TRADE_REVIEW_SOURCE`

The adapter accepts already computed oracle reports or payloads and shapes them into plain dictionaries that dashboard/review table code can display.

## Evidence surfaced

Each row can expose:

- no-trade status
- primary reason
- primary category
- primary message
- reason count
- blocker list
- evidence source list
- warning list
- reason summary
- generated timestamp
- read-only / no-append markers
- non-action metadata

## Scope guard

This PR does not:

- change the NoTradeOracle contract
- recompute strategy edge
- rank candidates
- score opportunities
- submit orders
- create order intent
- call external execution APIs
- mutate runtime evidence
- append files
- add dashboard action buttons
- add broker or execution imports

## Why this matters

Before EDGE-81, the no-trade explanation existed as an oracle report but was not shaped for operator review.

EDGE-81 gives the UI a stable read model so the operator can see why the bot is blocked without mistaking no-trade evidence for an executable candidate.

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_81_no_trade_evidence_review_ui.py`

## Acceptance proof

Tests prove that:

- primary no-trade reason is surfaced
- evidence sources and blockers are preserved
- payload remains read-only
- no append behavior is introduced
- non-action metadata remains false
- JSON oracle payloads can be rendered without runtime coupling
- rows can be consumed by the existing review table model
- malformed payloads are ignored safely

## Next PR

EDGE-82 — Final Executable Trade Quality Gate.

EDGE-82 must not use UI visibility as proof of executable quality. It needs a separate final quality gate with evidence-backed tests.
