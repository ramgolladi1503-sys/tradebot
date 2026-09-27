# Verification gateway dependency decisions — 2026-09-27

Scope is the isolated research verifier only. No root application dependencies were changed.

| Component | Decision | Version/evidence | Limitations and rollback |
|---|---|---|---|
| Pydantic | Retained for frozen schema validation | 2.13.5; isolated resolver lock at `requirements-verification-lock-py312-macos-arm64.txt`; focused tests passed | Schema validity is not source fidelity. Remove the gateway optional dependency set and module to roll back. |
| Pandera | Retained for fixture shape checks | 0.33.1; timezone-aware timestamp behavior exercised in focused tests | Shape validation cannot authenticate source/PIT authority. Remove optional set/module to roll back. |
| Hypothesis | Retained; already present in root requirements | 6.168.2; property-based causal ordering test passed | Root dependency was not modified. |
| pandas | Test/runtime library for fixture validation | 2.3.3 in the disposable lock, matching the repository CI `<3.0` bound | Lock is Python 3.12/macOS arm64 only; CI/Linux resolution remains unverified. |
| Freqtrade | Methodology-only evaluation; not adopted | GPL distribution and exchange/strategy assumptions are outside this prototype | No copied code or installed dependency. |
| NautilusTrader / LEAN | Neither adopted yet | No comparative synthetic POC or license/performance review completed | Node F blocked pending independently specified reference execution test; avoid a heavy engine without demonstrated value. |
| Third-party purged CV | Not adopted | Existing local CV has not yet been independently compared on overlapping-label fixtures | No package can repair legacy outcome exposure or missing trial denominators. |

The isolated lock is a single-platform resolver snapshot, not a portable lock or production dependency declaration. Before CI integration, reproduce an exact dependency resolution on the supported CI platform and bind it to an explicitly authorized test workflow. Current PR CI does not install this optional set and fails test collection on missing Pydantic.
