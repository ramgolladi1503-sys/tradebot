# TEP v1 — Module Dependency Graph

Status: DRAFT
Version: 1.0.0-draft

## Logical graph

```text
Applications
  |
  v
Mission Engine -----> Knowledge Service (read/advisory)
  |
  v
TBOS Scheduler/Event Runtime
  |
  +----> Authority Service ----> Capability Registry
  |
  +----> Domain Services
           |
           +--> GitHub Service --> GitHub Driver
           +--> Git Service -----> Git/Filesystem Driver
           +--> CI Service ------> GitHub Actions/CI Driver
           +--> Review Service
           +--> Merge Service
           +--> Cleanup Service
           +--> Evidence Service --> Evidence Storage Driver
           +--> Research Services --> Data/Research Drivers
           +--> Live Observation Service --> Broker Read Driver
           |
           +--> Worker Manager --> Codex Worker

All durable lifecycle components --> State/Event Store
All governed results -----------> Evidence Service
All operator/product views -----> API/Observability
```

## Dependency constraints

### D-001
Applications MAY depend on public Mission/API contracts and domain service read interfaces. They MUST NOT depend directly on external drivers for governed capabilities.

### D-002
TBOS MAY depend on state/event, mission contracts, capability metadata and service handler interfaces. It MUST NOT import GitHub-, trading- or research-specific policy.

### D-003
Services MAY depend on platform contracts, authority, evidence, worker/driver interfaces and lower-level utility libraries. Services MUST NOT depend on applications.

### D-004
Drivers MAY depend on external SDKs/protocol libraries and platform driver contracts. Drivers MUST NOT depend on Mission Engine, applications or domain business policy.

### D-005
Workers MAY depend on worker contracts and execution sandbox/tooling. Workers MUST NOT directly update authoritative mission/task state.

### D-006
Knowledge Service MAY ingest evidence/provenance and expose queries. Runtime mutation services MUST NOT accept knowledge retrieval as authority proof.

### D-007
Evidence Service MAY reference external immutable artifacts. It MUST NOT call workers to manufacture missing evidence for a claim during certification.

### D-008
Merge Service composes Git/GitHub/CI/Review/Authority services; it MUST NOT duplicate their implementations.

### D-009
Cleanup Service depends on Git/GitHub/evidence/provenance checks and requires destructive-cleanup authority. It MUST NOT infer deletability from age or naming.

### D-010
Live Observation Service may depend on market-calendar, broker-read driver, runtime storage and evidence service. It MUST NOT depend on order-placement capability for read-only missions.

## Cycle prevention

Forbidden dependency cycles include:

- Scheduler ↔ domain-specific service implementation imports;
- Service ↔ Application;
- Driver ↔ Service policy;
- Worker ↔ authoritative State Store writes;
- Evidence ↔ producer self-certification.

Event callbacks do not create ownership cycles: events are contracts routed by TBOS, and handlers remain owned by their service.

## Module ownership matrix

| Concern | Owner |
|---|---|
| Mission definition validity | Mission Engine |
| Runnable task computation | TBOS Scheduler |
| Durable lifecycle state | State Store/TBOS |
| Capability definition | Capability Registry |
| Authorization decision | Authority Service |
| Git semantics | Git Service |
| PR semantics | GitHub Service |
| CI interpretation | CI Service |
| Review contract | Review Service |
| Merge orchestration | Merge Service |
| Destructive local cleanup | Cleanup Service |
| Worker execution | Worker Manager |
| External API mechanics | Driver Framework |
| Evidence sealing/index | Evidence Service |
| Reusable provenance findings | Knowledge Service |
| Economic research validation | Research validators |
| Read-only market observation | Live Observation Service |

## Enforcement

Implementation MUST include architecture tests or import-boundary checks sufficient to detect prohibited dependency directions. A code review convention alone is insufficient for critical boundaries.