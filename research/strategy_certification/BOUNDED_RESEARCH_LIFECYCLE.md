# Bounded Research Lifecycle

## Purpose

Prevent discovery from turning into indefinite parameter mining and prevent failed certification from being rewritten after the fact.

## Separation of authority

`Hypothesis Factory -> Candidate Certification Kernel -> Strategy Passport -> MROS -> TradeBot research integration -> shadow/live-forward evidence -> possible runtime promotion`

MROS is not the hypothesis generator. Discovery is upstream. Certification is a fixed judge. MROS governs whether certified evidence is sufficient for later integration.

## Discovery law

A discovery generation is predeclared by information set, dataset identity, hypothesis families, parameter ranges, minimum trades, and cost assumptions.

A generation ends with one of two outcomes:

- zero admissible candidates -> generation closes;
- one or more admissible candidates -> select a small candidate set, freeze them, and stop changing those candidates.

A search domain closes with `NO_CANDIDATE_FOUND_IN_SEARCH_DOMAIN` when every declared generation has zero admissible candidates.

A closed domain cannot be reopened by changing nearby thresholds or adding more parameter combinations. Reopening requires a new `information_set_id` representing genuinely new information.

## Candidate-of-record law

Admission creates an immutable fingerprint from instrument, family, direction, parameters, entry rule, exit rule, cost assumption, dataset SHA-256, and information-set ID.

Any change to those fields creates a new candidate identity.

Legal lifecycle:

`DISCOVERED -> CANDIDATE_OF_RECORD -> CERTIFICATION_RUNNING -> VALIDATED_RESEARCH`

or

`DISCOVERED/CANDIDATE_OF_RECORD/CERTIFICATION_RUNNING -> REJECTED`

`REJECTED` and `VALIDATED_RESEARCH` are terminal.

A rejected candidate cannot be repaired, reopened, relabeled, have its holdout reshuffled, or have thresholds changed under the same identity.

## Certification law

Certification is not discovery. It consumes frozen candidate evidence and returns one controlled research-stage result:

- `VALIDATED_RESEARCH`
- `REJECTED`
- `ROBUSTNESS_REQUIRED`

The kernel must fail closed on missing evidence. A passing screen can never substitute for robustness evidence.

Required robustness dimensions include chronological OOS evidence, walk-forward positivity, cost/slippage stress, session concentration, negative controls, fallback exclusion, and any additional predeclared gates.

Synthetic truth controls are mandatory:

1. deterministic known-good evidence must be capable of reaching `VALIDATED_RESEARCH`;
2. failed OOS/negative-control evidence must return `REJECTED`;
3. missing robustness must return `ROBUSTNESS_REQUIRED`;
4. screen-level rejection must remain `REJECTED` even if downstream evidence falsely claims PASS.

## Current discovery boundary

The currently executed BANKNIFTY price-only generations and cross-market price-only generation are finalized by `finalize_current_bounded_domains.py`, which consumes the exact native run manifests and refuses closure if any generation has a survivor or if a frozen dataset SHA differs.

No further nearby BANKNIFTY 5-minute price-only parameter expansion is legal after those domains close.

The next legal discovery cycle, if desired, must use a new predeclared information set such as genuine options/microstructure data rather than more tuning of the closed price-only search spaces.

## Safety

All artifacts remain research-only:

- runtime authority: `NONE`
- broker actions allowed: `false`
- no production/live/broker-ready verdict may be created by this lifecycle.
