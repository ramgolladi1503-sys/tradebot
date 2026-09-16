# Merge gate

Do not merge while any of these is not evidenced:

- executable tests on PR head;
- existing 15/15 release mutation campaign;
- implemented and detected 22/22 rebootstrap behavioral mutations;
- independent verifier PASS on a copied quarantined store;
- append-only history preservation proof;
- zero broker/order authority regression.

A PR or code review approval alone is insufficient.
