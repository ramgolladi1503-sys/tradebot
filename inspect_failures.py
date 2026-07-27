import json
from research.option_analytics_v1.evidence import generate_reference_evidence
payload = generate_reference_evidence()
print(json.dumps(payload.get("failures", []), indent=2))
