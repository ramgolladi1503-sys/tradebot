# Portfolio readiness record

## Verdict

`INTERVIEW_KILLER_READY_WITH_ONE_EXTERNAL_EVIDENCE_GAP`

The engineering system is portfolio-ready. The remaining external evidence gap is a measured Gemini evaluation report produced with the owner's API key and, separately, a future eligible historical dataset for a genuine edge investigation. Neither gap is disguised as completed evidence.

## What is proven

- Existing TradeBot production architecture remains untouched.
- Read-only LangGraph manager with human approval and persistent state.
- Independent adversarial critic with a deterministic offline implementation and optional Gemini implementation.
- Deterministic certification judge remains final authority.
- SQLite idempotency ledger reuses completed tool outputs after restart.
- Prompt-injection patterns are removed from model evidence views and secret-bearing keys are excluded.
- Nine-tool MCP surface contains no broker, order, risk or mutation capability.
- Hypothesis generation is capped at three, evidence-linked and non-mutating.
- Duplicate hypothesis retests are rejected by durable fingerprint memory.
- Real committed legacy report is rejected for zero-volume evidence, same-bar proxy entry and lack of executable option evidence.
- Deterministic evaluation baseline: 64/64 correct next actions, zero unsafe actions, zero exceptions.
- Isolated sidecar suite: 21 tests passed in the construction environment.

## What is not claimed

- No profitable strategy has been certified.
- No option-execution edge has been proven.
- No Gemini accuracy number is claimed until the owner runs the online evaluation.
- No live-trading authority exists.
- The structural train/validation/holdout MVP is not represented as the trusted purged/embargoed option WFA.

## Interview positioning

> Built a stateful agentic research system that plans and executes read-only strategy investigations through MCP tools, pauses for human approval, survives restart without duplicate work, independently critiques evidence, blocks prompt injection, remembers failed hypotheses and delegates the final verdict to deterministic certification code.

The strongest demonstration is a rejection, not a convenient profitable result: the system discovers that the existing June 29 report is non-certifying and refuses to tune around invalid evidence.
