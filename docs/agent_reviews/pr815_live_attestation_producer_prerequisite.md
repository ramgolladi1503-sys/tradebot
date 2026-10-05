# PR815 Trusted Live-Attestation Producer Prerequisite Review

## Agent Work Contract

- source_agent: ChatGPT/GitHub connector
- action: implement the smallest missing trusted live-session attestation producer required before PR #815 can collect prospective evidence
- requested_paths: `core/live_session_attestation_producer.py`, `tests/test_live_session_attestation_producer.py`, this review document
- prohibited_paths: broker/order execution, strategy/ranking/risk, credentials, live authorization, PR815 evidence acceptance weakening
- artifact_cleanup_contract: no runtime artifacts are written inside the source checkout by this change; the producer exposes an explicit caller-selected output path primitive only
- tests_and_ci_contract: focused producer tests plus all repository-required CI must pass; CI PASS is not live PASS
- deployment_notes: producer remains dormant until explicitly wired into the governed read-only Kite observation session; no live session is authorized by this PR
- human_approval: normal branch protection and exact merge authorization remain required

## Scope Guard

The producer has one trust source: `core.kite_depth_ws.market_event_graph_subscription_evidence_for_tokens(...)`. It accepts no OHLC bars and cannot turn caller-declared provenance into a trusted live session.

The canonical accepted token identities are repository-pinned:

```text
NIFTY=256265
BANKNIFTY=260105
SENSEX=265
provider=kite
token_domain=kite_instrument_token
```

## Grill Me Review

The producer rejects missing/incorrect token identity, missing subscription request success, missing post-request tick proof, missing FULL-payload proof, cross-session lifecycle evidence, pre-15:30 attestations, non-exact Git SHAs, and missing/short signing keys. It writes immutable output or proves byte-identical idempotency.

## Hermes Review

This implementation does not use completed bars as its source of trust. A future PR815 evidence consumer may compare bars to the resulting attestation, but the producer is anchored independently to the WebSocket subscription lifecycle maintained by the read-only feed process.

## GSD Review

The implementation is intentionally a prerequisite only. It does not modify `core/prospective_market_evidence.py`, does not self-wire into a market session, and does not claim that a producer has been observed live. Wiring and one fresh exact read-only session remain separate evidence gates.

## QA / Safety Review

```text
BROKER_WRITE_AUTHORITY=false
ORDER_AUTHORITY=false
PAPER_AUTHORIZED=false
LIVE_AUTHORIZED=false
NO_ORDER_ACTIONS=true
NO_EXECUTION_ROUTING=true
NO_BAR_SELF_ATTESTATION=true
IMMUTABLE_ATTESTATION_OUTPUT=true
```

## Acceptance Proof

Implementation-valid requires:

- exact three-index identity checks;
- request-scoped subscription lifecycle checks;
- exact feed-session consistency;
- HMAC signing with trusted-key minimum length;
- fail-closed time/SHA validation;
- immutable write/idempotency tests;
- repository CI green.

## Runtime Proof Required After Merge

A later controlled read-only market session must wire this producer into the authoritative Kite observation process and prove it produces an attestation for the exact candidate SHA/session after 15:30 IST. Until then:

```text
PR815_LIVE_ATTESTATION_PRODUCER=IMPLEMENTED_NOT_LIVE_VERIFIED
PR815_SHADOW_LIVE_VALID=false
PR815_LIVE_ATTACH_READY=false
```

## What This PR Does Not Prove

It does not prove a live feed was observed, does not prove PR815 prospective evidence is valid, does not prove market edge or profitability, and grants no paper/live execution authority.

## Final Review Verdict

```text
IMPLEMENTATION_SCOPE=BOUNDED_PR815_PREREQUISITE
LIVE_PROOF=NOT_PROVIDED
MERGE_ALLOWED=ONLY_AFTER_REQUIRED_CHECKS_PASS
```
