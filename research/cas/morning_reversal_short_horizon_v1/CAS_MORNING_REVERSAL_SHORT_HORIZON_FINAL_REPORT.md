# CAS Morning-Reversal Short-Horizon Final Report

## Controlled verdict

`PROSPECTIVE_TEST_REQUIRED`

The new hypothesis was frozen as `CAS_MORNING_REVERSAL_SHORT_HORIZON_V1`. The prior all-horizon candidate remains failed; its four-session holdout was not reused as confirmation.

## Independence

No clean untouched historical evaluation surface was proven. The available preserved surfaces were used by prior CAS selection/search, and the sessions `2026-08-27`, `2026-08-28`, `2026-08-31`, and `2026-09-01` are excluded because they were already opened as the prior holdout.

Therefore no fixed-exit, first-hit, cost, MFE/MAE, benchmark, or negative-control result is claimed here. The results CSV is intentionally header-only.

## Required next evidence

Capture 20 newly admitted prospective sessions under the frozen specification, including the 09:15 and 10:00 prices, 15:14 entry reference, minute/tick path through 15:25, 15:20 and 15:25 exits, MFE, MAE, and costs. Option execution remains `UNKNOWN` unless authoritative option bid/ask data is captured.

## Safety

`broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.

No broker write or order call was made. No PR or runtime change was made.
