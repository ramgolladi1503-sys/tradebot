# PREVIOUS OUTCOME PASS INVALIDATED

The previous implementation of outcome labels was rejected due to the following critical defects:

* incomplete required tests;
* incomplete fingerprint authority;
* premature six-decimal rounding;
* holdout-set assertion bypass;
* verifier checks only labelled records;
* oracle source-path uncertainty;
* oracle not manifest-bound;
* oracle absent from determinism hashes;
* verifier does not run pytest;
* final required metrics absent;
* prohibited commit amendment.

These defects undermined the security, reproducibility, and immutability of the outcome labels, necessitating a complete repair.
