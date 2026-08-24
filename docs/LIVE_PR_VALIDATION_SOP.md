# Live PR validation SOP

Classify each PR before execution. Feed, launcher, broker, subscription,
persistence-authority, risk, or execution changes require a separate runtime
candidate. Observation, ranking, analytics, and evidence-only changes may be
sidecar-safe only when bound to an exact PR SHA, consuming canonical evidence,
using isolated output, and holding no order authority.

Sidecar failure must not stop or mutate canonical main. Sidecars stop, flush,
hash, and seal their own evidence. No sidecar result authorizes a merge.
