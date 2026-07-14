# Tradebot Observability Event Schema

Status: PR-OBS-02 contract  
Scope: schema-only; no runtime wiring

---

## Purpose

This document defines the structured event contract used by the Tradebot Observability Spine.

The schema exists so future logging, tracing, metrics, and evidence writers use one consistent decision-event shape instead of inventing fields independently.

This PR does not wire events into runtime flow. It only defines and tests the event schema.

---

## Required fields

Every serialized observability event must include:

```text
event
run_id
cycle_id
trace_id
stage
decision
timestamp
i-s_order_action
b-roker_api_called
source
```

Candidate events must also include:

```text
candidate_id
```

Blocked, downgraded, rejected, suppressed, or ignored events must include:

```text
reason
```

---

## Safety fields

Observability events are read-only. They must never become order actions.

Required safety values:

```text
is_order_action: false
broker_api_called: false
```

If either field is true, schema validation must fail.

---

## Example runtime event

```json
{
  "event": "runtime.cycle.started",
  "run_id": "run_tradebot_20260523t034501z",
  "cycle_id": "cycle_run_tradebot_20260523t034501z_000001_20260523t034501z",
  "trace_id": "trace_runtime_cycle_ab12cd34ef56",
  "stage": "runtime.cycle",
  "decision": "started",
  "timestamp": "2026-05-23T03:45:01Z",
  "is_order_action": false,
  "broker_api_called": false,
  "source": "tradebot.observability.events",
  "execution_mode": "PAPER"
}
```

---

## Example candidate event

```json
{
  "event": "candidate.blocked",
  "run_id": "run_tradebot_20260523t034501z",
  "cycle_id": "cycle_run_tradebot_20260523t034501z_000001_20260523t034501z",
  "trace_id": "trace_candidate_72cd8b681f3a",
  "candidate_id": "candidate_nifty_ce_22500_buy_opening_drive_5a1e9c043b2d",
  "stage": "risk.evaluate",
  "decision": "blocked",
  "reason": "FALLBACK_NOT_EXECUTABLE",
  "timestamp": "2026-05-23T03:45:02Z",
  "is_order_action": false,
  "broker_api_called": false,
  "source": "tradebot.observability.events",
  "execution_mode": "PAPER",
  "fallback_state": "recovered_fallback"
}
```

---

## Decisions requiring reason

These decisions must include a non-empty reason:

```text
blocked
downgraded
rejected
suppressed
ignored
```

Reason is optional for neutral lifecycle decisions such as:

```text
started
observed
passed
generated
ranked
displayed
completed
```

---

## Scope boundaries

This schema must not:

- call broker APIs
- mutate runtime state
- mutate strategy output
- mutate ranking output
- rescue absent data
- convert fallback data into executable status
- add dashboards
- export traces or metrics

Runtime wiring begins in later PRs.

---

## Next roadmap step

After this schema is merged, the next roadmap step is:

```text
PR-OBS-03 — Structured JSON Logging Adapter
```
