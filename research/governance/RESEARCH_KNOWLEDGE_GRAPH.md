# Research Knowledge Graph Specification

The future MROS knowledge graph must make research belief traversable from repository artifacts rather than conversational memory.

## Canonical Lineage

`Dataset -> Experiment -> Observation -> Claim -> Evidence -> Calibration -> Decision`

The graph may contain additional typed edges but must preserve provenance and directionality.

## Core Node Types

- Dataset
- Experiment
- Observation
- Claim
- Evidence
- Calibration
- Decision
- Confidence Passport
- Attack
- Operational Consumer

## Required Questions

The graph must eventually answer, from repository state:

- Why do we believe `CLAIM-XXXX`?
- Which datasets and experiments support it?
- Which evidence contradicts it?
- Which calibration results make its statistical certification trustworthy?
- Which independent attacks did it survive or fail?
- Which decision promoted, downgraded, invalidated, or superseded it?
- Which downstream consumers depend on it?

## Edge Rules

Every edge must reference immutable IDs and semantic relation type. Examples: `DERIVED_FROM`, `TESTS`, `PRODUCES`, `SUPPORTS`, `CONTRADICTS`, `CALIBRATES`, `PROMOTES`, `INVALIDATES`, `SUPERSEDES`, `CONSUMES`.

Edges must not manufacture authority. They expose lineage; lifecycle promotion still requires governance decisions.

## Sprint-001 Boundary

This file specifies the contract only. No graph database, indexer, inference engine, or UI is implemented or claimed in Sprint-001.
