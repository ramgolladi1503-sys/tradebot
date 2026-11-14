# Adversarial Gate Recertification Protocol

The adversarial gate protects its own workflow, policy implementation, key CI workflows, and governance tests. After the initial bootstrap, those paths are intentionally immutable to ordinary pull requests.

A future repair to a protected gate path requires a two-PR exact-SHA authorization flow:

1. Build the proposed gate repair on a branch whose name starts with `governance/adversarial-gate-recertification-`.
2. Freeze that candidate. Record its exact Git commit SHA. Do not modify the candidate after authorization is prepared.
3. Through a separate reviewed PR, add the following manifest to protected `main`:

   `docs/adversarial_gate_recertifications/<EXACT_CANDIDATE_SHA>.md`

4. The manifest must contain all of:

```text
candidate_sha: <EXACT_CANDIDATE_SHA>
authorized: true
scope: adversarial-gate-recertification
```

5. After that authorization manifest is merged to `main`, re-run the frozen recertification PR against the updated base. The gate recomputes the candidate SHA and reads the authorization only from the trusted base tree.
6. Any candidate commit after authorization changes the SHA and invalidates the authorization. A new manifest is required.

A branch name never authorizes a gate modification by itself. An authorization file supplied by the candidate branch is not trusted. The manifest must already exist in the exact protected base used by the gate.

This protocol does not replace branch ruleset protection. The repository ruleset must still require the adversarial candidate check and the trusted exact-head verdict, with strict required-status behavior enabled so a change in the base invalidates stale success evidence.
