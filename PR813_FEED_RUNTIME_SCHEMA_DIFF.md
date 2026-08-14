# PR813 feed runtime schema diff

## Before

First startup runtime artifact: all required runtime identity and integrity
fields present; `truth_lineage` absent when `feed_truth_latest.json` had not
yet been published.

## After

The first runtime publication ensures a current canonical truth artifact
exists, then stamps `truth_lineage` from that exact artifact before hashing and
atomic persistence. The loader contract is unchanged and remains fail-closed
for missing lineage, invalid truth, session mismatch, epoch mismatch, and hash
mismatch.

No changes were made to order, risk, broker, option verification, warmup,
ranking, strategy, or live authorization behavior.
