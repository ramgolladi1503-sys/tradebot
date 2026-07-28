import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from research.option_analytics_v1.evidence import write_complete_bundle
from research.option_analytics_v1.packaged_evidence import package_reference_artifact

ROOT = Path.cwd()
evidence_dir = ROOT / "research/option_analytics_v1/evidence"
write_complete_bundle(ROOT, evidence_dir)
package_reference_artifact(evidence_dir, remove_plaintext=True)
