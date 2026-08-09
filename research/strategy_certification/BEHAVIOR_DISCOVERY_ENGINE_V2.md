# Behavior Discovery Engine V2 — Implementation Contract

Status: `IMPLEMENTATION_CONTRACT`

Authority boundary:

```text
runtime_authority = NONE
broker_write_authority = false
order_authority = false
paper_authorized = false
live_authorized = false
broker_actions_permitted = false
edge_claimed = false
```

## Purpose

Build a causal discovery layer that converts verified NIFTY OHLC history into recurring behavior states, episodes, and frozen structural candidate passports without using forward outcomes during discovery.

This layer is not a strategy, not a ranking engine, and not an edge claim. Its first acceptable milestone is:

```text
BEHAVIOR_DISCOVERY_IMPLEMENTATION_VALID
```

## Pipeline

```text
verified OHLC
  -> causal behavior states
  -> collapsed behavior episodes
  -> recurrent sequence mining
  -> immutable structural candidate passports
  -> governed development outcome test only after freeze
```

## Prohibited shortcuts

- No centered windows.
- No future pivots masquerading as current state.
- No forward returns, PnL, target, label, or outcome-conditioned feature in discovery.
- No locked/final partition outcome access before candidate freeze and search-pressure accounting.
- No direction, entry, exit, profitability, tradability, robustness, or certification claim from recurrence alone.
- No broker, execution, paper, or live authority changes.

## Component contracts

### Behavior State Engine V1

Computes observable completed-bar states such as range compression/expansion, wick rejection, strong body morphology, directional acceleration/deceleration, and failed/successful escape relative to prior same-session ranges. Every state is observable at the current bar close using same-session prefix data only.

### Episode Graph V1

Groups noisy adjacent state events into same-session behavior episodes. Consecutive duplicate states are collapsed in the episode anatomy. This prevents counting every adjacent bar as an independent event.

### Sequence Miner V1

Mines recurrent contiguous state sequences using support and distinct-session support only. It does not inspect or compute forward outcomes.

### Hypothesis Compiler V1

Freezes recurrent structures into candidate passports. Direction remains `UNKNOWN`; entry and exit remain `NONE`; `edge_claimed=false`.

## Validation requirements

The validator must attack at least:

- prefix reproducibility;
- future-extension invariance;
- confirmation timestamp causality;
- session-boundary isolation;
- deterministic state generation;
- episode de-duplication/collapse;
- deterministic sequence mining;
- no outcome columns/features entering discovery;
- stable candidate passport hashing.

A validation pass only supports implementation behavior. It does not support structural edge certification.
