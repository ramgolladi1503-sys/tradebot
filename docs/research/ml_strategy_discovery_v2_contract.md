# ML Strategy Discovery V2 — Stability-First Research Contract

## Frozen V1 state

- V1 audit verdict: `BOTH_CANDIDATES_UNSTABLE`.
- V1 LONG candidate: `tree_rule_edb855245d2f`; retained only as historical evidence.
- V1 SHORT candidate: `tree_rule_7a6855962eee`; rejected.
- `VALIDATION_V1_CONSUMED` is permanently unavailable for V2 selection, ranking, thresholds, feature choice, or model choice.
- `HOLDOUT_V1_LOCKED` remains untouched.
- Sessions from 2026-07-11 through 2026-07-21 were previously exposed by the prototype and are classified `FRESH_CONFIRMATION_V2_CONSUMED_INVALID`.

## Revoked prototype result

The PR #688 prototype LONG candidate is revoked:

- candidate ID: `2256874b-1408-4e25-8b76-e9d2347703f2`
- reported bundle hash: `b6bfd5b4ce7d87e91b36928070cf0b34d3716633d9a6773f5bacaf6b78e1f704`
- status: `REVOKED_UNTRUSTED_PROTOTYPE_OUTPUT`

It was produced by placeholder provenance hashes, simulated multiple-testing statistics, simulated controls, non-deterministic candidate identity, and tests containing non-behavioral assertions. It is not eligible for confirmation, option replay, integration, or further interpretation.

## Development-only source boundary

The parent source manifest may be read as metadata. Before any parquet is opened, records are filtered by the committed partition registry and a child `DEVELOPMENT_V1` selection manifest is created. Only files in that child manifest may be reopened for feature and label generation.

The source contract requires manifest and sidecar presence, exact sidecar filename and SHA-256, deterministic record order, safe logical paths, unique identities, source-byte verification, V1 complete-session checks, and explicit exclusion of non-standard sessions without padding or synthesis.

## Stability-first discovery

Each side is run explicitly and independently. There is no default side. The development screen uses causal feature allowlisting, development-fitted median imputation, deterministic shallow trees, exact readable-rule reproduction, anchored nested whole-session folds, structural recurrence, support/base-rate/concentration/bootstrap gates, real session-aware multiple-testing correction, real negative controls, and deterministic candidate bundles.

This is a development research screen, not certifying WFA or profitability.

## Confirmation boundary

This PR does not evaluate confirmation outcomes and issues no confirmation token. The current confirmation status is `NEED_NEW_FRESH_CONFIRMATION_DATA`.

Any later token must be persisted and bound to the candidate bundle hash, new fresh-manifest hash, code SHA, side, and one-time evaluation ID. Token replay fails closed.

## Safety boundary

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `append=false`

`NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`
