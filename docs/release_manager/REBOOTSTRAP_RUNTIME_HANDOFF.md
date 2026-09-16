# Runtime validation handoff

Checkout exact PR head and run the reviewer checklist. Do not mutate the canonical release store during first validation. Use a byte-for-byte copy of the store for dry-run/recovery tests.

The most important unfinished gate is `scripts/release_rebootstrap_mutation_campaign.py`: it deliberately returns BLOCKED until 22 behavioral mutators are implemented. Do not change its verdict to PASS without implementing and detecting every attack in `REBOOTSTRAP_ATTACK_MATRIX.json`.

Only after tests, old 15/15 mutations, new 22/22 mutations, and independent verification are green may a controlled recovery against the canonical store be considered.
