# Pro Strategy Layer Shadow Wire-In Design

> **For agentic workers:** This design is for an isolated hardening branch only. Do not touch `main`. The shadow wire-in must remain observational until the offline bar is met and the branch is explicitly approved for promotion.

**Goal:** Add a shadow-only orchestrator attachment for the pro strategy layer so we can observe candidate quality, suppression behavior, and ranking stability without changing live execution behavior.

**Architecture:** Keep the pro strategy layer behind a dedicated shadow flag and attach it only from the orchestrator cycle. The shadow hook consumes the same cycle snapshot the live pipeline already sees, runs the pro evaluation path, and emits telemetry about candidate count, suppression rate, and error state. It must never mutate the legacy trade builder, candidate pool, or execution routing. Live behavior remains unchanged unless a later promotion design explicitly wires the pro layer into the candidate path.

**Tech Stack:** Python, `pytest`, `core.orchestrator`, `core.pro_strategy_pipeline`, `core.decision_engine`, existing logging and status writers.

---

## Scope

This design covers a shadow-only attachment for the pro strategy layer.

In scope:
- orchestrator-side shadow evaluation hook
- separate feature flag for shadow observation
- telemetry for enabled state, candidate count, suppression, and errors
- regression checks that live behavior remains unchanged

Out of scope for this phase:
- influencing trade selection
- mutating legacy candidates
- changing live execution routing
- enabling the pro pipeline in production flow

## Design Principles

- Fail closed: if the shadow hook fails, the orchestrator continues exactly as before.
- Observational only: the shadow layer reads data and records telemetry, but never affects decisions.
- Default off: the new shadow path is disabled unless explicitly enabled.
- Backward compatible: current orchestrator and status file behavior must remain valid.
- Minimal surface area: the shadow hook should mirror the existing `v2` shadow pipeline pattern and nothing more.

## Proposed Flow

1. The orchestrator cycle builds the normal market snapshot.
2. If the new shadow flag is enabled, the orchestrator calls the pro shadow pipeline with the cycle snapshot.
3. The shadow pipeline evaluates the pro strategies and produces a structured report.
4. The orchestrator logs the report or summary, but does not pass the pro results into live trade selection.
5. If the shadow pipeline raises, the orchestrator logs the exception and continues with the normal cycle.

## Shadow Report Contract

The pro shadow pipeline should return a structured payload that is easy to audit:

- `enabled`: whether the shadow path was active
- `flags`: the relevant pro flags in effect
- `candidates`: the ranked pro decisions produced for the cycle
- `errors`: non-fatal evaluation errors, if any

For branch safety, the shadow report should not alter any live-side state. It is for telemetry, validation, and later promotion review only.

## Flag Design

Use two distinct flags:

- `ENABLE_PRO_STRATEGY_LAYER`: existing pro pipeline enable flag, remains `false` by default
- `ENABLE_PRO_STRATEGY_SHADOW`: new shadow-only flag, also `false` by default

Reasoning:
- The pipeline enable flag is reserved for later promotion work.
- The shadow flag allows observability without changing current behavior.
- Keeping the flags separate prevents accidental interpretation of the shadow hook as a live activation path.

## Telemetry

The shadow attachment should emit enough information to answer:

- Did the shadow hook run?
- How many pro candidates survived the layer?
- Did the layer suppress weak or conflicted signals?
- Did the pro pipeline fail on this cycle?
- Was the shadow path enabled or disabled?

Telemetry should remain additive and backward compatible. The shadow hook should not change existing status file meanings or live execution decisions.

## Safety and Failure Handling

- If the pro shadow pipeline throws, the orchestrator logs the failure and continues.
- If the shadow report is empty, that is valid and should be recorded as such.
- If the shadow flag is disabled, the orchestrator should not pay the cost of evaluating the pro layer.
- The live pipeline must not import or depend on shadow-only telemetry structures.

## Validation Plan

The design is considered acceptable only if the following checks pass:

- shadow hook disabled by default
- shadow hook returns a report when enabled
- report generation does not alter live decisions
- orchestrator cycle error reporting still writes `suggestions_status.json` correctly
- existing pro strategy and replay tests remain green
- branch-level regression slices for restart and websocket behavior remain green

## Rollout Plan

1. Add the shadow-only pro pipeline hook in the orchestrator.
2. Add a disabled-by-default shadow flag.
3. Add tests proving the hook does not affect live behavior.
4. Re-run branch-level validation.
5. Only after the branch is consistently green, consider a later promotion design for candidate-path attachment.

## Risks

- Shadow telemetry can become noisy if the pro layer is too chatty.
- If the orchestrator hook is placed in the wrong stage, it could accidentally slow the cycle.
- If the shadow and live flags are confused, the branch could be misread as production-ready when it is still observational.

