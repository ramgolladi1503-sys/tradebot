import json
from research.option_analytics_v1.evidence import generate_reference_evidence
payload = generate_reference_evidence()
for case in payload.get("output_cases", []):
    if case["case_id"] in ("BLACK_76:CALL:0.9:7.0:0.1:-0.01", "BLACK_76:CALL:0.9:7.0:0.1:0.06"):
        print(json.dumps(case, indent=2))
