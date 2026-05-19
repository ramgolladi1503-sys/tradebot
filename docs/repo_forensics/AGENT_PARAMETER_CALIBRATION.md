# Agent Parameter Calibration

## Purpose

This document calibrates the TradeBot agent parameters from `.gsd-forensics.yaml` so the agents do not behave like generic reviewers.

The goal is not more process. The goal is higher signal:

```text
fewer fake passes
fewer symptom fixes
fewer unsafe changes
stronger repo truth
stronger code-hardening contracts
better trade-quality protection
```

## Hard Rule

Agent names do not matter unless their parameters force useful decisions.

Each agent must produce one of these outcomes:

```text
PASS
FAIL
BLOCKED
UNKNOWN
NEEDS_DAEDALUS_CONTRACT
NEEDS_ARIADNE_RCA
NEEDS_VULCAN_HARDENING
```

No agent may return vague approval.

---

## Severity Calibration

| Severity | Blocks Merge? | Meaning | Examples |
|---|---:|---|---|
| CRITICAL | Yes | Can cause live/broker/unsafe behavior or corrupt decision truth. | paper path imports live order placement; fallback candidate creates broker intent |
| HIGH | Yes unless waived | Breaks runtime truth, trade-quality trust, or safety evidence. | ranking module not runtime-wired; risk gate before execution is UNKNOWN |
| MEDIUM | No, but must be tracked | Weakens reliability, tests, or evidence. | shape-only tests, missing evidence reason |
| LOW | No | Maintainability/documentation issue. | stale comment, weak naming |
| INFO | No | Observation only. | module count, file inventory |
| UNKNOWN | Must be explained | Could not prove correctness/safety. | dynamic runtime path not statically traceable |

## Confidence Calibration

Ariadne and Daedalus must use confidence levels strictly.

| Confidence | Required Proof |
|---|---|
| CONFIRMED | Reproducible failing test, direct code path, or clear evidence chain. |
| LIKELY | Multiple findings converge on same file/flow, but reproduction is incomplete. |
| POSSIBLE | Plausible but weak evidence. Requires investigation before code. |
| UNKNOWN | Not enough proof. Must not become a patch plan. |

Rule:

```text
UNKNOWN root cause -> no Vulcan patch.
POSSIBLE root cause -> investigation PR or evidence-gathering only.
LIKELY root cause -> Daedalus may draft a scoped contract, but must list proof gaps.
CONFIRMED root cause -> Daedalus may create FIX_NOW contract.
```

---

## Agent Handoff Rules

### Argus -> Atlas

Argus hands off to Atlas when:

- a critical module is present but caller is unproven
- entrypoint chain is unclear
- dashboard/runtime/evidence path looks stale

### Atlas -> Ariadne

Atlas hands off to Ariadne when:

- multiple flow steps are UNKNOWN
- one missing caller explains several findings
- ranking/risk/execution boundary appears bypassed

### Minerva -> Ariadne

Minerva hands off to Ariadne when:

- many tests fail around same object/model/contract
- tests pass but prove only shape
- multiple fake-confidence tests protect the same weak behavior

### Cerberus -> Daedalus

Cerberus hands off directly to Daedalus only when safety issue is CONFIRMED.

Otherwise:

```text
Cerberus UNKNOWN -> Ariadne RCA first
Cerberus CONFIRMED CRITICAL -> Daedalus FIX_NOW contract
```

### Ariadne -> Daedalus

Ariadne hands off to Daedalus only when:

- root cause is LIKELY or CONFIRMED
- blast radius is listed
- files implicated are listed
- proof gaps are explicit

### Daedalus -> Vulcan

Vulcan may work only when Daedalus provides:

- root cause
- decision
- files to change
- files not to touch
- patch behavior
- tests required
- negative tests required
- evidence required
- done means

No Daedalus contract = no Vulcan patch.

---

## TradeBot Edge-Oriented Tripwires

These are not profitability promises. They are tripwires that prevent fake trade quality.

### Data Quality Tripwires

CRITICAL/HIGH if:

- fallback data can become executable
- stale feed can become executable
- missing quote can become executable
- contract-resolution fallback survives as executable candidate
- evidence does not reveal fallback/stale status

### Ranking Tripwires

HIGH if:

- ranking output is not proven consumed by runtime
- UI displays raw strategy rows as top opportunities
- confidence/score cluster is too tight without ranking explanation
- rank reason is missing
- score components are missing

### Safety Tripwires

CRITICAL if:

- SIM/PAPER path can reach broker order placement
- read-only proof sets order-action fields true
- live mode defaults without explicit readiness
- dashboard path exposes submit/modify/cancel/exit outside scope

### Test Tripwires

HIGH if:

- a safety or execution PR has only shape tests
- fallback/stale/risk behavior lacks negative tests
- broker mocks prove success but not unreachable real broker path

### Evidence Tripwires

MEDIUM/HIGH if:

- evidence says only `ok=true`
- decision records lack `reason`
- candidate records lack `candidate_id`
- order-adjacent proof lacks `is_order_action=false`
- broker-adjacent proof lacks `broker_api_called=false`

---

## Minimum Parameter Output Per Agent

### Grill Me

Must output:

- weakest assumption
- likely hidden failure
- fake-confidence risk
- missing proof
- verdict

### Hermes

Must output:

- files touched vs allowed files
- protected boundary status
- broker/live/dashboard/runtime safety status
- scope violations
- verdict

### GSD

Must output:

- delivery status
- evidence status
- unresolved risks
- next action
- verdict

### Argus

Must output:

- repo map
- critical module status
- unused/test-only critical modules
- duplicate/stale candidates
- top manual inspection files

### Atlas

Must output:

- runtime flow table
- PASS/FAIL/UNKNOWN per step
- missing callers
- evidence path proof
- unknowns needing proof

### Minerva

Must output:

- test class counts
- fake-confidence tests
- missing negative tests
- tests that should block merge

### Cerberus

Must output:

- safety boundary matrix
- forbidden import/action findings
- non-action field proof
- CRITICAL blockers

### Ariadne

Must output:

- root-cause clusters
- confidence level
- blast radius
- evidence chain
- unknowns

### Daedalus

Must output:

- remediation decision
- files to change
- files not to touch
- exact patch behavior
- required tests
- required evidence
- done means

### Vulcan

Must output:

- maturity before
- maturity after
- patch summary
- safety preserved
- tests added
- negative tests added
- evidence added

---

## Merge Policy

```text
CRITICAL -> block
HIGH -> fix or explicit waiver
UNKNOWN safety/runtime/execution -> explain or block
Shape-only tests for safety/execution -> block
No Daedalus contract for Vulcan patch -> block
No evidence file -> block
```

## Final Calibration Rule

The profile should make agents stricter, not busier.

If a parameter does not help one of these outcomes, remove it:

```text
safer runtime
clearer repo truth
stronger tests
better evidence
fewer fake opportunities
more realistic trade-quality validation
```
