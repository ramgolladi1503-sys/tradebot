# PR872 Kite auth credential provenance repair

## Agent Work Contract

This PR repairs the governed Kite browser-login credential source after two checksum-rejected exchanges. It is limited to `scripts/kite_autologin_localhost.py` and its focused provenance tests.

## Scope Guard

The launcher reads the operator-managed credential file, rejects conflicting ambient credentials, and preserves fail-closed validation. No credential values are added to the repository. No feed, strategy, CAS, execution, risk, or order path is changed.

## Grill Me Review

The repair addresses local credential shadowing only. It does not prove that the API key and secret belong to the same Kite developer application, broker availability, or token validity. Those remain explicit operator/live gates.

## Hermes Review

Credential precedence is explicit: the governed file is authoritative and any conflicting ambient API credential fails closed. `KITE_CREDENTIALS_PATH` permits controlled deployment without introducing repository credential storage.

## GSD Review

The change is based on exact protected main `a90a84d621efee6d8773a771318a3c162d5aa52a` in an isolated worktree. The dirty canonical checkout was not modified.

## QA / Safety Review

Focused auth tests pass. The official KiteConnect checksum implementation and an independent standard-library checksum calculation agree. No order-capable broker method was invoked; no third login is authorized by this PR alone.

## Acceptance Proof

Require protected CI checks, clean merged-main re-freeze, rerun of the focused auth tests, and operator confirmation of same-app pairing before any replacement login.

## Runtime Proof Required After Merge

The post-merge exact-head runtime must prove one governed login flow, fresh token exchange, read-only profile validation, and no credential shadowing before feed startup.

## What This PR Does Not Prove

This PR does not prove same-app pairing, live market-data connectivity, instrument authority, subscription truth, persistence, CAS, prospective evidence, execution viability, or structural edge.

## Human Approval

Human approval was received for same-app pairing verification and the explicitly recorded replacement-login path. Merge and subsequent live observation remain governed by protected CI and the read-only runtime contract.

## Evidence Traceability

mode: OFFLINE_AUTH_REPAIR
candidate_id: PR872_KITE_AUTH_CREDENTIAL_PROVENANCE
decision: THIRD_LOGIN_BLOCKED_UNTIL_MERGED_MAIN
reason: Credential shadowing was repaired and independently tested; protected-main merge and post-merge verification remain required.
timestamp: 2026-09-01T09:20:00+05:30
source: exact candidate commit plus focused auth test output
broker_api_called: false
is_order_action: false
live_order_action: false
broker_order_action: false
read_only: true
allowed_for_live_execution: false
authority: broker_write=false, order=false, paper=false, live=false

Historical runtime context: two prior governed read-only token-exchange attempts called the broker and failed with checksum rejection; those calls are not part of this offline PR validation and no order methods were invoked.
