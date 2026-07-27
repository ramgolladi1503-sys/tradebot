import shutil
from pathlib import Path
from research.option_analytics_v1.evidence import write_complete_bundle
from research.option_analytics_v1.packaged_evidence import package_reference_artifact

ROOT = Path(".")
evidence_dir = ROOT / "research/option_analytics_v1/evidence"

if evidence_dir.exists():
    shutil.rmtree(evidence_dir)
evidence_dir.mkdir(parents=True)

write_complete_bundle(ROOT, evidence_dir)
package_reference_artifact(evidence_dir, remove_plaintext=True)
