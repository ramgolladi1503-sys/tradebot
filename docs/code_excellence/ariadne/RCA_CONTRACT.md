# Ariadne RCA Contract

## Purpose

The Ariadne RCA contract defines the minimum standard for root-cause analysis before remediation work begins.

Ariadne exists because TradeBot has repeated failure modes where visible symptoms are not the real cause:

- misleading executable signals
- queue-only/executable contradiction
- fallback contract propagation gaps
- stale feed/freshness ambiguity
- tests that prove contracts but not runtime truth
- evidence that records status without enough traceability

## Contract Inputs

An RCA must start from at least one concrete input:

- failing CI check
- failing unit/integration test
- runtime log symptom
- repo-forensics finding
- product reality audit finding
- live read-only validation finding
- manual code review finding with file/function evidence

## Contract Outputs

Every RCA must produce:

1. symptom statement
2. evidence list
3. impact classification
4. related module map
5. hypotheses
6. selected root cause
7. unknowns/deferred questions
8. remediation requirements
9. Ariadne verdict

## Evidence Standard

Evidence must be specific.

Good evidence:

```text
runtime_health_latest.json reports feed freshness blocker ltp_stale:NIFTY
```

Good evidence:

```text
tests/test_contract_resolution_fallback_propagation_gate.py proves fallback candidate must remain queue-only
```

Bad evidence:

```text
The system feels unstable
```

Bad evidence:

```text
The code is probably overcomplicated
```

## Root Cause Standard

A root cause must explain:

- why the symptom occurred
- why the symptom was not blocked earlier
- why existing tests or gates missed it
- what exact contract was missing or violated

A root cause is not:

- the failing test
- the log line
- the CI failure
- the module name
- vague complexity

## Hypothesis Standard

When more than one cause is plausible, Ariadne must list alternatives.

Each hypothesis needs:

- statement
- supporting evidence
- contradicting evidence
- confidence

Confidence levels:

- low: possible but weakly supported
- medium: plausible and partially supported
- high: strongly supported by source/tests/logs

## Verdict Standard

### PASS

RCA is strong enough for remediation planning.

Required:

- concrete symptom
- enough evidence
- selected root cause
- clear remediation requirements

### NEEDS_MORE_EVIDENCE

RCA cannot yet support a fix.

Use when:

- logs are incomplete
- reproduction is missing
- hypotheses remain tied
- safety impact is unclear

### BLOCKED

RCA should not proceed.

Use when:

- root cause is unsupported
- proposed fix is too broad
- evidence contradicts the RCA
- safety boundary is unknown

## Safety Rules

Ariadne must fail closed for uncertainty around:

- broker calls
- live order actions
- paper/SIM/LIVE boundary drift
- stale feed becoming executable
- fallback contract becoming executable
- queue-only candidate becoming executable
- dashboard/read-only paths gaining action behavior

## Handoff to Daedalus

Ariadne does not write the remediation plan.

Ariadne hands Daedalus:

- selected root cause
- affected contracts
- required behavior change
- proof requirements
- forbidden shortcuts
- unresolved unknowns

Daedalus then turns that into a bounded implementation plan.

## Required File Location

RCA documents should live under:

```text
docs/code_excellence/ariadne/rca_records/
```

PR evidence still lives under:

```text
docs/agent_reviews/
```

## Non-Goals

Ariadne does not:

- auto-fix
- auto-merge
- call external services
- run live trading
- claim profitability
- rewrite unrelated modules
