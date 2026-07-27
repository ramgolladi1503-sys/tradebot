import json, hashlib, base64, gzip, shutil
from research.option_analytics_v1.evidence import write_complete_bundle
from research.option_analytics_v1.packaged_evidence import package_reference_artifact
from pathlib import Path

ROOT = Path(".")
evidence_dir = ROOT / "test_evidence_tmp"
write_complete_bundle(ROOT, evidence_dir)
package_reference_artifact(evidence_dir, remove_plaintext=False)

package_bytes = (evidence_dir / "reference_case_results.json.gz.b64").read_bytes()
package_digest = hashlib.sha256(package_bytes).hexdigest()

raw = (evidence_dir / "reference_case_results.json").read_bytes()
digest = hashlib.sha256(raw).hexdigest()

print("EXPECTED_PACKAGE_SHA256:", package_digest)
print("EXPECTED_REFERENCE_SHA256:", digest)

shutil.rmtree(evidence_dir)
