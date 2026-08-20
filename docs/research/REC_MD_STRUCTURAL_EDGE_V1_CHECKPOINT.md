# REC-MD Structural Edge V1 — PR Checkpoint

## Mission

REC-MD exists to discover and falsify a structural interaction edge around remaining-edge consumption for a previously valid BUY candidate.

The research question is whether displacement has consumed the remaining expectancy, or whether continuation/propagation evidence is strong enough that a late-looking entry remains structurally valid.

## Frozen anchor

```text
REC_H1_HASH=6a3652bac23780ba2dfb3c50ff2e5aac262d2ec7bde6277aea71db31cea8d193
H1_RULE_ID=H1_TRAPPED_PUSH_SNAPBACK
NEW_CANDIDATE_POPULATION_ID=H1_REC_BASELINE_V1
HISTORICAL_H1_51_EVENT_PARITY=UNVERIFIED_SOURCE_LOST
```

Historical 51-event equivalence is intentionally not claimed. The frozen H1 rule authority is separate from historical source-byte replication.

## Structural-edge loop

```text
FROZEN REC-H1
    ↓
real H1 candidate population
    ↓
autonomous mechanism generator
    ↓
Propagation
Exhaustion
Market State
Option Response
Remaining Reward
Interactions
    ↓
freeze before outcome
    ↓
causal DEV test
    ↓
controls / ablations / costs / stability
    ↓
independent HOLDOUT
    ↓
reject / rotate / survive
```

Current mechanism cursor:

```text
REC_AUTO_0002_MARKET_STATE_HYP
```

Legitimate stop conditions:

```text
STRUCTURAL_INTERACTION_EDGE_CERTIFIED
ANCHOR_HYPOTHESIS_FALSIFIED
MECHANISM_SPACE_AUDITABLY_EXHAUSTED
DATA_BLOCKER
INDEPENDENT_UNSEEN_EVIDENCE_REQUIRED
SAFETY_STOP
```

## Prospective observation lane

A separate read-only completed-bar exporter was implemented offline and packaged in a clean local observation candidate.

```text
LOCAL_OBSERVATION_CANDIDATE_SHA=0574d717c67dd2e27bab322edb8cdc4c30deb2a6
EXPORTER_SHA=a9dbb3e850892d6252fb5a679004fc15952a43ec72302c4f95b06c0533554a85
FUTURE_SYMBOL_AUTHORITY=PASS
EFFECTIVE_SYMBOLS=[NIFTY,BANKNIFTY,SENSEX]
NIFTY_TOKEN=256265
UNDERLYING_RETENTION=PASS_STRUCTURAL
ROUTING_TO_EXPORTER=PASS_STRUCTURAL_OFFLINE
FINALIZED_BAR_PATH=PASS
FUTURE_LAUNCH_READINESS=true
REAL_EVIDENCE_ROWS=0
SOURCE_AUTHORITY=AWAITING_REAL_PROSPECTIVE_ROWS
```

The local observation commit is not yet represented by this checkpoint commit; it must be published from the local clean worktree onto this PR branch.

## Safety / non-authority

Always:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
```

REC-MD must not own a broker connection, mutate feed subscriptions, place orders, or alter Loop A authority.

## PR scope

This PR is the durable home for:

1. REC-MD structural-edge discovery implementation and governance.
2. Frozen H1 authority and prospective population contracts.
3. Mechanism generation/evaluation infrastructure and tests.
4. Read-only completed-bar evidence exporter needed for prospective confirmation.
5. Research checkpoint documentation required to preserve exact hashes, blockers, and non-claims.

Do not sweep unrelated dirty-worktree changes into this PR.

## Promotion firewall

No REC-MD research result may alter live strategy, ranking, risk, or execution until separate prospective/shadow validation and governed promotion are complete.
