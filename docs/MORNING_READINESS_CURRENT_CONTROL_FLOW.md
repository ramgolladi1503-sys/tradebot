# Current control-flow inventory at `e1f803d9f56c60b9208ac686db8da8ddba055b4d`

| Stage | Current authority | Before 09:15 | Risk/observation note |
|---|---|---:|---|
| `run_live.sh` environment binding | `run_live.sh` | yes | Sets runtime roots, but defaults to repository-local `.runtime`. |
| auth/token validation | `run_live.sh`, `core/auth_health.py` | yes | Read-only validation is available. |
| persistence/runtime initialization | `main.py` and imported runtime modules | partially | Import/startup ordering requires a dedicated preflight proof. |
| instrument/universe resolution | `main.py`/core feed and resolver modules | partially | Must be bound to fresh external session root. |
| option subscription/mirror | feed/runtime modules | partially | Offline mirror exists; live convergence remains a live-only gate. |
| CAS primitive producer | `core/cas_primitive_producer.py`, `core/cas_runtime.py` | yes | Must be independent of option readiness in the final launcher. |
| coordinator/decision plane | `main.py` and candidate pipeline | no proof | Existing live launch is execution-mode capable and is not read-only by default. |
| shutdown/seal | `main.py` persistence shutdown hooks | end-of-session | Automatic EOD proof is not yet certified by Morning Readiness V1. |

The existing launch path forcibly exports `TRADING_MODE=LIVE`,
`EXECUTION_MODE=LIVE`, and `LIVE_BROKER_ADAPTER_ACTIVE=1`. It must not be
treated as a read-only Morning Readiness launcher without an independently
verified authority boundary.

Current conclusion: the base runtime contains useful components, but the
required single-command preopen/read-only orchestration is not yet proven.
