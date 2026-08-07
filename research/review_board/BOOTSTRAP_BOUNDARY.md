# MROS Review + Audit Board Bootstrap Boundary

Status: IMPLEMENTED COMPONENTS / NOT CALIBRATED / NOT AUTHORITATIVE
Authority: Research / R
Runtime authority: NONE

The automated Review Board and Audit Board were introduced while S002 remained ACTIVE. They therefore MUST NOT certify S002 or their own creation.

S002 requires the pre-existing genuinely independent bootstrap review mechanism against the exact native-validated candidate head. Only after S002 acceptance, deterministic Review+Audit calibration, and genuinely independent bootstrap review of the combined governance machinery may a recorded program decision authorize normal automated use, no earlier than S003.

Until that authorization decision exists:

- S002 remains ACTIVE.
- S003 remains NOT_STARTED.
- Review Board outputs are developmental evidence only.
- Audit Board outputs are developmental evidence only.
- Ten invocations from the implementing context do not establish reviewer independence.
- Ten audit invocations from the implementing/review-aggregation context do not establish auditor independence.
- No Review/Audit Board artifact may create runtime authority.
- M9 remains NOT_STARTED.

Any repaired candidate head invalidates prior-head native-validation, review, and audit authority for the repaired head. The new head requires fresh native validation plus new independent review and audit rounds before ordinary sprint acceptance.

The combined board is a certifier-like governance instrument and is therefore subject to calibration-before-trust. `IMPLEMENTED_NOT_CALIBRATED` must never be rewritten as `AUTHORIZED` merely because orchestration code exists or deterministic unit tests are green.
